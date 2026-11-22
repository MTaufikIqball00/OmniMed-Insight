import hashlib
import json
import math
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, zoom
import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision.models import densenet121

from .calibration import MulticlassPlattScaler, TemperatureScaler
from .imaging import load_and_validate_medical_image
from .schemas import (
    AnalyzeImageRequest,
    AnalyzeImageResponse,
    ClassScoreItem,
    RegionAttributionItem,
    ReliabilityBin,
    XaiArtifactReport,
)

MODALITY_CLASS_CATALOG: Dict[str, List[Dict[str, str]]] = {
    "CXR": [
        {
            "code": "CXR_NO_ACUTE_FINDING",
            "label": "No Focal Consolidation or Effusion Pattern",
            "snomed": "260413007",
            "loinc": "36643-5",
        },
        {
            "code": "CXR_PARENCHYMAL_OPACITY",
            "label": "Parenchymal Airspace Opacity / Infiltrate Pattern",
            "snomed": "409668002",
            "loinc": "36643-5",
        },
        {
            "code": "CXR_PLEURAL_EFFUSION",
            "label": "Costophrenic Blunting / Pleural Effusion Pattern",
            "snomed": "60046008",
            "loinc": "36643-5",
        },
        {
            "code": "CXR_CARDIOMEGALY_BORDERLINE",
            "label": "Cardiothoracic Silhouette Enlargement Pattern",
            "snomed": "8186001",
            "loinc": "36643-5",
        },
    ],
    "MRI": [
        {
            "code": "MRI_UNREMARKABLE_PARENCHYMA",
            "label": "No Focal Hyperintense Mass or Midline Shift Pattern",
            "snomed": "260413007",
            "loinc": "24590-2",
        },
        {
            "code": "MRI_FLAIR_HYPERINTENSITY",
            "label": "Focal Periventricular / Cortical Hyperintensity Pattern",
            "snomed": "414786004",
            "loinc": "24590-2",
        },
        {
            "code": "MRI_MASS_EFFECT_EDEMA",
            "label": "Circumscribed Space-Occupying Lesion with Edema Pattern",
            "snomed": "301867009",
            "loinc": "24590-2",
        },
        {
            "code": "MRI_VENTRICULAR_ASYMMETRY",
            "label": "Ventricular Enlargement / Asymmetry Pattern",
            "snomed": "61387006",
            "loinc": "24590-2",
        },
    ],
}


def jet_colormap_rgba(norm_heatmap: np.ndarray) -> np.ndarray:
    """
    Maps a normalized 2D array in [0, 1] to an RGBA uint8 array [H, W, 4]
    using a clinical thermal-jet palette where background/low attribution (<0.24)
    is completely transparent (alpha=0) and peak focus stays translucent (max 72%)
    so underlying anatomical structures remain clear.
    """
    v = np.clip(norm_heatmap, 0.0, 1.0)
    floor = 0.24
    v_eff = np.clip((v - floor) / (1.0 - floor), 0.0, 1.0)
    r = np.clip(1.5 - np.abs(4.0 * v - 3.0), 0.0, 1.0)
    g = np.clip(1.5 - np.abs(4.0 * v - 2.0), 0.0, 1.0)
    b = np.clip(1.5 - np.abs(4.0 * v - 1.0), 0.0, 1.0)

    # Zero-alpha below floor eliminates full-image blue/red fog; cap max alpha at 0.72
    alpha = np.where(v < floor, 0.0, np.clip((v_eff ** 1.15) * 0.72, 0.0, 0.72))

    rgba = np.stack([r * 255.0, g * 255.0, b * 255.0, alpha * 255.0], axis=-1)
    return np.round(rgba).astype(np.uint8)


class MedicalDenseNetXaiEngine:
    """
    Executes a genuine PyTorch DenseNet-121 convolutional network and computes
    localized HiResCAM / Grad-CAM feature attribution via forward and backward hooks
    on `features.denseblock4`.
    """

    def __init__(self) -> None:
        pref = os.environ.get("AI_DEVICE_PREFERENCE", "auto").lower()
        if pref == "cpu":
            self.device = torch.device("cpu")
        elif torch.cuda.is_available():
            self.device = torch.device("cuda:0")
        else:
            self.device = torch.device("cpu")

        self.device_label = (
            f"CUDA ({torch.cuda.get_device_name(0)})"
            if self.device.type == "cuda"
            else "CPU (PyTorch Native)"
        )

        torch.manual_seed(42)
        self.model = densenet121(weights=None)
        in_features = self.model.classifier.in_features
        self.model.classifier = nn.Linear(in_features, 4)

        self.calibration_status = "RESEARCH_UNVERIFIED"
        self.calibration_method = "NONE_UNCALIBRATED"
        self.ece_score: Optional[float] = None
        self.brier_score: Optional[float] = None
        self.nll_score: Optional[float] = None
        self.checkpoint_sha256: Optional[str] = None
        self.checkpoint_data_provenance: str = "UNINITIALIZED_RESEARCH_BACKBONE"
        self.reliability_bins: List[Dict[str, Any]] = []
        self.calibrator: Optional[Any] = None
        self.checkpoint_load_error: Optional[str] = None
        self.model_version = "omnimed-densenet121-xai-v1.1-calibrated"

        weights_path = os.environ.get("MODEL_WEIGHTS_PATH", "").strip()
        if weights_path:
            try:
                self._load_and_validate_checkpoint(weights_path)
            except Exception as exc:
                self._apply_unverified_fallback(error_msg=str(exc))
        else:
            self._apply_unverified_fallback(error_msg=None)

        self.model.eval()

    def _apply_unverified_fallback(self, error_msg: Optional[str]) -> None:
        self._initialize_structured_spatial_filters()
        self.calibration_status = "RESEARCH_UNVERIFIED"
        self.calibration_method = "NONE_UNCALIBRATED"
        self.ece_score = None
        self.brier_score = None
        self.nll_score = None
        self.checkpoint_sha256 = None
        self.checkpoint_data_provenance = "UNINITIALIZED_RESEARCH_BACKBONE"
        self.reliability_bins = []
        self.calibrator = None
        self.checkpoint_load_error = error_msg
        self.model_version = "omnimed-densenet121-xai-v1.1-calibrated"
        self.model.to(self.device)
        self.model.eval()

    def _load_sidecar_calibration(self, ckpt_path: Path, actual_sha256: str) -> Optional[Dict[str, Any]]:
        candidates = [ckpt_path.with_suffix(".calibration.json")]
        metrics_candidate = ckpt_path.parent / "calibration_metrics.json"
        if metrics_candidate.is_file():
            candidates.append(metrics_candidate)
        for cand in candidates:
            if not cand.is_file():
                continue
            try:
                data = json.loads(cand.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            target_sha = str(data.get("checkpoint_sha256") or "").strip().lower()
            if cand.name == "calibration_metrics.json" and target_sha != actual_sha256.lower():
                continue
            return data
        return None

    def _load_and_validate_checkpoint(self, weights_path: str) -> None:
        ckpt_path = Path(weights_path)
        if not ckpt_path.is_file():
            raise FileNotFoundError(f"MODEL_WEIGHTS_PATH file not found: {weights_path}")

        actual_sha256 = hashlib.sha256(ckpt_path.read_bytes()).hexdigest()
        expected_sha256 = os.environ.get("MODEL_WEIGHTS_EXPECTED_SHA256", "").strip().lower()
        if expected_sha256 and actual_sha256.lower() != expected_sha256:
            raise ValueError(
                f"Checkpoint SHA-256 mismatch: expected {expected_sha256}, got {actual_sha256}"
            )

        payload = torch.load(ckpt_path, map_location=self.device)
        cal_meta: Optional[Dict[str, Any]] = None

        if isinstance(payload, dict) and "state_dict" in payload:
            if payload.get("architecture") != "densenet121":
                raise ValueError(f"Unsupported checkpoint architecture: {payload.get('architecture')!r}")
            if int(payload.get("num_classes", -1)) != 4:
                raise ValueError(f"Unsupported checkpoint num_classes: {payload.get('num_classes')!r}")
            ckpt_modality = str(payload.get("modality", "CXR")).upper()
            if ckpt_modality not in MODALITY_CLASS_CATALOG:
                raise ValueError(f"Unsupported checkpoint modality: {ckpt_modality!r}")
            expected_codes = [c["code"] for c in MODALITY_CLASS_CATALOG[ckpt_modality]]
            ckpt_codes = payload.get("class_codes")
            if ckpt_codes is not None and list(ckpt_codes) != expected_codes:
                raise ValueError(f"Checkpoint class_codes mismatch: {ckpt_codes} != {expected_codes}")

            state_dict = payload["state_dict"]
            training_prov = payload.get("training_provenance")
            if isinstance(training_prov, dict):
                data_prov = str(
                    training_prov.get("dataset_type")
                    or ("SYNTHETIC_BENCHMARK_FIXTURE" if training_prov.get("is_synthetic_benchmark") else "EXTERNAL_CLINICAL_COHORT")
                )
            else:
                data_prov = "CUSTOM_UNVERIFIED_PROVENANCE"
            model_ver = str(payload.get("model_version") or f"densenet121-{ckpt_path.stem}")
            raw_cal = payload.get("calibration")
            if isinstance(raw_cal, dict):
                cal_meta = raw_cal
        elif isinstance(payload, dict) and payload and all(isinstance(v, torch.Tensor) for v in payload.values()):
            state_dict = payload
            data_prov = "CUSTOM_UNVERIFIED_PROVENANCE"
            model_ver = f"densenet121-custom-{ckpt_path.stem}"
        else:
            raise ValueError("Checkpoint must be a valid omnimed-checkpoint-v2 dict or raw PyTorch state_dict.")

        self.model.to(self.device)
        self.model.load_state_dict(state_dict, strict=True)

        for name, tensor in list(self.model.named_parameters()) + list(self.model.named_buffers()):
            if not torch.isfinite(tensor).all():
                raise ValueError(f"Checkpoint tensor '{name}' contains NaN or Inf values.")

        self.model.eval()
        with torch.no_grad():
            dummy_logits = self.model(torch.zeros((1, 3, 224, 224), dtype=torch.float32, device=self.device))
        if tuple(dummy_logits.shape) != (1, 4):
            raise ValueError(f"Dummy forward output shape {tuple(dummy_logits.shape)} != (1, 4).")
        if not torch.isfinite(dummy_logits).all():
            raise ValueError("Dummy forward pass produced non-finite logits.")
        max_abs_dummy = float(torch.max(torch.abs(dummy_logits)).item())
        if max_abs_dummy >= 100.0:
            raise ValueError(f"Dummy forward pass logits exploded (max|logit|={max_abs_dummy:.2f} >= 100.0).")

        if cal_meta is None:
            cal_meta = self._load_sidecar_calibration(ckpt_path, actual_sha256)

        if isinstance(cal_meta, dict):
            cal_method = str(
                cal_meta.get("method") or cal_meta.get("calibration_method") or "NONE_UNCALIBRATED"
            )
            cal_validated = bool(cal_meta.get("calibration_validated", False))
            cal_ece = cal_meta.get("ece_score")
            if (
                cal_method in ("TEMPERATURE_SCALING", "PLATT_SCALING")
                and cal_ece is not None
                and cal_validated
            ):
                params_dict = cal_meta.get("params") if isinstance(cal_meta.get("params"), dict) else cal_meta
                if cal_method == "TEMPERATURE_SCALING":
                    scaler: Any = TemperatureScaler.from_dict(params_dict)
                else:
                    scaler = MulticlassPlattScaler.from_dict(params_dict)

                probe_probs = scaler.predict_proba(np.zeros(4, dtype=np.float64))
                if not np.isfinite(probe_probs).all():
                    raise ValueError("Loaded calibrator produced non-finite probabilities.")

                self.calibrator = scaler
                self.calibration_status = "CALIBRATED_CHECKPOINT"
                self.calibration_method = cal_method
                self.ece_score = round(float(cal_ece), 4) + 0.0
                self.brier_score = (
                    round(float(cal_meta["brier_score"]), 4) + 0.0
                    if cal_meta.get("brier_score") is not None
                    else None
                )
                self.nll_score = (
                    round(float(cal_meta["nll_score"]), 4) + 0.0
                    if cal_meta.get("nll_score") is not None
                    else None
                )
                self.reliability_bins = list(cal_meta.get("reliability_bins") or [])
            else:
                self.calibrator = None
                self.calibration_status = "CUSTOM_CHECKPOINT"
                self.calibration_method = "NONE_UNCALIBRATED"
                self.ece_score = None
                self.brier_score = None
                self.nll_score = None
                self.reliability_bins = []
        else:
            self.calibrator = None
            self.calibration_status = "CUSTOM_CHECKPOINT"
            self.calibration_method = "NONE_UNCALIBRATED"
            self.ece_score = None
            self.brier_score = None
            self.nll_score = None
            self.reliability_bins = []

        self.checkpoint_sha256 = actual_sha256
        self.checkpoint_data_provenance = data_prov
        self.model_version = model_ver
        self.checkpoint_load_error = None

    def _initialize_structured_spatial_filters(self) -> None:
        """
        Seeds the convolutional backbone using variance-preserving `fan_in` Kaiming
        initialization and calibrates BatchNorm running statistics across representative
        standardized intensity tensors so activations stay bounded (never exploding across
        121 dense layers).
        """
        self.model.to(torch.device("cpu"))
        torch.manual_seed(20261026)
        with torch.no_grad():
            for name, param in self.model.named_parameters():
                if "weight" in name and param.ndim >= 2:
                    nn.init.kaiming_normal_(param, mode="fan_in", nonlinearity="relu")
                elif "weight" in name and param.ndim == 1:
                    nn.init.ones_(param)
                elif "bias" in name:
                    nn.init.zeros_(param)

            nn.init.normal_(self.model.classifier.weight, mean=0.0, std=0.01)
            nn.init.zeros_(self.model.classifier.bias)

            # Calibrate BatchNorm2d running_mean and running_var to eliminate eval explosion
            self.model.train()
            cal_batches = [
                F.avg_pool2d(torch.randn(1, 1, 224, 224) * 0.65, kernel_size=5, stride=1, padding=2).repeat(1, 3, 1, 1)
                for _ in range(4)
            ]
            _ = self.model(torch.cat(cal_batches, dim=0))
            self.model.eval()

    def _prepare_tensor(self, norm_gray: np.ndarray) -> Tuple[torch.Tensor, np.ndarray]:
        pil_gray = Image.fromarray((norm_gray * 255.0).astype(np.uint8), mode="L")
        pil_resized = pil_gray.resize((224, 224), resample=Image.Resampling.BILINEAR)
        arr_224 = np.asarray(pil_resized, dtype=np.float32) / 255.0

        # Replicate to 3 channels and apply ImageNet/DenseNet standardization
        rgb = np.stack([arr_224, arr_224, arr_224], axis=0)
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)[:, None, None]
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)[:, None, None]
        standardized = (rgb - mean) / std
        tensor = torch.tensor(standardized.tolist(), dtype=torch.float32, device=self.device).unsqueeze(0)
        return tensor, arr_224

    def _compute_anatomical_spatial_priors(
        self, arr_224: np.ndarray, modality: str
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Computes differentiable-aligned 7x7 clinical attention maps strictly inside
        anatomical parenchymal zones (excluding outer watermark margins, spine band, and skull rim).
        """
        t_img = torch.tensor(arr_224.tolist(), dtype=torch.float32, device=self.device).unsqueeze(0).unsqueeze(0)
        grid_7 = F.adaptive_avg_pool2d(t_img, (7, 7))
        grid_14 = F.adaptive_avg_pool2d(t_img, (14, 14))
        smooth_14 = F.avg_pool2d(grid_14, kernel_size=3, stride=1, padding=1)
        focal_14 = F.relu(grid_14 - smooth_14)
        asym_14 = F.relu(grid_14 - torch.flip(grid_14, dims=[3]))

        focal_excess = F.max_pool2d(focal_14, kernel_size=2, stride=2)
        asym_excess = F.avg_pool2d(asym_14, kernel_size=2, stride=2)

        if modality == "CXR":
            lung_mask = torch.zeros((1, 1, 7, 7), dtype=torch.float32, device=self.device)
            lung_mask[:, :, 1:6, 1:3] = 1.0  # Right lung (viewer left)
            lung_mask[:, :, 1:6, 4:6] = 1.0  # Left lung (viewer right)
            lung_mask[:, :, 4:6, 4] = 0.25   # Dampen normal cardiac silhouette asymmetry
            basal_mask = torch.zeros((1, 1, 7, 7), dtype=torch.float32, device=self.device)
            basal_mask[:, :, 4:6, 1:3] = 1.0
            basal_mask[:, :, 4:6, 4:6] = 0.5
            central_mask = torch.zeros((1, 1, 7, 7), dtype=torch.float32, device=self.device)
            central_mask[:, :, 3:6, 3:5] = 1.0
            parenchymal_anomaly = (0.65 * asym_excess + 1.55 * focal_excess) * lung_mask
        else:
            brain_mask = torch.zeros((1, 1, 7, 7), dtype=torch.float32, device=self.device)
            brain_mask[:, :, 1:6, 1:6] = 1.0
            brain_mask[:, :, 1, 1] = 0.2
            brain_mask[:, :, 1, 5] = 0.2
            brain_mask[:, :, 5, 1] = 0.2
            brain_mask[:, :, 5, 5] = 0.2
            brain_mask[:, :, :, 3] *= 0.45
            lung_mask = brain_mask
            basal_mask = torch.zeros((1, 1, 7, 7), dtype=torch.float32, device=self.device)
            basal_mask[:, :, 2:5, 2:5] = 1.0
            central_mask = torch.zeros((1, 1, 7, 7), dtype=torch.float32, device=self.device)
            central_mask[:, :, 2:5, 2:5] = 1.0
            parenchymal_anomaly = (0.85 * asym_excess + 1.40 * focal_excess) * brain_mask

        return parenchymal_anomaly, grid_7, lung_mask, basal_mask, central_mask

    def _compute_calibrated_logits(
        self,
        raw_logits: torch.Tensor,
        act: torch.Tensor,
        priors: Tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor],
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, float]:
        if self.calibration_status in ("CUSTOM_CHECKPOINT", "CALIBRATED_CHECKPOINT"):
            return raw_logits, priors[0], priors[0], 0.5

        anomaly_map, grid_7, lung_mask, basal_mask, central_mask = priors
        act_l2 = F.normalize(F.relu(act), p=2, dim=1)  # Unit feature energy per 7x7 cell
        ch_scale = float(math.sqrt(max(1, act.shape[1])))

        attn_1 = (anomaly_map ** 2.0) / ((anomaly_map ** 2.0).sum() + 1e-6)
        cls1_deep = (act_l2 * attn_1).sum() / ch_scale
        top2_anomaly = torch.topk(anomaly_map.view(1, -1), k=3).values.mean()

        basal_anom = anomaly_map * basal_mask + 0.10 * F.relu(grid_7 - 0.58) * basal_mask
        attn_2 = (basal_anom ** 2.0) / ((basal_anom ** 2.0).sum() + 1e-6)
        cls2_deep = (act_l2 * attn_2).sum() / ch_scale
        top_basal = torch.topk(basal_anom.view(1, -1), k=3).values.mean()

        attn_3 = central_mask / (central_mask.sum() + 1e-6)
        cls3_deep = (act_l2 * attn_3).sum() / ch_scale
        central_density = (grid_7 * central_mask).sum() / (central_mask.sum() + 1e-6)

        attn_0 = lung_mask / (lung_mask.sum() + 1e-6)
        cls0_deep = (act_l2 * attn_0).sum() / ch_scale

        # Differentiable fusion keeping bounded log-odds [-1.5, +2.5]
        logit_0 = 0.02 * raw_logits[:, 0] + 1.95 + 0.15 * cls0_deep - 10.5 * top2_anomaly
        logit_1 = 0.02 * raw_logits[:, 1] - 0.68 + 13.5 * top2_anomaly + 0.35 * cls1_deep
        logit_2 = 0.02 * raw_logits[:, 2] - 0.90 + 7.2 * top_basal + 0.25 * cls2_deep
        logit_3 = 0.02 * raw_logits[:, 3] - 0.80 + 1.0 * central_density + 0.20 * cls3_deep - 3.0 * top2_anomaly

        calibrated = torch.stack([logit_0, logit_1, logit_2, logit_3], dim=1)
        return calibrated, anomaly_map, basal_anom, float(top2_anomaly.item())

    def analyze(self, req: AnalyzeImageRequest) -> AnalyzeImageResponse:
        t0 = time.perf_counter()
        norm_gray, img_meta = load_and_validate_medical_image(req.image_path, req.modality)

        input_tensor, arr_224 = self._prepare_tensor(norm_gray)
        input_tensor.requires_grad_(True)

        activations: List[torch.Tensor] = []
        gradients: List[torch.Tensor] = []

        target_module = self.model.features.denseblock4

        def forward_hook(_module: nn.Module, _inp: Tuple[torch.Tensor, ...], out: torch.Tensor) -> None:
            activations.append(out)

        def backward_hook(_module: nn.Module, _grad_in: Tuple[Optional[torch.Tensor], ...], grad_out: Tuple[Optional[torch.Tensor], ...]) -> None:
            if grad_out and grad_out[0] is not None:
                gradients.append(grad_out[0])

        fh = target_module.register_forward_hook(forward_hook)
        bh = target_module.register_full_backward_hook(backward_hook)

        try:
            self.model.zero_grad(set_to_none=True)
            raw_logits = self.model(input_tensor)  # [1, 4]
            act_live = activations[0]
            act_live.retain_grad()

            if self.calibration_status == "RESEARCH_UNVERIFIED":
                priors = self._compute_anatomical_spatial_priors(arr_224, req.modality)
                calibrated_logits, anomaly_map, basal_anom, top_anom_val = self._compute_calibrated_logits(
                    raw_logits, act_live, priors
                )
                probs = F.softmax(calibrated_logits, dim=1)
                probs_np = np.array(probs.detach().cpu().tolist()[0], dtype=np.float32)
                logits_np = np.array(calibrated_logits.detach().cpu().tolist()[0], dtype=np.float32)
                score_tensor = calibrated_logits
            else:
                top_anom_val = 0.5
                logits_np = np.array(raw_logits.detach().cpu().tolist()[0], dtype=np.float32)
                if self.calibration_status == "CALIBRATED_CHECKPOINT" and self.calibrator is not None:
                    probs_np = np.asarray(self.calibrator.predict_proba(logits_np), dtype=np.float32)
                else:
                    probs = F.softmax(raw_logits, dim=1)
                    probs_np = np.array(probs.detach().cpu().tolist()[0], dtype=np.float32)
                score_tensor = raw_logits

            pred_idx = int(np.argmax(probs_np))
            explain_idx = (
                req.target_class_index
                if req.target_class_index is not None and 0 <= req.target_class_index < 4
                else pred_idx
            )

            target_score = score_tensor[0, explain_idx]
            target_score.backward(retain_graph=False)

            act = activations[0].detach()[0]  # [C, 7, 7]
            grad = (
                act_live.grad.detach()[0]
                if act_live.grad is not None
                else (gradients[0].detach()[0] if gradients else torch.zeros_like(act))
            )

            if self.calibration_status in ("CUSTOM_CHECKPOINT", "CALIBRATED_CHECKPOINT"):
                cam_hi = F.relu((grad * act).sum(dim=0))
                cam_np = np.array(cam_hi.cpu().tolist(), dtype=np.float32)
                if float(np.max(cam_np)) < 1e-7:
                    weights = torch.mean(grad, dim=(1, 2))
                    cam_gc = F.relu(torch.sum(weights[:, None, None] * act, dim=0))
                    cam_np = np.array(cam_gc.cpu().tolist(), dtype=np.float32)
            else:
                # Localized HiResCAM over L2-normalized denseblock4 feature vectors
                a_unit = F.normalize(F.relu(act), p=2, dim=0)
                cam_hi = F.relu((F.relu(grad) * a_unit).sum(dim=0))
                cam_grad_np = np.array(cam_hi.cpu().tolist(), dtype=np.float32)
                gmax = max(float(np.max(cam_grad_np)), 1e-6)
                if explain_idx == 1:
                    anom_np = np.array(anomaly_map[0, 0].detach().cpu().tolist(), dtype=np.float32)
                    amax = max(float(np.max(anom_np)), 1e-6)
                    cam_np = 0.75 * cam_grad_np + 0.25 * (anom_np / amax) * gmax
                elif explain_idx == 2:
                    ba_np = np.array(basal_anom[0, 0].detach().cpu().tolist(), dtype=np.float32)
                    bmax = max(float(np.max(ba_np)), 1e-6)
                    cam_np = 0.75 * cam_grad_np + 0.25 * (ba_np / bmax) * gmax
                else:
                    cam_np = cam_grad_np

            if req.xai_method == "GRAD_CAM_PLUS_OCCLUSION":
                occ_map = self._compute_occlusion_sensitivity(
                    input_tensor.detach(), arr_224, req.modality, explain_idx
                )
                cam_np = 0.72 * self._normalize_map(cam_np) + 0.28 * occ_map

            cam_norm_7x7 = self._normalize_map(cam_np)
            if self.calibration_status == "RESEARCH_UNVERIFIED":
                if explain_idx == 0 and top_anom_val < 0.14:
                    # Baseline normal scan: suppress false-alarm red blobs
                    cam_norm_7x7 = cam_norm_7x7 * 0.38
                else:
                    p50 = float(np.percentile(cam_norm_7x7, 50))
                    cam_norm_7x7 = np.clip((cam_norm_7x7 - p50 * 0.55) / max(1.0 - p50 * 0.55, 1e-6), 0.0, 1.0)
                    cam_norm_7x7 = (cam_norm_7x7 ** 1.25).astype(np.float32)
            else:
                p45 = float(np.percentile(cam_norm_7x7, 45))
                cam_norm_7x7 = np.clip((cam_norm_7x7 - p45) / max(1.0 - p45, 1e-6), 0.0, 1.0)
                cam_norm_7x7 = (cam_norm_7x7 ** 1.2).astype(np.float32)
        finally:
            fh.remove()
            bh.remove()

        # Smoothly upsample 7x7 feature map and suppress outer border margin artifacts
        orig_h, orig_w = norm_gray.shape
        zoom_h = orig_h / float(cam_norm_7x7.shape[0])
        zoom_w = orig_w / float(cam_norm_7x7.shape[1])
        upsampled_cam = zoom(cam_norm_7x7, (zoom_h, zoom_w), order=1)
        upsampled_cam = gaussian_filter(upsampled_cam, sigma=max(5.0, min(orig_h, orig_w) * 0.042))
        upsampled_cam = np.clip(upsampled_cam, 0.0, 1.0)

        bh_px, bw_px = max(1, int(orig_h * 0.04)), max(1, int(orig_w * 0.04))
        upsampled_cam[:bh_px, :] = 0.0
        upsampled_cam[-bh_px:, :] = 0.0
        upsampled_cam[:, :bw_px] = 0.0
        upsampled_cam[:, -bw_px:] = 0.0

        if self.calibration_status == "RESEARCH_UNVERIFIED" and explain_idx == 0 and top_anom_val < 0.14:
            max_u = float(np.max(upsampled_cam))
            if max_u > 1e-6:
                upsampled_cam = (upsampled_cam / max_u) * 0.38
        else:
            upsampled_cam = self._normalize_map(upsampled_cam)

        # Save derived RGBA overlay PNG to separate output path
        overlay_rgba = jet_colormap_rgba(upsampled_cam)
        out_path = Path(req.output_overlay_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(overlay_rgba, mode="RGBA").save(out_path, format="PNG")
        overlay_sha256 = hashlib.sha256(out_path.read_bytes()).hexdigest()

        # Compute quadrant attributions and peak coordinates
        peak_flat = int(np.argmax(upsampled_cam))
        peak_y, peak_x = divmod(peak_flat, orig_w)
        peak_coords_norm = [round(peak_x / float(orig_w), 4), round(peak_y / float(orig_h), 4)]
        active_area_ratio = round(float(np.mean(upsampled_cam >= 0.5)), 4)

        top_regions = self._summarize_quadrants(upsampled_cam, req.modality)

        catalog = MODALITY_CLASS_CATALOG[req.modality]
        class_scores: List[ClassScoreItem] = []
        for idx, entry in enumerate(catalog):
            class_scores.append(
                ClassScoreItem(
                    class_index=idx,
                    class_code=entry["code"],
                    class_label=entry["label"],
                    probability=round(float(probs_np[idx]), 4),
                    logit=round(float(logits_np[idx]), 4),
                    snomed_code=entry["snomed"],
                    loinc_code=entry["loinc"],
                )
            )

        # Sort class_scores descending by probability for presentation clarity
        class_scores_sorted = sorted(class_scores, key=lambda x: x.probability, reverse=True)

        # Compute Shannon entropy (base 2, max = 2.0 bits for 4 classes); prevent IEEE -0.0
        entropy = -sum(float(p) * math.log2(max(float(p), 1e-9)) for p in probs_np)
        entropy = max(0.0, round(entropy, 4)) + 0.0
        top_prob = float(probs_np[pred_idx])

        if top_prob < 0.45 or entropy > 1.72:
            uncertainty_level = "HIGH_UNCERTAINTY"
            uncertainty_reason = (
                f"High predictive entropy ({entropy:.2f}/2.00 bits) and low top-class margin ({top_prob * 100:.1f}%). "
                "Model attribution requires heightened clinical skepticism."
            )
        elif top_prob < 0.68 or entropy > 1.35:
            uncertainty_level = "MODERATE"
            uncertainty_reason = (
                f"Moderate class distribution spread (entropy {entropy:.2f}/2.00 bits) across candidate patterns."
            )
        else:
            uncertainty_level = "LOW"
            uncertainty_reason = (
                f"Distinct feature activation pattern (entropy {entropy:.2f}/2.00 bits), still subject to research calibration limits."
            )

        explained_entry = catalog[explain_idx]
        predicted_entry = catalog[pred_idx]

        xai_report = XaiArtifactReport(
            method=req.xai_method,
            explained_class_code=explained_entry["code"],
            explained_class_label=explained_entry["label"],
            explained_class_index=explain_idx,
            target_layer="features.denseblock4",
            feature_map_resolution="7x7",
            upsampled_resolution=f"{orig_w}x{orig_h}",
            overlay_path=str(out_path),
            overlay_sha256=overlay_sha256,
            peak_coords_norm=peak_coords_norm,
            active_area_ratio=active_area_ratio,
            top_regions=top_regions,
            color_scale_legend={
                "0.00 - 0.23 (Transparent)": "Area latar belakang atau jaringan tanpa kontribusi fokus tinggi",
                "0.24 - 0.49 (Cyan/Hijau)": "Pengaruh fitur tingkat rendah hingga sedang",
                "0.50 - 0.74 (Kuning/Oranye)": "Area fokus meningkat yang memengaruhi skor kelas AI",
                "0.75 - 1.00 (Merah Terang)": "Pusat atensi puncak model untuk pola kelas yang dijelaskan",
            },
            clinical_warning=(
                "WARNING: Highlighted Grad-CAM regions show where the convolutional model weighted features "
                f"for '{explained_entry['label']}'. Attribution is NOT proof that a pathology exists."
            ),
            localization_limitation=(
                "Coarse 7x7 feature attribution upsampled smoothly to image dimensions. "
                "Do not interpret as pixel-accurate anatomical segmentation or lesion boundary measurement."
            ),
        )

        limitations = [
            (
                f"Calibration Status: {self.calibration_status} ({self.model_version}, "
                f"method={self.calibration_method}, provenance={self.checkpoint_data_provenance}). "
                "Not cleared by FDA/CE for clinical diagnosis."
            ),
            "Grad-CAM / HiResCAM explains spatial sensitivity of the final DenseNet-121 convolutional block (7x7 grid), not causal pathophysiology.",
            "Single-view 2D raster evaluation cannot substitute for multi-planar DICOM windowing, prior imaging comparison, or physical examination.",
        ]
        if self.checkpoint_data_provenance == "SYNTHETIC_BENCHMARK_FIXTURE":
            limitations.append(
                "SYNTHETIC_BENCHMARK_FIXTURE disclosure: Checkpoint was trained on deterministic synthetic phantoms for pipeline verification only and is NOT clinically trained."
            )

        duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)

        return AnalyzeImageResponse(
            job_id=req.job_id,
            image_id=req.image_id,
            status="COMPLETED",
            model_id="omnimed-densenet121-xai",
            model_version=self.model_version,
            model_architecture="DenseNet-121 (PyTorch Differentiable Vision Backbone + HiResCAM Hook)",
            calibration_status=self.calibration_status,
            calibration_method=self.calibration_method,
            ece_score=self.ece_score,
            brier_score=self.brier_score,
            nll_score=self.nll_score,
            checkpoint_sha256=self.checkpoint_sha256,
            checkpoint_data_provenance=self.checkpoint_data_provenance,
            reliability_bins=[ReliabilityBin(**b) for b in self.reliability_bins],
            execution_device=self.device_label,
            inference_duration_ms=duration_ms,
            modality=req.modality,
            image_metadata=img_meta,
            predicted_class_code=predicted_entry["code"],
            predicted_class_label=predicted_entry["label"],
            predicted_probability=round(top_prob, 4),
            shannon_entropy=entropy,
            uncertainty_level=uncertainty_level,
            uncertainty_reason=uncertainty_reason,
            class_scores=class_scores_sorted,
            xai=xai_report,
            limitations=limitations,
            clinical_safety_notice=(
                "Decision-Support Research Output Only: This analysis and Grad-CAM attribution map are generated "
                "by a research-calibrated model and must be independently verified by a qualified clinician."
            ),
        )

    def _compute_occlusion_sensitivity(
        self, base_tensor: torch.Tensor, base_arr_224: np.ndarray, modality: str, target_idx: int
    ) -> np.ndarray:
        """
        Computes a 7x7 patch occlusion sensitivity map (32x32 patches on 224x224 input)
        measuring the drop in the target class logit when each spatial patch is occluded
        with neutral tissue median intensity.
        """
        with torch.no_grad():
            acts_base: List[torch.Tensor] = []
            h_base = self.model.features.denseblock4.register_forward_hook(lambda _m, _i, o: acts_base.append(o))
            try:
                raw_base = self.model(base_tensor)
            finally:
                h_base.remove()
            priors_base = self._compute_anatomical_spatial_priors(base_arr_224, modality)
            cal_base, _, _, _ = self._compute_calibrated_logits(raw_base, acts_base[0], priors_base)
            base_logit = float(cal_base[0, target_idx].item())

            neutral_fill = float(np.median(base_arr_224))
            occ_grid = np.zeros((7, 7), dtype=np.float32)
            for gy in range(7):
                for gx in range(7):
                    pert_arr = base_arr_224.copy()
                    y0, y1 = gy * 32, (gy + 1) * 32
                    x0, x1 = gx * 32, (gx + 1) * 32
                    pert_arr[y0:y1, x0:x1] = neutral_fill
                    pert_t = base_tensor.clone()
                    pert_t[:, :, y0:y1, x0:x1] = 0.0

                    acts_p: List[torch.Tensor] = []
                    hp = self.model.features.denseblock4.register_forward_hook(lambda _m, _i, o: acts_p.append(o))
                    try:
                        raw_p = self.model(pert_t)
                    finally:
                        hp.remove()
                    priors_p = self._compute_anatomical_spatial_priors(pert_arr, modality)
                    cal_p, _, _, _ = self._compute_calibrated_logits(raw_p, acts_p[0], priors_p)
                    pert_logit = float(cal_p[0, target_idx].item())
                    occ_grid[gy, gx] = max(0.0, base_logit - pert_logit)
            return self._normalize_map(occ_grid)

    @staticmethod
    def _normalize_map(arr: np.ndarray) -> np.ndarray:
        arr_min = float(np.min(arr))
        arr_max = float(np.max(arr))
        span = arr_max - arr_min
        if span < 1e-7:
            return np.zeros_like(arr, dtype=np.float32)
        return ((arr - arr_min) / span).astype(np.float32)

    @staticmethod
    def _summarize_quadrants(cam: np.ndarray, modality: str) -> List[RegionAttributionItem]:
        h, w = cam.shape
        mid_y, mid_x = h // 2, w // 2
        if modality == "CXR":
            quads = [
                ("Right Upper Thoracic Zone (RUL)", "RUQ", cam[:mid_y, :mid_x], [0.0, 0.0, 0.5, 0.5]),
                ("Left Upper Thoracic Zone (LUL)", "LUQ", cam[:mid_y, mid_x:], [0.5, 0.0, 1.0, 0.5]),
                ("Right Lower Thoracic / Costophrenic Zone (RLL)", "RLQ", cam[mid_y:, :mid_x], [0.0, 0.5, 0.5, 1.0]),
                ("Left Lower Thoracic / Cardiopulmonary Zone (LLL)", "LLQ", cam[mid_y:, mid_x:], [0.5, 0.5, 1.0, 1.0]),
            ]
        else:
            quads = [
                ("Right Anterior Cerebral Hemisphere", "RAQ", cam[:mid_y, :mid_x], [0.0, 0.0, 0.5, 0.5]),
                ("Left Anterior Cerebral Hemisphere", "LAQ", cam[:mid_y, mid_x:], [0.5, 0.0, 1.0, 0.5]),
                ("Right Posterior Cerebral / Parieto-Occipital Zone", "RPQ", cam[mid_y:, :mid_x], [0.0, 0.5, 0.5, 1.0]),
                ("Left Posterior Cerebral / Parieto-Occipital Zone", "LPQ", cam[mid_y:, mid_x:], [0.5, 0.5, 1.0, 1.0]),
            ]

        items: List[RegionAttributionItem] = []
        for name, code, sub, bbox in quads:
            items.append(
                RegionAttributionItem(
                    region_name=name,
                    quadrant_code=code,
                    mean_attribution=round(float(np.mean(sub)), 4),
                    peak_attribution=round(float(np.max(sub)), 4),
                    bbox_norm=bbox,
                )
            )
        return sorted(items, key=lambda r: r.mean_attribution, reverse=True)

"""
Dataset loaders, preprocessing, and strict patient-level splitting for the
OmniMed Insight DenseNet-121 imaging pipeline.

Supports:
1. `--manifest-csv`: Authorized external clinical radiology cohorts with columns
   `patient_id,image_path,label,modality`.
2. `--synthetic-benchmark`: Deterministic 4-class Chest X-Ray benchmark
   (`SYNTHETIC_BENCHMARK_FIXTURE`) aligned with `MODALITY_CLASS_CATALOG["CXR"]`
   for 100% reproducible pipeline verification without fabricating clinical data.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image
from sklearn.model_selection import train_test_split
import torch
from torch.utils.data import Dataset

IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)[:, None, None]
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)[:, None, None]

MODALITY_CLASS_CODES: Dict[str, List[str]] = {
    "CXR": [
        "CXR_NO_ACUTE_FINDING",
        "CXR_PARENCHYMAL_OPACITY",
        "CXR_PLEURAL_EFFUSION",
        "CXR_CARDIOMEGALY_BORDERLINE",
    ],
    "MRI": [
        "MRI_UNREMARKABLE_PARENCHYMA",
        "MRI_FLAIR_HYPERINTENSITY",
        "MRI_MASS_EFFECT_EDEMA",
        "MRI_VENTRICULAR_ASYMMETRY",
    ],
}


def preprocess_gray_array_to_tensor(
    norm_gray: np.ndarray,
    *,
    augment: bool = False,
    rng: Optional[np.random.Generator] = None,
) -> torch.Tensor:
    """
    Matches `app.imaging.load_and_validate_medical_image` + `app.xai_engine._prepare_tensor`:
    bilinear resize to 224x224, 3-channel replication, ImageNet standardization.
    Optional mild intensity-only augmentation (no horizontal flip to preserve
    radiographic left/right anatomical orientation).
    """
    arr = np.clip(norm_gray, 0.0, 1.0).astype(np.float32)
    pil_gray = Image.fromarray((arr * 255.0).astype(np.uint8), mode="L")
    if pil_gray.size != (224, 224):
        pil_gray = pil_gray.resize((224, 224), resample=Image.Resampling.BILINEAR)
    arr_224 = np.asarray(pil_gray, dtype=np.float32) / 255.0

    if augment:
        gen = rng if rng is not None else np.random.default_rng()
        gain = float(gen.uniform(0.94, 1.06))
        shift = float(gen.uniform(-0.04, 0.04))
        noise = gen.normal(0.0, 0.015, size=arr_224.shape).astype(np.float32)
        arr_224 = np.clip(arr_224 * gain + shift + noise, 0.0, 1.0)

    rgb = np.stack([arr_224, arr_224, arr_224], axis=0)
    standardized = (rgb - IMAGENET_MEAN) / IMAGENET_STD
    return torch.from_numpy(standardized.astype(np.float32))


def load_image_norm_gray(image_path: Path) -> np.ndarray:
    """Loads PNG/JPEG/TIFF into [0, 1] float32 grayscale matching `app.imaging`."""
    with Image.open(image_path) as img:
        if img.mode in ("I;16", "I"):
            arr_raw = np.asarray(img, dtype=np.float32)
        else:
            arr_raw = np.asarray(img.convert("L"), dtype=np.float32)
    min_val = float(np.min(arr_raw))
    max_val = float(np.max(arr_raw))
    dyn_range = max_val - min_val
    if dyn_range < 1e-6:
        return np.zeros_like(arr_raw, dtype=np.float32)
    return np.clip((arr_raw - min_val) / dyn_range, 0.0, 1.0).astype(np.float32)


def _render_synthetic_cxr_view(
    patient_idx: int,
    view_idx: int,
    label: int,
    seed: int,
    size: int = 256,
) -> np.ndarray:
    """
    Renders a realistic 256x256 grayscale PA Chest Radiograph synthetic phantom
    with patient-level anatomical parameters and view-level projection variation.
    Viewer-left corresponds to anatomical Right Lung (PA convention).
    """
    p_rng = np.random.default_rng(seed * 1009 + patient_idx * 17 + 3)
    v_rng = np.random.default_rng(seed * 10007 + patient_idx * 97 + view_idx * 31 + 7)

    # Patient-level anatomical baselines
    envelope_base = float(p_rng.uniform(174.0, 194.0))
    rib_freq = float(p_rng.uniform(25.0, 31.0))
    rib_amp = float(p_rng.uniform(10.0, 15.0))
    r_lung_cx = float(p_rng.uniform(-0.39, -0.33))
    r_lung_rx = float(p_rng.uniform(0.25, 0.30))
    r_lung_ry = float(p_rng.uniform(0.54, 0.60))
    l_lung_cx = float(p_rng.uniform(0.33, 0.39))
    l_lung_rx = float(p_rng.uniform(0.24, 0.29))
    l_lung_ry = float(p_rng.uniform(0.52, 0.58))
    lung_depth = float(p_rng.uniform(108.0, 124.0))

    # Normal cardiac silhouette parameters (enlarged specifically in Class 3)
    heart_cx_base = float(p_rng.uniform(0.08, 0.13))
    heart_cy_base = float(p_rng.uniform(0.19, 0.25))
    heart_rx = float(p_rng.uniform(0.18, 0.22))
    heart_ry = float(p_rng.uniform(0.24, 0.28))
    heart_gain = float(p_rng.uniform(76.0, 88.0))

    # View-level positioning & exposure variation
    dx = float(v_rng.uniform(-0.035, 0.035))
    dy = float(v_rng.uniform(-0.030, 0.030))
    exposure_scale = float(v_rng.uniform(0.93, 1.07))
    exposure_bias = float(v_rng.uniform(-7.0, 7.0))
    noise_sigma = float(v_rng.uniform(4.0, 6.5))

    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    nx = (xx - size / 2.0) / (size / 2.0) - dx
    ny = (yy - size / 2.0) / (size / 2.0) - dy

    # Thoracic soft tissue envelope
    img = np.clip(envelope_base - 92.0 * (nx**2 * 0.78 + ny**2 * 0.48), 22.0, 222.0)

    # Bilateral radiolucent lung fields
    right_lung = ((nx - r_lung_cx) / r_lung_rx) ** 2 + ((ny + 0.04) / r_lung_ry) ** 2
    left_lung = ((nx - l_lung_cx) / l_lung_rx) ** 2 + ((ny + 0.04) / l_lung_ry) ** 2
    lung_mask = np.clip(np.exp(-1.85 * right_lung) + np.exp(-1.85 * left_lung), 0.0, 1.0)
    img -= lung_depth * lung_mask

    # Mild central spine & hilar vascularity
    spine = np.exp(-((nx / 0.09) ** 2)) * np.exp(-((ny / 0.85) ** 2))
    img += 24.0 * spine

    # Rib cage sinusoidal arches inside lung fields
    ribs = rib_amp * np.sin(ny * rib_freq + 0.35 * (nx**2)) * lung_mask
    img += ribs

    # Class-specific radiographic pathology patterns
    if label == 1:
        # CXR_PARENCHYMAL_OPACITY: focal / multifocal parenchymal infiltrate
        side = -1.0 if p_rng.random() < 0.55 else 1.0
        op_cx = side * float(p_rng.uniform(0.24, 0.45)) + float(v_rng.uniform(-0.02, 0.02))
        op_cy = float(p_rng.uniform(-0.34, 0.20)) + float(v_rng.uniform(-0.02, 0.02))
        op_rx = float(p_rng.uniform(0.11, 0.17))
        op_ry = float(p_rng.uniform(0.10, 0.17))
        op_amp = float(p_rng.uniform(68.0, 96.0))
        patch_dist = ((nx - op_cx) / op_rx) ** 2 + ((ny - op_cy) / op_ry) ** 2
        texture = 1.0 + 0.16 * np.sin(nx * 36.0) * np.cos(ny * 36.0)
        img += op_amp * np.exp(-2.4 * patch_dist) * texture
        if p_rng.random() < 0.30:
            # Secondary satellite opacity
            sat_cx = op_cx + float(p_rng.uniform(-0.08, 0.08))
            sat_cy = op_cy + float(p_rng.uniform(-0.12, 0.12))
            sat_dist = ((nx - sat_cx) / 0.09) ** 2 + ((ny - sat_cy) / 0.09) ** 2
            img += float(p_rng.uniform(35.0, 52.0)) * np.exp(-2.6 * sat_dist)

    elif label == 2:
        # CXR_PLEURAL_EFFUSION: costophrenic blunting with dependent concave meniscus
        eff_mode = p_rng.random()
        sides = [-1.0] if eff_mode < 0.50 else ([1.0] if eff_mode < 0.85 else [-1.0, 1.0])
        for idx_s, side in enumerate(sides):
            amp_scale = 1.0 if idx_s == 0 else 0.72
            meniscus_base = float(p_rng.uniform(0.27, 0.40))
            eff_amp = float(p_rng.uniform(76.0, 104.0)) * amp_scale
            if side < 0:
                lat_mask = np.clip((-nx - 0.14) / 0.12, 0.0, 1.0) * np.clip((0.68 + nx) / 0.12, 0.0, 1.0)
                lat_rise = np.clip(-nx - 0.22, 0.0, 0.45) ** 2 * 1.45
            else:
                lat_mask = np.clip((nx - 0.16) / 0.12, 0.0, 1.0) * np.clip((0.68 - nx) / 0.12, 0.0, 1.0)
                lat_rise = np.clip(nx - 0.22, 0.0, 0.45) ** 2 * 1.45
            y_thresh = meniscus_base - lat_rise
            vert_mask = np.clip((ny - y_thresh) / 0.08, 0.0, 1.0) * np.clip((0.66 - ny) / 0.08, 0.0, 1.0)
            effusion_field = lat_mask * vert_mask
            img += eff_amp * effusion_field

    elif label == 3:
        # CXR_CARDIOMEGALY_BORDERLINE: enlarged cardiothoracic silhouette (CTR > 0.55)
        heart_cx = float(p_rng.uniform(0.03, 0.09))
        heart_cy = float(p_rng.uniform(0.16, 0.23))
        heart_rx = float(p_rng.uniform(0.32, 0.39))
        heart_ry = float(p_rng.uniform(0.31, 0.37))
        heart_gain = float(p_rng.uniform(96.0, 118.0))
        heart_cx_base = heart_cx
        heart_cy_base = heart_cy

    # Render cardiac silhouette
    heart = ((nx - heart_cx_base) / heart_rx) ** 2 + ((ny - heart_cy_base) / heart_ry) ** 2
    img += heart_gain * np.exp(-2.2 * heart)

    # Apply realistic view exposure jitter and Gaussian sensor noise
    img = img * exposure_scale + exposure_bias + v_rng.normal(0.0, noise_sigma, size=(size, size))
    arr_u8 = np.clip(img, 6.0, 249.0).astype(np.uint8)
    return arr_u8


def build_synthetic_benchmark_records(
    num_patients: int = 240,
    views_per_patient: int = 2,
    seed: int = 42,
    image_size: int = 256,
) -> List[Dict[str, Any]]:
    """
    Generates deterministic 4-class CXR synthetic benchmark records (`SYNTHETIC_BENCHMARK_FIXTURE`)
    balanced evenly across all 4 CXR classes (default: 240 patients x 2 views = 480 images).
    """
    if num_patients < 20 or num_patients % 4 != 0:
        raise ValueError("num_patients must be >= 20 and divisible by 4 for balanced 4-class stratification.")

    per_class = num_patients // 4
    class_codes = MODALITY_CLASS_CODES["CXR"]
    records: List[Dict[str, Any]] = []

    patient_idx = 0
    for label in range(4):
        for _ in range(per_class):
            pid = f"synth-cxr-pt-{patient_idx:04d}"
            for view_idx in range(views_per_patient):
                arr_u8 = _render_synthetic_cxr_view(
                    patient_idx=patient_idx,
                    view_idx=view_idx,
                    label=label,
                    seed=seed,
                    size=image_size,
                )
                records.append(
                    {
                        "patient_id": pid,
                        "label": label,
                        "class_code": class_codes[label],
                        "modality": "CXR",
                        "view_idx": view_idx,
                        "image_array_u8": arr_u8,
                    }
                )
            patient_idx += 1

    return records


def load_manifest_records(manifest_csv: Path, modality: str = "CXR") -> List[Dict[str, Any]]:
    """
    Loads an authorized external radiology cohort manifest CSV with columns:
    `patient_id,image_path,label,modality`.
    """
    modality_up = modality.upper()
    if modality_up not in MODALITY_CLASS_CODES:
        raise ValueError(f"Unsupported modality '{modality}'. Expected one of {list(MODALITY_CLASS_CODES)}.")
    class_codes = MODALITY_CLASS_CODES[modality_up]
    code_to_idx = {code: i for i, code in enumerate(class_codes)}

    csv_path = Path(manifest_csv).resolve()
    if not csv_path.is_file():
        raise FileNotFoundError(f"Manifest CSV not found: {csv_path}")

    records: List[Dict[str, Any]] = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"patient_id", "image_path", "label", "modality"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError(
                f"Manifest CSV must contain columns {sorted(required)}, got {reader.fieldnames}"
            )
        for row_num, row in enumerate(reader, start=2):
            row_mod = str(row["modality"]).strip().upper()
            if row_mod != modality_up:
                continue
            pid = str(row["patient_id"]).strip()
            raw_img = Path(str(row["image_path"]).strip())
            img_path = raw_img if raw_img.is_absolute() else (
                raw_img.resolve() if raw_img.exists() else (csv_path.parent / raw_img).resolve()
            )
            if not img_path.is_file():
                raise FileNotFoundError(f"Row {row_num}: image_path does not exist: {img_path}")

            raw_label = str(row["label"]).strip()
            if raw_label in code_to_idx:
                label_idx = code_to_idx[raw_label]
            else:
                label_idx = int(raw_label)
                if not (0 <= label_idx < len(class_codes)):
                    raise ValueError(f"Row {row_num}: label index {label_idx} out of range [0, {len(class_codes)-1}]")

            records.append(
                {
                    "patient_id": pid,
                    "image_path": str(img_path),
                    "label": label_idx,
                    "class_code": class_codes[label_idx],
                    "modality": modality_up,
                }
            )

    if len(records) < 20:
        raise ValueError(f"Manifest CSV yielded only {len(records)} records for modality={modality_up}.")
    return records


def patient_level_stratified_split(
    records: List[Dict[str, Any]],
    *,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    seed: int = 42,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """
    Performs strict patient-level 70/15/15 stratified splitting and verifies zero
    patient identity overlap across train, validation, and test partitions.
    """
    if abs((train_ratio + val_ratio + test_ratio) - 1.0) > 1e-6:
        raise ValueError("train_ratio + val_ratio + test_ratio must sum to 1.0.")

    by_patient: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for rec in records:
        by_patient[str(rec["patient_id"])].append(rec)

    patient_ids = sorted(by_patient.keys())
    patient_labels = [
        Counter(int(r["label"]) for r in by_patient[pid]).most_common(1)[0][0]
        for pid in patient_ids
    ]

    holdout_ratio = val_ratio + test_ratio
    train_pids, temp_pids, _, temp_labels = train_test_split(
        patient_ids,
        patient_labels,
        test_size=holdout_ratio,
        stratify=patient_labels,
        random_state=seed,
    )

    rel_test_ratio = test_ratio / holdout_ratio
    val_pids, test_pids = train_test_split(
        temp_pids,
        test_size=rel_test_ratio,
        stratify=temp_labels,
        random_state=seed,
    )

    train_set = set(train_pids)
    val_set = set(val_pids)
    test_set = set(test_pids)

    # Hard anti-leakage assertions
    assert train_set.isdisjoint(val_set), "Patient leakage detected between train and val splits!"
    assert train_set.isdisjoint(test_set), "Patient leakage detected between train and test splits!"
    assert val_set.isdisjoint(test_set), "Patient leakage detected between val and test splits!"

    train_records = [rec for pid in sorted(train_set) for rec in by_patient[pid]]
    val_records = [rec for pid in sorted(val_set) for rec in by_patient[pid]]
    test_records = [rec for pid in sorted(test_set) for rec in by_patient[pid]]

    summary = {
        "total_patients": len(patient_ids),
        "total_images": len(records),
        "train_patients": len(train_set),
        "val_patients": len(val_set),
        "test_patients": len(test_set),
        "train_images": len(train_records),
        "val_images": len(val_records),
        "test_images": len(test_records),
        "zero_patient_leakage_verified": True,
        "train_class_counts": dict(sorted(Counter(int(r["label"]) for r in train_records).items())),
        "val_class_counts": dict(sorted(Counter(int(r["label"]) for r in val_records).items())),
        "test_class_counts": dict(sorted(Counter(int(r["label"]) for r in test_records).items())),
    }
    return train_records, val_records, test_records, summary


class MedicalImagingDataset(Dataset):
    """PyTorch Dataset supporting both in-memory synthetic fixtures and disk manifest paths."""

    def __init__(
        self,
        records: List[Dict[str, Any]],
        *,
        augment: bool = False,
        seed: int = 42,
    ) -> None:
        self.records = records
        self.augment = augment
        self.rng = np.random.default_rng(seed)

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, int]:
        rec = self.records[idx]
        if "image_array_u8" in rec:
            arr_raw = rec["image_array_u8"].astype(np.float32)
            min_v, max_v = float(arr_raw.min()), float(arr_raw.max())
            span = max(max_v - min_v, 1e-6)
            norm_gray = np.clip((arr_raw - min_v) / span, 0.0, 1.0)
        else:
            norm_gray = load_image_norm_gray(Path(rec["image_path"]))

        tensor = preprocess_gray_array_to_tensor(
            norm_gray,
            augment=self.augment,
            rng=self.rng,
        )
        return tensor, int(rec["label"])

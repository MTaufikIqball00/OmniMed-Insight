"""
Post-Hoc Multiclass Probability Calibration & Checkpoint Export for DenseNet-121

Fits Temperature Scaling and Multiclass Platt Scaling EXCLUSIVELY on validation logits
(`val_logits.npz`), selects the winning calibrator strictly on validation NLL/ECE,
evaluates all methods on held-out test logits (`test_logits.npz`), exports a verified
calibrated checkpoint (`densenet121_cxr_calibrated.pt`), saves `calibration_metrics.json`,
and updates `checkpoint_manifest.json` with exact SHA-256 digests.

Usage:
    python ai-service-python/imaging_pipeline/calibrate_densenet.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np
import torch

AI_SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(AI_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE_ROOT))

from app.calibration import (  # noqa: E402
    MulticlassPlattScaler,
    TemperatureScaler,
    compute_ece,
    compute_multiclass_metrics,
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _unrounded_nll_and_ece(y_true: np.ndarray, probs: np.ndarray) -> Tuple[float, float, float]:
    n, c = probs.shape
    row_sums = np.sum(probs, axis=1, keepdims=True)
    probs_norm = np.where(row_sums > 0, probs / np.maximum(row_sums, 1e-12), 1.0 / c)
    nll = float(-np.mean(np.log(np.clip(probs_norm[np.arange(n), y_true], 1e-12, 1.0))))
    one_hot = np.eye(c, dtype=np.float64)[y_true]
    brier = float(np.mean((probs_norm - one_hot) ** 2))
    ece, _ = compute_ece(y_true, probs_norm, n_bins=10, multiclass=True)
    return nll, float(ece), brier


def run_calibration(args: argparse.Namespace) -> Dict[str, Any]:
    models_dir = Path(args.models_dir).resolve()
    manifest_path = models_dir / "checkpoint_manifest.json"
    manifest: Dict[str, Any] = {}
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    ckpt_name = args.checkpoint
    if not ckpt_name and isinstance(manifest.get("uncalibrated_checkpoint"), dict):
        ckpt_name = str(manifest["uncalibrated_checkpoint"].get("filename") or "")
    if not ckpt_name:
        ckpt_name = "densenet121_cxr_synthetic_benchmark.pt"

    base_ckpt_path = (models_dir / ckpt_name).resolve()
    val_logits_path = (models_dir / args.val_logits).resolve()
    test_logits_path = (models_dir / args.test_logits).resolve()
    output_ckpt_path = (models_dir / args.output_checkpoint).resolve()
    metrics_json_path = (models_dir / "calibration_metrics.json").resolve()

    if not base_ckpt_path.is_file():
        raise FileNotFoundError(f"Base checkpoint not found: {base_ckpt_path}")
    if not val_logits_path.is_file():
        raise FileNotFoundError(f"Validation logits not found: {val_logits_path}")
    if not test_logits_path.is_file():
        raise FileNotFoundError(f"Test logits not found: {test_logits_path}")

    val_data = np.load(val_logits_path)
    val_logits = np.asarray(val_data["logits"], dtype=np.float64)
    val_labels = np.asarray(val_data["labels"], dtype=np.int64).ravel()

    test_data = np.load(test_logits_path)
    test_logits = np.asarray(test_data["logits"], dtype=np.float64)
    test_labels = np.asarray(test_data["labels"], dtype=np.int64).ravel()

    # 1. Fit calibrators EXCLUSIVELY on validation logits/labels
    identity_scaler = TemperatureScaler(temperature=1.0)
    temp_scaler = TemperatureScaler().fit(val_logits, val_labels)
    platt_scaler = MulticlassPlattScaler().fit(val_logits, val_labels)

    val_probs_uncal = identity_scaler.predict_proba(val_logits)
    val_probs_temp = temp_scaler.predict_proba(val_logits)
    val_probs_platt = platt_scaler.predict_proba(val_logits)

    val_comparison = {
        "NONE_UNCALIBRATED": compute_multiclass_metrics(val_labels, val_probs_uncal),
        "TEMPERATURE_SCALING": compute_multiclass_metrics(val_labels, val_probs_temp),
        "PLATT_SCALING": compute_multiclass_metrics(val_labels, val_probs_platt),
    }

    # Tie-free winner selection strictly on validation (NLL + 0.5*ECE, tie-break NLL, Brier)
    temp_val_nll, temp_val_ece, temp_val_brier = _unrounded_nll_and_ece(val_labels, val_probs_temp)
    platt_val_nll, platt_val_ece, platt_val_brier = _unrounded_nll_and_ece(val_labels, val_probs_platt)

    temp_score = (temp_val_nll + 0.5 * temp_val_ece, temp_val_nll, temp_val_brier)
    platt_score = (platt_val_nll + 0.5 * platt_val_ece, platt_val_nll, platt_val_brier)

    if temp_score <= platt_score:
        winner_method = "TEMPERATURE_SCALING"
        winner_scaler: Any = temp_scaler
    else:
        winner_method = "PLATT_SCALING"
        winner_scaler = platt_scaler

    # 2. Evaluate uncalibrated vs Temperature Scaling vs Platt Scaling strictly on held-out test logits
    test_probs_uncal = identity_scaler.predict_proba(test_logits)
    test_probs_temp = temp_scaler.predict_proba(test_logits)
    test_probs_platt = platt_scaler.predict_proba(test_logits)

    test_comparison = {
        "NONE_UNCALIBRATED": compute_multiclass_metrics(test_labels, test_probs_uncal),
        "TEMPERATURE_SCALING": compute_multiclass_metrics(test_labels, test_probs_temp),
        "PLATT_SCALING": compute_multiclass_metrics(test_labels, test_probs_platt),
    }
    selected_test_metrics = dict(test_comparison[winner_method])

    calibration_validated = bool(
        selected_test_metrics["ece_score"] is not None
        and np.isfinite(selected_test_metrics["ece_score"])
        and selected_test_metrics["ece_score"] < 0.15
    )

    # 3. Export calibrated checkpoint with embedded calibrator state & verified SHA-256
    base_payload = torch.load(base_ckpt_path, map_location="cpu")
    if not isinstance(base_payload, dict) or "state_dict" not in base_payload:
        raise ValueError(f"Expected structured omnimed-checkpoint-v2 dict in {base_ckpt_path}")

    training_prov = base_payload.get("training_provenance") or {}
    data_provenance = str(
        training_prov.get("dataset_type")
        or manifest.get("checkpoint_data_provenance")
        or ("SYNTHETIC_BENCHMARK_FIXTURE" if training_prov.get("is_synthetic_benchmark") else "EXTERNAL_CLINICAL_COHORT")
    )

    calibration_payload = {
        "method": winner_method,
        "params": winner_scaler.to_dict(),
        "ece_score": selected_test_metrics["ece_score"],
        "brier_score": selected_test_metrics["brier_score"],
        "nll_score": selected_test_metrics["nll_score"],
        "accuracy": selected_test_metrics["accuracy"],
        "reliability_bins": selected_test_metrics["reliability_bins"],
        "calibration_validated": calibration_validated,
    }

    calibrated_payload = dict(base_payload)
    calibrated_payload["calibration"] = calibration_payload
    torch.save(calibrated_payload, output_ckpt_path)
    calibrated_sha256 = sha256_file(output_ckpt_path)

    # 4. Save calibration_metrics.json (sidecar + full val/test benchmark)
    metrics_doc: Dict[str, Any] = {
        "checkpoint_filename": output_ckpt_path.name,
        "checkpoint_sha256": calibrated_sha256,
        "source_uncalibrated_checkpoint": base_ckpt_path.name,
        "checkpoint_data_provenance": data_provenance,
        "best_method": winner_method,
        "method": winner_method,
        "calibration_method": winner_method,
        "calibration_validated": calibration_validated,
        "params": winner_scaler.to_dict(),
        "ece_score": selected_test_metrics["ece_score"],
        "brier_score": selected_test_metrics["brier_score"],
        "nll_score": selected_test_metrics["nll_score"],
        "accuracy": selected_test_metrics["accuracy"],
        "reliability_bins": selected_test_metrics["reliability_bins"],
        "val_samples": int(len(val_labels)),
        "test_samples": int(len(test_labels)),
        "val_comparison": val_comparison,
        "test_comparison": test_comparison,
        "selected_test_metrics": selected_test_metrics,
    }
    metrics_json_path.write_text(json.dumps(metrics_doc, indent=2), encoding="utf-8")

    # 5. Update checkpoint_manifest.json with exact calibrated checkpoint SHA-256
    manifest["calibrated_checkpoint"] = {
        "filename": output_ckpt_path.name,
        "path": str(output_ckpt_path),
        "sha256": calibrated_sha256,
        "size_bytes": output_ckpt_path.stat().st_size,
        "calibration_method": winner_method,
        "calibration_validated": calibration_validated,
        "params": winner_scaler.to_dict(),
        "ece_score": selected_test_metrics["ece_score"],
        "brier_score": selected_test_metrics["brier_score"],
        "nll_score": selected_test_metrics["nll_score"],
        "test_accuracy": selected_test_metrics["accuracy"],
    }
    manifest["calibration_metrics_json"] = {
        "filename": metrics_json_path.name,
        "sha256": sha256_file(metrics_json_path),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(
        f"Imaging Calibration Complete:\n"
        f"  Winner (selected on val): {winner_method} (params={winner_scaler.to_dict()})\n"
        f"  Calibrated checkpoint: {output_ckpt_path}\n"
        f"  SHA-256: {calibrated_sha256}\n"
        f"  Held-out Test Comparison ({len(test_labels)} images):\n"
        f"    NONE_UNCALIBRATED:   acc={test_comparison['NONE_UNCALIBRATED']['accuracy']:.4f}, "
        f"ece={test_comparison['NONE_UNCALIBRATED']['ece_score']:.4f}, "
        f"brier={test_comparison['NONE_UNCALIBRATED']['brier_score']:.4f}, "
        f"nll={test_comparison['NONE_UNCALIBRATED']['nll_score']:.4f}\n"
        f"    TEMPERATURE_SCALING: acc={test_comparison['TEMPERATURE_SCALING']['accuracy']:.4f}, "
        f"ece={test_comparison['TEMPERATURE_SCALING']['ece_score']:.4f}, "
        f"brier={test_comparison['TEMPERATURE_SCALING']['brier_score']:.4f}, "
        f"nll={test_comparison['TEMPERATURE_SCALING']['nll_score']:.4f}\n"
        f"    PLATT_SCALING:       acc={test_comparison['PLATT_SCALING']['accuracy']:.4f}, "
        f"ece={test_comparison['PLATT_SCALING']['ece_score']:.4f}, "
        f"brier={test_comparison['PLATT_SCALING']['brier_score']:.4f}, "
        f"nll={test_comparison['PLATT_SCALING']['nll_score']:.4f}\n"
        f"  calibration_validated={calibration_validated}"
    )
    return metrics_doc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calibrate DenseNet-121 imaging checkpoint on validation logits.")
    parser.add_argument(
        "--models-dir",
        type=str,
        default=str(AI_SERVICE_ROOT / "models" / "imaging"),
    )
    parser.add_argument("--checkpoint", type=str, default="densenet121_cxr_synthetic_benchmark.pt")
    parser.add_argument("--output-checkpoint", type=str, default="densenet121_cxr_calibrated.pt")
    parser.add_argument("--val-logits", type=str, default="val_logits.npz")
    parser.add_argument("--test-logits", type=str, default="test_logits.npz")
    return parser.parse_args()


if __name__ == "__main__":
    run_calibration(parse_args())

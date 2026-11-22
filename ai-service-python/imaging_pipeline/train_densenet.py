"""
Reproducible DenseNet-121 training and checkpoint export pipeline for OmniMed Insight.

Supports:
1. `--manifest-csv`: Authorized external clinical radiology cohorts (`patient_id,image_path,label,modality`).
2. `--synthetic-benchmark`: Deterministic 4-class CXR fixture (`SYNTHETIC_BENCHMARK_FIXTURE`)
   for reproducible pipeline, calibration, and HiResCAM verification without fabricating
   clinical data or bypassing external dataset DUAs.

Usage:
    python ai-service-python/imaging_pipeline/train_densenet.py --synthetic-benchmark
    python ai-service-python/imaging_pipeline/train_densenet.py --manifest-csv path/to/manifest.csv --modality CXR
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader
from torchvision.models import densenet121

AI_SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(AI_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE_ROOT))

from imaging_pipeline.dataset import (  # noqa: E402
    MODALITY_CLASS_CODES,
    MedicalImagingDataset,
    build_synthetic_benchmark_records,
    load_manifest_records,
    patient_level_stratified_split,
)


def set_deterministic_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def build_densenet121_4class(seed: int) -> nn.Module:
    set_deterministic_seed(seed)
    model = densenet121(weights=None)
    in_features = model.classifier.in_features
    model.classifier = nn.Linear(in_features, 4)

    for name, param in model.named_parameters():
        if "weight" in name and param.ndim >= 2:
            nn.init.kaiming_normal_(param, mode="fan_in", nonlinearity="relu")
        elif "weight" in name and param.ndim == 1:
            nn.init.ones_(param)
        elif "bias" in name:
            nn.init.zeros_(param)
    return model


def resolve_device(device_pref: str) -> torch.device:
    pref = device_pref.lower().strip()
    if pref == "cpu":
        return torch.device("cpu")
    if pref == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA requested via --device cuda, but torch.cuda.is_available() is False.")
        return torch.device("cuda:0")
    return torch.device("cuda:0" if torch.cuda.is_available() else "cpu")


def evaluate_logits(
    model: nn.Module,
    loader: DataLoader,
    device: torch.device,
) -> Tuple[np.ndarray, np.ndarray, float, float]:
    model.eval()
    all_logits: List[np.ndarray] = []
    all_labels: List[np.ndarray] = []
    total_loss = 0.0
    total_count = 0

    with torch.no_grad():
        for inputs, targets in loader:
            inputs = inputs.to(device)
            targets = targets.to(device, dtype=torch.long)
            logits = model(inputs)
            loss = F.cross_entropy(logits, targets, reduction="sum")
            total_loss += float(loss.item())
            total_count += int(targets.shape[0])
            all_logits.append(logits.detach().cpu().numpy().astype(np.float32))
            all_labels.append(targets.detach().cpu().numpy().astype(np.int64))

    logits_np = np.concatenate(all_logits, axis=0)
    labels_np = np.concatenate(all_labels, axis=0)
    mean_loss = total_loss / max(1, total_count)
    preds = np.argmax(logits_np, axis=1)
    acc = float(np.mean(preds == labels_np))
    return logits_np, labels_np, mean_loss, acc


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _train_model_loop(
    train_ds: MedicalImagingDataset,
    val_ds: MedicalImagingDataset,
    *,
    device: torch.device,
    epochs: int,
    batch_size: int,
    lr: float,
    weight_decay: float,
    patience: int,
    seed: int,
) -> Tuple[Dict[str, torch.Tensor], int, int, float, List[Dict[str, float]]]:
    set_deterministic_seed(seed)
    train_gen = torch.Generator().manual_seed(seed)
    train_loader = DataLoader(
        train_ds,
        batch_size=batch_size,
        shuffle=True,
        num_workers=0,
        pin_memory=False,
        generator=train_gen,
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=batch_size,
        shuffle=False,
        num_workers=0,
        pin_memory=False,
    )

    model = build_densenet121_4class(seed=seed).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=max(1, epochs), eta_min=1e-6
    )

    best_val_loss = float("inf")
    best_epoch = 0
    best_state: Optional[Dict[str, torch.Tensor]] = None
    no_improve = 0
    history: List[Dict[str, float]] = []

    for epoch in range(1, epochs + 1):
        model.train()
        running_loss = 0.0
        running_correct = 0
        seen = 0

        for inputs, targets in train_loader:
            inputs = inputs.to(device)
            targets = targets.to(device, dtype=torch.long)
            optimizer.zero_grad(set_to_none=True)
            logits = model(inputs)
            loss = F.cross_entropy(logits, targets)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=2.0)
            optimizer.step()

            batch_n = int(targets.shape[0])
            running_loss += float(loss.item()) * batch_n
            running_correct += int((torch.argmax(logits, dim=1) == targets).sum().item())
            seen += batch_n

        scheduler.step()
        train_loss = running_loss / max(1, seen)
        train_acc = running_correct / max(1, seen)

        _, _, val_loss, val_acc = evaluate_logits(model, val_loader, device)
        history.append(
            {
                "epoch": epoch,
                "train_loss": round(train_loss, 5),
                "train_acc": round(train_acc, 4),
                "val_loss": round(val_loss, 5),
                "val_acc": round(val_acc, 4),
                "lr": round(float(optimizer.param_groups[0]["lr"]), 7),
            }
        )
        print(
            f"[Epoch {epoch:02d}/{epochs:02d}] "
            f"train_loss={train_loss:.4f} train_acc={train_acc:.4f} | "
            f"val_loss={val_loss:.4f} val_acc={val_acc:.4f}",
            flush=True,
        )

        if val_loss < best_val_loss - 1e-4:
            best_val_loss = val_loss
            best_epoch = epoch
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            no_improve = 0
        else:
            no_improve += 1
            if no_improve >= patience:
                print(
                    f"Early stopping triggered at epoch {epoch} (best epoch={best_epoch}).",
                    flush=True,
                )
                break

    if best_state is None:
        best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}

    return best_state, len(history), best_epoch, best_val_loss, history


def run_training_pipeline(args: argparse.Namespace) -> Dict[str, Any]:
    t0 = time.perf_counter()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.synthetic_benchmark:
        modality = "CXR"
        dataset_type = "SYNTHETIC_BENCHMARK_FIXTURE"
        is_synthetic = True
        records = build_synthetic_benchmark_records(
            num_patients=args.num_patients,
            views_per_patient=args.views_per_patient,
            seed=args.seed,
        )
        ckpt_filename = "densenet121_cxr_synthetic_benchmark.pt"
        model_version = "densenet121-cxr-synth-bench-v1"
        manifest_ref: Optional[str] = None
    elif args.manifest_csv:
        modality = args.modality.upper()
        dataset_type = "EXTERNAL_CLINICAL_COHORT"
        is_synthetic = False
        records = load_manifest_records(Path(args.manifest_csv), modality=modality)
        ckpt_filename = f"densenet121_{modality.lower()}_cohort.pt"
        model_version = f"densenet121-{modality.lower()}-cohort-v1"
        manifest_ref = str(Path(args.manifest_csv).resolve())
    else:
        raise ValueError("Specify either --synthetic-benchmark or --manifest-csv <path>.")

    class_codes = MODALITY_CLASS_CODES[modality]
    train_records, val_records, test_records, split_summary = patient_level_stratified_split(
        records, seed=args.seed
    )
    print(
        f"Dataset mode={dataset_type} modality={modality} | "
        f"patients(train/val/test)={split_summary['train_patients']}/"
        f"{split_summary['val_patients']}/{split_summary['test_patients']} | "
        f"images={split_summary['train_images']}/{split_summary['val_images']}/{split_summary['test_images']} | "
        f"zero_patient_leakage_verified={split_summary['zero_patient_leakage_verified']}",
        flush=True,
    )

    train_ds = MedicalImagingDataset(train_records, augment=True, seed=args.seed)
    val_ds = MedicalImagingDataset(val_records, augment=False, seed=args.seed)
    test_ds = MedicalImagingDataset(test_records, augment=False, seed=args.seed)

    device = resolve_device(args.device)
    if device.type == "cuda":
        torch.backends.cudnn.benchmark = True
    print(
        f"Training DenseNet-121 on device={device} (batch_size={args.batch_size}, num_workers=0)",
        flush=True,
    )

    try:
        best_state, epochs_trained, best_epoch, best_val_loss, history = _train_model_loop(
            train_ds,
            val_ds,
            device=device,
            epochs=args.epochs,
            batch_size=args.batch_size,
            lr=args.lr,
            weight_decay=args.weight_decay,
            patience=args.patience,
            seed=args.seed,
        )
    except RuntimeError as exc:
        if device.type == "cuda" and "out of memory" in str(exc).lower():
            print("CUDA OOM encountered on GPU; releasing VRAM and falling back safely to CPU.")
            torch.cuda.empty_cache()
            device = torch.device("cpu")
            best_state, epochs_trained, best_epoch, best_val_loss, history = _train_model_loop(
                train_ds,
                val_ds,
                device=device,
                epochs=args.epochs,
                batch_size=args.batch_size,
                lr=args.lr,
                weight_decay=args.weight_decay,
                patience=args.patience,
                seed=args.seed,
            )
        else:
            raise

    # Evaluate final best checkpoint strictly on val and held-out test splits
    eval_model = build_densenet121_4class(seed=args.seed)
    eval_model.load_state_dict(best_state, strict=True)
    eval_model.to(device)
    eval_model.eval()

    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False, num_workers=0)
    test_loader = DataLoader(test_ds, batch_size=args.batch_size, shuffle=False, num_workers=0)

    val_logits, val_labels, val_nll, val_acc = evaluate_logits(eval_model, val_loader, device)
    test_logits, test_labels, test_nll, test_acc = evaluate_logits(eval_model, test_loader, device)

    # Verify finite bounded logits on dummy input and test set
    with torch.no_grad():
        dummy_out = eval_model(torch.zeros((1, 3, 224, 224), device=device))
    assert torch.isfinite(dummy_out).all(), "Dummy forward pass produced non-finite logits!"
    assert float(torch.max(torch.abs(dummy_out)).item()) < 100.0, "Dummy forward logits exceeded bound 100.0!"
    assert np.isfinite(val_logits).all() and np.isfinite(test_logits).all()

    max_abs_test_logit = float(np.max(np.abs(test_logits)))
    assert max_abs_test_logit < 100.0, f"Test logits exceeded safety bound: {max_abs_test_logit}"

    val_logits_path = output_dir / "val_logits.npz"
    test_logits_path = output_dir / "test_logits.npz"
    np.savez(val_logits_path, logits=val_logits, labels=val_labels)
    np.savez(test_logits_path, logits=test_logits, labels=test_labels)

    training_provenance: Dict[str, Any] = {
        "dataset_type": dataset_type,
        "is_synthetic_benchmark": is_synthetic,
        "manifest_csv": manifest_ref,
        "split_sizes": {
            "train_patients": split_summary["train_patients"],
            "val_patients": split_summary["val_patients"],
            "test_patients": split_summary["test_patients"],
            "train_images": split_summary["train_images"],
            "val_images": split_summary["val_images"],
            "test_images": split_summary["test_images"],
        },
        "train_class_counts": split_summary["train_class_counts"],
        "val_class_counts": split_summary["val_class_counts"],
        "test_class_counts": split_summary["test_class_counts"],
        "zero_patient_leakage_verified": True,
        "seed": args.seed,
        "epochs_requested": args.epochs,
        "epochs_trained": epochs_trained,
        "best_epoch": best_epoch,
        "best_val_loss": round(float(best_val_loss), 6),
        "val_accuracy": round(float(val_acc), 4),
        "val_nll": round(float(val_nll), 4),
        "test_accuracy": round(float(test_acc), 4),
        "test_nll": round(float(test_nll), 4),
        "max_abs_test_logit": round(max_abs_test_logit, 4),
        "train_device": str(device),
        "duration_seconds": round(time.perf_counter() - t0, 2),
        "history": history,
    }

    checkpoint_payload = {
        "format_version": "omnimed-checkpoint-v2",
        "architecture": "densenet121",
        "modality": modality,
        "num_classes": 4,
        "class_codes": class_codes,
        "model_version": model_version,
        "state_dict": copy.deepcopy(best_state),
        "training_provenance": training_provenance,
        "calibration": None,
    }

    ckpt_path = output_dir / ckpt_filename
    torch.save(checkpoint_payload, ckpt_path)
    ckpt_sha256 = sha256_file(ckpt_path)

    manifest_data: Dict[str, Any] = {
        "format_version": "omnimed-checkpoint-v2",
        "architecture": "densenet121",
        "modality": modality,
        "num_classes": 4,
        "class_codes": class_codes,
        "model_version": model_version,
        "checkpoint_data_provenance": dataset_type,
        "uncalibrated_checkpoint": {
            "filename": ckpt_filename,
            "path": str(ckpt_path),
            "sha256": ckpt_sha256,
            "size_bytes": ckpt_path.stat().st_size,
        },
        "calibrated_checkpoint": None,
        "val_logits_npz": {
            "filename": val_logits_path.name,
            "sha256": sha256_file(val_logits_path),
            "num_samples": int(val_labels.shape[0]),
        },
        "test_logits_npz": {
            "filename": test_logits_path.name,
            "sha256": sha256_file(test_logits_path),
            "num_samples": int(test_labels.shape[0]),
        },
        "training_provenance": training_provenance,
    }

    manifest_path = output_dir / "checkpoint_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    print(
        f"Export complete in {training_provenance['duration_seconds']}s:\n"
        f"  Checkpoint: {ckpt_path} (sha256={ckpt_sha256[:16]}...)\n"
        f"  Val accuracy={val_acc:.4f}, Val NLL={val_nll:.4f}\n"
        f"  Test accuracy={test_acc:.4f}, Test NLL={test_nll:.4f}, max|logit|={max_abs_test_logit:.4f}\n"
        f"  Manifest: {manifest_path}"
    )
    return manifest_data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OmniMed Insight DenseNet-121 Reproducible Training & Export Pipeline"
    )
    mode_grp = parser.add_mutually_exclusive_group(required=True)
    mode_grp.add_argument(
        "--synthetic-benchmark",
        action="store_true",
        help="Train on deterministic 4-class CXR synthetic benchmark (SYNTHETIC_BENCHMARK_FIXTURE).",
    )
    mode_grp.add_argument(
        "--manifest-csv",
        type=str,
        default=None,
        help="Path to authorized clinical cohort CSV (patient_id,image_path,label,modality).",
    )
    parser.add_argument("--modality", type=str, default="CXR", choices=["CXR", "MRI"])
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(AI_SERVICE_ROOT / "models" / "imaging"),
    )
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=8e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--patience", type=int, default=4)
    parser.add_argument("--num-patients", type=int, default=240)
    parser.add_argument("--views-per-patient", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", type=str, default="auto", choices=["auto", "cpu", "cuda"])
    return parser.parse_args()


if __name__ == "__main__":
    run_training_pipeline(parse_args())

import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from PIL import Image
import pytest

os.environ["INTERNAL_SERVICE_TOKEN"] = "test-internal-token-32-chars-minimum-12345"

from app.main import app
from app.synthetic_fixtures import generate_synthetic_cxr, generate_synthetic_mri

client = TestClient(app)
AUTH_HEADERS = {"X-Internal-Service-Token": os.environ["INTERNAL_SERVICE_TOKEN"]}


def test_health_endpoint_discloses_capabilities_and_status() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["model_id"] == "omnimed-densenet121-xai"
    assert data["calibration_status"] == "RESEARCH_UNVERIFIED"
    assert "CXR" in data["supported_modalities"]
    assert "MRI" in data["supported_modalities"]
    assert "GRAD_CAM" in data["supported_xai_methods"]


def test_internal_endpoints_reject_missing_or_wrong_token() -> None:
    resp_missing = client.get("/internal/v1/models")
    assert resp_missing.status_code == 401

    resp_wrong = client.get(
        "/internal/v1/models",
        headers={"X-Internal-Service-Token": "wrong-token"},
    )
    assert resp_wrong.status_code == 401


def test_rejects_corrupted_or_non_image_upload(tmp_path: Path) -> None:
    bad_file = tmp_path / "malicious.png"
    bad_file.write_bytes(b"<!DOCTYPE html><html>not a medical image</html>")
    out_overlay = tmp_path / "overlay.png"

    resp = client.post(
        "/internal/v1/analyze",
        headers=AUTH_HEADERS,
        json={
            "job_id": "job-bad-001",
            "image_id": "img-bad-001",
            "image_path": str(bad_file),
            "output_overlay_path": str(out_overlay),
            "modality": "CXR",
            "body_part": "CHEST",
            "xai_method": "GRAD_CAM",
        },
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "UNSUPPORTED_FILE_SIGNATURE"


def test_rejects_blank_zero_contrast_image(tmp_path: Path) -> None:
    blank_file = tmp_path / "blank.png"
    Image.new("L", (256, 256), color=128).save(blank_file, format="PNG")
    out_overlay = tmp_path / "overlay_blank.png"

    resp = client.post(
        "/internal/v1/analyze",
        headers=AUTH_HEADERS,
        json={
            "job_id": "job-blank-001",
            "image_id": "img-blank-001",
            "image_path": str(blank_file),
            "output_overlay_path": str(out_overlay),
            "modality": "CXR",
            "body_part": "CHEST",
            "xai_method": "GRAD_CAM",
        },
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "LOW_DYNAMIC_RANGE_OR_BLANK"


def test_gradcam_and_occlusion_analysis_preserves_source_and_creates_overlay(tmp_path: Path) -> None:
    cxr_path = tmp_path / "synthetic_cxr.png"
    orig_sha, w, h = generate_synthetic_cxr(cxr_path, focal_opacity=True)
    overlay_path = tmp_path / "derived_gradcam.png"

    resp = client.post(
        "/internal/v1/analyze",
        headers=AUTH_HEADERS,
        json={
            "job_id": "job-cxr-101",
            "image_id": "img-cxr-101",
            "image_path": str(cxr_path),
            "output_overlay_path": str(overlay_path),
            "modality": "CXR",
            "body_part": "CHEST",
            "xai_method": "GRAD_CAM_PLUS_OCCLUSION",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "COMPLETED"
    assert body["calibration_status"] == "RESEARCH_UNVERIFIED"
    assert body["image_metadata"]["sha256_digest"] == orig_sha
    assert body["image_metadata"]["width"] == w
    assert body["image_metadata"]["height"] == h

    # Verify original file was never mutated
    assert hashlib.sha256(cxr_path.read_bytes()).hexdigest() == orig_sha
    # Verify derived Grad-CAM overlay file exists, matches dimensions, and keeps background transparent
    assert overlay_path.is_file()
    import numpy as np
    with Image.open(overlay_path) as ov:
        assert ov.size == (w, h)
        assert ov.mode == "RGBA"
        ov_arr = np.asarray(ov)
        transparent_ratio = float(np.mean(ov_arr[:, :, 3] == 0))
        assert transparent_ratio >= 0.45, f"Overlay obscures too much scan (transparent={transparent_ratio:.2%})"

    # Verify bounded logits (no BatchNorm variance explosion) and non-negative entropy
    assert all(abs(c["logit"]) < 50.0 for c in body["class_scores"])
    assert body["shannon_entropy"] >= 0.0
    assert not str(body["shannon_entropy"]).startswith("-0")
    assert body["predicted_class_code"] == "CXR_PARENCHYMAL_OPACITY"

    # Verify class probabilities sum to ~1.0 and XAI warnings exist
    prob_sum = sum(c["probability"] for c in body["class_scores"])
    assert pytest.approx(prob_sum, abs=1e-2) == 1.0
    assert "NOT proof" in body["xai"]["clinical_warning"]
    assert len(body["xai"]["top_regions"]) == 4


def test_normal_cxr_avoids_massive_red_false_alarm(tmp_path: Path) -> None:
    normal_path = tmp_path / "normal_cxr.png"
    generate_synthetic_cxr(normal_path, focal_opacity=False)
    overlay_path = tmp_path / "normal_gradcam.png"

    resp = client.post(
        "/internal/v1/analyze",
        headers=AUTH_HEADERS,
        json={
            "job_id": "job-cxr-norm-001",
            "image_id": "img-cxr-norm-001",
            "image_path": str(normal_path),
            "output_overlay_path": str(overlay_path),
            "modality": "CXR",
            "body_part": "CHEST",
            "xai_method": "GRAD_CAM",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["predicted_class_code"] == "CXR_NO_ACUTE_FINDING"
    assert body["xai"]["active_area_ratio"] <= 0.10


def test_mri_gradcam_inference(tmp_path: Path) -> None:
    mri_path = tmp_path / "synthetic_mri.png"
    orig_sha, _, _ = generate_synthetic_mri(mri_path)
    overlay_path = tmp_path / "mri_gradcam.png"

    resp = client.post(
        "/internal/v1/analyze",
        headers=AUTH_HEADERS,
        json={
            "job_id": "job-mri-202",
            "image_id": "img-mri-202",
            "image_path": str(mri_path),
            "output_overlay_path": str(overlay_path),
            "modality": "MRI",
            "body_part": "BRAIN",
            "xai_method": "GRAD_CAM",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["modality"] == "MRI"
    assert body["image_metadata"]["sha256_digest"] == orig_sha
    assert overlay_path.is_file()
    assert all(abs(c["logit"]) < 50.0 for c in body["class_scores"])
    assert body["predicted_class_code"] == "MRI_FLAIR_HYPERINTENSITY"


def _build_analyze_req(image_path: Path, overlay_path: Path, job_id: str) -> "AnalyzeImageRequest":
    from app.schemas import AnalyzeImageRequest

    return AnalyzeImageRequest(
        job_id=job_id,
        image_id=f"img-{job_id}",
        image_path=str(image_path),
        output_overlay_path=str(overlay_path),
        modality="CXR",
        body_part="CHEST",
        xai_method="GRAD_CAM",
    )


def test_loads_uncalibrated_synthetic_benchmark_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import numpy as np
    from app.xai_engine import MedicalDenseNetXaiEngine

    ckpt_path = (
        Path(__file__).resolve().parents[1]
        / "models"
        / "imaging"
        / "densenet121_cxr_synthetic_benchmark.pt"
    )
    assert ckpt_path.is_file(), f"Missing trained benchmark checkpoint: {ckpt_path}"
    expected_sha = hashlib.sha256(ckpt_path.read_bytes()).hexdigest()

    monkeypatch.setenv("MODEL_WEIGHTS_PATH", str(ckpt_path))
    monkeypatch.delenv("MODEL_WEIGHTS_EXPECTED_SHA256", raising=False)

    eng = MedicalDenseNetXaiEngine()
    assert eng.calibration_status == "CUSTOM_CHECKPOINT"
    assert eng.calibration_method == "NONE_UNCALIBRATED"
    assert eng.ece_score is None
    assert eng.checkpoint_sha256 == expected_sha
    assert eng.checkpoint_data_provenance == "SYNTHETIC_BENCHMARK_FIXTURE"
    assert eng.reliability_bins == []
    assert eng.checkpoint_load_error is None

    cxr_path = tmp_path / "cxr_custom.png"
    generate_synthetic_cxr(cxr_path, focal_opacity=True)
    overlay_path = tmp_path / "overlay_custom.png"
    res = eng.analyze(_build_analyze_req(cxr_path, overlay_path, "job-custom-ckpt-01"))

    assert res.calibration_status == "CUSTOM_CHECKPOINT"
    assert res.calibration_method == "NONE_UNCALIBRATED"
    assert res.checkpoint_sha256 == expected_sha
    assert res.checkpoint_data_provenance == "SYNTHETIC_BENCHMARK_FIXTURE"
    assert all(abs(c.logit) < 50.0 for c in res.class_scores)
    assert pytest.approx(sum(c.probability for c in res.class_scores), abs=1e-2) == 1.0
    assert overlay_path.is_file()
    with Image.open(overlay_path) as ov:
        ov_arr = np.asarray(ov)
        transparent_ratio = float(np.mean(ov_arr[:, :, 3] == 0))
        assert transparent_ratio >= 0.45


def test_loads_calibrated_synthetic_benchmark_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import numpy as np
    from app.xai_engine import MedicalDenseNetXaiEngine
    from imaging_pipeline.dataset import _render_synthetic_cxr_view

    ckpt_path = (
        Path(__file__).resolve().parents[1]
        / "models"
        / "imaging"
        / "densenet121_cxr_calibrated.pt"
    )
    assert ckpt_path.is_file(), f"Missing calibrated benchmark checkpoint: {ckpt_path}"
    expected_sha = hashlib.sha256(ckpt_path.read_bytes()).hexdigest()

    monkeypatch.setenv("MODEL_WEIGHTS_PATH", str(ckpt_path))
    monkeypatch.setenv("MODEL_WEIGHTS_EXPECTED_SHA256", expected_sha)

    eng = MedicalDenseNetXaiEngine()
    assert eng.calibration_status == "CALIBRATED_CHECKPOINT"
    assert eng.calibration_method in ("TEMPERATURE_SCALING", "PLATT_SCALING")
    assert eng.ece_score is not None and eng.ece_score < 0.05
    assert eng.brier_score is not None
    assert eng.nll_score is not None
    assert len(eng.reliability_bins) > 0
    assert eng.checkpoint_sha256 == expected_sha
    assert eng.checkpoint_data_provenance == "SYNTHETIC_BENCHMARK_FIXTURE"
    assert eng.checkpoint_load_error is None

    # Render an in-distribution synthetic CXR opacity case (patient 999 outside train/val/test)
    arr_u8 = _render_synthetic_cxr_view(patient_idx=999, view_idx=0, label=1, seed=42)
    cxr_path = tmp_path / "cxr_in_dist.png"
    Image.fromarray(arr_u8, mode="L").save(cxr_path, format="PNG")
    overlay_path = tmp_path / "overlay_calibrated.png"

    res = eng.analyze(_build_analyze_req(cxr_path, overlay_path, "job-cal-ckpt-01"))
    assert res.calibration_status == "CALIBRATED_CHECKPOINT"
    assert res.calibration_method in ("TEMPERATURE_SCALING", "PLATT_SCALING")
    assert res.ece_score == eng.ece_score
    assert res.checkpoint_sha256 == expected_sha
    assert res.checkpoint_data_provenance == "SYNTHETIC_BENCHMARK_FIXTURE"
    assert len(res.reliability_bins) == len(eng.reliability_bins)
    assert all(abs(c.logit) < 50.0 for c in res.class_scores)
    assert pytest.approx(sum(c.probability for c in res.class_scores), abs=1e-2) == 1.0
    assert res.predicted_class_code == "CXR_PARENCHYMAL_OPACITY"

    with Image.open(overlay_path) as ov:
        ov_arr = np.asarray(ov)
        transparent_ratio = float(np.mean(ov_arr[:, :, 3] == 0))
        assert transparent_ratio >= 0.45


def test_corrupted_or_mismatched_checkpoint_rolls_back_safely(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import torch
    import torch.nn as nn
    from torchvision.models import densenet121
    from app.xai_engine import MedicalDenseNetXaiEngine

    def _assert_rolled_back(eng: MedicalDenseNetXaiEngine) -> None:
        assert eng.calibration_status == "RESEARCH_UNVERIFIED"
        assert eng.calibration_method == "NONE_UNCALIBRATED"
        assert eng.ece_score is None
        assert eng.checkpoint_sha256 is None
        assert eng.checkpoint_data_provenance == "UNINITIALIZED_RESEARCH_BACKBONE"
        assert eng.reliability_bins == []
        assert eng.checkpoint_load_error is not None

    # 1. Corrupted bytes
    corrupt_path = tmp_path / "corrupt.pt"
    corrupt_path.write_bytes(b"not a valid pytorch zip archive")
    monkeypatch.setenv("MODEL_WEIGHTS_PATH", str(corrupt_path))
    monkeypatch.delenv("MODEL_WEIGHTS_EXPECTED_SHA256", raising=False)
    eng_corrupt = MedicalDenseNetXaiEngine()
    _assert_rolled_back(eng_corrupt)

    # 2. Wrong classifier head shape (10 classes instead of 4)
    wrong_model = densenet121(weights=None)
    wrong_model.classifier = nn.Linear(wrong_model.classifier.in_features, 10)
    wrong_shape_path = tmp_path / "wrong_head.pt"
    torch.save(wrong_model.state_dict(), wrong_shape_path)
    monkeypatch.setenv("MODEL_WEIGHTS_PATH", str(wrong_shape_path))
    eng_shape = MedicalDenseNetXaiEngine()
    _assert_rolled_back(eng_shape)

    # 3. SHA-256 mismatch on valid checkpoint
    valid_ckpt = (
        Path(__file__).resolve().parents[1]
        / "models"
        / "imaging"
        / "densenet121_cxr_calibrated.pt"
    )
    monkeypatch.setenv("MODEL_WEIGHTS_PATH", str(valid_ckpt))
    monkeypatch.setenv("MODEL_WEIGHTS_EXPECTED_SHA256", "0" * 64)
    eng_sha = MedicalDenseNetXaiEngine()
    _assert_rolled_back(eng_sha)

    # Rolled-back engine still serves RESEARCH_UNVERIFIED inference safely
    cxr_path = tmp_path / "fallback_cxr.png"
    generate_synthetic_cxr(cxr_path, focal_opacity=True)
    ov_path = tmp_path / "fallback_ov.png"
    res = eng_sha.analyze(_build_analyze_req(cxr_path, ov_path, "job-fallback-01"))
    assert res.calibration_status == "RESEARCH_UNVERIFIED"
    assert res.predicted_class_code == "CXR_PARENCHYMAL_OPACITY"

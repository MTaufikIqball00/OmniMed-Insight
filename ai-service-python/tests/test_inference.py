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
    # Verify derived Grad-CAM overlay file exists and matches dimensions
    assert overlay_path.is_file()
    with Image.open(overlay_path) as ov:
        assert ov.size == (w, h)
        assert ov.mode == "RGBA"

    # Verify class probabilities sum to ~1.0 and XAI warnings exist
    prob_sum = sum(c["probability"] for c in body["class_scores"])
    assert pytest.approx(prob_sum, abs=1e-2) == 1.0
    assert "NOT proof" in body["xai"]["clinical_warning"]
    assert len(body["xai"]["top_regions"]) == 4


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

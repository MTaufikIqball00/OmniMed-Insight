"""
Unit and Integration Tests for ICU Early Warning Inference & SHAP Explainability Service
"""

import os
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app

TEST_TOKEN = "test-internal-token-32-chars-minimum-12345"
os.environ["INTERNAL_SERVICE_TOKEN"] = TEST_TOKEN

@pytest.fixture
def client():
    return TestClient(app)

def test_icu_requires_internal_service_token(client):
    # Missing token -> 401
    resp = client.post(
        "/internal/v1/icu/predict",
        json={
            "stay_id": "stay-001",
            "patient_id": "pat-001",
            "current_iculos": 12,
            "observations": []
        }
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["error_code"] == "UNAUTHORIZED_INTERNAL_CALLER"

def test_icu_predict_insufficient_data(client):
    resp = client.post(
        "/internal/v1/icu/predict",
        headers={"X-Internal-Service-Token": TEST_TOKEN},
        json={
            "stay_id": "stay-001",
            "patient_id": "pat-001",
            "current_iculos": 12,
            "observations": []
        }
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["risk_tier"] == "INSUFFICIENT_DATA"
    assert data["data_quality_status"] == "INSUFFICIENT_DATA"
    assert "Insufficient observations" in data["clinical_disclaimer"]

def test_icu_predict_with_valid_vitals_and_shap(client):
    observations = [
        {"variable_name": "HR", "value": 115.0, "iculos_hour": 10},
        {"variable_name": "HR", "value": 118.0, "iculos_hour": 12},
        {"variable_name": "SBP", "value": 92.0, "iculos_hour": 12},
        {"variable_name": "DBP", "value": 58.0, "iculos_hour": 12},
        {"variable_name": "MAP", "value": 69.3, "iculos_hour": 12},
        {"variable_name": "Resp", "value": 24.0, "iculos_hour": 12},
        {"variable_name": "Temp", "value": 35.8, "iculos_hour": 12}, # Hypothermia
        {"variable_name": "O2Sat", "value": 94.0, "iculos_hour": 12},
        {"variable_name": "Lactate", "value": 3.2, "iculos_hour": 11}, # Elevated lactate
        {"variable_name": "WBC", "value": 3.4, "iculos_hour": 11},     # Leukopenia
    ]
    resp = client.post(
        "/internal/v1/icu/predict",
        headers={"X-Internal-Service-Token": TEST_TOKEN},
        json={
            "stay_id": "stay-test-001",
            "patient_id": "pat-test-001",
            "current_iculos": 12,
            "observations": observations,
            "age": 72.0,
            "gender": 1.0
        }
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["stay_id"] == "stay-test-001"
    assert data["prediction_horizon"] == "6_to_12_hours"
    assert 0.0 <= data["risk_score"] <= 1.0
    assert data["risk_tier"] in ["LOW", "MODERATE", "HIGH", "CRITICAL"]
    assert len(data["top_shap_attributions"]) > 0
    
    # Check SHAP item structure
    for item in data["top_shap_attributions"]:
        assert "feature" in item
        assert "display_name" in item
        assert "shap_value" in item
        assert item["direction"] in ["INCREASES_RISK", "DECREASES_RISK", "NEUTRAL"]
        assert len(item["clinical_rationale"]) > 5

def test_icu_models_metadata(client):
    resp = client.get(
        "/internal/v1/icu/models",
        headers={"X-Internal-Service-Token": TEST_TOKEN}
    )
    assert resp.status_code == 200
    meta = resp.json()
    assert "model_id" in meta
    assert "test_metrics" in meta
    assert "auroc" in meta["test_metrics"]
    assert len(meta["top_features"]) > 0
    if "cohort_model" in meta:
        cohort = meta["cohort_model"]
        assert cohort["model_id"] == "omnimed-icu-cohort-lgbm-v1"
        assert "top_features" in cohort
        assert len(cohort["top_features"]) > 0


def test_temporal_leakage_exclusion_future_observations(client):
    """Verify that observations recorded after current_iculos (future data) are strictly excluded."""
    base_obs = [
        {"variable_name": "HR", "value": 82.0, "iculos_hour": 6},
        {"variable_name": "SBP", "value": 122.0, "iculos_hour": 6},
        {"variable_name": "DBP", "value": 76.0, "iculos_hour": 6},
        {"variable_name": "MAP", "value": 91.0, "iculos_hour": 6},
        {"variable_name": "Resp", "value": 16.0, "iculos_hour": 6},
        {"variable_name": "Temp", "value": 36.9, "iculos_hour": 6},
        {"variable_name": "O2Sat", "value": 98.0, "iculos_hour": 6},
    ]
    future_obs = base_obs + [
        {"variable_name": "HR", "value": 155.0, "iculos_hour": 10},
        {"variable_name": "Lactate", "value": 8.5, "iculos_hour": 11},
        {"variable_name": "MAP", "value": 45.0, "iculos_hour": 12},
    ]
    r1 = client.post(
        "/internal/v1/icu/predict",
        headers={"X-Internal-Service-Token": TEST_TOKEN},
        json={"stay_id": "s1", "patient_id": "p1", "current_iculos": 6, "observations": base_obs},
    ).json()
    r2 = client.post(
        "/internal/v1/icu/predict",
        headers={"X-Internal-Service-Token": TEST_TOKEN},
        json={"stay_id": "s1", "patient_id": "p1", "current_iculos": 6, "observations": future_obs},
    ).json()
    assert r1["risk_score"] == r2["risk_score"]
    assert r1["vital_signs_summary"]["HR"] == 82.0


def test_calibrated_models_specificity_and_anti_leakage_guarantees(client):
    """Verify that calibrated models enforce non-zero specificity and exclude synthetic/outcome leakage."""
    resp = client.get(
        "/internal/v1/icu/models",
        headers={"X-Internal-Service-Token": TEST_TOKEN},
    )
    assert resp.status_code == 200
    meta = resp.json()

    # PhysioNet 2019 6-12h model guarantees
    ts_metrics = meta["test_metrics"]
    assert ts_metrics["auroc"] > 0.80
    assert ts_metrics["specificity"] > 0.50
    assert ts_metrics["sensitivity"] >= 0.85

    # Archive2 5,000-patient cohort guarantees
    cohort = meta["cohort_model"]
    cohort_lgbm = cohort["test_metrics"]
    assert 0.90 < cohort_lgbm["auroc"] < 0.9999
    assert cohort_lgbm["specificity"] > 0.90
    assert cohort_lgbm["brier_score"] > 0.001

    forbidden = {
        "sofa_score",
        "apache_iv",
        "sirs_criteria",
        "qsofa",
        "pao2_fio2_ratio",
        "lactate_mmol",
        "creatinine",
        "vasopressors_flag",
        "icu_los_hours",
        "readmission_30day",
    }
    feature_set = set(cohort["feature_cols"])
    assert forbidden.isdisjoint(feature_set)


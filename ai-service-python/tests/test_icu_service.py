"""
Unit and Integration Tests for ICU Early Warning Inference & SHAP Explainability Service
"""

import os
import sys
from pathlib import Path
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app, get_icu_engine

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

    # PhysioNet 2019 (~1,000 stays) monotonic & calibrated 6-12h model guarantees
    ts_metrics = meta["test_metrics"]
    assert ts_metrics["auroc"] > 0.72
    assert ts_metrics["specificity"] >= 0.60
    assert ts_metrics["sensitivity"] >= 0.60
    assert ts_metrics["ece_score"] < 0.05
    assert meta["ece_score"] < 0.05
    assert meta["monotone_constraints_active"] is True

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


def _extract_raw_shap_dict(observations, age: float = 72.0, gender: float = 1.0, current_iculos: int = 12):
    eng = get_icu_engine()
    vec, _, _ = eng.compute_features_from_observations(observations, age=age, gender=gender, current_iculos=current_iculos)
    vec_df = pd.DataFrame(vec, columns=eng.feature_cols)
    raw_shap = eng.explainer.shap_values(vec_df, check_additivity=False)
    if isinstance(raw_shap, list):
        shap_vec = raw_shap[1][0] if len(raw_shap) > 1 else raw_shap[0][0]
    elif len(raw_shap.shape) == 3:
        shap_vec = raw_shap[0, :, 1]
    else:
        shap_vec = raw_shap[0]
    return dict(zip(eng.feature_cols, [float(v) for v in shap_vec]))


def test_monotonic_lactate_increase_never_reverses_shap(client):
    """Identical patient at Lactate=1.1 vs 4.5 mmol/L must never decrease risk or reverse Lactate SHAP."""
    base_obs = [
        {"variable_name": "HR", "value": 115.0, "iculos_hour": 10},
        {"variable_name": "HR", "value": 118.0, "iculos_hour": 12},
        {"variable_name": "SBP", "value": 92.0, "iculos_hour": 12},
        {"variable_name": "DBP", "value": 58.0, "iculos_hour": 12},
        {"variable_name": "MAP", "value": 69.3, "iculos_hour": 12},
        {"variable_name": "Resp", "value": 24.0, "iculos_hour": 12},
        {"variable_name": "Temp", "value": 35.8, "iculos_hour": 12},
        {"variable_name": "O2Sat", "value": 94.0, "iculos_hour": 12},
        {"variable_name": "WBC", "value": 3.4, "iculos_hour": 11},
    ]
    obs_low = base_obs + [{"variable_name": "Lactate", "value": 1.1, "iculos_hour": 12}]
    obs_high = base_obs + [{"variable_name": "Lactate", "value": 4.5, "iculos_hour": 12}]

    resp_low = client.post(
        "/internal/v1/icu/predict",
        headers={"X-Internal-Service-Token": TEST_TOKEN},
        json={"stay_id": "mono-lac-low", "patient_id": "pat-mono-1", "current_iculos": 12, "observations": obs_low, "age": 72.0, "gender": 1.0},
    )
    resp_high = client.post(
        "/internal/v1/icu/predict",
        headers={"X-Internal-Service-Token": TEST_TOKEN},
        json={"stay_id": "mono-lac-high", "patient_id": "pat-mono-1", "current_iculos": 12, "observations": obs_high, "age": 72.0, "gender": 1.0},
    )
    assert resp_low.status_code == 200 and resp_high.status_code == 200
    d_low = resp_low.json()
    d_high = resp_high.json()

    assert d_high["risk_score"] >= d_low["risk_score"]

    shap_low = _extract_raw_shap_dict(obs_low)
    shap_high = _extract_raw_shap_dict(obs_high)
    for feat in ["Lactate_latest", "Lactate_roll_max_6h", "Lactate_roll_mean_6h"]:
        assert shap_high[feat] >= shap_low[feat] - 1e-6, f"Monotonicity violated on {feat}: {shap_low[feat]} -> {shap_high[feat]}"

    for item in d_high["top_shap_attributions"]:
        if "Lactate" in item["feature"] and item["feature"] != "Lactate_roll_std_6h":
            assert item["direction"] != "DECREASES_RISK"


def test_monotonic_map_drop_never_reverses_shap(client):
    """Identical patient at MAP=85 vs 55 mmHg must never decrease risk or reverse MAP/hypoperfusion SHAP."""
    base_obs = [
        {"variable_name": "HR", "value": 115.0, "iculos_hour": 10},
        {"variable_name": "HR", "value": 118.0, "iculos_hour": 12},
        {"variable_name": "SBP", "value": 92.0, "iculos_hour": 12},
        {"variable_name": "DBP", "value": 58.0, "iculos_hour": 12},
        {"variable_name": "Resp", "value": 24.0, "iculos_hour": 12},
        {"variable_name": "Temp", "value": 35.8, "iculos_hour": 12},
        {"variable_name": "O2Sat", "value": 94.0, "iculos_hour": 12},
        {"variable_name": "WBC", "value": 3.4, "iculos_hour": 11},
    ]
    obs_high_map = base_obs + [{"variable_name": "MAP", "value": 85.0, "iculos_hour": 12}]
    obs_low_map = base_obs + [{"variable_name": "MAP", "value": 55.0, "iculos_hour": 12}]

    resp_high_map = client.post(
        "/internal/v1/icu/predict",
        headers={"X-Internal-Service-Token": TEST_TOKEN},
        json={"stay_id": "mono-map-high", "patient_id": "pat-mono-2", "current_iculos": 12, "observations": obs_high_map, "age": 72.0, "gender": 1.0},
    )
    resp_low_map = client.post(
        "/internal/v1/icu/predict",
        headers={"X-Internal-Service-Token": TEST_TOKEN},
        json={"stay_id": "mono-map-low", "patient_id": "pat-mono-2", "current_iculos": 12, "observations": obs_low_map, "age": 72.0, "gender": 1.0},
    )
    assert resp_high_map.status_code == 200 and resp_low_map.status_code == 200
    d_high_map = resp_high_map.json()
    d_low_map = resp_low_map.json()

    assert d_low_map["risk_score"] >= d_high_map["risk_score"]

    shap_high_map = _extract_raw_shap_dict(obs_high_map)
    shap_low_map = _extract_raw_shap_dict(obs_low_map)
    for feat in ["MAP_latest", "MAP_roll_min_6h", "MAP_roll_mean_6h", "map_hypoperfusion_depth"]:
        assert shap_low_map[feat] >= shap_high_map[feat] - 1e-6, f"Monotonicity violated on {feat}: {shap_high_map[feat]} -> {shap_low_map[feat]}"

    for item in d_low_map["top_shap_attributions"]:
        if "MAP" in item["feature"] or item["feature"] == "map_hypoperfusion_depth":
            assert item["direction"] != "DECREASES_RISK"


def test_icu_calibration_telemetry_exposed(client):
    """Verify /internal/v1/icu/predict and /internal/v1/icu/models expose calibration & monotonicity telemetry."""
    models_resp = client.get(
        "/internal/v1/icu/models",
        headers={"X-Internal-Service-Token": TEST_TOKEN},
    )
    assert models_resp.status_code == 200
    models_data = models_resp.json()
    assert models_data["calibration_method"] in ("PLATT_SCALING", "ISOTONIC_CALIBRATION")
    assert models_data["ece_score"] is not None and models_data["ece_score"] < 0.05
    assert models_data["calibrated_threshold"] is not None and 0.0 < models_data["calibrated_threshold"] < 1.0
    assert models_data["monotone_constraints_active"] is True
    assert isinstance(models_data["reliability_bins"], list) and len(models_data["reliability_bins"]) > 0

    pred_resp = client.post(
        "/internal/v1/icu/predict",
        headers={"X-Internal-Service-Token": TEST_TOKEN},
        json={
            "stay_id": "stay-cal-telemetry",
            "patient_id": "pat-cal-telemetry",
            "current_iculos": 12,
            "observations": [
                {"variable_name": "HR", "value": 102.0, "iculos_hour": 12},
                {"variable_name": "SBP", "value": 106.0, "iculos_hour": 12},
                {"variable_name": "MAP", "value": 74.0, "iculos_hour": 12},
                {"variable_name": "Resp", "value": 20.0, "iculos_hour": 12},
                {"variable_name": "Temp", "value": 37.8, "iculos_hour": 12},
                {"variable_name": "O2Sat", "value": 96.0, "iculos_hour": 12},
            ],
        },
    )
    assert pred_resp.status_code == 200
    pred_data = pred_resp.json()
    assert pred_data["calibration_method"] in ("PLATT_SCALING", "ISOTONIC_CALIBRATION")
    assert pred_data["ece_score"] is not None and pred_data["ece_score"] < 0.05
    assert pred_data["calibrated_threshold"] is not None and 0.0 < pred_data["calibrated_threshold"] < 1.0
    assert pred_data["monotone_constraints_active"] is True
    assert isinstance(pred_data["reliability_bins"], list) and len(pred_data["reliability_bins"]) > 0
    for b in pred_data["reliability_bins"]:
        assert b["count"] > 0
        assert 0.0 <= b["bin_lower"] < b["bin_upper"] <= 1.0
        assert 0.0 <= b["avg_confidence"] <= 1.0
        assert 0.0 <= b["empirical_accuracy"] <= 1.0
        assert b["gap"] >= 0.0


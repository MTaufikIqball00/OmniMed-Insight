-- OmniMed Insight — ICU Early Warning & Clinical Deterioration Schema

CREATE TABLE IF NOT EXISTS icu_stays (
    id TEXT PRIMARY KEY NOT NULL,
    patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    icu_unit TEXT NOT NULL,
    bed_number TEXT NOT NULL,
    admit_time TEXT NOT NULL,
    discharge_time TEXT,
    iculos_hours INTEGER NOT NULL DEFAULT 1,
    chief_syndrome TEXT NOT NULL,
    acuity_status TEXT NOT NULL CHECK (acuity_status IN ('STABLE', 'MONITORING', 'DETERIORATING', 'CRITICAL')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_icu_stays_patient ON icu_stays(patient_id);

CREATE TABLE IF NOT EXISTS icu_observations (
    id TEXT PRIMARY KEY NOT NULL,
    stay_id TEXT NOT NULL REFERENCES icu_stays(id) ON DELETE CASCADE,
    patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    iculos_hour INTEGER NOT NULL,
    chart_time TEXT NOT NULL,
    variable_name TEXT NOT NULL,
    valuenum REAL NOT NULL,
    value_unit TEXT NOT NULL,
    loinc_code TEXT,
    recorded_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_icu_obs_stay ON icu_observations(stay_id, iculos_hour);
CREATE INDEX IF NOT EXISTS idx_icu_obs_patient ON icu_observations(patient_id);

CREATE TABLE IF NOT EXISTS icu_predictions (
    id TEXT PRIMARY KEY NOT NULL,
    stay_id TEXT NOT NULL REFERENCES icu_stays(id) ON DELETE CASCADE,
    patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    requested_by TEXT NOT NULL REFERENCES users(id),
    prediction_time TEXT NOT NULL,
    prediction_horizon TEXT NOT NULL DEFAULT '6_to_12_hours',
    risk_score REAL NOT NULL,
    risk_tier TEXT NOT NULL CHECK (risk_tier IN ('LOW', 'MODERATE', 'HIGH', 'CRITICAL', 'INSUFFICIENT_DATA')),
    decision_threshold REAL NOT NULL,
    model_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    data_quality_status TEXT NOT NULL,
    stale_warning TEXT,
    shap_attributions_json TEXT NOT NULL DEFAULT '[]',
    vital_summary_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_icu_pred_stay ON icu_predictions(stay_id, created_at DESC);

CREATE TABLE IF NOT EXISTS icu_alerts (
    id TEXT PRIMARY KEY NOT NULL,
    prediction_id TEXT NOT NULL REFERENCES icu_predictions(id) ON DELETE CASCADE,
    stay_id TEXT NOT NULL REFERENCES icu_stays(id) ON DELETE CASCADE,
    patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    risk_tier TEXT NOT NULL,
    risk_score REAL NOT NULL,
    alert_time TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('TRIGGERED', 'ACKNOWLEDGED', 'RESOLVED')),
    cooldown_until TEXT,
    acknowledged_by TEXT REFERENCES users(id),
    acknowledged_at TEXT,
    acknowledgement_notes TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_icu_alerts_stay ON icu_alerts(stay_id);
CREATE INDEX IF NOT EXISTS idx_icu_alerts_status ON icu_alerts(status);

CREATE TABLE IF NOT EXISTS icu_models (
    id TEXT PRIMARY KEY NOT NULL,
    model_id TEXT NOT NULL UNIQUE,
    model_name TEXT NOT NULL,
    version TEXT NOT NULL,
    algorithm TEXT NOT NULL,
    target_endpoint TEXT NOT NULL,
    prediction_horizon TEXT NOT NULL,
    decision_threshold REAL NOT NULL,
    auroc REAL NOT NULL,
    auprc REAL NOT NULL,
    brier_score REAL NOT NULL,
    sensitivity REAL NOT NULL,
    specificity REAL NOT NULL,
    f1_score REAL NOT NULL,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    top_features_json TEXT NOT NULL DEFAULT '[]',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

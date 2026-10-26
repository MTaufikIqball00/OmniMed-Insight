-- OmniMed Insight (XAI) — Core Clinical, Security, Provenance & Audit Schema

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY NOT NULL,
    email TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'clinician', 'reviewer', 'readonly')),
    specialty TEXT NOT NULL DEFAULT 'General Medicine',
    fhir_practitioner_id TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY NOT NULL,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    csrf_token TEXT NOT NULL,
    ip_address TEXT NOT NULL,
    user_agent TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions(token_hash);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);

CREATE TABLE IF NOT EXISTS patients (
    id TEXT PRIMARY KEY NOT NULL,
    mrn TEXT NOT NULL UNIQUE,
    fhir_patient_id TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    birth_date TEXT NOT NULL,
    sex TEXT NOT NULL CHECK (sex IN ('male', 'female', 'other', 'unknown')),
    is_synthetic INTEGER NOT NULL DEFAULT 1,
    clinical_summary TEXT NOT NULL,
    allergies_json TEXT NOT NULL DEFAULT '[]',
    active_conditions_json TEXT NOT NULL DEFAULT '[]',
    retention_policy TEXT NOT NULL DEFAULT 'SYNTHETIC_DEV_RETENTION_90D',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS patient_assignments (
    id TEXT PRIMARY KEY NOT NULL,
    patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    access_level TEXT NOT NULL CHECK (access_level IN ('PRIMARY_CLINICIAN', 'CONSULTING_REVIEWER', 'AUTHORIZED_READONLY')),
    assigned_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(patient_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_patient_assignments_user ON patient_assignments(user_id, patient_id);

CREATE TABLE IF NOT EXISTS clinical_cases (
    id TEXT PRIMARY KEY NOT NULL,
    case_number TEXT NOT NULL UNIQUE,
    patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    managing_clinician_id TEXT NOT NULL REFERENCES users(id),
    encounter_type TEXT NOT NULL,
    modality TEXT NOT NULL CHECK (modality IN ('CXR', 'MRI')),
    body_part TEXT NOT NULL,
    chief_complaint TEXT NOT NULL,
    clinical_history TEXT NOT NULL,
    priority TEXT NOT NULL CHECK (priority IN ('ROUTINE', 'URGENT', 'STAT')),
    status TEXT NOT NULL CHECK (status IN ('OPEN', 'IN_ANALYSIS', 'DRAFT_READY', 'APPROVED', 'REJECTED')),
    fhir_encounter_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_clinical_cases_patient ON clinical_cases(patient_id);

CREATE TABLE IF NOT EXISTS clinical_observations (
    id TEXT PRIMARY KEY NOT NULL,
    case_id TEXT NOT NULL REFERENCES clinical_cases(id) ON DELETE CASCADE,
    patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    loinc_code TEXT NOT NULL,
    display_name TEXT NOT NULL,
    value_text TEXT NOT NULL,
    unit TEXT NOT NULL,
    reference_range TEXT NOT NULL,
    interpretation TEXT NOT NULL,
    recorded_by TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_observations_case ON clinical_observations(case_id);

CREATE TABLE IF NOT EXISTS medical_images (
    id TEXT PRIMARY KEY NOT NULL,
    case_id TEXT NOT NULL REFERENCES clinical_cases(id) ON DELETE CASCADE,
    patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    uploaded_by TEXT NOT NULL REFERENCES users(id),
    original_filename TEXT NOT NULL,
    storage_filename TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    modality TEXT NOT NULL CHECK (modality IN ('CXR', 'MRI')),
    body_part TEXT NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    sha256_digest TEXT NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    bit_depth INTEGER NOT NULL,
    orientation TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_medical_images_case ON medical_images(case_id);

CREATE TABLE IF NOT EXISTS analysis_jobs (
    id TEXT PRIMARY KEY NOT NULL,
    case_id TEXT NOT NULL REFERENCES clinical_cases(id) ON DELETE CASCADE,
    image_id TEXT NOT NULL REFERENCES medical_images(id) ON DELETE CASCADE,
    requested_by TEXT NOT NULL REFERENCES users(id),
    model_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    xai_method TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED')),
    calibration_status TEXT NOT NULL,
    execution_device TEXT NOT NULL,
    predicted_class_code TEXT,
    predicted_class_label TEXT,
    predicted_probability REAL,
    shannon_entropy REAL,
    uncertainty_level TEXT,
    uncertainty_reason TEXT,
    class_scores_json TEXT NOT NULL DEFAULT '[]',
    xai_metadata_json TEXT NOT NULL DEFAULT '{}',
    overlay_storage_path TEXT,
    overlay_sha256 TEXT,
    limitations_json TEXT NOT NULL DEFAULT '[]',
    error_message TEXT,
    started_at TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_analysis_jobs_case ON analysis_jobs(case_id);

CREATE TABLE IF NOT EXISTS report_drafts (
    id TEXT PRIMARY KEY NOT NULL,
    case_id TEXT NOT NULL REFERENCES clinical_cases(id) ON DELETE CASCADE,
    patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    analysis_job_id TEXT REFERENCES analysis_jobs(id),
    author_id TEXT NOT NULL REFERENCES users(id),
    version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL CHECK (status IN ('DRAFT_PENDING_REVIEW', 'APPROVED', 'REJECTED')),
    clinical_facts_section TEXT NOT NULL,
    model_findings_section TEXT NOT NULL,
    xai_attribution_section TEXT NOT NULL,
    impression_narrative TEXT NOT NULL,
    limitations_section TEXT NOT NULL,
    provenance_json TEXT NOT NULL DEFAULT '[]',
    reviewer_id TEXT REFERENCES users(id),
    reviewer_notes TEXT,
    reviewed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_report_drafts_case ON report_drafts(case_id);

CREATE TABLE IF NOT EXISTS fhir_exports (
    id TEXT PRIMARY KEY NOT NULL,
    case_id TEXT NOT NULL REFERENCES clinical_cases(id) ON DELETE CASCADE,
    report_id TEXT REFERENCES report_drafts(id),
    exported_by TEXT NOT NULL REFERENCES users(id),
    fhir_version TEXT NOT NULL DEFAULT '4.0.1',
    validation_status TEXT NOT NULL,
    external_server_status TEXT NOT NULL,
    bundle_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY NOT NULL,
    actor_user_id TEXT,
    actor_email TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    event_category TEXT NOT NULL,
    event_action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('SUCCESS', 'DENIED', 'FAILURE')),
    ip_address TEXT NOT NULL,
    details_redacted TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at DESC);

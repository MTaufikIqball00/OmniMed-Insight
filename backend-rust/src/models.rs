use serde::{Deserialize, Serialize};
use sqlx::FromRow;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum UserRole {
    Admin,
    Clinician,
    Reviewer,
    Readonly,
}

impl UserRole {
    pub fn as_str(&self) -> &'static str {
        match self {
            UserRole::Admin => "admin",
            UserRole::Clinician => "clinician",
            UserRole::Reviewer => "reviewer",
            UserRole::Readonly => "readonly",
        }
    }

    pub fn from_db(val: &str) -> Self {
        match val {
            "admin" => UserRole::Admin,
            "clinician" => UserRole::Clinician,
            "reviewer" => UserRole::Reviewer,
            _ => UserRole::Readonly,
        }
    }

    pub fn can_manage_users(&self) -> bool {
        matches!(self, UserRole::Admin)
    }

    pub fn can_view_audit_logs(&self) -> bool {
        matches!(self, UserRole::Admin | UserRole::Reviewer)
    }

    pub fn can_upload_and_analyze(&self) -> bool {
        matches!(self, UserRole::Admin | UserRole::Clinician)
    }

    pub fn can_draft_or_edit_report(&self) -> bool {
        matches!(self, UserRole::Admin | UserRole::Clinician)
    }

    pub fn can_review_approve_report(&self) -> bool {
        matches!(
            self,
            UserRole::Admin | UserRole::Clinician | UserRole::Reviewer
        )
    }

    pub fn can_export_fhir(&self) -> bool {
        matches!(
            self,
            UserRole::Admin | UserRole::Clinician | UserRole::Reviewer
        )
    }
}

#[derive(Debug, Clone, FromRow, Serialize)]
pub struct UserRow {
    pub id: String,
    pub email: String,
    pub full_name: String,
    pub role: String,
    pub specialty: String,
    pub fhir_practitioner_id: String,
    #[serde(skip_serializing)]
    pub password_hash: String,
    pub is_active: i64,
    pub failed_login_attempts: i64,
    pub locked_until: Option<String>,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuthenticatedUser {
    pub user_id: String,
    pub email: String,
    pub full_name: String,
    pub role: UserRole,
    pub specialty: String,
    pub fhir_practitioner_id: String,
    pub session_id: String,
    pub csrf_token: String,
}

#[derive(Debug, Deserialize)]
pub struct LoginRequest {
    pub email: String,
    pub password: String,
}

#[derive(Debug, Serialize)]
pub struct LoginResponse {
    pub user: AuthenticatedUser,
    pub session_token: String,
    pub csrf_token: String,
    pub expires_at: String,
}

#[derive(Debug, Clone, FromRow, Serialize)]
pub struct PatientRow {
    pub id: String,
    pub mrn: String,
    pub fhir_patient_id: String,
    pub full_name: String,
    pub birth_date: String,
    pub sex: String,
    pub is_synthetic: i64,
    pub clinical_summary: String,
    pub allergies_json: String,
    pub active_conditions_json: String,
    pub retention_policy: String,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Debug, Clone, FromRow, Serialize)]
pub struct ClinicalCaseRow {
    pub id: String,
    pub case_number: String,
    pub patient_id: String,
    pub managing_clinician_id: String,
    pub encounter_type: String,
    pub modality: String,
    pub body_part: String,
    pub chief_complaint: String,
    pub clinical_history: String,
    pub priority: String,
    pub status: String,
    pub fhir_encounter_id: String,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Debug, Clone, FromRow, Serialize)]
pub struct ObservationRow {
    pub id: String,
    pub case_id: String,
    pub patient_id: String,
    pub loinc_code: String,
    pub display_name: String,
    pub value_text: String,
    pub unit: String,
    pub reference_range: String,
    pub interpretation: String,
    pub recorded_by: String,
    pub recorded_at: String,
}

#[derive(Debug, Clone, FromRow, Serialize)]
pub struct MedicalImageRow {
    pub id: String,
    pub case_id: String,
    pub patient_id: String,
    pub uploaded_by: String,
    pub original_filename: String,
    pub storage_filename: String,
    #[serde(skip_serializing)]
    pub storage_path: String,
    pub mime_type: String,
    pub modality: String,
    pub body_part: String,
    pub file_size_bytes: i64,
    pub sha256_digest: String,
    pub width: i64,
    pub height: i64,
    pub bit_depth: i64,
    pub orientation: String,
    pub metadata_json: String,
    pub created_at: String,
}

#[derive(Debug, Clone, FromRow, Serialize)]
pub struct AnalysisJobRow {
    pub id: String,
    pub case_id: String,
    pub image_id: String,
    pub requested_by: String,
    pub model_id: String,
    pub model_version: String,
    pub xai_method: String,
    pub status: String,
    pub calibration_status: String,
    pub execution_device: String,
    pub predicted_class_code: Option<String>,
    pub predicted_class_label: Option<String>,
    pub predicted_probability: Option<f64>,
    pub shannon_entropy: Option<f64>,
    pub uncertainty_level: Option<String>,
    pub uncertainty_reason: Option<String>,
    pub class_scores_json: String,
    pub xai_metadata_json: String,
    #[serde(skip_serializing)]
    pub overlay_storage_path: Option<String>,
    pub overlay_sha256: Option<String>,
    pub limitations_json: String,
    pub error_message: Option<String>,
    pub started_at: Option<String>,
    pub completed_at: Option<String>,
    pub created_at: String,
}

#[derive(Debug, Clone, FromRow, Serialize)]
pub struct ReportDraftRow {
    pub id: String,
    pub case_id: String,
    pub patient_id: String,
    pub analysis_job_id: Option<String>,
    pub author_id: String,
    pub version: i64,
    pub status: String,
    pub clinical_facts_section: String,
    pub model_findings_section: String,
    pub xai_attribution_section: String,
    pub impression_narrative: String,
    pub limitations_section: String,
    pub provenance_json: String,
    pub reviewer_id: Option<String>,
    pub reviewer_notes: Option<String>,
    pub reviewed_at: Option<String>,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Debug, Clone, FromRow, Serialize)]
pub struct AuditLogRow {
    pub id: String,
    pub actor_user_id: Option<String>,
    pub actor_email: String,
    pub actor_role: String,
    pub event_category: String,
    pub event_action: String,
    pub resource_type: String,
    pub resource_id: String,
    pub outcome: String,
    pub ip_address: String,
    pub details_redacted: String,
    pub created_at: String,
}

#[derive(Debug, Deserialize)]
pub struct CreatePatientRequest {
    pub full_name: String,
    pub birth_date: String,
    pub sex: String,
    pub clinical_summary: String,
    pub allergies: Option<Vec<String>>,
    pub active_conditions: Option<Vec<String>>,
}

#[derive(Debug, Deserialize)]
pub struct CreateCaseRequest {
    pub patient_id: String,
    pub encounter_type: String,
    pub modality: String,
    pub body_part: String,
    pub chief_complaint: String,
    pub clinical_history: String,
    pub priority: String,
}

#[derive(Debug, Deserialize)]
pub struct CreateObservationRequest {
    pub loinc_code: String,
    pub display_name: String,
    pub value_text: String,
    pub unit: String,
    pub reference_range: String,
    pub interpretation: String,
}

#[derive(Debug, Deserialize)]
pub struct TriggerAnalysisRequest {
    pub image_id: String,
    pub xai_method: Option<String>,
    pub target_class_index: Option<i32>,
}

#[derive(Debug, Deserialize)]
pub struct GenerateReportDraftRequest {
    pub analysis_job_id: Option<String>,
    pub clinician_context_note: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct UpdateReportDraftRequest {
    pub clinical_facts_section: String,
    pub model_findings_section: String,
    pub xai_attribution_section: String,
    pub impression_narrative: String,
    pub limitations_section: String,
}

#[derive(Debug, Deserialize)]
pub struct ReviewReportRequest {
    pub decision: String, // "APPROVE" | "REJECT"
    pub reviewer_notes: String,
}

#[derive(Debug, Deserialize)]
pub struct CreateUserRequest {
    pub email: String,
    pub full_name: String,
    pub role: String,
    pub specialty: String,
    pub password: String,
    pub assign_all_synthetic_patients: Option<bool>,
}

#[derive(Debug, Deserialize)]
pub struct UpdateUserRequest {
    pub role: Option<String>,
    pub is_active: Option<bool>,
    pub specialty: Option<String>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ProvenanceCitation {
    pub ref_id: String,
    pub source_type: String,
    pub title: String,
    pub summary: String,
    pub timestamp: String,
    pub verifier: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct InternalAiRequest {
    pub job_id: String,
    pub image_id: String,
    pub image_path: String,
    pub output_overlay_path: String,
    pub modality: String,
    pub body_part: String,
    pub xai_method: String,
    pub target_class_index: Option<i32>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct InternalAiResponse {
    pub job_id: String,
    pub image_id: String,
    pub status: String,
    pub model_id: String,
    pub model_version: String,
    pub model_architecture: String,
    pub calibration_status: String,
    pub execution_device: String,
    pub inference_duration_ms: f64,
    pub modality: String,
    pub image_metadata: serde_json::Value,
    pub predicted_class_code: String,
    pub predicted_class_label: String,
    pub predicted_probability: f64,
    pub shannon_entropy: f64,
    pub uncertainty_level: String,
    pub uncertainty_reason: String,
    pub class_scores: serde_json::Value,
    pub xai: serde_json::Value,
    pub limitations: Vec<String>,
    pub clinical_safety_notice: String,
}

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8100";

export type UserRole = "admin" | "clinician" | "reviewer" | "readonly";

export interface AuthenticatedUser {
  user_id: string;
  email: string;
  full_name: string;
  role: UserRole;
  specialty: string;
  fhir_practitioner_id: string;
  session_id: string;
  csrf_token: string;
}

export interface RolePermissions {
  can_manage_users: boolean;
  can_view_audit_logs: boolean;
  can_upload_and_analyze: boolean;
  can_draft_or_edit_report: boolean;
  can_review_approve_report: boolean;
  can_export_fhir: boolean;
}

export interface PatientRecord {
  id: string;
  mrn: string;
  fhir_patient_id: string;
  full_name: string;
  birth_date: string;
  sex: string;
  is_synthetic: number;
  clinical_summary: string;
  allergies_json: string;
  active_conditions_json: string;
  retention_policy: string;
  created_at: string;
  updated_at: string;
}

export interface ClinicalCaseRecord {
  id: string;
  case_number: string;
  patient_id: string;
  managing_clinician_id: string;
  encounter_type: string;
  modality: "CXR" | "MRI";
  body_part: string;
  chief_complaint: string;
  clinical_history: string;
  priority: "ROUTINE" | "URGENT" | "STAT";
  status: "OPEN" | "IN_ANALYSIS" | "DRAFT_READY" | "APPROVED" | "REJECTED";
  fhir_encounter_id: string;
  created_at: string;
  updated_at: string;
}

export interface ObservationRecord {
  id: string;
  case_id: string;
  patient_id: string;
  loinc_code: string;
  display_name: string;
  value_text: string;
  unit: string;
  reference_range: string;
  interpretation: string;
  recorded_by: string;
  recorded_at: string;
}

export interface MedicalImageRecord {
  id: string;
  case_id: string;
  patient_id: string;
  uploaded_by: string;
  original_filename: string;
  storage_filename: string;
  mime_type: string;
  modality: "CXR" | "MRI";
  body_part: string;
  file_size_bytes: number;
  sha256_digest: string;
  width: number;
  height: number;
  bit_depth: number;
  orientation: string;
  metadata_json: string;
  created_at: string;
}

export interface ClassScoreItem {
  class_index: number;
  class_code: string;
  class_label: string;
  probability: number;
  logit: number;
  snomed_code: string;
  loinc_code: string;
}

export interface RegionAttributionItem {
  region_name: string;
  quadrant_code: string;
  mean_attribution: number;
  peak_attribution: number;
  bbox_norm: number[];
}

export interface XaiMetadata {
  method: string;
  explained_class_code: string;
  explained_class_label: string;
  explained_class_index: number;
  target_layer: string;
  feature_map_resolution: string;
  upsampled_resolution: string;
  overlay_sha256: string;
  peak_coords_norm: number[];
  active_area_ratio: number;
  top_regions: RegionAttributionItem[];
  color_scale_legend: Record<string, string>;
  clinical_warning: string;
  localization_limitation: string;
}

export interface AnalysisJobRecord {
  id: string;
  case_id: string;
  image_id: string;
  requested_by: string;
  model_id: string;
  model_version: string;
  xai_method: string;
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED";
  calibration_status: string;
  execution_device: string;
  predicted_class_code: string | null;
  predicted_class_label: string | null;
  predicted_probability: number | null;
  shannon_entropy: number | null;
  uncertainty_level: "LOW" | "MODERATE" | "HIGH_UNCERTAINTY" | null;
  uncertainty_reason: string | null;
  class_scores_json: string;
  xai_metadata_json: string;
  overlay_sha256: string | null;
  limitations_json: string;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface ProvenanceCitation {
  ref_id: string;
  source_type: string;
  title: string;
  summary: string;
  timestamp: string;
  verifier: string;
}

export interface ReportDraftRecord {
  id: string;
  case_id: string;
  patient_id: string;
  analysis_job_id: string | null;
  author_id: string;
  version: number;
  status: "DRAFT_PENDING_REVIEW" | "APPROVED" | "REJECTED";
  clinical_facts_section: string;
  model_findings_section: string;
  xai_attribution_section: string;
  impression_narrative: string;
  limitations_section: string;
  provenance_json: string;
  reviewer_id: string | null;
  reviewer_notes: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AuditLogRecord {
  id: string;
  actor_user_id: string | null;
  actor_email: string;
  actor_role: string;
  event_category: string;
  event_action: string;
  resource_type: string;
  resource_id: string;
  outcome: "SUCCESS" | "DENIED" | "FAILURE";
  ip_address: string;
  details_redacted: string;
  created_at: string;
}

export class ApiRequestError extends Error {
  status: number;
  errorCode: string;

  constructor(status: number, errorCode: string, message: string) {
    super(message);
    this.status = status;
    this.errorCode = errorCode;
  }
}

let inMemorySessionToken: string | null = null;
let inMemoryCsrfToken: string | null = null;
let backendOfflineDetected = false;

export function setAuthTokens(sessionToken: string | null, csrfToken: string | null) {
  inMemorySessionToken = sessionToken;
  inMemoryCsrfToken = csrfToken;
}

export function getAuthHeaders(extra?: Record<string, string>): Record<string, string> {
  const headers: Record<string, string> = { ...(extra || {}) };
  if (inMemorySessionToken) {
    headers["Authorization"] = `Bearer ${inMemorySessionToken}`;
  }
  if (inMemoryCsrfToken) {
    headers["X-CSRF-Token"] = inMemoryCsrfToken;
  }
  return headers;
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  if (backendOfflineDetected) {
    const { cloudFallbackRequest } = await import("./cloudFallback");
    return cloudFallbackRequest<T>(path, options);
  }

  const isFormData = options.body instanceof FormData;
  const headers: Record<string, string> = getAuthHeaders(
    isFormData ? {} : { "Content-Type": "application/json" }
  );

  if (options.headers) {
    Object.assign(headers, options.headers);
  }

  let resp: Response;
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3500);
    resp = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers,
      credentials: "include",
      signal: options.signal || controller.signal,
    });
    clearTimeout(timeoutId);
  } catch {
    backendOfflineDetected = true;
    const { cloudFallbackRequest } = await import("./cloudFallback");
    return cloudFallbackRequest<T>(path, options);
  }

  if (!resp.ok) {
    let errorCode = `HTTP_${resp.status}`;
    let message = `Request failed with status ${resp.status}`;
    try {
      const errBody = await resp.json();
      if (errBody.error_code) errorCode = errBody.error_code;
      if (errBody.message) message = errBody.message;
    } catch {
      // fallback to status message
    }
    throw new ApiRequestError(resp.status, errorCode, message);
  }

  return (await resp.json()) as T;
}

export async function fetchAuthorizedImageBlobUrl(path: string): Promise<string> {
  if (backendOfflineDetected) {
    const { cloudFallbackImageBlobUrl } = await import("./cloudFallback");
    return cloudFallbackImageBlobUrl(path);
  }

  try {
    const resp = await fetch(`${API_BASE_URL}${path}`, {
      method: "GET",
      headers: getAuthHeaders(),
      credentials: "include",
    });
    if (!resp.ok) {
      throw new Error(`Failed to load protected image (${resp.status})`);
    }
    const blob = await resp.blob();
    return URL.createObjectURL(blob);
  } catch {
    backendOfflineDetected = true;
    const { cloudFallbackImageBlobUrl } = await import("./cloudFallback");
    return cloudFallbackImageBlobUrl(path);
  }
}

// =============================================================================
// ICU Early Warning & Sepsis Deterioration Interfaces
// =============================================================================

export interface IcuStayRecord {
  stay_id: string;
  patient_id: string;
  mrn: string;
  patient_name: string;
  birth_date: string;
  sex: string;
  icu_unit: string;
  bed_number: string;
  admit_time: string;
  iculos_hours: number;
  chief_syndrome: string;
  acuity_status: "STABLE" | "MONITORING" | "DETERIORATING" | "CRITICAL";
  created_at: string;
  latest_prediction?: IcuPredictionRecord | null;
  active_alert?: IcuAlertRecord | null;
}

export interface IcuObservationRecord {
  id: string;
  stay_id: string;
  patient_id: string;
  iculos_hour: number;
  chart_time: string;
  variable_name: string;
  valuenum: number;
  value_unit: string;
  loinc_code?: string | null;
  recorded_at: string;
}

export interface IcuShapItem {
  feature: string;
  display_name: string;
  current_value: number;
  shap_value: number;
  direction: "INCREASES_RISK" | "DECREASES_RISK" | "NEUTRAL";
  clinical_rationale: string;
}

export interface IcuPredictionRecord {
  id: string;
  stay_id: string;
  patient_id: string;
  requested_by: string;
  prediction_time: string;
  prediction_horizon: string;
  risk_score: number;
  risk_tier: "LOW" | "MODERATE" | "HIGH" | "CRITICAL" | "INSUFFICIENT_DATA";
  decision_threshold: number;
  model_id: string;
  model_version: string;
  data_quality_status: "ADEQUATE" | "SPARSE_DATA" | "STALE_OBSERVATIONS" | "INSUFFICIENT_DATA";
  stale_warning?: string | null;
  shap_attributions_json: string;
  vital_summary_json: string;
  created_at: string;
}

export interface IcuAlertRecord {
  id: string;
  prediction_id: string;
  stay_id: string;
  patient_id: string;
  patient_mrn?: string;
  patient_name?: string;
  icu_unit?: string;
  bed_number?: string;
  risk_tier: string;
  risk_score: number;
  alert_time: string;
  status: "TRIGGERED" | "ACKNOWLEDGED" | "RESOLVED";
  cooldown_until?: string | null;
  acknowledged_by?: string | null;
  acknowledged_at?: string | null;
  acknowledgement_notes?: string | null;
  created_at: string;
}

export interface IcuModelRecord {
  id: string;
  model_id: string;
  model_name: string;
  version: string;
  algorithm: string;
  target_endpoint: string;
  prediction_horizon: string;
  decision_threshold: number;
  auroc: number;
  auprc: number;
  brier_score: number;
  sensitivity: number;
  specificity: number;
  f1_score: number;
  metrics_json: string;
  top_features_json: string;
  is_active: number;
  created_at: string;
}


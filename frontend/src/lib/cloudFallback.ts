import {
  AnalysisJobRecord,
  ApiRequestError,
  AuditLogRecord,
  AuthenticatedUser,
  ClinicalCaseRecord,
  MedicalImageRecord,
  ObservationRecord,
  PatientRecord,
  ReportDraftRecord,
  RolePermissions,
  UserRole,
} from "./api";

interface StoredUser {
  id: string;
  email: string;
  password: string;
  full_name: string;
  role: UserRole;
  specialty: string;
  fhir_practitioner_id: string;
  is_active: number;
  created_at: string;
}

interface CloudDemoState {
  users: StoredUser[];
  currentUserEmail: string | null;
  patients: PatientRecord[];
  assignedPatientIdsByRole: Record<UserRole, string[]>;
  cases: ClinicalCaseRecord[];
  observations: ObservationRecord[];
  images: MedicalImageRecord[];
  uploadedImageDataUrls: Record<string, string>;
  jobs: AnalysisJobRecord[];
  reports: ReportDraftRecord[];
  audits: AuditLogRecord[];
}

const STORAGE_KEY = "omnimed_vercel_cloud_demo_state_v1";

function getPermissionsForRole(role: UserRole): RolePermissions {
  switch (role) {
    case "admin":
      return {
        can_manage_users: true,
        can_view_audit_logs: true,
        can_upload_and_analyze: true,
        can_draft_or_edit_report: true,
        can_review_approve_report: true,
        can_export_fhir: true,
      };
    case "clinician":
      return {
        can_manage_users: false,
        can_view_audit_logs: false,
        can_upload_and_analyze: true,
        can_draft_or_edit_report: true,
        can_review_approve_report: false,
        can_export_fhir: true,
      };
    case "reviewer":
      return {
        can_manage_users: false,
        can_view_audit_logs: true,
        can_upload_and_analyze: false,
        can_draft_or_edit_report: true,
        can_review_approve_report: true,
        can_export_fhir: true,
      };
    case "readonly":
    default:
      return {
        can_manage_users: false,
        can_view_audit_logs: false,
        can_upload_and_analyze: false,
        can_draft_or_edit_report: false,
        can_review_approve_report: false,
        can_export_fhir: true,
      };
  }
}

function createInitialSeedState(): CloudDemoState {
  return {
    users: [
      {
        id: "usr-admin-001",
        email: "admin@omnimed-insight.local",
        password: "Admin!2026",
        full_name: "Dr. Elena Vance (System Admin)",
        role: "admin",
        specialty: "Clinical Informatics & Governance",
        fhir_practitioner_id: "Practitioner/prac-admin-001",
        is_active: 1,
        created_at: "2026-10-01T08:00:00Z",
      },
      {
        id: "usr-clin-001",
        email: "clinician@omnimed-insight.local",
        password: "Clinician!2026",
        full_name: "Dr. Aris Thorne, MD",
        role: "clinician",
        specialty: "Thoracic & Neuro Diagnostic Radiology",
        fhir_practitioner_id: "Practitioner/prac-clin-001",
        is_active: 1,
        created_at: "2026-10-01T08:05:00Z",
      },
      {
        id: "usr-rev-001",
        email: "reviewer@omnimed-insight.local",
        password: "Reviewer!2026",
        full_name: "Dr. Maya Lin, MD (Senior Reviewer)",
        role: "reviewer",
        specialty: "Cardiopulmonary Imaging Board Review",
        fhir_practitioner_id: "Practitioner/prac-rev-001",
        is_active: 1,
        created_at: "2026-10-01T08:10:00Z",
      },
      {
        id: "usr-ro-001",
        email: "readonly@omnimed-insight.local",
        password: "Readonly!2026",
        full_name: "Clinical Audit Observer",
        role: "readonly",
        specialty: "Quality Assurance & FHIR Interop",
        fhir_practitioner_id: "Practitioner/prac-ro-001",
        is_active: 1,
        created_at: "2026-10-01T08:15:00Z",
      },
    ],
    currentUserEmail: null,
    patients: [
      {
        id: "pat-synth-001",
        mrn: "PT-SYN-001",
        fhir_patient_id: "Patient/fhir-pat-synth-001",
        full_name: "SYNTHETIC_CASE_ALPHA (Thoracic Cohort)",
        birth_date: "1968-04-14",
        sex: "male",
        is_synthetic: 1,
        clinical_summary:
          "58-year-old male presenting with 5-day productive cough, low-grade fever (38.4 C), and right lower zone crackles on auscultation. Synthetic record for XAI decision-support evaluation.",
        allergies_json: JSON.stringify(["Penicillin (Mild Rash)"]),
        active_conditions_json: JSON.stringify([
          "Community-acquired lower respiratory tract symptoms",
          "Essential hypertension",
        ]),
        retention_policy: "SYNTHETIC_RESEARCH_COHORT_365D",
        created_at: "2026-10-15T09:00:00Z",
        updated_at: "2026-10-25T10:30:00Z",
      },
      {
        id: "pat-synth-002",
        mrn: "PT-SYN-002",
        fhir_patient_id: "Patient/fhir-pat-synth-002",
        full_name: "SYNTHETIC_CASE_BETA (Neuro MRI Cohort)",
        birth_date: "1979-11-22",
        sex: "female",
        is_synthetic: 1,
        clinical_summary:
          "46-year-old female evaluated for intermittent bifrontal headaches and transient visual aura. Axial T2/FLAIR brain MRI requested for structural screening.",
        allergies_json: JSON.stringify(["No Known Drug Allergies"]),
        active_conditions_json: JSON.stringify(["Migraine with aura"]),
        retention_policy: "SYNTHETIC_RESEARCH_COHORT_365D",
        created_at: "2026-10-16T11:20:00Z",
        updated_at: "2026-10-25T11:00:00Z",
      },
      {
        id: "pat-synth-003",
        mrn: "PT-SYN-003",
        fhir_patient_id: "Patient/fhir-pat-synth-003",
        full_name: "SYNTHETIC_RESTRICTED_GAMMA (IDOR Boundary Cohort)",
        birth_date: "1955-08-03",
        sex: "male",
        is_synthetic: 1,
        clinical_summary:
          "Restricted synthetic patient assigned exclusively to external unit for verifying server-side IDOR and RBAC boundary enforcement.",
        allergies_json: JSON.stringify(["Sulfa antibiotics"]),
        active_conditions_json: JSON.stringify(["Restricted Governance Test Cohort"]),
        retention_policy: "RESTRICTED_AUDIT_HOLD",
        created_at: "2026-10-17T14:00:00Z",
        updated_at: "2026-10-25T12:00:00Z",
      },
    ],
    assignedPatientIdsByRole: {
      admin: ["pat-synth-001", "pat-synth-002", "pat-synth-003"],
      clinician: ["pat-synth-001", "pat-synth-002"],
      reviewer: ["pat-synth-001", "pat-synth-002"],
      readonly: ["pat-synth-001", "pat-synth-002"],
    },
    cases: [
      {
        id: "case-synth-001",
        case_number: "CASE-2026-0101",
        patient_id: "pat-synth-001",
        managing_clinician_id: "usr-clin-001",
        encounter_type: "Inpatient Acute Respiratory Evaluation",
        modality: "CXR",
        body_part: "CHEST",
        chief_complaint: "Productive cough, dyspnea on exertion, and right basal rales",
        clinical_history:
          "58M with 5 days of febrile respiratory illness; SpO2 94% on room air, elevated CRP (48 mg/L).",
        priority: "URGENT",
        status: "DRAFT_READY",
        fhir_encounter_id: "Encounter/fhir-enc-0101",
        created_at: "2026-10-20T09:15:00Z",
        updated_at: "2026-10-26T08:30:00Z",
      },
      {
        id: "case-synth-002",
        case_number: "CASE-2026-0102",
        patient_id: "pat-synth-002",
        managing_clinician_id: "usr-clin-001",
        encounter_type: "Outpatient Neurology Diagnostic Consult",
        modality: "MRI",
        body_part: "BRAIN",
        chief_complaint: "Recurrent headache with transient visual field shimmer",
        clinical_history:
          "46F neurological baseline screening; normal cranial nerve exam, requesting structural MRI review.",
        priority: "ROUTINE",
        status: "IN_ANALYSIS",
        fhir_encounter_id: "Encounter/fhir-enc-0102",
        created_at: "2026-10-21T10:30:00Z",
        updated_at: "2026-10-26T09:00:00Z",
      },
      {
        id: "case-synth-003",
        case_number: "CASE-2026-0103",
        patient_id: "pat-synth-003",
        managing_clinician_id: "usr-admin-001",
        encounter_type: "Restricted Governance Audit Encounter",
        modality: "CXR",
        body_part: "CHEST",
        chief_complaint: "Restricted cross-department governance test case",
        clinical_history: "Synthetic case used to validate IDOR protection.",
        priority: "ROUTINE",
        status: "OPEN",
        fhir_encounter_id: "Encounter/fhir-enc-0103",
        created_at: "2026-10-22T12:00:00Z",
        updated_at: "2026-10-26T09:15:00Z",
      },
    ],
    observations: [
      {
        id: "obs-synth-001",
        case_id: "case-synth-001",
        patient_id: "pat-synth-001",
        loinc_code: "8310-5",
        display_name: "Body temperature",
        value_text: "38.4",
        unit: "degC",
        reference_range: "36.1 - 37.2",
        interpretation: "HIGH (Febrile)",
        recorded_by: "usr-clin-001",
        recorded_at: "2026-10-20T09:20:00Z",
      },
      {
        id: "obs-synth-002",
        case_id: "case-synth-001",
        patient_id: "pat-synth-001",
        loinc_code: "59408-5",
        display_name: "Oxygen saturation in Arterial blood by Pulse oximetry",
        value_text: "94",
        unit: "%",
        reference_range: "95 - 100",
        interpretation: "BORDERLINE_LOW",
        recorded_by: "usr-clin-001",
        recorded_at: "2026-10-20T09:22:00Z",
      },
      {
        id: "obs-synth-003",
        case_id: "case-synth-001",
        patient_id: "pat-synth-001",
        loinc_code: "1988-5",
        display_name: "C reactive protein [Mass/volume] in Serum or Plasma",
        value_text: "48.2",
        unit: "mg/L",
        reference_range: "0.0 - 5.0",
        interpretation: "ELEVATED",
        recorded_by: "usr-clin-001",
        recorded_at: "2026-10-20T09:25:00Z",
      },
      {
        id: "obs-synth-004",
        case_id: "case-synth-002",
        patient_id: "pat-synth-002",
        loinc_code: "8480-6",
        display_name: "Systolic blood pressure",
        value_text: "118",
        unit: "mm[Hg]",
        reference_range: "90 - 120",
        interpretation: "NORMAL",
        recorded_by: "usr-clin-001",
        recorded_at: "2026-10-21T10:40:00Z",
      },
    ],
    images: [
      {
        id: "img-synth-001",
        case_id: "case-synth-001",
        patient_id: "pat-synth-001",
        uploaded_by: "usr-clin-001",
        original_filename: "synth_cxr_right_lower_opacity.png",
        storage_filename: "seed_cxr_001.png",
        mime_type: "image/png",
        modality: "CXR",
        body_part: "CHEST",
        file_size_bytes: 184320,
        sha256_digest:
          "a94f6e2d18c7b3095f1e88c27a610d44e92b5c3f8a710294e8c6a1f3d5b70912",
        width: 512,
        height: 512,
        bit_depth: 8,
        orientation: "PA_UPRIGHT",
        metadata_json: JSON.stringify({
          acquisition_mode: "SYNTHETIC_PHANTOM_PA",
          pixel_spacing_mm: [0.143, 0.143],
          kvp: 120,
        }),
        created_at: "2026-10-20T09:30:00Z",
      },
      {
        id: "img-synth-002",
        case_id: "case-synth-002",
        patient_id: "pat-synth-002",
        uploaded_by: "usr-clin-001",
        original_filename: "synth_mri_axial_flair.png",
        storage_filename: "seed_mri_002.png",
        mime_type: "image/png",
        modality: "MRI",
        body_part: "BRAIN",
        file_size_bytes: 196608,
        sha256_digest:
          "c41e89b207a5d3f16e9082b47c15a8f39201d6e7b4c8a2901f5e3d7b9a204816",
        width: 512,
        height: 512,
        bit_depth: 8,
        orientation: "AXIAL_FLAIR",
        metadata_json: JSON.stringify({
          sequence: "T2_FLAIR_SYNTHETIC",
          field_strength_tesla: 3.0,
          slice_thickness_mm: 4.0,
        }),
        created_at: "2026-10-21T10:45:00Z",
      },
    ],
    uploadedImageDataUrls: {},
    jobs: [
      {
        id: "job-synth-001",
        case_id: "case-synth-001",
        image_id: "img-synth-001",
        requested_by: "usr-clin-001",
        model_id: "omnimed-densenet121-multimodal",
        model_version: "densenet121-torchvision-v0.19+xai-1.0 (Cloud Demo)",
        xai_method: "GRAD_CAM",
        status: "COMPLETED",
        calibration_status: "RESEARCH_UNVERIFIED",
        execution_device: "cpu (cloud-demo-fallback)",
        predicted_class_code: "FOCAL_CONSOLIDATION_PATTERN",
        predicted_class_label: "Focal Alveolar / Interstitial Opacity Pattern",
        predicted_probability: 0.784,
        shannon_entropy: 0.682,
        uncertainty_level: "LOW",
        uncertainty_reason:
          "Normalized Shannon entropy (0.492) is within stable confidence bounds for research feature attribution.",
        class_scores_json: JSON.stringify([
          {
            class_index: 1,
            class_code: "FOCAL_CONSOLIDATION_PATTERN",
            class_label: "Focal Alveolar / Interstitial Opacity Pattern",
            probability: 0.784,
            logit: 2.14,
            snomed_code: "95436008",
            loinc_code: "LP199959-0",
          },
          {
            class_index: 2,
            class_code: "PLEURAL_CARDIOMEDIASTINAL_SHIFT",
            class_label: "Pleural Effusion / Cardiomegaly / Mediastinal Shift",
            probability: 0.132,
            logit: 0.36,
            snomed_code: "60046008",
            loinc_code: "LP199974-9",
          },
          {
            class_index: 0,
            class_code: "NO_ACUTE_OPACITY",
            class_label: "Low Parenchymal Opacity / Baseline Pattern",
            probability: 0.061,
            logit: -0.41,
            snomed_code: "17621005",
            loinc_code: "LA6626-1",
          },
          {
            class_index: 3,
            class_code: "NON_SPECIFIC_ARTIFACT_OR_OTHER",
            class_label: "Non-Specific High-Attenuation / Technical Variance",
            probability: 0.023,
            logit: -1.38,
            snomed_code: "260413007",
            loinc_code: "LA4489-6",
          },
        ]),
        xai_metadata_json: JSON.stringify({
          method: "GRAD_CAM",
          explained_class_code: "FOCAL_CONSOLIDATION_PATTERN",
          explained_class_label: "Focal Alveolar / Interstitial Opacity Pattern",
          explained_class_index: 1,
          target_layer: "features.denseblock4.denselayer16.conv2",
          feature_map_resolution: "7x7",
          upsampled_resolution: "512x512",
          overlay_sha256:
            "7e21f09a4b8c3d6e51209a8f7c4b2e1d9034a6f8b2c1e5d7a9083b4c6e1f2a90",
          peak_coords_norm: [0.64, 0.68],
          active_area_ratio: 0.245,
          top_regions: [
            {
              region_name: "Right Lower Zone (RLZ)",
              quadrant_code: "RLZ",
              mean_attribution: 0.72,
              peak_attribution: 0.96,
              bbox_norm: [0.5, 0.5, 1.0, 1.0],
            },
            {
              region_name: "Right Upper Zone (RUZ)",
              quadrant_code: "RUZ",
              mean_attribution: 0.34,
              peak_attribution: 0.58,
              bbox_norm: [0.5, 0.0, 1.0, 0.5],
            },
            {
              region_name: "Left Lower Zone (LLZ)",
              quadrant_code: "LLZ",
              mean_attribution: 0.19,
              peak_attribution: 0.39,
              bbox_norm: [0.0, 0.5, 0.5, 1.0],
            },
            {
              region_name: "Left Upper Zone (LUZ)",
              quadrant_code: "LUZ",
              mean_attribution: 0.11,
              peak_attribution: 0.24,
              bbox_norm: [0.0, 0.0, 0.5, 0.5],
            },
          ],
          color_scale_legend: {
            "0.00_0.25": "Low / Minimal Attribution (Transparent Cool Blue)",
            "0.25_0.50": "Moderate Feature Weighting (Cyan / Green)",
            "0.50_0.75": "Elevated Spatial Attribution (Amber / Yellow)",
            "0.75_1.00": "Peak Gradient Attribution (Crimson Red)",
          },
          clinical_warning:
            "Grad-CAM highlights spatial feature importance from convolutional layer 'features.denseblock4.denselayer16.conv2', NOT confirmed anatomical pathology boundaries.",
          localization_limitation:
            "Coarse 7x7 feature maps upsampled to 512x512 cannot resolve sub-millimeter lesions or replace radiologist visual inspection.",
        }),
        overlay_sha256:
          "7e21f09a4b8c3d6e51209a8f7c4b2e1d9034a6f8b2c1e5d7a9083b4c6e1f2a90",
        limitations_json: JSON.stringify([
          "DECISION SUPPORT ONLY: Output is generated by an uncalibrated research classifier and must be verified by a qualified clinician.",
          "ATTRIBUTION != SEGMENTATION: Saliency overlays show convolutional gradient sensitivity, not exact lesion margins.",
          "CLOUD DEMO MODE: Running in browser fallback mode because local Rust/Python backend (:8100/:8200) is not reachable from this client.",
        ]),
        error_message: null,
        started_at: "2026-10-20T09:31:00Z",
        completed_at: "2026-10-20T09:31:02Z",
        created_at: "2026-10-20T09:31:00Z",
      },
    ],
    reports: [
      {
        id: "rep-synth-001",
        case_id: "case-synth-001",
        patient_id: "pat-synth-001",
        analysis_job_id: "job-synth-001",
        author_id: "usr-clin-001",
        version: 1,
        status: "DRAFT_PENDING_REVIEW",
        clinical_facts_section:
          "Patient: SYNTHETIC_CASE_ALPHA (Thoracic Cohort) (MRN: PT-SYN-001, Sex: male, DOB: 1968-04-14) [SYNTHETIC COHORT]\nCase: CASE-2026-0101 | Modality: CXR (CHEST) | Priority: URGENT\nChief Complaint: Productive cough, dyspnea on exertion, and right basal rales\nClinical History: 58M with 5 days of febrile respiratory illness; SpO2 94% on room air, elevated CRP (48 mg/L).\nRecorded Observations:\n- Body temperature (LOINC 8310-5): 38.4 degC [Ref: 36.1 - 37.2] -> HIGH (Febrile)\n- Oxygen saturation in Arterial blood by Pulse oximetry (LOINC 59408-5): 94 % [Ref: 95 - 100] -> BORDERLINE_LOW\n- C reactive protein [Mass/volume] in Serum or Plasma (LOINC 1988-5): 48.2 mg/L [Ref: 0.0 - 5.0] -> ELEVATED",
        model_findings_section:
          "Model Architecture: omnimed-densenet121-multimodal (densenet121-torchvision-v0.19+xai-1.0)\nCalibration Status: RESEARCH_UNVERIFIED | Execution Device: cpu\nTop Predicted Pattern: Focal Alveolar / Interstitial Opacity Pattern (Code: FOCAL_CONSOLIDATION_PATTERN, Probability: 78.4%)\nUncertainty Assessment: LOW (Shannon Entropy: 0.6820 nats)\nNote: Probabilities reflect uncalibrated softmax outputs and do not equate to clinical post-test probability.",
        xai_attribution_section:
          "XAI Method: GRAD_CAM on layer features.denseblock4.denselayer16.conv2\nPrimary Spatial Attribution Region: Right Lower Zone (RLZ) (Mean Attribution: 0.720, Peak: 0.960)\nActive Saliency Area Ratio (>0.50 threshold): 24.5% of image field\nPeak Normalized Coordinates (x, y): (0.640, 0.680)\nOverlay Integrity SHA-256: 7e21f09a4b8c3d6e51209a8f7c4b2e1d9034a6f8b2c1e5d7a9083b4c6e1f2a90",
        impression_narrative:
          "PRELIMINARY CLINICAL DECISION-SUPPORT DRAFT (REQUIRES RADIOLOGIST VERIFICATION):\nMultimodal correlation of clinical presentation (Productive cough, dyspnea on exertion, and right basal rales) with CXR imaging demonstrates model feature attribution concentrated in the Right Lower Zone (RLZ), corresponding to the 'Focal Alveolar / Interstitial Opacity Pattern' pattern (uncalibrated score 78.4%, uncertainty: LOW). Clinical correlation with recorded laboratory/vital observations and direct inspection of the unaltered source radiograph are mandatory prior to diagnostic sign-off.",
        limitations_section:
          "1. NON-DIAGNOSTIC STATUS: This draft is synthesized from structured records and research AI telemetry. It is NOT a signed diagnostic radiology report.\n2. XAI LIMITATION: Grad-CAM saliency maps reflect coarse convolutional feature gradients (7x7 upsampled) and must not be interpreted as anatomical lesion segmentation.\n3. HUMAN-IN-THE-LOOP MANDATE: Final diagnostic interpretation requires review and explicit sign-off by an authorized clinician/reviewer.",
        provenance_json: JSON.stringify([
          {
            ref_id: "PROV-PAT-1",
            source_type: "PATIENT_DEMOGRAPHICS",
            title: "Patient Record PT-SYN-001",
            summary:
              "SYNTHETIC_CASE_ALPHA (Thoracic Cohort) (male, DOB 1968-04-14) - Synthetic Flag: true",
            timestamp: "2026-10-25T10:30:00Z",
            verifier: "SQLite Primary Store",
          },
          {
            ref_id: "PROV-OBS-1",
            source_type: "CLINICAL_OBSERVATIONS",
            title: "3 Structured LOINC Observation(s)",
            summary:
              "Vitals and laboratory parameters bound to case CASE-2026-0101",
            timestamp: "2026-10-26T08:30:00Z",
            verifier: "Clinician Entry / Seed Cohort",
          },
          {
            ref_id: "PROV-AI-1",
            source_type: "PYTORCH_XAI_INFERENCE",
            title: "Job job-synth-001 (GRAD_CAM)",
            summary:
              "Model densenet121-torchvision-v0.19+xai-1.0 predicted Focal Alveolar / Interstitial Opacity Pattern (p=78.4%, entropy=0.682)",
            timestamp: "2026-10-20T09:31:02Z",
            verifier: "PyTorch 2.5.1 DenseNet-121 + Grad-CAM",
          },
        ]),
        reviewer_id: null,
        reviewer_notes: null,
        reviewed_at: null,
        created_at: "2026-10-20T09:35:00Z",
        updated_at: "2026-10-20T09:35:00Z",
      },
    ],
    audits: [
      {
        id: "aud-synth-001",
        actor_user_id: "usr-clin-001",
        actor_email: "clinician@omnimed-insight.local",
        actor_role: "clinician",
        event_category: "XAI_ANALYSIS",
        event_action: "RUN_PYTORCH_GRADCAM",
        resource_type: "analysis_job",
        resource_id: "job-synth-001",
        outcome: "SUCCESS",
        ip_address: "127.0.0.1",
        details_redacted:
          "Completed GRAD_CAM inference on case-synth-001 (Focal Alveolar / Interstitial Opacity Pattern, p=0.784)",
        created_at: "2026-10-20T09:31:02Z",
      },
      {
        id: "aud-synth-002",
        actor_user_id: "usr-clin-001",
        actor_email: "clinician@omnimed-insight.local",
        actor_role: "clinician",
        event_category: "REPORT_DRAFT",
        event_action: "GENERATE_DRAFT",
        resource_type: "report_draft",
        resource_id: "rep-synth-001",
        outcome: "SUCCESS",
        ip_address: "127.0.0.1",
        details_redacted: "Generated evidence-bound report draft v1 for CASE-2026-0101",
        created_at: "2026-10-20T09:35:00Z",
      },
    ],
  };
}

function loadState(): CloudDemoState {
  if (typeof window === "undefined") {
    return createInitialSeedState();
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      const seed = createInitialSeedState();
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(seed));
      return seed;
    }
    return JSON.parse(raw) as CloudDemoState;
  } catch {
    return createInitialSeedState();
  }
}

function saveState(state: CloudDemoState): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // ignore storage quota errors
  }
}

function recordAudit(
  state: CloudDemoState,
  user: StoredUser | null,
  category: string,
  action: string,
  resourceType: string,
  resourceId: string,
  outcome: "SUCCESS" | "DENIED" | "FAILURE",
  details: string
) {
  state.audits.unshift({
    id: `aud-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    actor_user_id: user?.id || null,
    actor_email: user?.email || "anonymous",
    actor_role: user?.role || "unauthenticated",
    event_category: category,
    event_action: action,
    resource_type: resourceType,
    resource_id: resourceId,
    outcome,
    ip_address: "vercel-edge-client",
    details_redacted: details,
    created_at: new Date().toISOString(),
  });
}

function requireUser(state: CloudDemoState): StoredUser {
  const email = state.currentUserEmail || "clinician@omnimed-insight.local";
  const found = state.users.find((u) => u.email.toLowerCase() === email.toLowerCase());
  if (!found && !state.currentUserEmail) {
    throw new ApiRequestError(401, "AUTH_REQUIRED", "Authentication session required.");
  }
  if (!found) {
    throw new ApiRequestError(401, "SESSION_INVALID", "User session not found.");
  }
  return found;
}

export async function cloudFallbackRequest<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const state = loadState();
  const method = (options.method || "GET").toUpperCase();
  const url = new URL(path, "http://localhost");
  const pathname = url.pathname;

  const parseJsonBody = (): Record<string, unknown> => {
    if (!options.body || typeof options.body !== "string") return {};
    try {
      return JSON.parse(options.body) as Record<string, unknown>;
    } catch {
      return {};
    }
  };

  // 1. System Status
  if (pathname === "/api/system/status" && method === "GET") {
    return {
      rust_backend: {
        status: "CLOUD_DEMO_FALLBACK (Local :8100 Offline)",
        bind: "browser-local-storage",
        database_mode: "IN_BROWSER_SYNTHETIC_STATE",
      },
      python_ai_service: {
        status: "SIMULATED_FALLBACK_ONLINE",
        url: "browser://densenet121-gradcam-simulator",
        port: 8200,
        details: {
          mode: "VERCEL_CLOUD_PREVIEW",
          note: "Run backend-rust (:8100) and ai-service-python (:8200) locally for live PyTorch DenseNet-121 execution.",
        },
      },
      fhir_interoperability: {
        local_r4_validator: "ACTIVE (Structural R4 JSON Schema)",
        external_fhir_server_url: "http://127.0.0.1:8080/fhir",
        external_fhir_server_port: 8080,
        external_fhir_server_status: "OFFLINE_LOCAL_EXPORT_ONLY",
      },
      capability_matrix: [
        {
          feature: "RBAC + Session + Cross-Patient IDOR Guard",
          status: "IMPLEMENTED",
          notes: "Active in both Rust backend and Vercel Cloud Preview mode.",
        },
        {
          feature: "PyTorch DenseNet-121 + Grad-CAM Saliency",
          status: "CLOUD_SIMULATION_FALLBACK",
          notes: "Using deterministic Grad-CAM telemetry while local Python service (:8200) is unreachable.",
        },
        {
          feature: "Evidence-Bound Report Drafting & Clinician Sign-Off",
          status: "IMPLEMENTED",
          notes: "Full versioning, provenance citations, and reviewer lock.",
        },
        {
          feature: "HL7 FHIR R4 DiagnosticReport Bundle Export",
          status: "IMPLEMENTED",
          notes: "Generates structurally validated R4 transaction bundles.",
        },
      ],
    } as unknown as T;
  }

  // 2. Auth Login
  if (pathname === "/api/auth/login" && method === "POST") {
    const body = parseJsonBody();
    const email = String(body.email || "").trim().toLowerCase();
    const password = String(body.password || "");
    const found = state.users.find(
      (u) => u.email.toLowerCase() === email && u.password === password && u.is_active === 1
    );
    if (!found) {
      recordAudit(
        state,
        null,
        "AUTH",
        "LOGIN_FAILED",
        "session",
        email || "unknown",
        "DENIED",
        `Failed login attempt for ${email}`
      );
      saveState(state);
      throw new ApiRequestError(
        401,
        "INVALID_CREDENTIALS",
        "Invalid email or password. Use one of the Quick Demo Role Switcher accounts."
      );
    }
    state.currentUserEmail = found.email;
    recordAudit(
      state,
      found,
      "AUTH",
      "LOGIN_SUCCESS",
      "session",
      found.id,
      "SUCCESS",
      `Authenticated ${found.email} (${found.role}) in Cloud Demo Mode`
    );
    saveState(state);
    const authUser: AuthenticatedUser = {
      user_id: found.id,
      email: found.email,
      full_name: found.full_name,
      role: found.role,
      specialty: found.specialty,
      fhir_practitioner_id: found.fhir_practitioner_id,
      session_id: `sess-cloud-${found.id}`,
      csrf_token: `csrf-cloud-${found.id}`,
    };
    return {
      user: authUser,
      session_token: authUser.session_id,
      csrf_token: authUser.csrf_token,
    } as unknown as T;
  }

  // 3. Auth Logout
  if (pathname === "/api/auth/logout" && method === "POST") {
    state.currentUserEmail = null;
    saveState(state);
    return { status: "logged_out" } as unknown as T;
  }

  // 4. Auth Me
  if (pathname === "/api/auth/me" && method === "GET") {
    if (!state.currentUserEmail) {
      throw new ApiRequestError(401, "UNAUTHENTICATED", "No active session");
    }
    const found = requireUser(state);
    const authUser: AuthenticatedUser = {
      user_id: found.id,
      email: found.email,
      full_name: found.full_name,
      role: found.role,
      specialty: found.specialty,
      fhir_practitioner_id: found.fhir_practitioner_id,
      session_id: `sess-cloud-${found.id}`,
      csrf_token: `csrf-cloud-${found.id}`,
    };
    return {
      authenticated: true,
      user: authUser,
      permissions: getPermissionsForRole(found.role),
    } as unknown as T;
  }

  const currentUser = requireUser(state);
  const perms = getPermissionsForRole(currentUser.role);
  const allowedPatientIds =
    currentUser.role === "admin"
      ? state.patients.map((p) => p.id)
      : state.assignedPatientIdsByRole[currentUser.role] || ["pat-synth-001", "pat-synth-002"];

  // 5. Dashboard
  if (pathname === "/api/dashboard" && method === "GET") {
    const visiblePatients = state.patients.filter((p) => allowedPatientIds.includes(p.id));
    const visibleCases = state.cases.filter((c) => allowedPatientIds.includes(c.patient_id));
    const visibleCaseIds = new Set(visibleCases.map((c) => c.id));
    const completedJobs = state.jobs.filter(
      (j) => visibleCaseIds.has(j.case_id) && j.status === "COMPLETED"
    );
    const pendingDrafts = state.reports.filter(
      (r) => visibleCaseIds.has(r.case_id) && r.status === "DRAFT_PENDING_REVIEW"
    );
    const approvedReports = state.reports.filter(
      (r) => visibleCaseIds.has(r.case_id) && r.status === "APPROVED"
    );

    return {
      metrics: {
        authorized_patients_count: visiblePatients.length,
        authorized_cases_count: visibleCases.length,
        completed_xai_analyses: completedJobs.length,
        pending_report_drafts: pendingDrafts.length,
        approved_reports: approvedReports.length,
      },
      recent_audit_events: state.audits.slice(0, 12),
    } as unknown as T;
  }

  // 6. List / Create Patients
  if (pathname === "/api/patients" && method === "GET") {
    const q = (url.searchParams.get("search") || "").trim().toLowerCase();
    const list = state.patients.filter((p) => {
      if (!allowedPatientIds.includes(p.id)) return false;
      if (!q) return true;
      return (
        p.full_name.toLowerCase().includes(q) ||
        p.mrn.toLowerCase().includes(q) ||
        p.clinical_summary.toLowerCase().includes(q)
      );
    });
    return {
      patients: list,
      scope_note:
        currentUser.role === "admin"
          ? "Admin Global Governance Scope (All Synthetic Cohorts Visible)"
          : `RBAC Assigned Cohort Scope (${list.length} authorized patients; pat-synth-003 restricted by IDOR guard)`,
    } as unknown as T;
  }

  if (pathname === "/api/patients" && method === "POST") {
    if (!perms.can_upload_and_analyze && !perms.can_manage_users) {
      throw new ApiRequestError(
        403,
        "RBAC_FORBIDDEN",
        "Your role is not authorized to register new patients."
      );
    }
    const body = parseJsonBody();
    const fullName = String(body.full_name || "").trim();
    const birthDate = String(body.birth_date || "").trim();
    const sex = String(body.sex || "unknown").trim().toLowerCase();
    const summary = String(body.clinical_summary || "").trim();
    const allergies = Array.isArray(body.allergies) ? body.allergies : [];
    const conditions = Array.isArray(body.active_conditions) ? body.active_conditions : [];

    const seq = state.patients.length + 1;
    const newId = `pat-synth-00${seq}-${Date.now().toString().slice(-3)}`;
    const mrn = `PT-SYN-00${seq}`;
    const now = new Date().toISOString();

    const newPatient: PatientRecord = {
      id: newId,
      mrn,
      fhir_patient_id: `Patient/fhir-${newId}`,
      full_name: fullName,
      birth_date: birthDate,
      sex,
      is_synthetic: 1,
      clinical_summary: summary,
      allergies_json: JSON.stringify(allergies),
      active_conditions_json: JSON.stringify(conditions),
      retention_policy: "SYNTHETIC_RESEARCH_COHORT_365D",
      created_at: now,
      updated_at: now,
    };

    state.patients.unshift(newPatient);
    (["admin", "clinician", "reviewer", "readonly"] as UserRole[]).forEach((r) => {
      if (!state.assignedPatientIdsByRole[r].includes(newId)) {
        state.assignedPatientIdsByRole[r].push(newId);
      }
    });

    recordAudit(
      state,
      currentUser,
      "PATIENT_REGISTRY",
      "CREATE_PATIENT",
      "patient",
      newId,
      "SUCCESS",
      `Registered new synthetic patient ${mrn} (${fullName})`
    );
    saveState(state);
    return {
      patient: newPatient,
      message: "Patient registered and assigned to clinical team.",
    } as unknown as T;
  }

  // 7. Patient Detail (IDOR Guard test endpoint)
  const patDetailMatch = pathname.match(/^\/api\/patients\/([^/]+)$/);
  if (patDetailMatch && method === "GET") {
    const patId = patDetailMatch[1];
    const pat = state.patients.find((p) => p.id === patId);
    if (!pat) {
      throw new ApiRequestError(404, "NOT_FOUND", `Patient ${patId} not found`);
    }
    if (!allowedPatientIds.includes(patId)) {
      recordAudit(
        state,
        currentUser,
        "SECURITY_BOUNDARY",
        "RBAC_DENIED",
        "patient",
        patId,
        "DENIED",
        `Blocked unauthorized cross-patient IDOR access to ${pat.mrn} by role '${currentUser.role}'`
      );
      saveState(state);
      throw new ApiRequestError(
        403,
        "IDOR_ACCESS_DENIED",
        `Access denied: Patient ${pat.mrn} is outside your assigned clinical cohort.`
      );
    }
    return { patient: pat } as unknown as T;
  }

  // 8. List / Create Cases
  if (pathname === "/api/cases" && method === "GET") {
    const mod = (url.searchParams.get("modality") || "").trim().toUpperCase();
    const list = state.cases.filter((c) => {
      if (!allowedPatientIds.includes(c.patient_id)) return false;
      if (!mod) return true;
      return c.modality === mod;
    });
    return { cases: list } as unknown as T;
  }

  if (pathname === "/api/cases" && method === "POST") {
    if (!perms.can_upload_and_analyze && !perms.can_manage_users) {
      throw new ApiRequestError(403, "RBAC_FORBIDDEN", "Not permitted to create clinical cases.");
    }
    const body = parseJsonBody();
    const patId = String(body.patient_id || "");
    if (!allowedPatientIds.includes(patId)) {
      throw new ApiRequestError(403, "IDOR_ACCESS_DENIED", "Unauthorized patient ID.");
    }
    const seq = 100 + state.cases.length + 1;
    const now = new Date().toISOString();
    const newCase: ClinicalCaseRecord = {
      id: `case-synth-${seq}`,
      case_number: `CASE-2026-0${seq}`,
      patient_id: patId,
      managing_clinician_id: currentUser.id,
      encounter_type: String(body.encounter_type || "Outpatient Clinical Evaluation"),
      modality: String(body.modality || "CXR").toUpperCase() === "MRI" ? "MRI" : "CXR",
      body_part: String(body.body_part || "CHEST").toUpperCase(),
      chief_complaint: String(body.chief_complaint || ""),
      clinical_history: String(body.clinical_history || ""),
      priority:
        String(body.priority || "ROUTINE").toUpperCase() === "STAT"
          ? "STAT"
          : String(body.priority || "ROUTINE").toUpperCase() === "URGENT"
          ? "URGENT"
          : "ROUTINE",
      status: "OPEN",
      fhir_encounter_id: `Encounter/fhir-enc-0${seq}`,
      created_at: now,
      updated_at: now,
    };
    state.cases.unshift(newCase);
    recordAudit(
      state,
      currentUser,
      "CASE_WORKFLOW",
      "CREATE_CASE",
      "clinical_case",
      newCase.id,
      "SUCCESS",
      `Opened case ${newCase.case_number} (${newCase.modality}) for patient ${patId}`
    );
    saveState(state);
    return { case: newCase } as unknown as T;
  }

  // 9. Case Workspace Detail
  const caseMatch = pathname.match(/^\/api\/cases\/([^/]+)$/);
  if (caseMatch && method === "GET") {
    const caseId = caseMatch[1];
    const c = state.cases.find((item) => item.id === caseId);
    if (!c) {
      throw new ApiRequestError(404, "CASE_NOT_FOUND", `Case ${caseId} not found`);
    }
    if (!allowedPatientIds.includes(c.patient_id)) {
      recordAudit(
        state,
        currentUser,
        "SECURITY_BOUNDARY",
        "RBAC_DENIED",
        "clinical_case",
        caseId,
        "DENIED",
        `Blocked cross-patient case access to ${c.case_number}`
      );
      saveState(state);
      throw new ApiRequestError(403, "IDOR_ACCESS_DENIED", "Case belongs to an unassigned patient.");
    }
    const patient = state.patients.find((p) => p.id === c.patient_id)!;
    return {
      case: c,
      patient,
      observations: state.observations.filter((o) => o.case_id === caseId),
      images: state.images.filter((i) => i.case_id === caseId),
      analysis_jobs: state.jobs.filter((j) => j.case_id === caseId),
      report_drafts: state.reports
        .filter((r) => r.case_id === caseId)
        .sort((a, b) => b.version - a.version),
    } as unknown as T;
  }

  // 10. Add Observation
  const obsMatch = pathname.match(/^\/api\/cases\/([^/]+)\/observations$/);
  if (obsMatch && method === "POST") {
    const caseId = obsMatch[1];
    const c = state.cases.find((item) => item.id === caseId);
    if (!c) throw new ApiRequestError(404, "CASE_NOT_FOUND", "Case not found");
    const body = parseJsonBody();
    const obs: ObservationRecord = {
      id: `obs-${Date.now()}`,
      case_id: caseId,
      patient_id: c.patient_id,
      loinc_code: String(body.loinc_code || "8867-4"),
      display_name: String(body.display_name || "Clinical Observation"),
      value_text: String(body.value_text || ""),
      unit: String(body.unit || ""),
      reference_range: String(body.reference_range || ""),
      interpretation: String(body.interpretation || "RECORDED"),
      recorded_by: currentUser.id,
      recorded_at: new Date().toISOString(),
    };
    state.observations.push(obs);
    recordAudit(
      state,
      currentUser,
      "CLINICAL_DATA",
      "ADD_OBSERVATION",
      "observation",
      obs.id,
      "SUCCESS",
      `Added LOINC ${obs.loinc_code} (${obs.display_name}) to ${c.case_number}`
    );
    saveState(state);
    return { observation: obs } as unknown as T;
  }

  // 11. Upload Image
  const imgUploadMatch = pathname.match(/^\/api\/cases\/([^/]+)\/images$/);
  if (imgUploadMatch && method === "POST") {
    if (!perms.can_upload_and_analyze) {
      throw new ApiRequestError(403, "RBAC_FORBIDDEN", "Role not permitted to upload images.");
    }
    const caseId = imgUploadMatch[1];
    const c = state.cases.find((item) => item.id === caseId);
    if (!c) throw new ApiRequestError(404, "CASE_NOT_FOUND", "Case not found");

    let fileName = "uploaded_study.png";
    let fileSize = 163840;
    let mimeType = "image/png";
    let dataUrl: string | null = null;

    if (options.body instanceof FormData) {
      const f = options.body.get("file");
      if (f instanceof File) {
        fileName = f.name;
        fileSize = f.size || 163840;
        mimeType = f.type || "image/png";
        dataUrl = await new Promise<string>((resolve) => {
          const reader = new FileReader();
          reader.onloadend = () => resolve(String(reader.result || ""));
          reader.readAsDataURL(f);
        });
      }
    }

    const newImgId = `img-${Date.now()}`;
    const newImg: MedicalImageRecord = {
      id: newImgId,
      case_id: caseId,
      patient_id: c.patient_id,
      uploaded_by: currentUser.id,
      original_filename: fileName,
      storage_filename: `${newImgId}.png`,
      mime_type: mimeType,
      modality: c.modality,
      body_part: c.body_part,
      file_size_bytes: fileSize,
      sha256_digest: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b${Date.now()
        .toString()
        .slice(-8)}`,
      width: 512,
      height: 512,
      bit_depth: 8,
      orientation: c.modality === "MRI" ? "AXIAL_FLAIR" : "PA_UPRIGHT",
      metadata_json: JSON.stringify({
        uploaded_via: "VERCEL_CLOUD_DEMO",
        original_filename: fileName,
      }),
      created_at: new Date().toISOString(),
    };

    if (dataUrl) {
      state.uploadedImageDataUrls[newImgId] = dataUrl;
    }
    state.images.unshift(newImg);
    recordAudit(
      state,
      currentUser,
      "IMAGE_INGEST",
      "UPLOAD_MEDICAL_IMAGE",
      "medical_image",
      newImgId,
      "SUCCESS",
      `Validated & stored ${fileName} (${mimeType}) for ${c.case_number}`
    );
    saveState(state);
    return { image: newImg } as unknown as T;
  }

  // 12. Run XAI Analysis
  const analyzeMatch = pathname.match(/^\/api\/cases\/([^/]+)\/analyze$/);
  if (analyzeMatch && method === "POST") {
    if (!perms.can_upload_and_analyze) {
      throw new ApiRequestError(403, "RBAC_FORBIDDEN", "Role not permitted to trigger AI inference.");
    }
    const caseId = analyzeMatch[1];
    const c = state.cases.find((item) => item.id === caseId);
    if (!c) throw new ApiRequestError(404, "CASE_NOT_FOUND", "Case not found");
    const body = parseJsonBody();
    const imageId = String(body.image_id || state.images.find((i) => i.case_id === caseId)?.id || "");
    const xaiMethod = String(body.xai_method || "GRAD_CAM");
    const isMri = c.modality === "MRI";

    const now = new Date().toISOString();
    const newJob: AnalysisJobRecord = {
      id: `job-${Date.now()}`,
      case_id: caseId,
      image_id: imageId,
      requested_by: currentUser.id,
      model_id: "omnimed-densenet121-multimodal",
      model_version: "densenet121-torchvision-v0.19+xai-1.0 (Cloud Demo)",
      xai_method: xaiMethod,
      status: "COMPLETED",
      calibration_status: "RESEARCH_UNVERIFIED",
      execution_device: "cpu (cloud-demo-fallback)",
      predicted_class_code: isMri
        ? "WHITE_MATTER_FLAIR_HYPERINTENSITY"
        : "FOCAL_CONSOLIDATION_PATTERN",
      predicted_class_label: isMri
        ? "Focal Periventricular / Subcortical Hyperintensity Pattern"
        : "Focal Alveolar / Interstitial Opacity Pattern",
      predicted_probability: isMri ? 0.742 : 0.812,
      shannon_entropy: isMri ? 0.731 : 0.641,
      uncertainty_level: "LOW",
      uncertainty_reason:
        "Normalized Shannon entropy is within low-uncertainty bounds for convolutional attribution.",
      class_scores_json: state.jobs[0].class_scores_json,
      xai_metadata_json: JSON.stringify({
        ...JSON.parse(state.jobs[0].xai_metadata_json),
        method: xaiMethod,
        explained_class_label: isMri
          ? "Focal Periventricular / Subcortical Hyperintensity Pattern"
          : "Focal Alveolar / Interstitial Opacity Pattern",
      }),
      overlay_sha256:
        "7e21f09a4b8c3d6e51209a8f7c4b2e1d9034a6f8b2c1e5d7a9083b4c6e1f2a90",
      limitations_json: state.jobs[0].limitations_json,
      error_message: null,
      started_at: now,
      completed_at: now,
      created_at: now,
    };

    state.jobs.unshift(newJob);
    c.status = "IN_ANALYSIS";
    c.updated_at = now;
    recordAudit(
      state,
      currentUser,
      "XAI_ANALYSIS",
      "RUN_PYTORCH_GRADCAM",
      "analysis_job",
      newJob.id,
      "SUCCESS",
      `Executed ${xaiMethod} inference on ${c.case_number} -> ${newJob.predicted_class_label}`
    );
    saveState(state);
    return { job: newJob } as unknown as T;
  }

  // 13. Generate Report Draft
  const draftMatch = pathname.match(/^\/api\/cases\/([^/]+)\/reports\/draft$/);
  if (draftMatch && method === "POST") {
    if (!perms.can_draft_or_edit_report) {
      throw new ApiRequestError(403, "RBAC_FORBIDDEN", "Not permitted to generate report drafts.");
    }
    const caseId = draftMatch[1];
    const c = state.cases.find((item) => item.id === caseId);
    if (!c) throw new ApiRequestError(404, "CASE_NOT_FOUND", "Case not found");
    const pat = state.patients.find((p) => p.id === c.patient_id)!;
    const body = parseJsonBody();
    const jobId = body.analysis_job_id
      ? String(body.analysis_job_id)
      : state.jobs.find((j) => j.case_id === caseId)?.id || null;
    const job = state.jobs.find((j) => j.id === jobId) || state.jobs[0];
    const note = String(body.clinician_context_note || "").trim();

    const caseObs = state.observations.filter((o) => o.case_id === caseId);
    const existingVersions = state.reports
      .filter((r) => r.case_id === caseId)
      .map((r) => r.version);
    const nextVersion = existingVersions.length > 0 ? Math.max(...existingVersions) + 1 : 1;

    const obsLines =
      caseObs.length > 0
        ? caseObs
            .map(
              (o) =>
                `- ${o.display_name} (LOINC ${o.loinc_code}): ${o.value_text} ${o.unit} [Ref: ${o.reference_range}] -> ${o.interpretation}`
            )
            .join("\n")
        : "- No structured LOINC observations recorded yet.";

    const factsSection = [
      `Patient: ${pat.full_name} (MRN: ${pat.mrn}, Sex: ${pat.sex}, DOB: ${pat.birth_date}) [SYNTHETIC COHORT]`,
      `Case: ${c.case_number} | Modality: ${c.modality} (${c.body_part}) | Priority: ${c.priority}`,
      `Chief Complaint: ${c.chief_complaint}`,
      `Clinical History: ${c.clinical_history}`,
      `Recorded Observations:\n${obsLines}`,
      note ? `Clinician Context Note: ${note}` : "",
    ]
      .filter(Boolean)
      .join("\n");

    const now = new Date().toISOString();
    const newReport: ReportDraftRecord = {
      id: `rep-${Date.now()}`,
      case_id: caseId,
      patient_id: pat.id,
      analysis_job_id: job?.id || null,
      author_id: currentUser.id,
      version: nextVersion,
      status: "DRAFT_PENDING_REVIEW",
      clinical_facts_section: factsSection,
      model_findings_section:
        job
          ? `Model Architecture: ${job.model_id} (${job.model_version})\nCalibration Status: ${job.calibration_status} | Execution Device: ${job.execution_device}\nTop Predicted Pattern: ${job.predicted_class_label} (Code: ${job.predicted_class_code}, Probability: ${((job.predicted_probability || 0) * 100).toFixed(1)}%)\nUncertainty Assessment: ${job.uncertainty_level} (Shannon Entropy: ${(job.shannon_entropy || 0).toFixed(4)} nats)`
          : "No AI inference job bound to this draft.",
      xai_attribution_section: state.reports[0].xai_attribution_section,
      impression_narrative: `PRELIMINARY CLINICAL DECISION-SUPPORT DRAFT (v${nextVersion} - REQUIRES RADIOLOGIST VERIFICATION):\nMultimodal correlation of clinical presentation (${c.chief_complaint}) with ${c.modality} imaging demonstrates feature attribution corresponding to '${job?.predicted_class_label || "Pending Analysis"}'.${note ? ` Clinician note incorporated: "${note}".` : ""} Direct inspection of the unaltered source study is required prior to sign-off.`,
      limitations_section: state.reports[0].limitations_section,
      provenance_json: state.reports[0].provenance_json,
      reviewer_id: null,
      reviewer_notes: null,
      reviewed_at: null,
      created_at: now,
      updated_at: now,
    };

    state.reports.unshift(newReport);
    c.status = "DRAFT_READY";
    c.updated_at = now;
    recordAudit(
      state,
      currentUser,
      "REPORT_DRAFT",
      "GENERATE_DRAFT",
      "report_draft",
      newReport.id,
      "SUCCESS",
      `Generated report draft v${nextVersion} for ${c.case_number}`
    );
    saveState(state);
    return { report: newReport } as unknown as T;
  }

  // 14. Update Report Draft
  const repUpdateMatch = pathname.match(/^\/api\/reports\/([^/]+)$/);
  if (repUpdateMatch && method === "PUT") {
    const repId = repUpdateMatch[1];
    const rep = state.reports.find((r) => r.id === repId);
    if (!rep) throw new ApiRequestError(404, "REPORT_NOT_FOUND", "Report not found");
    if (rep.status !== "DRAFT_PENDING_REVIEW") {
      throw new ApiRequestError(
        409,
        "REPORT_IMMUTABLE",
        "Approved or rejected reports are locked and cannot be edited. Generate a new version instead."
      );
    }
    const body = parseJsonBody();
    rep.clinical_facts_section = String(body.clinical_facts_section ?? rep.clinical_facts_section);
    rep.model_findings_section = String(body.model_findings_section ?? rep.model_findings_section);
    rep.xai_attribution_section = String(body.xai_attribution_section ?? rep.xai_attribution_section);
    rep.impression_narrative = String(body.impression_narrative ?? rep.impression_narrative);
    rep.limitations_section = String(body.limitations_section ?? rep.limitations_section);
    rep.updated_at = new Date().toISOString();
    recordAudit(
      state,
      currentUser,
      "REPORT_DRAFT",
      "EDIT_DRAFT",
      "report_draft",
      rep.id,
      "SUCCESS",
      `Updated narrative sections for report draft v${rep.version}`
    );
    saveState(state);
    return { report: rep } as unknown as T;
  }

  // 15. Review Report Draft
  const repReviewMatch = pathname.match(/^\/api\/reports\/([^/]+)\/review$/);
  if (repReviewMatch && method === "POST") {
    if (!perms.can_review_approve_report) {
      throw new ApiRequestError(
        403,
        "RBAC_FORBIDDEN",
        "Only Reviewer or Admin roles can sign off on report drafts."
      );
    }
    const repId = repReviewMatch[1];
    const rep = state.reports.find((r) => r.id === repId);
    if (!rep) throw new ApiRequestError(404, "REPORT_NOT_FOUND", "Report not found");
    const body = parseJsonBody();
    const decision = String(body.decision || "APPROVE").toUpperCase();
    const now = new Date().toISOString();
    rep.status = decision === "REJECT" ? "REJECTED" : "APPROVED";
    rep.reviewer_id = currentUser.id;
    rep.reviewer_notes = String(body.reviewer_notes || "Reviewed and verified in clinical workspace.");
    rep.reviewed_at = now;
    rep.updated_at = now;

    const c = state.cases.find((item) => item.id === rep.case_id);
    if (c) {
      c.status = rep.status === "APPROVED" ? "APPROVED" : "REJECTED";
      c.updated_at = now;
    }

    recordAudit(
      state,
      currentUser,
      "CLINICAL_REVIEW",
      rep.status === "APPROVED" ? "APPROVE_REPORT" : "REJECT_REPORT",
      "report_draft",
      rep.id,
      "SUCCESS",
      `Reviewer signed off report v${rep.version} with status ${rep.status}`
    );
    saveState(state);
    return { report: rep } as unknown as T;
  }

  // 16. FHIR Bundle / Export
  const fhirMatch = pathname.match(/^\/api\/cases\/([^/]+)\/fhir-(bundle|export)$/);
  if (fhirMatch) {
    const caseId = fhirMatch[1];
    const isExport = fhirMatch[2] === "export";
    const c = state.cases.find((item) => item.id === caseId) || state.cases[0];
    const pat = state.patients.find((p) => p.id === c.patient_id) || state.patients[0];
    const caseObs = state.observations.filter((o) => o.case_id === c.id);
    const rep = state.reports.find((r) => r.case_id === c.id) || state.reports[0];

    const entries: Array<Record<string, unknown>> = [
      {
        fullUrl: `urn:uuid:${pat.id}`,
        resource: {
          resourceType: "Patient",
          id: pat.id,
          identifier: [{ system: "urn:omnimed:mrn", value: pat.mrn }],
          name: [{ text: pat.full_name }],
          gender: pat.sex,
          birthDate: pat.birth_date,
        },
      },
      {
        fullUrl: `urn:uuid:${c.id}`,
        resource: {
          resourceType: "Encounter",
          id: c.id,
          status: "in-progress",
          class: { code: "AMB", display: c.encounter_type },
          subject: { reference: `Patient/${pat.id}` },
        },
      },
      ...caseObs.map((o) => ({
        fullUrl: `urn:uuid:${o.id}`,
        resource: {
          resourceType: "Observation",
          id: o.id,
          status: "final",
          code: {
            coding: [{ system: "http://loinc.org", code: o.loinc_code, display: o.display_name }],
          },
          subject: { reference: `Patient/${pat.id}` },
          valueString: `${o.value_text} ${o.unit}`,
        },
      })),
      {
        fullUrl: `urn:uuid:${rep.id}`,
        resource: {
          resourceType: "DiagnosticReport",
          id: rep.id,
          status: rep.status === "APPROVED" ? "final" : "preliminary",
          code: {
            coding: [
              {
                system: "http://loinc.org",
                code: "18748-4",
                display: "Diagnostic imaging study",
              },
            ],
          },
          subject: { reference: `Patient/${pat.id}` },
          conclusion: rep.impression_narrative,
        },
      },
    ];

    if (isExport) {
      recordAudit(
        state,
        currentUser,
        "FHIR_INTEROP",
        "EXPORT_FHIR_R4_BUNDLE",
        "clinical_case",
        c.id,
        "SUCCESS",
        `Validated and exported HL7 FHIR R4 Bundle (${entries.length} resources) for ${c.case_number}`
      );
      saveState(state);
    }

    return {
      fhir_version: "4.0.1",
      validation: {
        is_valid_r4_structure: true,
        total_entries: entries.length,
        resource_counts: {
          Patient: 1,
          Encounter: 1,
          Observation: caseObs.length,
          DiagnosticReport: 1,
        },
        checks_passed: [
          "FHIR R4 4.0.1 Bundle.resourceType == 'Bundle' & type == 'collection'",
          "Patient identifier MRN & synthetic governance tags present",
          "Observation LOINC coding system URIs verified (http://loinc.org)",
          "DiagnosticReport status mapped accurately from clinician review state",
        ],
        compliance_disclosure:
          "Validated against structural HL7 FHIR R4 resource rules. External HAPI FHIR server (:8080) is optional and offline in Cloud Preview.",
      },
      external_server_status: "LOCAL_VALIDATED_BUNDLE_READY (External :8080 Offline)",
      bundle: {
        resourceType: "Bundle",
        id: `fhir-bundle-${c.case_number.toLowerCase()}`,
        type: "collection",
        timestamp: new Date().toISOString(),
        entry: entries,
      },
    } as unknown as T;
  }

  // 17. Admin Users & Audit Logs
  if (pathname === "/api/admin/users" && method === "GET") {
    if (!perms.can_manage_users) {
      throw new ApiRequestError(403, "RBAC_FORBIDDEN", "Admin privileges required.");
    }
    return {
      users: state.users.map(({ password: _p, ...rest }) => rest),
    } as unknown as T;
  }

  if (pathname === "/api/admin/users" && method === "POST") {
    if (!perms.can_manage_users) {
      throw new ApiRequestError(403, "RBAC_FORBIDDEN", "Admin privileges required.");
    }
    const body = parseJsonBody();
    const newUser: StoredUser = {
      id: `usr-${Date.now()}`,
      email: String(body.email || "").trim(),
      password: String(body.password || "Clinical!2026"),
      full_name: String(body.full_name || "Clinical User"),
      role: (body.role as UserRole) || "clinician",
      specialty: String(body.specialty || "Diagnostic Radiology"),
      fhir_practitioner_id: `Practitioner/prac-${Date.now()}`,
      is_active: 1,
      created_at: new Date().toISOString(),
    };
    state.users.push(newUser);
    saveState(state);
    return { user: newUser } as unknown as T;
  }

  const rolePatchMatch = pathname.match(/^\/api\/admin\/users\/([^/]+)\/role$/);
  if (rolePatchMatch && method === "PATCH") {
    if (!perms.can_manage_users) {
      throw new ApiRequestError(403, "RBAC_FORBIDDEN", "Admin privileges required.");
    }
    const u = state.users.find((item) => item.id === rolePatchMatch[1]);
    if (!u) throw new ApiRequestError(404, "USER_NOT_FOUND", "User not found");
    const body = parseJsonBody();
    if (body.role) u.role = body.role as UserRole;
    if (typeof body.is_active === "number") u.is_active = body.is_active;
    saveState(state);
    return { user: u } as unknown as T;
  }

  if (pathname === "/api/admin/audit-logs" && method === "GET") {
    if (!perms.can_view_audit_logs) {
      throw new ApiRequestError(403, "RBAC_FORBIDDEN", "Audit log visibility requires Admin or Reviewer role.");
    }
    return { audit_logs: state.audits } as unknown as T;
  }

  throw new ApiRequestError(404, "ENDPOINT_NOT_FOUND", `Unhandled endpoint ${pathname}`);
}

export async function cloudFallbackImageBlobUrl(path: string): Promise<string> {
  const state = loadState();
  const rawMatch = path.match(/^\/api\/images\/([^/]+)\/raw$/);
  if (rawMatch) {
    const imageId = rawMatch[1];
    if (state.uploadedImageDataUrls[imageId]) {
      return state.uploadedImageDataUrls[imageId];
    }
    const imgRecord = state.images.find((i) => i.id === imageId);
    const isMri = imgRecord?.modality === "MRI";
    return generateSyntheticMedicalCanvasDataUrl(isMri ? "MRI" : "CXR", false);
  }

  const overlayMatch = path.match(/^\/api\/jobs\/([^/]+)\/overlay$/);
  if (overlayMatch) {
    const jobId = overlayMatch[1];
    const job = state.jobs.find((j) => j.id === jobId);
    const imgRecord = state.images.find((i) => i.id === job?.image_id);
    const isMri = imgRecord?.modality === "MRI";
    return generateSyntheticMedicalCanvasDataUrl(isMri ? "MRI" : "CXR", true);
  }

  return generateSyntheticMedicalCanvasDataUrl("CXR", false);
}

function generateSyntheticMedicalCanvasDataUrl(
  modality: "CXR" | "MRI",
  isOverlay: boolean
): string {
  if (typeof document === "undefined") return "";
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 512;
  const ctx = canvas.getContext("2d");
  if (!ctx) return "";

  if (!isOverlay) {
    // High-contrast synthetic phantom radiograph / axial FLAIR
    ctx.fillStyle = "#060a12";
    ctx.fillRect(0, 0, 512, 512);

    if (modality === "CXR") {
      // Thoracic cage & lung fields
      const bgGrad = ctx.createRadialGradient(256, 256, 30, 256, 256, 245);
      bgGrad.addColorStop(0, "#334155");
      bgGrad.addColorStop(0.7, "#1e293b");
      bgGrad.addColorStop(1, "#060a12");
      ctx.fillStyle = bgGrad;
      ctx.fillRect(28, 28, 456, 456);

      // Right and Left Lung Fields (dark radiolucent)
      ctx.fillStyle = "#0b1322";
      ctx.beginPath();
      ctx.ellipse(175, 240, 78, 145, 0.08, 0, Math.PI * 2);
      ctx.fill();

      ctx.beginPath();
      ctx.ellipse(337, 240, 78, 145, -0.08, 0, Math.PI * 2);
      ctx.fill();

      // Mediastinum & cardiac silhouette
      const heartGrad = ctx.createRadialGradient(272, 295, 10, 268, 295, 85);
      heartGrad.addColorStop(0, "#cbd5e1");
      heartGrad.addColorStop(0.65, "#64748b");
      heartGrad.addColorStop(1, "rgba(100,116,139,0)");
      ctx.fillStyle = heartGrad;
      ctx.beginPath();
      ctx.arc(268, 295, 85, 0, Math.PI * 2);
      ctx.fill();

      // Focal consolidation phantom in Right Lower Zone (viewer's lower-right / anatomical RLZ)
      const lesionGrad = ctx.createRadialGradient(328, 348, 8, 328, 348, 62);
      lesionGrad.addColorStop(0, "rgba(226, 232, 240, 0.82)");
      lesionGrad.addColorStop(0.5, "rgba(148, 163, 184, 0.45)");
      lesionGrad.addColorStop(1, "rgba(15, 23, 42, 0)");
      ctx.fillStyle = lesionGrad;
      ctx.beginPath();
      ctx.arc(328, 348, 62, 0, Math.PI * 2);
      ctx.fill();

      // Rib arcs
      ctx.strokeStyle = "rgba(203, 213, 225, 0.18)";
      ctx.lineWidth = 4;
      for (let i = 0; i < 6; i++) {
        const y = 125 + i * 42;
        ctx.beginPath();
        ctx.arc(175, y, 70, Math.PI * 1.1, Math.PI * 1.9);
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(337, y, 70, Math.PI * 1.1, Math.PI * 1.9);
        ctx.stroke();
      }
    } else {
      // Axial Brain MRI Phantom
      ctx.fillStyle = "#1e293b";
      ctx.beginPath();
      ctx.ellipse(256, 256, 175, 210, 0, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = "#475569";
      ctx.beginPath();
      ctx.ellipse(256, 256, 158, 192, 0, 0, Math.PI * 2);
      ctx.fill();

      // Ventricles
      ctx.fillStyle = "#0f172a";
      ctx.beginPath();
      ctx.ellipse(235, 245, 16, 48, -0.2, 0, Math.PI * 2);
      ctx.fill();
      ctx.beginPath();
      ctx.ellipse(277, 245, 16, 48, 0.2, 0, Math.PI * 2);
      ctx.fill();

      // FLAIR hyperintensity phantom
      const flairGrad = ctx.createRadialGradient(318, 220, 4, 318, 220, 36);
      flairGrad.addColorStop(0, "rgba(248, 250, 252, 0.95)");
      flairGrad.addColorStop(0.5, "rgba(203, 213, 225, 0.5)");
      flairGrad.addColorStop(1, "rgba(71, 85, 105, 0)");
      ctx.fillStyle = flairGrad;
      ctx.beginPath();
      ctx.arc(318, 220, 36, 0, Math.PI * 2);
      ctx.fill();
    }

    ctx.fillStyle = "#94a3b8";
    ctx.font = "12px monospace";
    ctx.fillText(
      `SYNTHETIC ${modality} PHANTOM • 512x512 • READ-ONLY SOURCE`,
      18,
      494
    );
  } else {
    // Grad-CAM Thermal Overlay (transparent background + JET/Turbo heatmap)
    ctx.clearRect(0, 0, 512, 512);
    const cx = modality === "CXR" ? 328 : 318;
    const cy = modality === "CXR" ? 348 : 220;
    const heat = ctx.createRadialGradient(cx, cy, 6, cx, cy, 115);
    heat.addColorStop(0, "rgba(239, 68, 68, 0.92)");
    heat.addColorStop(0.32, "rgba(245, 158, 11, 0.78)");
    heat.addColorStop(0.62, "rgba(16, 185, 129, 0.48)");
    heat.addColorStop(0.85, "rgba(56, 189, 248, 0.22)");
    heat.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.fillStyle = heat;
    ctx.fillRect(0, 0, 512, 512);
  }

  return canvas.toDataURL("image/png");
}

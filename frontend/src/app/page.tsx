"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  Brain,
  CheckCircle2,
  ClipboardCheck,
  Database,
  FileCode2,
  FileText,
  Lock,
  LogOut,
  Plus,
  RefreshCw,
  Search,
  Server,
  Shield,
  ShieldAlert,
  Sparkles,
  Stethoscope,
  Upload,
  UserCheck,
  UserPlus,
  Users,
  X,
  XCircle,
} from "lucide-react";
import MedicalImageViewer from "@/components/MedicalImageViewer";
import {
  AnalysisJobRecord,
  apiFetch,
  ApiRequestError,
  AuditLogRecord,
  AuthenticatedUser,
  ClassScoreItem,
  ClinicalCaseRecord,
  MedicalImageRecord,
  ObservationRecord,
  PatientRecord,
  ProvenanceCitation,
  ReportDraftRecord,
  RolePermissions,
  setAuthTokens,
  XaiMetadata,
} from "@/lib/api";

type NavTab =
  | "overview"
  | "patients"
  | "workspace"
  | "reports"
  | "fhir"
  | "admin-users"
  | "audit-status";

interface SystemStatusData {
  rust_backend: { status: string; bind: string; database_mode: string };
  python_ai_service: {
    status: string;
    url: string;
    port: number;
    details: Record<string, unknown>;
  };
  fhir_interoperability: {
    local_r4_validator: string;
    external_fhir_server_url: string;
    external_fhir_server_port: number;
    external_fhir_server_status: string;
  };
  capability_matrix: Array<{
    feature: string;
    status: string;
    notes: string;
  }>;
}

export default function OmniMedApp() {
  const [user, setUser] = useState<AuthenticatedUser | null>(null);
  const [permissions, setPermissions] = useState<RolePermissions | null>(null);
  const [authChecking, setAuthChecking] = useState<boolean>(true);

  // Login State
  const [loginEmail, setLoginEmail] = useState<string>(
    "clinician@omnimed-insight.local"
  );
  const [loginPassword, setLoginPassword] = useState<string>("Clinician!2026");
  const [loginError, setLoginError] = useState<string | null>(null);
  const [loggingIn, setLoggingIn] = useState<boolean>(false);

  // Navigation & Global Banner Feedback
  const [activeTab, setActiveTab] = useState<NavTab>("overview");
  const [bannerNotice, setBannerNotice] = useState<{
    type: "success" | "error" | "warning";
    title: string;
    message: string;
  } | null>(null);

  // System Status & Dashboard
  const [systemStatus, setSystemStatus] = useState<SystemStatusData | null>(
    null
  );
  const [dashboardMetrics, setDashboardMetrics] = useState<{
    authorized_patients_count: number;
    authorized_cases_count: number;
    completed_xai_analyses: number;
    pending_report_drafts: number;
    approved_reports: number;
  } | null>(null);
  const [recentAudits, setRecentAudits] = useState<AuditLogRecord[]>([]);

  // Patients & Cases
  const [patients, setPatients] = useState<PatientRecord[]>([]);
  const [patientScopeNote, setPatientScopeNote] = useState<string>("");
  const [patientSearch, setPatientSearch] = useState<string>("");
  const [cases, setCases] = useState<ClinicalCaseRecord[]>([]);
  const [modalityFilter, setModalityFilter] = useState<string>("");

  // Active Case Workspace
  const [selectedCaseId, setSelectedCaseId] = useState<string>("case-synth-001");
  const [activeCase, setActiveCase] = useState<ClinicalCaseRecord | null>(null);
  const [activePatient, setActivePatient] = useState<PatientRecord | null>(null);
  const [caseObservations, setCaseObservations] = useState<ObservationRecord[]>(
    []
  );
  const [caseImages, setCaseImages] = useState<MedicalImageRecord[]>([]);
  const [selectedImageId, setSelectedImageId] = useState<string | null>(null);
  const [caseJobs, setCaseJobs] = useState<AnalysisJobRecord[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [caseReports, setCaseReports] = useState<ReportDraftRecord[]>([]);
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);
  const [workspaceLoading, setWorkspaceLoading] = useState<boolean>(false);

  // Action Loading States
  const [uploadingImage, setUploadingImage] = useState<boolean>(false);
  const [runningAnalysis, setRunningAnalysis] = useState<boolean>(false);
  const [xaiMethodChoice, setXaiMethodChoice] = useState<
    "GRAD_CAM" | "GRAD_CAM_PLUS_OCCLUSION"
  >("GRAD_CAM");
  const [generatingDraft, setGeneratingDraft] = useState<boolean>(false);
  const [clinicianContextNote, setClinicianContextNote] = useState<string>("");

  // Report Edit & Review State
  const [editFacts, setEditFacts] = useState<string>("");
  const [editModelFindings, setEditModelFindings] = useState<string>("");
  const [editXaiSection, setEditXaiSection] = useState<string>("");
  const [editImpression, setEditImpression] = useState<string>("");
  const [editLimitations, setEditLimitations] = useState<string>("");
  const [reviewerNote, setReviewerNote] = useState<string>("");
  const [savingReport, setSavingReport] = useState<boolean>(false);

  // Observation Form
  const [obsLoinc, setObsLoinc] = useState<string>("8867-4");
  const [obsName, setObsName] = useState<string>("Heart rate");
  const [obsVal, setObsVal] = useState<string>("88");
  const [obsUnit, setObsUnit] = useState<string>("/min");
  const [obsRange, setObsRange] = useState<string>("60 - 100");
  const [obsInterp, setObsInterp] = useState<string>("NORMAL (Synthetic)");

  // FHIR Bundle State
  const [fhirData, setFhirData] = useState<{
    fhir_version: string;
    validation: {
      is_valid_r4_structure: boolean;
      total_entries: number;
      resource_counts: Record<string, number>;
      checks_passed: string[];
      compliance_disclosure: string;
    };
    external_server_status: string;
    bundle: Record<string, unknown>;
  } | null>(null);
  const [loadingFhir, setLoadingFhir] = useState<boolean>(false);

  // Admin Users & Audit Logs
  const [adminUsers, setAdminUsers] = useState<
    Array<{
      id: string;
      email: string;
      full_name: string;
      role: string;
      specialty: string;
      fhir_practitioner_id: string;
      is_active: number;
      created_at: string;
    }>
  >([]);
  const [newUserEmail, setNewUserEmail] = useState<string>("");
  const [newUserName, setNewUserName] = useState<string>("");
  const [newUserRole, setNewUserRole] = useState<string>("clinician");
  const [newUserSpecialty, setNewUserSpecialty] = useState<string>(
    "Diagnostic Radiology"
  );
  const [newUserPassword, setNewUserPassword] = useState<string>("");
  const [fullAuditLogs, setFullAuditLogs] = useState<AuditLogRecord[]>([]);

  // New Patient & Case Creation Modal State
  const [showAddPatientModal, setShowAddPatientModal] = useState<boolean>(false);
  const [newPatientName, setNewPatientName] = useState<string>("");
  const [newPatientDob, setNewPatientDob] = useState<string>("1985-05-20");
  const [newPatientSex, setNewPatientSex] = useState<string>("male");
  const [newPatientSummary, setNewPatientSummary] = useState<string>("");
  const [newPatientAllergies, setNewPatientAllergies] = useState<string>("");
  const [newPatientConditions, setNewPatientConditions] = useState<string>("");
  const [submittingPatient, setSubmittingPatient] = useState<boolean>(false);

  const [showAddCaseModal, setShowAddCaseModal] = useState<boolean>(false);
  const [targetPatientForCase, setTargetPatientForCase] = useState<PatientRecord | null>(null);
  const [newCaseModality, setNewCaseModality] = useState<string>("CXR");
  const [newCaseBodyPart, setNewCaseBodyPart] = useState<string>("CHEST");
  const [newCasePriority, setNewCasePriority] = useState<string>("URGENT");
  const [newCaseEncounterType, setNewCaseEncounterType] = useState<string>("Outpatient Clinical Evaluation");
  const [newCaseChiefComplaint, setNewCaseChiefComplaint] = useState<string>("");
  const [newCaseClinicalHistory, setNewCaseClinicalHistory] = useState<string>("");
  const [submittingCase, setSubmittingCase] = useState<boolean>(false);

  const loadSystemStatus = useCallback(async () => {
    try {
      const st = await apiFetch<SystemStatusData>("/api/system/status");
      setSystemStatus(st);
    } catch {
      // ignore when backend is starting
    }
  }, []);

  const loadDashboardAndLists = useCallback(async () => {
    try {
      const [dash, patResp, caseResp] = await Promise.all([
        apiFetch<{
          metrics: {
            authorized_patients_count: number;
            authorized_cases_count: number;
            completed_xai_analyses: number;
            pending_report_drafts: number;
            approved_reports: number;
          };
          recent_audit_events: AuditLogRecord[];
        }>("/api/dashboard"),
        apiFetch<{
          patients: PatientRecord[];
          scope_note: string;
        }>(`/api/patients?search=${encodeURIComponent(patientSearch)}`),
        apiFetch<{ cases: ClinicalCaseRecord[] }>(
          `/api/cases?modality=${encodeURIComponent(modalityFilter)}`
        ),
      ]);
      setDashboardMetrics(dash.metrics);
      setRecentAudits(dash.recent_audit_events);
      setPatients(patResp.patients);
      setPatientScopeNote(patResp.scope_note);
      setCases(caseResp.cases);
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 401) {
        setUser(null);
      }
    }
  }, [patientSearch, modalityFilter]);

  const loadCaseWorkspace = useCallback(async (caseId: string) => {
    if (!caseId) return;
    setWorkspaceLoading(true);
    try {
      const data = await apiFetch<{
        case: ClinicalCaseRecord;
        patient: PatientRecord;
        observations: ObservationRecord[];
        images: MedicalImageRecord[];
        analysis_jobs: AnalysisJobRecord[];
        report_drafts: ReportDraftRecord[];
      }>(`/api/cases/${caseId}`);

      setActiveCase(data.case);
      setActivePatient(data.patient);
      setCaseObservations(data.observations);
      setCaseImages(data.images);
      if (data.images.length > 0) {
        setSelectedImageId((prev) =>
          prev && data.images.some((i) => i.id === prev)
            ? prev
            : data.images[0].id
        );
      } else {
        setSelectedImageId(null);
      }

      setCaseJobs(data.analysis_jobs);
      if (data.analysis_jobs.length > 0) {
        setSelectedJobId(data.analysis_jobs[0].id);
      } else {
        setSelectedJobId(null);
      }

      setCaseReports(data.report_drafts);
      if (data.report_drafts.length > 0) {
        const rep = data.report_drafts[0];
        setSelectedReportId(rep.id);
        setEditFacts(rep.clinical_facts_section);
        setEditModelFindings(rep.model_findings_section);
        setEditXaiSection(rep.xai_attribution_section);
        setEditImpression(rep.impression_narrative);
        setEditLimitations(rep.limitations_section);
      } else {
        setSelectedReportId(null);
      }
    } catch (err) {
      if (err instanceof ApiRequestError) {
        setBannerNotice({
          type: "error",
          title: `Case Access Error (${err.errorCode})`,
          message: err.message,
        });
      }
    } finally {
      setWorkspaceLoading(false);
    }
  }, []);

  // Initial Session Restore & System Status Probe
  useEffect(() => {
    loadSystemStatus();
    apiFetch<{
      authenticated: boolean;
      user: AuthenticatedUser;
      permissions: RolePermissions;
    }>("/api/auth/me")
      .then((res) => {
        setAuthTokens(null, res.user.csrf_token);
        setUser(res.user);
        setPermissions(res.permissions);
      })
      .catch(() => {
        setUser(null);
      })
      .finally(() => {
        setAuthChecking(false);
      });
  }, [loadSystemStatus]);

  useEffect(() => {
    if (user) {
      loadDashboardAndLists();
      loadCaseWorkspace(selectedCaseId);
    }
  }, [user, selectedCaseId, loadDashboardAndLists, loadCaseWorkspace]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoggingIn(true);
    setLoginError(null);
    try {
      const resp = await apiFetch<{
        user: AuthenticatedUser;
        session_token: string;
        csrf_token: string;
      }>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: loginEmail,
          password: loginPassword,
        }),
      });
      setAuthTokens(resp.session_token, resp.csrf_token);
      const me = await apiFetch<{
        user: AuthenticatedUser;
        permissions: RolePermissions;
      }>("/api/auth/me");
      setUser(me.user);
      setPermissions(me.permissions);
      setBannerNotice(null);
    } catch (err) {
      setLoginError(
        err instanceof Error ? err.message : "Authentication failed"
      );
    } finally {
      setLoggingIn(false);
    }
  };

  const handleLogout = async () => {
    try {
      await apiFetch("/api/auth/logout", { method: "POST" });
    } catch {
      // ignore
    }
    setAuthTokens(null, null);
    setUser(null);
    setPermissions(null);
    setActiveTab("overview");
  };

  const handleTestIdorBoundary = async () => {
    try {
      await apiFetch("/api/patients/pat-synth-003");
      setBannerNotice({
        type: "warning",
        title: "Admin Override Active",
        message:
          "As an Administrator, you have global audit visibility into pat-synth-003. Sign in as Clinician, Reviewer, or Read-Only to observe server-side 403 IDOR blocking.",
      });
    } catch (err) {
      if (err instanceof ApiRequestError) {
        setBannerNotice({
          type: "error",
          title: `Server-Side IDOR Guard Verified (HTTP ${err.status} • ${err.errorCode})`,
          message: `${err.message} An immutable RBAC_DENIED event has been written to the audit log.`,
        });
        loadDashboardAndLists();
      }
    }
  };

  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !activeCase) return;
    setUploadingImage(true);
    setBannerNotice(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await apiFetch<{ image: MedicalImageRecord }>(
        `/api/cases/${activeCase.id}/images`,
        {
          method: "POST",
          body: formData,
        }
      );
      setBannerNotice({
        type: "success",
        title: "Medical Image Validated & Stored",
        message: `Verified ${res.image.mime_type} header (${res.image.width}×${res.image.height}px, SHA-256: ${res.image.sha256_digest.slice(0, 12)}…).`,
      });
      await loadCaseWorkspace(activeCase.id);
      setSelectedImageId(res.image.id);
    } catch (err) {
      setBannerNotice({
        type: "error",
        title: "Upload Rejected by Security / Modality Validator",
        message: err instanceof Error ? err.message : "Upload failed",
      });
    } finally {
      setUploadingImage(false);
      e.target.value = "";
    }
  };

  const handleRunAnalysis = async () => {
    if (!activeCase || !selectedImageId) return;
    setRunningAnalysis(true);
    setBannerNotice(null);
    try {
      const res = await apiFetch<{ job: AnalysisJobRecord }>(
        `/api/cases/${activeCase.id}/analyze`,
        {
          method: "POST",
          body: JSON.stringify({
            image_id: selectedImageId,
            xai_method: xaiMethodChoice,
          }),
        }
      );
      setBannerNotice({
        type: "success",
        title: "PyTorch DenseNet-121 + Grad-CAM Analysis Completed",
        message: `Model ${res.job.model_version} executed on ${res.job.execution_device}. Predicted pattern: ${res.job.predicted_class_label} (${((res.job.predicted_probability || 0) * 100).toFixed(1)}%).`,
      });
      await loadCaseWorkspace(activeCase.id);
      await loadDashboardAndLists();
      setSelectedJobId(res.job.id);
    } catch (err) {
      setBannerNotice({
        type: "error",
        title: "AI Inference Error",
        message: err instanceof Error ? err.message : "Failed to run analysis",
      });
    } finally {
      setRunningAnalysis(false);
    }
  };

  const handleAddObservation = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeCase) return;
    try {
      await apiFetch(`/api/cases/${activeCase.id}/observations`, {
        method: "POST",
        body: JSON.stringify({
          loinc_code: obsLoinc,
          display_name: obsName,
          value_text: obsVal,
          unit: obsUnit,
          reference_range: obsRange,
          interpretation: obsInterp,
        }),
      });
      setBannerNotice({
        type: "success",
        title: "LOINC Observation Recorded",
        message: `Added ${obsName} (${obsLoinc}) to ${activeCase.case_number}.`,
      });
      await loadCaseWorkspace(activeCase.id);
    } catch (err) {
      setBannerNotice({
        type: "error",
        title: "Could Not Add Observation",
        message: err instanceof Error ? err.message : "Failed",
      });
    }
  };

  const handleCreatePatient = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newPatientName.trim() || !newPatientDob.trim() || !newPatientSummary.trim()) {
      setBannerNotice({
        type: "error",
        title: "Validation Error",
        message: "Nama lengkap, tanggal lahir (YYYY-MM-DD), dan ringkasan klinis wajib diisi.",
      });
      return;
    }
    setSubmittingPatient(true);
    setBannerNotice(null);
    try {
      const allergiesArr = newPatientAllergies
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const conditionsArr = newPatientConditions
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);

      const res = await apiFetch<{ patient: PatientRecord; message: string }>("/api/patients", {
        method: "POST",
        body: JSON.stringify({
          full_name: newPatientName.trim(),
          birth_date: newPatientDob.trim(),
          sex: newPatientSex,
          clinical_summary: newPatientSummary.trim(),
          allergies: allergiesArr.length > 0 ? allergiesArr : undefined,
          active_conditions: conditionsArr.length > 0 ? conditionsArr : undefined,
        }),
      });

      setBannerNotice({
        type: "success",
        title: "Pasien Baru Berhasil Didaftarkan",
        message: `Pasien ${res.patient.full_name} (${res.patient.mrn}) berhasil ditambahkan dan ditugaskan ke tim klinis Anda.`,
      });
      await loadDashboardAndLists();
      setShowAddPatientModal(false);
      setNewPatientName("");
      setNewPatientSummary("");
      setNewPatientAllergies("");
      setNewPatientConditions("");
    } catch (err) {
      setBannerNotice({
        type: "error",
        title: "Gagal Mendaftarkan Pasien",
        message: err instanceof Error ? err.message : "Terjadi kesalahan saat pendaftaran pasien.",
      });
    } finally {
      setSubmittingPatient(false);
    }
  };

  const handleCreateCase = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!targetPatientForCase) return;
    if (!newCaseChiefComplaint.trim()) {
      setBannerNotice({
        type: "error",
        title: "Validation Error",
        message: "Keluhan utama kasus (chief complaint) wajib diisi.",
      });
      return;
    }
    setSubmittingCase(true);
    setBannerNotice(null);
    try {
      const res = await apiFetch<{ case: ClinicalCaseRecord }>("/api/cases", {
        method: "POST",
        body: JSON.stringify({
          patient_id: targetPatientForCase.id,
          encounter_type: newCaseEncounterType.trim() || "Outpatient Clinical Evaluation",
          modality: newCaseModality,
          body_part: newCaseBodyPart,
          chief_complaint: newCaseChiefComplaint.trim(),
          clinical_history:
            newCaseClinicalHistory.trim() ||
            `Pemeriksaan pencitraan ${newCaseModality} untuk evaluasi klinis ${newCaseChiefComplaint.trim()}.`,
          priority: newCasePriority,
        }),
      });

      setBannerNotice({
        type: "success",
        title: `Kasus Baru ${res.case.case_number} Dibuka`,
        message: `Kasus pencitraan ${res.case.modality} (${res.case.body_part}) berhasil dibuka untuk pasien ${targetPatientForCase.full_name}. Beralih ke Workspace untuk mengunggah gambar.`,
      });

      await loadDashboardAndLists();
      setSelectedCaseId(res.case.id);
      setShowAddCaseModal(false);
      setActiveTab("workspace");
    } catch (err) {
      setBannerNotice({
        type: "error",
        title: "Gagal Membuka Kasus Baru",
        message: err instanceof Error ? err.message : "Terjadi kesalahan saat membuka kasus.",
      });
    } finally {
      setSubmittingCase(false);
    }
  };

  const handleGenerateDraft = async () => {
    if (!activeCase) return;
    setGeneratingDraft(true);
    setBannerNotice(null);
    try {
      const noteSent = clinicianContextNote.trim();
      const res = await apiFetch<{ report: ReportDraftRecord }>(
        `/api/cases/${activeCase.id}/reports/draft`,
        {
          method: "POST",
          body: JSON.stringify({
            analysis_job_id: selectedJobId,
            clinician_context_note: noteSent,
          }),
        }
      );
      setBannerNotice({
        type: "success",
        title: `Draft Laporan Versi v${res.report.version} Berhasil Dibuat`,
        message: noteSent
          ? `Catatan Anda ("${noteSent}") telah berhasil dimasukkan ke Bagian 1 (Sourced Clinical Facts) pada draf versi v${res.report.version}. Silakan verifikasi seluruh draf di bawah.`
          : `Draf versi v${res.report.version} berhasil digenerate dari observasi klinis dan temuan AI.`,
      });
      await loadCaseWorkspace(activeCase.id);
      setSelectedReportId(res.report.id);
      setEditFacts(res.report.clinical_facts_section);
      setEditModelFindings(res.report.model_findings_section);
      setEditXaiSection(res.report.xai_attribution_section);
      setEditImpression(res.report.impression_narrative);
      setEditLimitations(res.report.limitations_section);
      setClinicianContextNote("");
      await loadDashboardAndLists();
      setActiveTab("reports");
    } catch (err) {
      setBannerNotice({
        type: "error",
        title: "Draft Generation Failed",
        message: err instanceof Error ? err.message : "Error",
      });
    } finally {
      setGeneratingDraft(false);
    }
  };

  const handleSaveReportEdits = async () => {
    if (!selectedReportId || !activeCase) return;
    setSavingReport(true);
    try {
      await apiFetch(`/api/reports/${selectedReportId}`, {
        method: "PUT",
        body: JSON.stringify({
          clinical_facts_section: editFacts,
          model_findings_section: editModelFindings,
          xai_attribution_section: editXaiSection,
          impression_narrative: editImpression,
          limitations_section: editLimitations,
        }),
      });
      setBannerNotice({
        type: "success",
        title: "Report Draft Saved",
        message: "Updated draft sections and recorded edit event in audit log.",
      });
      await loadCaseWorkspace(activeCase.id);
    } catch (err) {
      setBannerNotice({
        type: "error",
        title: "Could Not Update Draft",
        message: err instanceof Error ? err.message : "Error",
      });
    } finally {
      setSavingReport(false);
    }
  };

  const handleReviewDecision = async (decision: "APPROVE" | "REJECT") => {
    if (!selectedReportId || !activeCase) return;
    setSavingReport(true);
    try {
      await apiFetch(`/api/reports/${selectedReportId}/review`, {
        method: "POST",
        body: JSON.stringify({
          decision,
          reviewer_notes: reviewerNote,
        }),
      });
      setBannerNotice({
        type: "success",
        title: `Report Draft ${decision === "APPROVE" ? "Approved" : "Rejected"}`,
        message: `Reviewer sign-off recorded with timestamp and provenance.`,
      });
      setReviewerNote("");
      await loadCaseWorkspace(activeCase.id);
      await loadDashboardAndLists();
    } catch (err) {
      setBannerNotice({
        type: "error",
        title: "Review Sign-Off Rejected",
        message: err instanceof Error ? err.message : "Error",
      });
    } finally {
      setSavingReport(false);
    }
  };

  const loadFhirBundle = useCallback(
    async (doExport: boolean) => {
      if (!activeCase) return;
      setLoadingFhir(true);
      try {
        const path = doExport
          ? `/api/cases/${activeCase.id}/fhir-export`
          : `/api/cases/${activeCase.id}/fhir-bundle`;
        const data = await apiFetch<{
          fhir_version: string;
          validation: {
            is_valid_r4_structure: boolean;
            total_entries: number;
            resource_counts: Record<string, number>;
            checks_passed: string[];
            compliance_disclosure: string;
          };
          external_server_status: string;
          bundle: Record<string, unknown>;
        }>(path, {
          method: doExport ? "POST" : "GET",
        });
        setFhirData(data);
        if (doExport) {
          setBannerNotice({
            type: "success",
            title: "FHIR R4 Bundle Validated & Recorded",
            message: `Status: ${data.external_server_status}`,
          });
        }
      } catch (err) {
        setBannerNotice({
          type: "error",
          title: "FHIR Bundle Error",
          message: err instanceof Error ? err.message : "Failed",
        });
      } finally {
        setLoadingFhir(false);
      }
    },
    [activeCase]
  );

  const loadAdminUsers = useCallback(async () => {
    try {
      const res = await apiFetch<{
        users: Array<{
          id: string;
          email: string;
          full_name: string;
          role: string;
          specialty: string;
          fhir_practitioner_id: string;
          is_active: number;
          created_at: string;
        }>;
      }>("/api/admin/users");
      setAdminUsers(res.users);
    } catch (err) {
      if (err instanceof ApiRequestError) {
        setBannerNotice({
          type: "error",
          title: `Admin Access Denied (${err.errorCode})`,
          message: err.message,
        });
      }
    }
  }, []);

  const loadAuditTrail = useCallback(async () => {
    try {
      const res = await apiFetch<{ audit_logs: AuditLogRecord[] }>(
        "/api/admin/audit-logs"
      );
      setFullAuditLogs(res.audit_logs);
    } catch (err) {
      if (err instanceof ApiRequestError) {
        setBannerNotice({
          type: "error",
          title: `Audit Log Access Denied (${err.errorCode})`,
          message: err.message,
        });
      }
    }
  }, []);

  useEffect(() => {
    if (!user) return;
    if (activeTab === "fhir") {
      loadFhirBundle(false);
    } else if (activeTab === "admin-users") {
      loadAdminUsers();
    } else if (activeTab === "audit-status") {
      loadSystemStatus();
      if (permissions?.can_view_audit_logs) {
        loadAuditTrail();
      }
    }
  }, [
    user,
    activeTab,
    permissions,
    loadFhirBundle,
    loadAdminUsers,
    loadAuditTrail,
    loadSystemStatus,
  ]);

  const selectedImage = useMemo(
    () => caseImages.find((i) => i.id === selectedImageId) || caseImages[0] || null,
    [caseImages, selectedImageId]
  );

  const selectedJob = useMemo(
    () => caseJobs.find((j) => j.id === selectedJobId) || caseJobs[0] || null,
    [caseJobs, selectedJobId]
  );

  const selectedReport = useMemo(
    () =>
      caseReports.find((r) => r.id === selectedReportId) ||
      caseReports[0] ||
      null,
    [caseReports, selectedReportId]
  );

  const parsedClassScores: ClassScoreItem[] = useMemo(() => {
    if (!selectedJob) return [];
    try {
      return JSON.parse(selectedJob.class_scores_json) as ClassScoreItem[];
    } catch {
      return [];
    }
  }, [selectedJob]);

  const parsedXaiMeta: XaiMetadata | null = useMemo(() => {
    if (!selectedJob) return null;
    try {
      return JSON.parse(selectedJob.xai_metadata_json) as XaiMetadata;
    } catch {
      return null;
    }
  }, [selectedJob]);

  const parsedLimitations: string[] = useMemo(() => {
    if (!selectedJob) return [];
    try {
      return JSON.parse(selectedJob.limitations_json) as string[];
    } catch {
      return [];
    }
  }, [selectedJob]);

  const parsedProvenance: ProvenanceCitation[] = useMemo(() => {
    if (!selectedReport) return [];
    try {
      return JSON.parse(selectedReport.provenance_json) as ProvenanceCitation[];
    } catch {
      return [];
    }
  }, [selectedReport]);

  if (authChecking) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-900 text-slate-100">
        <div className="flex items-center gap-3">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-sky-400 border-t-transparent" />
          <span className="text-sm font-medium">
            Initializing OmniMed Insight (XAI) Security Boundary...
          </span>
        </div>
      </div>
    );
  }

  // =========================================================================
  // VIEW 1: SECURE LOGIN & ROLE PROVISIONING SCREEN
  // =========================================================================
  if (!user) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col justify-between">
        {/* Top Clinical Safety Disclosure Bar */}
        <div className="border-b border-amber-500/30 bg-amber-950/60 px-6 py-2.5 text-xs text-amber-200">
          <div className="mx-auto flex max-w-6xl items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <ShieldAlert className="h-4 w-4 shrink-0 text-amber-400" />
              <span>
                <strong>CLINICAL DECISION-SUPPORT SYSTEM:</strong> Research-calibrated XAI &amp; report drafting for qualified healthcare professionals. Never use as an autonomous diagnostic replacement.
              </span>
            </div>
            <span className="rounded bg-amber-500/20 px-2 py-0.5 font-mono text-[11px] text-amber-300">
              SYNTHETIC DATA MODE
            </span>
          </div>
        </div>

        <div className="mx-auto my-auto grid w-full max-w-6xl grid-cols-1 gap-8 px-6 py-12 lg:grid-cols-12">
          {/* Left Branding & Architecture Overview */}
          <div className="space-y-6 lg:col-span-7">
            <div className="inline-flex items-center gap-2.5 rounded-full border border-sky-500/30 bg-sky-500/10 px-3.5 py-1.5 text-xs font-semibold text-sky-300">
              <Stethoscope className="h-4 w-4" />
              OmniMed Insight (XAI) • Multimodal Medical AI Platform
            </div>
            <h1 className="text-3xl font-bold tracking-tight text-white sm:text-4xl">
              Explainable Medical Imaging, Evidence-Grounded Reporting &amp; FHIR R4 Interoperability
            </h1>
            <p className="text-sm leading-relaxed text-slate-300">
              Protected by a Rust (Axum + SQLx) security boundary on port{" "}
              <code className="text-sky-300">8100</code> and an isolated PyTorch DenseNet-121 + Grad-CAM inference microservice on port{" "}
              <code className="text-sky-300">8200</code>.
            </p>

            {/* Quick-Fill Synthetic Role Accounts for Evaluation */}
            <div className="rounded-xl border border-slate-800 bg-slate-900/90 p-5 space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Provisioned Local RBAC Demonstration Accounts (Click to Fill)
                </h2>
                <span className="text-[11px] text-sky-400">
                  Argon2id + HttpOnly Session + CSRF
                </span>
              </div>
              <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                {[
                  {
                    role: "Clinician",
                    email: "clinician@omnimed-insight.local",
                    pass: "Clinician!2026",
                    desc: "Upload scans, run Grad-CAM, draft & edit reports",
                  },
                  {
                    role: "Reviewer",
                    email: "reviewer@omnimed-insight.local",
                    pass: "Reviewer!2026",
                    desc: "Inspect XAI, approve/reject drafts, view audit trail",
                  },
                  {
                    role: "Administrator",
                    email: "admin@omnimed-insight.local",
                    pass: "OmniMed!Admin#2026",
                    desc: "Manage users, roles, system status & full audit logs",
                  },
                  {
                    role: "Read-Only",
                    email: "readonly@omnimed-insight.local",
                    pass: "Readonly!2026",
                    desc: "View assigned cases & XAI only; write actions blocked",
                  },
                ].map((acct) => (
                  <button
                    key={acct.email}
                    type="button"
                    onClick={() => {
                      setLoginEmail(acct.email);
                      setLoginPassword(acct.pass);
                    }}
                    className="flex flex-col items-start rounded-lg border border-slate-800 bg-slate-950/80 p-3 text-left transition hover:border-sky-500/60 hover:bg-slate-900"
                  >
                    <div className="flex w-full items-center justify-between">
                      <span className="text-xs font-bold text-white">
                        {acct.role}
                      </span>
                      <span className="font-mono text-[11px] text-sky-400">
                        {acct.email}
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] text-slate-400">{acct.desc}</p>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Right Login Card */}
          <div className="lg:col-span-5">
            <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-xl">
              <div className="flex items-center gap-3 border-b border-slate-800 pb-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-sky-600 text-white">
                  <Lock className="h-5 w-5" />
                </div>
                <div>
                  <h2 className="text-base font-bold text-white">
                    Authorized Clinician Sign-In
                  </h2>
                  <p className="text-xs text-slate-400">
                    Server-verified RBAC &amp; patient assignment boundary
                  </p>
                </div>
              </div>

              {loginError && (
                <div className="mt-4 flex items-start gap-2 rounded-lg border border-rose-500/40 bg-rose-950/60 p-3 text-xs text-rose-200">
                  <AlertCircle className="h-4 w-4 shrink-0 text-rose-400 mt-0.5" />
                  <span>{loginError}</span>
                </div>
              )}

              <form onSubmit={handleLogin} className="mt-5 space-y-4">
                <div>
                  <label
                    htmlFor="login-email"
                    className="block text-xs font-medium text-slate-300"
                  >
                    Institutional Email Address
                  </label>
                  <input
                    id="login-email"
                    type="email"
                    required
                    value={loginEmail}
                    onChange={(e) => setLoginEmail(e.target.value)}
                    className="mt-1.5 w-full rounded-lg border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-sm text-white placeholder-slate-500"
                  />
                </div>

                <div>
                  <label
                    htmlFor="login-password"
                    className="block text-xs font-medium text-slate-300"
                  >
                    Password
                  </label>
                  <input
                    id="login-password"
                    type="password"
                    required
                    value={loginPassword}
                    onChange={(e) => setLoginPassword(e.target.value)}
                    className="mt-1.5 w-full rounded-lg border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-sm text-white placeholder-slate-500"
                  />
                </div>

                <button
                  type="submit"
                  disabled={loggingIn}
                  className="w-full rounded-lg bg-sky-600 px-4 py-2.5 text-sm font-semibold text-white shadow hover:bg-sky-500 disabled:opacity-50"
                >
                  {loggingIn
                    ? "Verifying Argon2id Credentials..."
                    : "Sign In to Clinical Workspace"}
                </button>
              </form>

              {/* Live Service Connectivity Footer */}
              <div className="mt-6 border-t border-slate-800 pt-4 text-xs text-slate-400 space-y-1.5">
                <div className="flex items-center justify-between">
                  <span>Rust Security API (:8100)</span>
                  <span className="font-mono text-emerald-400">
                    {systemStatus ? "ONLINE" : "PROBING..."}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Python Medical XAI Service (:8200)</span>
                  <span
                    className={`font-mono ${
                      systemStatus?.python_ai_service.status === "ONLINE"
                        ? "text-emerald-400"
                        : "text-amber-400"
                    }`}
                  >
                    {systemStatus?.python_ai_service.status || "PROBING..."}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <footer className="border-t border-slate-900 px-6 py-4 text-center text-xs text-slate-500">
          OmniMed Insight (XAI) • Ports: Frontend 3100 | Rust API 8100 | Python AI 8200 | Optional FHIR 8300 | PostgreSQL 5433
        </footer>
      </div>
    );
  }

  // =========================================================================
  // AUTHENTICATED APPLICATION SHELL
  // =========================================================================
  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      {/* Persistent Clinical Safety & Synthetic Data Banner */}
      <div className="bg-slate-900 text-slate-200 border-b border-slate-800 px-4 py-2 text-xs">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1 rounded bg-amber-500/20 px-2 py-0.5 font-semibold text-amber-300 border border-amber-500/30">
              <AlertTriangle className="h-3.5 w-3.5" />
              DECISION SUPPORT ONLY
            </span>
            <span className="text-slate-300">
              All patient records are <strong>[SYNTHETIC]</strong>. Model outputs &amp; Grad-CAM maps are{" "}
              <strong>RESEARCH_UNVERIFIED</strong> and require clinician sign-off.
            </span>
          </div>
          <div className="flex items-center gap-3 font-mono text-[11px] text-slate-400">
            <span>API :8100</span>
            <span>•</span>
            <span>
              AI :8200 ({systemStatus?.python_ai_service.status || "READY"})
            </span>
          </div>
        </div>
      </div>

      {/* Top Navigation Header */}
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-sky-700 text-white shadow-sm">
              <Stethoscope className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-base font-bold tracking-tight text-slate-900">
                  OmniMed Insight
                </span>
                <span className="rounded-md bg-sky-50 px-2 py-0.5 text-[11px] font-semibold text-sky-800 border border-sky-200">
                  XAI + FHIR R4
                </span>
              </div>
              <p className="text-xs text-slate-500">
                Multimodal Clinical Decision-Support Workspace
              </p>
            </div>
          </div>

          {/* Primary Navigation Tabs */}
          <nav
            aria-label="Primary Workspace Navigation"
            className="flex flex-wrap items-center gap-1"
          >
            {[
              { id: "overview", label: "Overview", icon: Activity },
              { id: "patients", label: "Patients & Cases", icon: Users },
              {
                id: "workspace",
                label: "Image & XAI Workspace",
                icon: Brain,
              },
              {
                id: "reports",
                label: "Report Drafting & Review",
                icon: FileText,
              },
              { id: "fhir", label: "FHIR R4 Bundle", icon: FileCode2 },
              {
                id: "admin-users",
                label: "Users & RBAC",
                icon: UserCheck,
              },
              {
                id: "audit-status",
                label: "Audit & System Status",
                icon: Shield,
              },
            ].map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveTab(tab.id as NavTab)}
                  className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-semibold transition ${
                    isActive
                      ? "bg-sky-700 text-white shadow-sm"
                      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {tab.label}
                </button>
              );
            })}
          </nav>

          {/* Active User & Role Indicator */}
          <div className="flex items-center gap-3">
            <div className="text-right">
              <div className="flex items-center justify-end gap-1.5">
                <span className="text-xs font-semibold text-slate-900">
                  {user.full_name}
                </span>
                <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-bold uppercase text-slate-800 border border-slate-300">
                  {user.role}
                </span>
              </div>
              <p className="text-[11px] text-slate-500">{user.specialty}</p>
            </div>
            <button
              type="button"
              onClick={handleLogout}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
            >
              <LogOut className="h-3.5 w-3.5" />
              Sign Out
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Container */}
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 space-y-6">
        {/* Global Notification / Error Alert */}
        {bannerNotice && (
          <div
            role="alert"
            className={`flex items-start justify-between gap-4 rounded-xl border p-4 text-xs shadow-sm ${
              bannerNotice.type === "success"
                ? "border-emerald-300 bg-emerald-50 text-emerald-950"
                : bannerNotice.type === "warning"
                ? "border-amber-300 bg-amber-50 text-amber-950"
                : "border-rose-300 bg-rose-50 text-rose-950"
            }`}
          >
            <div className="flex items-start gap-2.5">
              {bannerNotice.type === "success" ? (
                <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-700 mt-0.5" />
              ) : bannerNotice.type === "warning" ? (
                <AlertTriangle className="h-4 w-4 shrink-0 text-amber-700 mt-0.5" />
              ) : (
                <XCircle className="h-4 w-4 shrink-0 text-rose-700 mt-0.5" />
              )}
              <div>
                <p className="font-bold">{bannerNotice.title}</p>
                <p className="mt-0.5">{bannerNotice.message}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setBannerNotice(null)}
              className="text-xs font-semibold underline"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* =============================================================== */}
        {/* TAB 1: OVERVIEW DASHBOARD (VERIFIED OPERATIONAL METRICS ONLY)   */}
        {/* =============================================================== */}
        {activeTab === "overview" && (
          <div className="space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h1 className="text-xl font-bold text-slate-900">
                  Clinical Operations &amp; XAI Governance Overview
                </h1>
                <p className="text-xs text-slate-600">
                  Live metrics retrieved from the Rust SQLx backend on port 8100. No simulated counters.
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  loadDashboardAndLists();
                  loadSystemStatus();
                }}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                Refresh Verified State
              </button>
            </div>

            {/* Verified Metric Cards */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
              {[
                {
                  label: "Authorized Synthetic Patients",
                  value: dashboardMetrics?.authorized_patients_count ?? 0,
                  sub: "Scoped by RBAC assignment",
                },
                {
                  label: "Active Clinical Cases",
                  value: dashboardMetrics?.authorized_cases_count ?? 0,
                  sub: "CXR & Brain MRI workflows",
                },
                {
                  label: "Completed Grad-CAM Jobs",
                  value: dashboardMetrics?.completed_xai_analyses ?? 0,
                  sub: "PyTorch DenseNet-121",
                },
                {
                  label: "Pending Report Drafts",
                  value: dashboardMetrics?.pending_report_drafts ?? 0,
                  sub: "Awaiting clinician review",
                },
                {
                  label: "Clinician-Approved Reports",
                  value: dashboardMetrics?.approved_reports ?? 0,
                  sub: "Signed off with provenance",
                },
              ].map((m) => (
                <div
                  key={m.label}
                  className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
                >
                  <p className="text-xs font-medium text-slate-500">{m.label}</p>
                  <p className="mt-2 text-2xl font-bold text-slate-900">
                    {m.value}
                  </p>
                  <p className="mt-1 text-[11px] text-slate-500">{m.sub}</p>
                </div>
              ))}
            </div>

            {/* Recent Authorized Clinical Cases & Quick Launch */}
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
              <div className="lg:col-span-7 rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-bold text-slate-900">
                    Authorized Clinical Cases
                  </h2>
                  <button
                    type="button"
                    onClick={() => setActiveTab("patients")}
                    className="text-xs font-semibold text-sky-700 hover:underline"
                  >
                    View Full Registry →
                  </button>
                </div>

                <div className="divide-y divide-slate-200">
                  {cases.map((c) => (
                    <div
                      key={c.id}
                      className="flex flex-wrap items-center justify-between gap-3 py-3"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs font-bold text-slate-900">
                            {c.case_number}
                          </span>
                          <span className="rounded bg-sky-100 px-2 py-0.5 text-[11px] font-semibold text-sky-800">
                            {c.modality} • {c.body_part}
                          </span>
                          <span
                            className={`rounded px-2 py-0.5 text-[11px] font-semibold ${
                              c.status === "APPROVED"
                                ? "bg-emerald-100 text-emerald-800"
                                : c.status === "REJECTED"
                                ? "bg-rose-100 text-rose-800"
                                : "bg-amber-100 text-amber-800"
                            }`}
                          >
                            {c.status}
                          </span>
                        </div>
                        <p className="text-xs text-slate-600">
                          {c.chief_complaint}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedCaseId(c.id);
                          setActiveTab("workspace");
                        }}
                        className="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800"
                      >
                        Open XAI Workspace
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              {/* Capability Disclosure Table */}
              <div className="lg:col-span-5 rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-3">
                <h2 className="text-sm font-bold text-slate-900">
                  Implemented vs. Unverified vs. Disabled Capabilities
                </h2>
                <div className="space-y-2.5 text-xs">
                  {(systemStatus?.capability_matrix || []).map((cap) => (
                    <div
                      key={cap.feature}
                      className="rounded-lg border border-slate-200 bg-slate-50 p-3"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-semibold text-slate-900">
                          {cap.feature}
                        </span>
                        <span
                          className={`rounded px-2 py-0.5 text-[10px] font-bold ${
                            cap.status.startsWith("IMPLEMENTED")
                              ? "bg-emerald-100 text-emerald-800"
                              : "bg-slate-200 text-slate-700"
                          }`}
                        >
                          {cap.status}
                        </span>
                      </div>
                      <p className="mt-1 text-slate-600">{cap.notes}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* =============================================================== */}
        {/* TAB 2: AUTHORIZED PATIENTS & CASES + IDOR VERIFICATION          */}
        {/* =============================================================== */}
        {activeTab === "patients" && (
          <div className="space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h1 className="text-xl font-bold text-slate-900">
                  Synthetic Patient &amp; Case Registry
                </h1>
                <p className="text-xs text-slate-600">{patientScopeNote}</p>
              </div>

              <div className="flex flex-wrap items-center gap-2.5">
                {permissions?.can_upload_and_analyze && (
                  <button
                    type="button"
                    onClick={() => setShowAddPatientModal(true)}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-sky-700 px-3.5 py-2 text-xs font-bold text-white shadow-sm hover:bg-sky-600 focus:outline-none focus:ring-2 focus:ring-sky-500"
                  >
                    <UserPlus className="h-4 w-4" />
                    Tambah Pasien Baru (+ Add Patient)
                  </button>
                )}

                {/* Live Cross-Patient IDOR Security Verification Button */}
                <button
                  type="button"
                  onClick={handleTestIdorBoundary}
                  className="inline-flex items-center gap-2 rounded-lg border border-rose-300 bg-rose-50 px-3.5 py-2 text-xs font-semibold text-rose-900 hover:bg-rose-100"
                >
                  <ShieldAlert className="h-4 w-4 text-rose-700" />
                  Test Cross-Patient IDOR Guard (Request Unassigned pat-synth-003)
                </button>
              </div>
            </div>

            {/* Search & Modality Filter Bar */}
            <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="relative flex-1 min-w-[240px]">
                <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
                <input
                  type="text"
                  value={patientSearch}
                  onChange={(e) => setPatientSearch(e.target.value)}
                  placeholder="Search synthetic patients by name, MRN, or clinical summary..."
                  className="w-full rounded-lg border border-slate-300 py-2 pl-9 pr-3 text-xs"
                />
              </div>

              <select
                aria-label="Filter cases by modality"
                value={modalityFilter}
                onChange={(e) => setModalityFilter(e.target.value)}
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700"
              >
                <option value="">All Modalities (CXR + MRI)</option>
                <option value="CXR">Chest Radiograph (CXR)</option>
                <option value="MRI">Brain MRI (FLAIR)</option>
              </select>

              <button
                type="button"
                onClick={loadDashboardAndLists}
                className="rounded-lg bg-sky-700 px-4 py-2 text-xs font-semibold text-white hover:bg-sky-600"
              >
                Apply Filter
              </button>
            </div>

            {/* Authorized Patients Grid */}
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {patients.map((p) => {
                const patientCases = cases.filter((c) => c.patient_id === p.id);
                return (
                  <div
                    key={p.id}
                    className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-3"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="flex items-center gap-2">
                          <h2 className="text-sm font-bold text-slate-900">
                            {p.full_name}
                          </h2>
                          <span className="rounded bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-900">
                            SYNTHETIC
                          </span>
                        </div>
                        <p className="font-mono text-xs text-slate-500">
                          MRN: {p.mrn} • DOB: {p.birth_date} • Sex: {p.sex}
                        </p>
                      </div>
                      <span className="font-mono text-[11px] text-slate-400">
                        {p.fhir_patient_id}
                      </span>
                    </div>

                    <p className="text-xs text-slate-700 leading-relaxed">
                      {p.clinical_summary}
                    </p>

                    <div className="border-t border-slate-100 pt-3 space-y-2">
                      <div className="flex items-center justify-between">
                        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                          Associated Imaging Cases ({patientCases.length})
                        </p>
                        {permissions?.can_upload_and_analyze && (
                          <button
                            type="button"
                            onClick={() => {
                              setTargetPatientForCase(p);
                              setNewCaseModality("CXR");
                              setNewCaseBodyPart("CHEST");
                              setNewCaseChiefComplaint("");
                              setNewCaseClinicalHistory("");
                              setShowAddCaseModal(true);
                            }}
                            className="inline-flex items-center gap-1 text-[11px] font-bold text-sky-700 hover:underline"
                          >
                            <Plus className="h-3 w-3" />
                            + Buka Kasus Baru
                          </button>
                        )}
                      </div>

                      {patientCases.map((c) => (
                        <div
                          key={c.id}
                          className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs"
                        >
                          <div>
                            <span className="font-mono font-bold text-slate-900">
                              {c.case_number}
                            </span>{" "}
                            <span className="text-slate-600">
                              ({c.modality} • {c.status})
                            </span>
                          </div>
                          <button
                            type="button"
                            onClick={() => {
                              setSelectedCaseId(c.id);
                              setActiveTab("workspace");
                            }}
                            className="font-semibold text-sky-700 hover:underline"
                          >
                            Select Case →
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Modal Tambah Pasien Baru */}
            {showAddPatientModal && (
              <div
                role="dialog"
                aria-modal="true"
                className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm"
              >
                <div className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
                  <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                    <div>
                      <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                        <UserPlus className="h-5 w-5 text-sky-700" />
                        Tambah Pasien Sintetis Baru
                      </h2>
                      <p className="text-xs text-slate-500">
                        Pasien akan otomatis terdaftar dengan IDOR Guard &amp; Standar FHIR R4
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setShowAddPatientModal(false)}
                      className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                    >
                      <X className="h-5 w-5" />
                    </button>
                  </div>

                  <form onSubmit={handleCreatePatient} className="space-y-4">
                    <div className="space-y-1">
                      <label className="block text-xs font-semibold text-slate-700">
                        Nama Lengkap Pasien *
                      </label>
                      <input
                        type="text"
                        required
                        value={newPatientName}
                        onChange={(e) => setNewPatientName(e.target.value)}
                        placeholder="Contoh: Budi Santoso / Siti Rahmawati"
                        className="w-full rounded-lg border border-slate-300 p-2.5 text-xs focus:ring-2 focus:ring-sky-500"
                      />
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div className="space-y-1">
                        <label className="block text-xs font-semibold text-slate-700">
                          Tanggal Lahir (YYYY-MM-DD) *
                        </label>
                        <input
                          type="date"
                          required
                          value={newPatientDob}
                          onChange={(e) => setNewPatientDob(e.target.value)}
                          className="w-full rounded-lg border border-slate-300 p-2.5 text-xs focus:ring-2 focus:ring-sky-500"
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="block text-xs font-semibold text-slate-700">
                          Jenis Kelamin *
                        </label>
                        <select
                          value={newPatientSex}
                          onChange={(e) => setNewPatientSex(e.target.value)}
                          className="w-full rounded-lg border border-slate-300 bg-white p-2.5 text-xs focus:ring-2 focus:ring-sky-500"
                        >
                          <option value="male">Laki-laki (Male)</option>
                          <option value="female">Perempuan (Female)</option>
                          <option value="other">Lainnya (Other)</option>
                        </select>
                      </div>
                    </div>

                    <div className="space-y-1">
                      <label className="block text-xs font-semibold text-slate-700">
                        Ringkasan Klinis &amp; Riwayat Medis Pasien *
                      </label>
                      <textarea
                        required
                        rows={3}
                        value={newPatientSummary}
                        onChange={(e) => setNewPatientSummary(e.target.value)}
                        placeholder="Contoh: Pasien usia 40 tahun dengan riwayat batuk berdahak 4 hari dan sesak napas saat aktivitas sedang..."
                        className="w-full rounded-lg border border-slate-300 p-2.5 text-xs focus:ring-2 focus:ring-sky-500"
                      />
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div className="space-y-1">
                        <label className="block text-xs font-semibold text-slate-700">
                          Alergi (Pisahkan koma)
                        </label>
                        <input
                          type="text"
                          value={newPatientAllergies}
                          onChange={(e) => setNewPatientAllergies(e.target.value)}
                          placeholder="Misal: Penicillin, NSAID"
                          className="w-full rounded-lg border border-slate-300 p-2.5 text-xs focus:ring-2 focus:ring-sky-500"
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="block text-xs font-semibold text-slate-700">
                          Kondisi Aktif / Diagnosa Awal
                        </label>
                        <input
                          type="text"
                          value={newPatientConditions}
                          onChange={(e) => setNewPatientConditions(e.target.value)}
                          placeholder="Misal: Hipertensi, Batuk Kronis"
                          className="w-full rounded-lg border border-slate-300 p-2.5 text-xs focus:ring-2 focus:ring-sky-500"
                        />
                      </div>
                    </div>

                    <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 text-[11px] text-amber-900 space-y-1">
                      <p className="font-bold flex items-center gap-1.5">
                        <AlertCircle className="h-3.5 w-3.5 text-amber-700" />
                        Pemberitahuan Rekam Medis Sintetis
                      </p>
                      <p>
                        Pasien akan otomatis diberi tanda <strong>SYNTHETIC</strong>, mendapatkan nomor MRN unik dan FHIR Patient ID, serta langsung ditugaskan ke akun dokter Anda.
                      </p>
                    </div>

                    <div className="flex items-center justify-end gap-2.5 border-t border-slate-100 pt-3">
                      <button
                        type="button"
                        onClick={() => setShowAddPatientModal(false)}
                        className="rounded-lg border border-slate-300 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                      >
                        Batal
                      </button>
                      <button
                        type="submit"
                        disabled={submittingPatient}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-sky-700 px-4 py-2 text-xs font-bold text-white hover:bg-sky-600 disabled:opacity-50"
                      >
                        <UserPlus className="h-4 w-4" />
                        {submittingPatient ? "Mendaftarkan..." : "Daftarkan Pasien"}
                      </button>
                    </div>
                  </form>
                </div>
              </div>
            )}

            {/* Modal Buka Kasus Imaging Baru */}
            {showAddCaseModal && targetPatientForCase && (
              <div
                role="dialog"
                aria-modal="true"
                className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm"
              >
                <div className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
                  <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                    <div>
                      <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                        <Plus className="h-5 w-5 text-sky-700" />
                        Buka Kasus Imaging Baru
                      </h2>
                      <p className="text-xs text-slate-500">
                        Pasien: <strong>{targetPatientForCase.full_name}</strong> ({targetPatientForCase.mrn})
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setShowAddCaseModal(false)}
                      className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                    >
                      <X className="h-5 w-5" />
                    </button>
                  </div>

                  <form onSubmit={handleCreateCase} className="space-y-4">
                    <div className="grid grid-cols-2 gap-3">
                      <div className="space-y-1">
                        <label className="block text-xs font-semibold text-slate-700">
                          Modalitas Citra Medis *
                        </label>
                        <select
                          value={newCaseModality}
                          onChange={(e) => {
                            const mod = e.target.value;
                            setNewCaseModality(mod);
                            setNewCaseBodyPart(mod === "CXR" ? "CHEST" : "BRAIN");
                          }}
                          className="w-full rounded-lg border border-slate-300 bg-white p-2.5 text-xs focus:ring-2 focus:ring-sky-500"
                        >
                          <option value="CXR">Chest Radiograph (CXR)</option>
                          <option value="MRI">Brain MRI (FLAIR)</option>
                        </select>
                      </div>
                      <div className="space-y-1">
                        <label className="block text-xs font-semibold text-slate-700">
                          Bagian Tubuh (Body Part) *
                        </label>
                        <input
                          type="text"
                          required
                          value={newCaseBodyPart}
                          onChange={(e) => setNewCaseBodyPart(e.target.value.toUpperCase())}
                          className="w-full rounded-lg border border-slate-300 p-2.5 text-xs uppercase focus:ring-2 focus:ring-sky-500"
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div className="space-y-1">
                        <label className="block text-xs font-semibold text-slate-700">
                          Prioritas Klinis *
                        </label>
                        <select
                          value={newCasePriority}
                          onChange={(e) => setNewCasePriority(e.target.value)}
                          className="w-full rounded-lg border border-slate-300 bg-white p-2.5 text-xs focus:ring-2 focus:ring-sky-500"
                        >
                          <option value="ROUTINE">ROUTINE</option>
                          <option value="URGENT">URGENT</option>
                          <option value="STAT">STAT (Darurat)</option>
                        </select>
                      </div>
                      <div className="space-y-1">
                        <label className="block text-xs font-semibold text-slate-700">
                          Tipe Encounter / Kunjungan
                        </label>
                        <input
                          type="text"
                          value={newCaseEncounterType}
                          onChange={(e) => setNewCaseEncounterType(e.target.value)}
                          placeholder="Outpatient Clinical Evaluation"
                          className="w-full rounded-lg border border-slate-300 p-2.5 text-xs focus:ring-2 focus:ring-sky-500"
                        />
                      </div>
                    </div>

                    <div className="space-y-1">
                      <label className="block text-xs font-semibold text-slate-700">
                        Keluhan Utama (Chief Complaint) *
                      </label>
                      <input
                        type="text"
                        required
                        value={newCaseChiefComplaint}
                        onChange={(e) => setNewCaseChiefComplaint(e.target.value)}
                        placeholder="Contoh: Batuk produktif 5 hari, demam, evaluasi infiltrat lobus kanan bawah"
                        className="w-full rounded-lg border border-slate-300 p-2.5 text-xs focus:ring-2 focus:ring-sky-500"
                      />
                    </div>

                    <div className="space-y-1">
                      <label className="block text-xs font-semibold text-slate-700">
                        Riwayat Klinis Tambahan untuk Kasus Ini
                      </label>
                      <textarea
                        rows={2}
                        value={newCaseClinicalHistory}
                        onChange={(e) => setNewCaseClinicalHistory(e.target.value)}
                        placeholder="Keterangan tambahan untuk interpretasi radiologi..."
                        className="w-full rounded-lg border border-slate-300 p-2.5 text-xs focus:ring-2 focus:ring-sky-500"
                      />
                    </div>

                    <div className="flex items-center justify-end gap-2.5 border-t border-slate-100 pt-3">
                      <button
                        type="button"
                        onClick={() => setShowAddCaseModal(false)}
                        className="rounded-lg border border-slate-300 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                      >
                        Batal
                      </button>
                      <button
                        type="submit"
                        disabled={submittingCase}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-sky-700 px-4 py-2 text-xs font-bold text-white hover:bg-sky-600 disabled:opacity-50"
                      >
                        <Plus className="h-4 w-4" />
                        {submittingCase ? "Membuka Kasus..." : "Buka Kasus & Lanjut ke Workspace"}
                      </button>
                    </div>
                  </form>
                </div>
              </div>
            )}
          </div>
        )}

        {/* =============================================================== */}
        {/* TAB 3: MEDICAL IMAGE VIEWER & PYTORCH GRAD-CAM XAI WORKSPACE    */}
        {/* =============================================================== */}
        {activeTab === "workspace" && (
          <div className="space-y-6">
            {/* Case Selector Header */}
            <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex flex-wrap items-center gap-3">
                <label
                  htmlFor="workspace-case-select"
                  className="text-xs font-bold uppercase tracking-wider text-slate-500"
                >
                  Active Case:
                </label>
                <select
                  id="workspace-case-select"
                  value={selectedCaseId}
                  onChange={(e) => setSelectedCaseId(e.target.value)}
                  className="rounded-lg border border-slate-300 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-900"
                >
                  {cases.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.case_number} — {c.modality} ({c.body_part}) •{" "}
                      {c.chief_complaint.slice(0, 48)}
                    </option>
                  ))}
                </select>
                {activePatient && (
                  <span className="text-xs text-slate-600">
                    Patient: <strong>{activePatient.full_name}</strong> (
                    <code>{activePatient.mrn}</code>)
                  </span>
                )}
              </div>

              {/* Upload Supported Medical Image */}
              <div className="flex items-center gap-2">
                {permissions?.can_upload_and_analyze ? (
                  <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-sky-300 bg-sky-50 px-3.5 py-2 text-xs font-semibold text-sky-900 hover:bg-sky-100">
                    <Upload className="h-3.5 w-3.5 text-sky-700" />
                    {uploadingImage
                      ? "Validating & Hashing..."
                      : "Upload Scan (PNG/JPEG)"}
                    <input
                      type="file"
                      accept="image/png,image/jpeg"
                      onChange={handleImageUpload}
                      disabled={uploadingImage}
                      className="hidden"
                    />
                  </label>
                ) : (
                  <span className="rounded bg-slate-100 px-2.5 py-1.5 text-xs text-slate-500">
                    Upload restricted for {user.role} role
                  </span>
                )}
              </div>
            </div>

            {workspaceLoading ? (
              <div className="rounded-xl border border-slate-200 bg-white p-12 text-center text-xs text-slate-500">
                Loading clinical case workspace...
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                {/* Left Column: Medical Image & Grad-CAM Viewer + Clinical Context */}
                <div className="space-y-6 lg:col-span-7">
                  {selectedImage ? (
                    <MedicalImageViewer
                      image={selectedImage}
                      activeJob={selectedJob}
                    />
                  ) : (
                    <div className="rounded-xl border border-dashed border-slate-300 bg-white p-12 text-center text-xs text-slate-500">
                      No medical image uploaded for this case yet.
                    </div>
                  )}

                  {/* Clinical History & Sourced LOINC Observations */}
                  {activeCase && (
                    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
                      <div>
                        <h3 className="text-sm font-bold text-slate-900">
                          Clinical Context &amp; Sourced LOINC Observations
                        </h3>
                        <p className="mt-1 text-xs text-slate-700">
                          {activeCase.clinical_history}
                        </p>
                      </div>

                      <div className="overflow-x-auto">
                        <table className="w-full text-left text-xs">
                          <thead>
                            <tr className="border-b border-slate-200 text-slate-500">
                              <th className="py-2 pr-3">LOINC</th>
                              <th className="py-2 pr-3">Observation</th>
                              <th className="py-2 pr-3">Value</th>
                              <th className="py-2 pr-3">Reference</th>
                              <th className="py-2">Interpretation</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100">
                            {caseObservations.map((o) => (
                              <tr key={o.id}>
                                <td className="py-2 pr-3 font-mono text-slate-600">
                                  {o.loinc_code}
                                </td>
                                <td className="py-2 pr-3 font-medium text-slate-900">
                                  {o.display_name}
                                </td>
                                <td className="py-2 pr-3 font-bold text-slate-900">
                                  {o.value_text} {o.unit}
                                </td>
                                <td className="py-2 pr-3 text-slate-500">
                                  {o.reference_range}
                                </td>
                                <td className="py-2 font-semibold text-amber-800">
                                  {o.interpretation}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>

                      {permissions?.can_upload_and_analyze && (
                        <form
                          onSubmit={handleAddObservation}
                          className="grid grid-cols-2 gap-2 border-t border-slate-100 pt-3 sm:grid-cols-6"
                        >
                          <input
                            type="text"
                            value={obsLoinc}
                            onChange={(e) => setObsLoinc(e.target.value)}
                            placeholder="LOINC"
                            className="rounded border border-slate-300 px-2 py-1.5 text-xs"
                          />
                          <input
                            type="text"
                            value={obsName}
                            onChange={(e) => setObsName(e.target.value)}
                            placeholder="Parameter"
                            className="rounded border border-slate-300 px-2 py-1.5 text-xs sm:col-span-2"
                          />
                          <input
                            type="text"
                            value={obsVal}
                            onChange={(e) => setObsVal(e.target.value)}
                            placeholder="Value"
                            className="rounded border border-slate-300 px-2 py-1.5 text-xs"
                          />
                          <input
                            type="text"
                            value={obsUnit}
                            onChange={(e) => setObsUnit(e.target.value)}
                            placeholder="Unit"
                            className="rounded border border-slate-300 px-2 py-1.5 text-xs"
                          />
                          <button
                            type="submit"
                            className="inline-flex items-center justify-center gap-1 rounded bg-slate-900 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-slate-800"
                          >
                            <Plus className="h-3.5 w-3.5" />
                            Add
                          </button>
                        </form>
                      )}
                    </div>
                  )}
                </div>

                {/* Right Column: AI Execution Control, Model Outputs, Uncertainty & Provenance */}
                <div className="space-y-6 lg:col-span-5">
                  {/* Run Configured Model Card */}
                  <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <h2 className="text-sm font-bold text-slate-900">
                          Configured Medical Imaging &amp; XAI Engine
                        </h2>
                        <p className="text-xs text-slate-500">
                          PyTorch DenseNet-121 • Internal Service (:8200)
                        </p>
                      </div>
                      <span className="rounded bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-900 border border-amber-300">
                        RESEARCH_UNVERIFIED
                      </span>
                    </div>

                    <div className="space-y-2">
                      <label
                        htmlFor="xai-method-select"
                        className="block text-xs font-medium text-slate-700"
                      >
                        Explainability Attribution Method
                      </label>
                      <select
                        id="xai-method-select"
                        value={xaiMethodChoice}
                        onChange={(e) =>
                          setXaiMethodChoice(
                            e.target.value as
                              | "GRAD_CAM"
                              | "GRAD_CAM_PLUS_OCCLUSION"
                          )
                        }
                        className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-medium"
                      >
                        <option value="GRAD_CAM">
                          Grad-CAM (Layer features.denseblock4 Gradient Activation)
                        </option>
                        <option value="GRAD_CAM_PLUS_OCCLUSION">
                          Grad-CAM + Patch Occlusion Sensitivity (7×7 Perturbation)
                        </option>
                      </select>
                    </div>

                    {permissions?.can_upload_and_analyze ? (
                      <button
                        type="button"
                        disabled={!selectedImageId || runningAnalysis}
                        onClick={handleRunAnalysis}
                        className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-sky-700 px-4 py-2.5 text-xs font-bold text-white shadow-sm hover:bg-sky-600 disabled:opacity-50"
                      >
                        <Sparkles className="h-4 w-4" />
                        {runningAnalysis
                          ? "Running PyTorch Forward/Backward Hooks..."
                          : "Execute Medical Image & Grad-CAM Analysis"}
                      </button>
                    ) : (
                      <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
                        Your role (<strong>{user.role}</strong>) has read-only inspection access to completed AI/XAI artifacts.
                      </div>
                    )}
                  </div>

                  {/* Completed Job Output & Uncertainty Card */}
                  {selectedJob ? (
                    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
                      <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                        <div>
                          <span className="text-[11px] font-mono text-slate-500">
                            Job: {selectedJob.id.slice(0, 16)} •{" "}
                            {selectedJob.execution_device}
                          </span>
                          <h3 className="text-sm font-bold text-slate-900">
                            {selectedJob.predicted_class_label}
                          </h3>
                        </div>
                        <span className="rounded-md bg-emerald-100 px-2.5 py-1 text-xs font-bold text-emerald-900">
                          {selectedJob.status}
                        </span>
                      </div>

                      {/* Uncertainty & Shannon Entropy Disclosure */}
                      <div
                        className={`rounded-lg border p-3 text-xs ${
                          selectedJob.uncertainty_level === "HIGH_UNCERTAINTY"
                            ? "border-rose-300 bg-rose-50 text-rose-950"
                            : "border-amber-300 bg-amber-50 text-amber-950"
                        }`}
                      >
                        <p className="font-bold">
                          Uncertainty Status: {selectedJob.uncertainty_level} •
                          Shannon Entropy: {selectedJob.shannon_entropy} / 2.00
                          bits
                        </p>
                        <p className="mt-1">{selectedJob.uncertainty_reason}</p>
                      </div>

                      {/* Candidate Class Probability Distribution */}
                      <div className="space-y-2">
                        <p className="text-xs font-bold uppercase tracking-wider text-slate-500">
                          Candidate Pattern Score Distribution
                        </p>
                        {parsedClassScores.map((cs) => (
                          <div key={cs.class_code} className="space-y-1">
                            <div className="flex justify-between text-xs">
                              <span className="font-medium text-slate-800">
                                {cs.class_label}
                              </span>
                              <span className="font-mono font-bold text-slate-900">
                                {(cs.probability * 100).toFixed(1)}%
                              </span>
                            </div>
                            <div className="h-2 w-full rounded-full bg-slate-100 overflow-hidden">
                              <div
                                className="h-full rounded-full bg-sky-600"
                                style={{
                                  width: `${Math.max(3, cs.probability * 100)}%`,
                                }}
                              />
                            </div>
                          </div>
                        ))}
                      </div>

                      {/* Anatomical Quadrant Attribution Summary */}
                      {parsedXaiMeta && (
                        <div className="space-y-2 border-t border-slate-100 pt-3">
                          <p className="text-xs font-bold uppercase tracking-wider text-slate-500">
                            Anatomical Quadrant Attribution ({parsedXaiMeta.method})
                          </p>
                          <div className="space-y-1.5">
                            {parsedXaiMeta.top_regions.map((reg) => (
                              <div
                                key={reg.quadrant_code}
                                className="flex items-center justify-between rounded bg-slate-50 px-2.5 py-1.5 text-xs"
                              >
                                <span className="font-medium text-slate-700">
                                  {reg.region_name}
                                </span>
                                <span className="font-mono text-slate-900">
                                  mean {reg.mean_attribution.toFixed(2)} | peak{" "}
                                  {reg.peak_attribution.toFixed(2)}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Model Limitations */}
                      <div className="border-t border-slate-100 pt-3 space-y-1.5">
                        <p className="text-xs font-bold uppercase tracking-wider text-slate-500">
                          Mandatory Model &amp; Clinical Limitations
                        </p>
                        <ul className="list-disc pl-4 text-xs text-slate-600 space-y-1">
                          {parsedLimitations.map((lim, i) => (
                            <li key={i}>{lim}</li>
                          ))}
                        </ul>
                      </div>

                      {/* Proceed to Evidence-Grounded Report Drafting */}
                      {permissions?.can_draft_or_edit_report && (
                        <div className="border-t border-slate-200 pt-4 space-y-2">
                          <label className="block text-xs font-semibold text-slate-800">
                            Catatan Klinis Tambahan untuk Sintesis Draf Laporan:
                          </label>
                          <input
                            type="text"
                            value={clinicianContextNote}
                            onChange={(e) =>
                              setClinicianContextNote(e.target.value)
                            }
                            placeholder="Contoh: qweqwe / observasi klinis tambahan untuk dimasukkan ke Bagian 1..."
                            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-xs"
                          />
                          <p className="text-[11px] text-slate-500">
                            Catatan ini akan otomatis digabungkan ke <strong>Bagian 1 (Sourced Clinical Facts)</strong> di draf laporan baru.
                          </p>
                          <button
                            type="button"
                            disabled={generatingDraft}
                            onClick={handleGenerateDraft}
                            className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-xs font-bold text-white hover:bg-slate-800"
                          >
                            <FileText className="h-4 w-4" />
                            {generatingDraft
                              ? "Menyintesis Draf Laporan Berbasis Bukti..."
                              : "Generate Evidence-Grounded Report Draft →"}
                          </button>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center text-xs text-slate-500 space-y-3">
                      <Brain className="mx-auto h-8 w-8 text-slate-400" />
                      <p className="font-semibold text-slate-700">
                        No AI / Grad-CAM Analysis Executed Yet for This Case
                      </p>
                      <p>
                        Click &ldquo;Execute Medical Image &amp; Grad-CAM Analysis&rdquo; above to run the PyTorch DenseNet-121 vision model and generate spatial attribution maps.
                      </p>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* =============================================================== */}
        {/* TAB 4: EVIDENCE-GROUNDED REPORT DRAFTING & CLINICIAN REVIEW     */}
        {/* =============================================================== */}
        {activeTab === "reports" && (
          <div className="space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h1 className="text-xl font-bold text-slate-900">
                  Evidence-Grounded Report Drafting &amp; Clinician Sign-Off
                </h1>
                <p className="text-xs text-slate-600">
                  Strictly distinguishes sourced clinical facts, model predictions, XAI attribution, and clinician-reviewed narrative.
                </p>
              </div>
              {permissions?.can_draft_or_edit_report && (
                <button
                  type="button"
                  disabled={generatingDraft}
                  onClick={handleGenerateDraft}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-sky-700 px-4 py-2 text-xs font-bold text-white hover:bg-sky-600"
                >
                  <Plus className="h-4 w-4" />
                  Generate New Draft Version for {activeCase?.case_number}
                </button>
              )}
            </div>

            {/* Daftar Riwayat Versi Laporan (Report Version History & Selector) */}
            {caseReports.length > 0 && (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex items-center gap-2.5">
                  <FileText className="h-4 w-4 text-sky-700" />
                  <div>
                    <h2 className="text-xs font-bold text-slate-900">
                      Daftar Versi Laporan Kasus Ini ({caseReports.length} Versi Tersimpan):
                    </h2>
                    <p className="text-[11px] text-slate-500">
                      Klik salah satu versi di bawah untuk memeriksa isinya. (Nomor 1 s/d 5 di bawah adalah 5 Bagian Struktur Dokumen Laporan).
                    </p>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  {caseReports.map((rep) => {
                    const isSelected = rep.id === selectedReportId;
                    return (
                      <button
                        key={rep.id}
                        type="button"
                        onClick={() => {
                          setSelectedReportId(rep.id);
                          setEditFacts(rep.clinical_facts_section);
                          setEditModelFindings(rep.model_findings_section);
                          setEditXaiSection(rep.xai_attribution_section);
                          setEditImpression(rep.impression_narrative);
                          setEditLimitations(rep.limitations_section);
                        }}
                        className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition border ${
                          isSelected
                            ? "bg-sky-900 text-white border-sky-900 shadow-sm ring-2 ring-sky-500/30"
                            : "bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100"
                        }`}
                      >
                        <span>Versi v{rep.version}</span>
                        <span
                          className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                            rep.status === "APPROVED"
                              ? isSelected
                                ? "bg-emerald-400 text-slate-950"
                                : "bg-emerald-100 text-emerald-800"
                              : rep.status === "REJECTED"
                              ? isSelected
                                ? "bg-rose-400 text-slate-950"
                                : "bg-rose-100 text-rose-800"
                              : isSelected
                              ? "bg-amber-400 text-slate-950"
                              : "bg-amber-100 text-amber-800"
                          }`}
                        >
                          {rep.status}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {!selectedReport ? (
              <div className="rounded-xl border border-dashed border-slate-300 bg-white p-12 text-center text-xs text-slate-500 space-y-3">
                <FileText className="mx-auto h-8 w-8 text-slate-400" />
                <p className="font-semibold text-slate-700">
                  No Report Draft Generated Yet for {activeCase?.case_number}
                </p>
                <p>
                  Generate an evidence-grounded draft from the Image &amp; XAI Workspace or click the button above.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                {/* Report Sections Editor / Inspector */}
                <div className="lg:col-span-8 rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-5">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 pb-4">
                    <div>
                      <span className="font-mono text-xs text-slate-500">
                        Report ID: {selectedReport.id} • Version v
                        {selectedReport.version}
                      </span>
                      <h2 className="text-base font-bold text-slate-900">
                        Diagnostic Decision-Support Draft ({activeCase?.case_number})
                      </h2>
                    </div>
                    <span
                      className={`rounded-md px-3 py-1 text-xs font-bold ${
                        selectedReport.status === "APPROVED"
                          ? "bg-emerald-100 text-emerald-900"
                          : selectedReport.status === "REJECTED"
                          ? "bg-rose-100 text-rose-900"
                          : "bg-amber-100 text-amber-900"
                      }`}
                    >
                      {selectedReport.status}
                    </span>
                  </div>

                  {[
                    {
                      label: "1. Sourced Clinical Facts & LOINC Observations",
                      val: editFacts,
                      setter: setEditFacts,
                      badge: "SOURCED CLINICAL RECORD",
                      rows: 8,
                    },
                    {
                      label:
                        "2. Configured Model Prediction Output & Uncertainty",
                      val: editModelFindings,
                      setter: setEditModelFindings,
                      badge: "MODEL PREDICTION (RESEARCH_UNVERIFIED)",
                      rows: 6,
                    },
                    {
                      label: "3. Grad-CAM Spatial Attribution Interpretation",
                      val: editXaiSection,
                      setter: setEditXaiSection,
                      badge: "XAI ATTRIBUTION",
                      rows: 5,
                    },
                    {
                      label:
                        "4. Clinician Impression & Decision-Support Narrative",
                      val: editImpression,
                      setter: setEditImpression,
                      badge: "DRAFT NARRATIVE",
                      rows: 6,
                    },
                    {
                      label: "5. Mandatory Limitations & Safety Disclosures",
                      val: editLimitations,
                      setter: setEditLimitations,
                      badge: "CLINICAL SAFETY",
                      rows: 5,
                    },
                  ].map((sec) => (
                    <div key={sec.label} className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <label className="text-xs font-bold text-slate-800">
                          {sec.label}
                        </label>
                        <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-700">
                          {sec.badge}
                        </span>
                      </div>
                      <textarea
                        rows={sec.rows || 5}
                        value={sec.val}
                        disabled={
                          !permissions?.can_draft_or_edit_report ||
                          selectedReport.status === "APPROVED"
                        }
                        onChange={(e) => sec.setter(e.target.value)}
                        className="w-full rounded-lg border border-slate-300 bg-slate-50 p-3 font-mono text-xs text-slate-800 disabled:opacity-75 focus:bg-white focus:ring-2 focus:ring-sky-500"
                      />
                      {sec.label.startsWith("1.") && sec.val.includes("Clinician Context Note:") && (
                        <div className="rounded-md border border-sky-200 bg-sky-50 px-3 py-1.5 text-[11px] text-sky-800">
                          ✓ <strong>Catatan Klinisi Tambahan Tersemat:</strong> Teks catatan yang Anda masukkan saat Generate Draft tersimpan di baris paling bawah Bagian 1 ini.
                        </div>
                      )}
                    </div>
                  ))}

                  {permissions?.can_draft_or_edit_report &&
                    selectedReport.status !== "APPROVED" && (
                      <div className="flex justify-end">
                        <button
                          type="button"
                          disabled={savingReport}
                          onClick={handleSaveReportEdits}
                          className="rounded-lg bg-slate-900 px-4 py-2 text-xs font-bold text-white hover:bg-slate-800"
                        >
                          Save Clinician Edits to Draft
                        </button>
                      </div>
                    )}
                </div>

                {/* Right Column: Provenance Citations & Clinician Review Sign-Off */}
                <div className="lg:col-span-4 space-y-6">
                  {/* Clinician / Reviewer Sign-Off Box */}
                  <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
                    <div className="flex items-center gap-2">
                      <ClipboardCheck className="h-5 w-5 text-sky-700" />
                      <h3 className="text-sm font-bold text-slate-900">
                        Clinician Review &amp; Attestation
                      </h3>
                    </div>

                    {selectedReport.reviewed_at && (
                      <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs space-y-1">
                        <p className="font-bold text-slate-900">
                          Reviewed Status: {selectedReport.status}
                        </p>
                        <p className="text-slate-600">
                          Reviewer ID: <code>{selectedReport.reviewer_id}</code>
                        </p>
                        <p className="text-slate-600">
                          Timestamp: {selectedReport.reviewed_at}
                        </p>
                        <p className="mt-1 italic text-slate-800">
                          &ldquo;{selectedReport.reviewer_notes}&rdquo;
                        </p>
                      </div>
                    )}

                    {selectedReport.status === "APPROVED" ? (
                      <div className="rounded-lg border border-emerald-300 bg-emerald-50 p-4 text-xs text-emerald-950 space-y-2">
                        <div className="flex items-center gap-1.5 font-bold text-emerald-900">
                          <CheckCircle2 className="h-4 w-4 text-emerald-700 flex-shrink-0" />
                          <span>Laporan Versi v{selectedReport.version} Ini Sudah APPROVED</span>
                        </div>
                        <p className="text-[11px] text-emerald-800">
                          Laporan ini telah disetujui resmi dan terkunci. Kolom catatan tanda tangan tidak perlu diisi lagi.
                        </p>
                        <p className="text-[11px] text-emerald-800">
                          Bila Anda ingin membuat revisi draf baru, klik tombol <strong>Generate New Draft Version</strong> di kanan atas.
                        </p>
                      </div>
                    ) : selectedReport.status === "REJECTED" ? (
                      <div className="rounded-lg border border-rose-300 bg-rose-50 p-4 text-xs text-rose-950 space-y-2">
                        <div className="flex items-center gap-1.5 font-bold text-rose-900">
                          <AlertTriangle className="h-4 w-4 text-rose-700 flex-shrink-0" />
                          <span>Laporan Versi v{selectedReport.version} Ini Telah Ditolak (REJECTED)</span>
                        </div>
                        <p className="text-[11px] text-rose-800">
                          Draf ini sudah berstatus ditolak. Anda dapat mengklik tombol <strong>Generate New Draft Version</strong> di atas untuk membuat draf baru.
                        </p>
                      </div>
                    ) : permissions?.can_review_approve_report ? (
                      <div className="space-y-3">
                        <div>
                          <label
                            htmlFor="reviewer-attestation-note"
                            className="block text-xs font-semibold text-slate-800"
                          >
                            Catatan Pengesahan Dokter (Wajib Saat Approve / Reject)
                          </label>
                          <p className="text-[11px] text-slate-500">
                            Tuliskan alasan klinis verifikasi Anda di bawah sebelum menekan tombol Approve atau Reject:
                          </p>
                        </div>
                        <textarea
                          id="reviewer-attestation-note"
                          rows={3}
                          value={reviewerNote}
                          onChange={(e) => setReviewerNote(e.target.value)}
                          placeholder="Masukkan catatan verifikasi klinis dokter untuk tanda tangan pengesahan..."
                          className="w-full rounded-lg border border-slate-300 p-2.5 text-xs focus:ring-2 focus:ring-sky-500"
                        />
                        <div className="grid grid-cols-2 gap-2.5">
                          <button
                            type="button"
                            disabled={savingReport}
                            onClick={() => handleReviewDecision("APPROVE")}
                            className="rounded-lg bg-emerald-700 px-3 py-2 text-xs font-bold text-white hover:bg-emerald-600"
                          >
                            Approve Draft
                          </button>
                          <button
                            type="button"
                            disabled={savingReport}
                            onClick={() => handleReviewDecision("REJECT")}
                            className="rounded-lg bg-rose-700 px-3 py-2 text-xs font-bold text-white hover:bg-rose-600"
                          >
                            Reject Draft
                          </button>
                        </div>
                      </div>
                    ) : (
                      <p className="text-xs text-slate-500">
                        Read-only users cannot sign off or reject report drafts.
                      </p>
                    )}
                  </div>

                  {/* Provenance & Evidence References */}
                  <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-3">
                    <h3 className="text-sm font-bold text-slate-900">
                      Evidence Provenance Chain ({parsedProvenance.length})
                    </h3>
                    <div className="space-y-2.5">
                      {parsedProvenance.map((cit) => (
                        <div
                          key={cit.ref_id}
                          className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs space-y-1"
                        >
                          <div className="flex items-center justify-between">
                            <span className="rounded bg-sky-100 px-2 py-0.5 font-mono text-[10px] font-bold text-sky-900">
                              [{cit.ref_id}]
                            </span>
                            <span className="text-[10px] font-semibold text-slate-500">
                              {cit.source_type}
                            </span>
                          </div>
                          <p className="font-semibold text-slate-900">
                            {cit.title}
                          </p>
                          <p className="text-slate-600">{cit.summary}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* =============================================================== */}
        {/* TAB 5: FHIR R4 INTEROPERABILITY & BUNDLE VALIDATOR              */}
        {/* =============================================================== */}
        {activeTab === "fhir" && (
          <div className="space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h1 className="text-xl font-bold text-slate-900">
                  HL7 FHIR R4 (v4.0.1) Interoperability &amp; Bundle Validation
                </h1>
                <p className="text-xs text-slate-600">
                  Generates and validates Patient, Practitioner, Encounter, Observation, ImagingStudy, and DiagnosticReport resources.
                </p>
              </div>
              {permissions?.can_export_fhir && (
                <button
                  type="button"
                  disabled={loadingFhir}
                  onClick={() => loadFhirBundle(true)}
                  className="inline-flex items-center gap-2 rounded-lg bg-sky-700 px-4 py-2 text-xs font-bold text-white hover:bg-sky-600"
                >
                  <FileCode2 className="h-4 w-4" />
                  Validate &amp; Export FHIR R4 Bundle ({activeCase?.case_number})
                </button>
              )}
            </div>

            {fhirData && (
              <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                <div className="lg:col-span-5 space-y-4">
                  <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-3">
                    <div className="flex items-center justify-between">
                      <h2 className="text-sm font-bold text-slate-900">
                        Structural &amp; Terminology Validation
                      </h2>
                      <span className="rounded bg-emerald-100 px-2.5 py-0.5 text-xs font-bold text-emerald-900">
                        VALID R4 BUNDLE
                      </span>
                    </div>
                    <p className="text-xs text-slate-600">
                      External Server (Port 8300) Status:{" "}
                      <strong className="text-slate-900">
                        {fhirData.external_server_status}
                      </strong>
                    </p>
                    <div className="grid grid-cols-2 gap-2 pt-2">
                      {Object.entries(
                        fhirData.validation.resource_counts || {}
                      ).map(([resType, count]) => (
                        <div
                          key={resType}
                          className="flex items-center justify-between rounded border border-slate-200 bg-slate-50 px-3 py-2 text-xs"
                        >
                          <span className="font-medium text-slate-700">
                            {resType}
                          </span>
                          <span className="font-mono font-bold text-slate-900">
                            {count}
                          </span>
                        </div>
                      ))}
                    </div>
                    <ul className="list-disc pl-4 text-xs text-slate-600 space-y-1 pt-2">
                      {fhirData.validation.checks_passed.map((chk, idx) => (
                        <li key={idx}>{chk}</li>
                      ))}
                    </ul>
                    <p className="rounded bg-amber-50 p-2.5 text-[11px] text-amber-900 border border-amber-200">
                      {fhirData.validation.compliance_disclosure}
                    </p>
                  </div>
                </div>

                <div className="lg:col-span-7 rounded-xl border border-slate-200 bg-slate-950 p-4 shadow-sm">
                  <div className="flex items-center justify-between border-b border-slate-800 pb-2 text-xs text-slate-400">
                    <span>FHIR R4 Bundle JSON Payload</span>
                    <span className="font-mono">
                      {fhirData.validation.total_entries} Resources
                    </span>
                  </div>
                  <pre className="mt-3 max-h-[500px] overflow-auto font-mono text-xs text-sky-300">
                    {JSON.stringify(fhirData.bundle, null, 2)}
                  </pre>
                </div>
              </div>
            )}
          </div>
        )}

        {/* =============================================================== */}
        {/* TAB 6: ADMINISTRATOR USER MANAGEMENT & RBAC                     */}
        {/* =============================================================== */}
        {activeTab === "admin-users" && (
          <div className="space-y-6">
            <div>
              <h1 className="text-xl font-bold text-slate-900">
                User Provisioning &amp; Role-Based Access Control (RBAC)
              </h1>
              <p className="text-xs text-slate-600">
                Restricted to Administrators. Role changes and account deactivations take effect immediately on the server.
              </p>
            </div>

            {!permissions?.can_manage_users ? (
              <div className="rounded-xl border border-rose-300 bg-rose-50 p-6 text-xs text-rose-950 space-y-2">
                <div className="flex items-center gap-2 font-bold text-sm">
                  <Lock className="h-4 w-4 text-rose-700" />
                  Access Denied — Administrator Role Required
                </div>
                <p>
                  Your active session role is <strong>{user.role}</strong>. Server-side RBAC policy blocks non-administrators from provisioning or modifying user accounts.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                <div className="lg:col-span-8 rounded-xl border border-slate-200 bg-white p-5 shadow-sm overflow-x-auto">
                  <h2 className="text-sm font-bold text-slate-900 mb-3">
                    Provisioned Accounts ({adminUsers.length})
                  </h2>
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-slate-200 text-slate-500">
                        <th className="py-2 pr-3">Name &amp; Email</th>
                        <th className="py-2 pr-3">Role</th>
                        <th className="py-2 pr-3">Specialty</th>
                        <th className="py-2 pr-3">Status</th>
                        <th className="py-2">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {adminUsers.map((u) => (
                        <tr key={u.id}>
                          <td className="py-2.5 pr-3">
                            <p className="font-bold text-slate-900">
                              {u.full_name}
                            </p>
                            <p className="font-mono text-slate-500">{u.email}</p>
                          </td>
                          <td className="py-2.5 pr-3">
                            <select
                              aria-label={`Change role for ${u.email}`}
                              value={u.role}
                              onChange={async (e) => {
                                await apiFetch(`/api/admin/users/${u.id}`, {
                                  method: "PATCH",
                                  body: JSON.stringify({
                                    role: e.target.value,
                                  }),
                                });
                                loadAdminUsers();
                              }}
                              className="rounded border border-slate-300 bg-white px-2 py-1 text-xs font-semibold"
                            >
                              <option value="admin">admin</option>
                              <option value="clinician">clinician</option>
                              <option value="reviewer">reviewer</option>
                              <option value="readonly">readonly</option>
                            </select>
                          </td>
                          <td className="py-2.5 pr-3 text-slate-600">
                            {u.specialty}
                          </td>
                          <td className="py-2.5 pr-3">
                            <span
                              className={`rounded px-2 py-0.5 text-[10px] font-bold ${
                                u.is_active === 1
                                  ? "bg-emerald-100 text-emerald-800"
                                  : "bg-rose-100 text-rose-800"
                              }`}
                            >
                              {u.is_active === 1 ? "ACTIVE" : "DEACTIVATED"}
                            </span>
                          </td>
                          <td className="py-2.5">
                            {u.id !== user.user_id && (
                              <button
                                type="button"
                                onClick={async () => {
                                  await apiFetch(`/api/admin/users/${u.id}`, {
                                    method: "PATCH",
                                    body: JSON.stringify({
                                      is_active: u.is_active === 0,
                                    }),
                                  });
                                  loadAdminUsers();
                                }}
                                className="text-xs font-semibold text-sky-700 hover:underline"
                              >
                                {u.is_active === 1 ? "Deactivate" : "Activate"}
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Provision New User Form */}
                <div className="lg:col-span-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
                  <h2 className="text-sm font-bold text-slate-900">
                    Provision New Authorized User
                  </h2>
                  <form
                    onSubmit={async (e) => {
                      e.preventDefault();
                      try {
                        await apiFetch("/api/admin/users", {
                          method: "POST",
                          body: JSON.stringify({
                            email: newUserEmail,
                            full_name: newUserName,
                            role: newUserRole,
                            specialty: newUserSpecialty,
                            password: newUserPassword,
                            assign_all_synthetic_patients: true,
                          }),
                        });
                        setNewUserEmail("");
                        setNewUserName("");
                        setNewUserPassword("");
                        loadAdminUsers();
                        setBannerNotice({
                          type: "success",
                          title: "User Account Provisioned",
                          message:
                            "Hashed password with Argon2id and assigned synthetic patient scope.",
                        });
                      } catch (err) {
                        setBannerNotice({
                          type: "error",
                          title: "User Creation Failed",
                          message:
                            err instanceof Error ? err.message : "Error",
                        });
                      }
                    }}
                    className="space-y-3 text-xs"
                  >
                    <input
                      type="text"
                      required
                      value={newUserName}
                      onChange={(e) => setNewUserName(e.target.value)}
                      placeholder="Full Name & Credentials (e.g. Dr. Jane Doe, MD)"
                      className="w-full rounded-lg border border-slate-300 px-3 py-2"
                    />
                    <input
                      type="email"
                      required
                      value={newUserEmail}
                      onChange={(e) => setNewUserEmail(e.target.value)}
                      placeholder="Email Address"
                      className="w-full rounded-lg border border-slate-300 px-3 py-2"
                    />
                    <select
                      aria-label="Select new user role"
                      value={newUserRole}
                      onChange={(e) => setNewUserRole(e.target.value)}
                      className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2"
                    >
                      <option value="clinician">Clinician</option>
                      <option value="reviewer">Reviewer</option>
                      <option value="readonly">Read-Only</option>
                      <option value="admin">Administrator</option>
                    </select>
                    <input
                      type="text"
                      required
                      value={newUserSpecialty}
                      onChange={(e) => setNewUserSpecialty(e.target.value)}
                      placeholder="Clinical Specialty"
                      className="w-full rounded-lg border border-slate-300 px-3 py-2"
                    />
                    <input
                      type="password"
                      required
                      minLength={8}
                      value={newUserPassword}
                      onChange={(e) => setNewUserPassword(e.target.value)}
                      placeholder="Initial Password (min 8 chars)"
                      className="w-full rounded-lg border border-slate-300 px-3 py-2"
                    />
                    <button
                      type="submit"
                      className="w-full rounded-lg bg-sky-700 px-4 py-2 font-bold text-white hover:bg-sky-600"
                    >
                      Create User Account
                    </button>
                  </form>
                </div>
              </div>
            )}
          </div>
        )}

        {/* =============================================================== */}
        {/* TAB 7: SECURITY AUDIT TRAIL & LIVE SERVICE HEALTH               */}
        {/* =============================================================== */}
        {activeTab === "audit-status" && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-xl font-bold text-slate-900">
                  Operational Service Topology &amp; Security Audit Trail
                </h1>
                <p className="text-xs text-slate-600">
                  Verifies live service health on assigned ports (3100, 8100, 8200, 8300, 5433) and displays PHI-redacted audit events.
                </p>
              </div>
            </div>

            {/* Service Port Health Cards */}
            <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
              <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-slate-900">
                    Frontend UI (:3100)
                  </span>
                  <span className="rounded bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-800">
                    ONLINE
                  </span>
                </div>
                <p className="text-[11px] text-slate-500">
                  Next.js 14 + Tailwind CSS v3
                </p>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-slate-900">
                    Rust Backend (:8100)
                  </span>
                  <span className="rounded bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-800">
                    {systemStatus?.rust_backend.status || "ONLINE"}
                  </span>
                </div>
                <p className="text-[11px] text-slate-500">
                  {systemStatus?.rust_backend.database_mode || "Axum + SQLx"}
                </p>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-slate-900">
                    Python XAI (:8200)
                  </span>
                  <span
                    className={`rounded px-2 py-0.5 text-[10px] font-bold ${
                      systemStatus?.python_ai_service.status === "ONLINE"
                        ? "bg-emerald-100 text-emerald-800"
                        : "bg-amber-100 text-amber-800"
                    }`}
                  >
                    {systemStatus?.python_ai_service.status || "CHECKING"}
                  </span>
                </div>
                <p className="text-[11px] text-slate-500">
                  PyTorch DenseNet-121 + Grad-CAM
                </p>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-slate-900">
                    FHIR R4 (:8300)
                  </span>
                  <span className="rounded bg-sky-100 px-2 py-0.5 text-[10px] font-bold text-sky-900">
                    LOCAL R4 ACTIVE
                  </span>
                </div>
                <p className="text-[11px] text-slate-500">
                  {systemStatus?.fhir_interoperability
                    .external_fhir_server_status || "Optional external server"}
                </p>
              </div>
            </div>

            {/* Immutable Security & Workflow Audit Log Table */}
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="text-sm font-bold text-slate-900 mb-3">
                Immutable Security &amp; Clinical Workflow Audit Trail
              </h2>
              {!permissions?.can_view_audit_logs ? (
                <p className="text-xs text-slate-500">
                  Full system audit log inspection is restricted to Administrators and Reviewers. Showing your recent personal session events ({recentAudits.length}).
                </p>
              ) : null}

              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-500">
                      <th className="py-2 pr-3">Timestamp</th>
                      <th className="py-2 pr-3">Actor</th>
                      <th className="py-2 pr-3">Category</th>
                      <th className="py-2 pr-3">Action</th>
                      <th className="py-2 pr-3">Resource</th>
                      <th className="py-2 pr-3">Outcome</th>
                      <th className="py-2">Redacted Details</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {(permissions?.can_view_audit_logs
                      ? fullAuditLogs
                      : recentAudits
                    ).map((log) => (
                      <tr key={log.id}>
                        <td className="py-2 pr-3 font-mono text-[11px] text-slate-500">
                          {log.created_at.slice(0, 19).replace("T", " ")}
                        </td>
                        <td className="py-2 pr-3">
                          <span className="font-medium text-slate-900">
                            {log.actor_email}
                          </span>{" "}
                          <span className="text-[10px] uppercase text-slate-500">
                            ({log.actor_role})
                          </span>
                        </td>
                        <td className="py-2 pr-3 font-mono text-[11px] text-slate-700">
                          {log.event_category}
                        </td>
                        <td className="py-2 pr-3 font-semibold text-slate-900">
                          {log.event_action}
                        </td>
                        <td className="py-2 pr-3 font-mono text-[11px] text-slate-600">
                          {log.resource_type}:{log.resource_id.slice(0, 14)}
                        </td>
                        <td className="py-2 pr-3">
                          <span
                            className={`rounded px-2 py-0.5 text-[10px] font-bold ${
                              log.outcome === "SUCCESS"
                                ? "bg-emerald-100 text-emerald-800"
                                : "bg-rose-100 text-rose-800"
                            }`}
                          >
                            {log.outcome}
                          </span>
                        </td>
                        <td className="py-2 text-slate-600">
                          {log.details_redacted}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

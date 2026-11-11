"use client";

import React, { useState, useEffect, useMemo, useCallback } from "react";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  Clock,
  ExternalLink,
  FileText,
  Info,
  Layers,
  RefreshCw,
  Shield,
  ShieldAlert,
  Sliders,
  TrendingDown,
  TrendingUp,
  UserCheck,
  Zap,
} from "lucide-react";
import {
  apiFetch,
  ApiRequestError,
  AuthenticatedUser,
  IcuAlertRecord,
  IcuModelRecord,
  IcuObservationRecord,
  IcuPredictionRecord,
  IcuShapItem,
  IcuStayRecord,
  PatientRecord,
} from "@/lib/api";

interface IcuEarlyWarningWorkspaceProps {
  user: AuthenticatedUser | null;
  onShowNotice?: (notice: { type: "success" | "error" | "warning"; title: string; message: string }) => void;
}

export default function IcuEarlyWarningWorkspace({
  user,
  onShowNotice,
}: IcuEarlyWarningWorkspaceProps) {
  // Stays & Active Selection
  const [stays, setStays] = useState<IcuStayRecord[]>([]);
  const [selectedStayId, setSelectedStayId] = useState<string>("stay-synth-001");
  const [loadingStays, setLoadingStays] = useState<boolean>(true);

  // Active Workspace Data
  const [activeStay, setActiveStay] = useState<IcuStayRecord | null>(null);
  const [activePatient, setActivePatient] = useState<PatientRecord | null>(null);
  const [observations, setObservations] = useState<IcuObservationRecord[]>([]);
  const [predictions, setPredictions] = useState<IcuPredictionRecord[]>([]);
  const [alerts, setAlerts] = useState<IcuAlertRecord[]>([]);
  const [activeModel, setActiveModel] = useState<IcuModelRecord | null>(null);
  const [allModels, setAllModels] = useState<IcuModelRecord[]>([]);
  const [loadingWorkspace, setLoadingWorkspace] = useState<boolean>(false);

  // Action States
  const [predicting, setPredicting] = useState<boolean>(false);
  const [acknowledgingAlertId, setAcknowledgingAlertId] = useState<string | null>(null);
  const [ackNotes, setAckNotes] = useState<string>("");
  const [submittingAck, setSubmittingAck] = useState<boolean>(false);
  const [showModelModal, setShowModelModal] = useState<boolean>(false);
  const [selectedVitalTab, setSelectedVitalTab] = useState<string>("HR");

  // Load Stays List
  const loadStays = useCallback(async () => {
    try {
      setLoadingStays(true);
      const res = await apiFetch<{ stays?: IcuStayRecord[]; total?: number }>("/api/icu/stays");
      const loadedStays = Array.isArray(res?.stays) ? res.stays : [];
      setStays(loadedStays);
      if (loadedStays.length > 0 && !loadedStays.some((s) => s.stay_id === selectedStayId)) {
        setSelectedStayId(loadedStays[0].stay_id);
      }
    } catch (err) {
      const msg = err instanceof ApiRequestError ? err.message : "Failed to load ICU stays.";
      onShowNotice?.({ type: "error", title: "ICU Stays Error", message: msg });
    } finally {
      setLoadingStays(false);
    }
  }, [selectedStayId, onShowNotice]);

  useEffect(() => {
    loadStays();
  }, [loadStays]);

  // Load Active Stay Workspace
  const loadStayWorkspace = useCallback(async (stayId: string) => {
    try {
      setLoadingWorkspace(true);
      const res = await apiFetch<{
        stay?: IcuStayRecord;
        patient?: PatientRecord;
        observations?: IcuObservationRecord[];
        predictions?: IcuPredictionRecord[];
        alerts?: IcuAlertRecord[];
        active_model?: IcuModelRecord;
        models?: IcuModelRecord[];
      }>(`/api/icu/stays/${stayId}`);

      const st = res?.stay || null;
      setActiveStay(st);

      const pat = res?.patient || (st ? {
        id: st.patient_id,
        mrn: st.mrn || "PT-SYN-001",
        fhir_patient_id: `Patient/${st.patient_id}`,
        full_name: st.patient_name || "Synthetic Patient",
        birth_date: st.birth_date || "1970-01-01",
        sex: st.sex || "male",
        is_synthetic: 1,
        clinical_summary: st.chief_syndrome || "",
        allergies_json: JSON.stringify([]),
        active_conditions_json: JSON.stringify([]),
        retention_policy: "RESEARCH_COHORT",
        created_at: st.created_at || new Date().toISOString(),
        updated_at: st.created_at || new Date().toISOString(),
      } : null);
      setActivePatient(pat);

      setObservations(Array.isArray(res?.observations) ? res.observations : []);
      setPredictions(Array.isArray(res?.predictions) ? res.predictions : (st?.latest_prediction ? [st.latest_prediction] : []));
      setAlerts(Array.isArray(res?.alerts) ? res.alerts : (st?.active_alert ? [st.active_alert] : []));

      if (res?.active_model) setActiveModel(res.active_model);
      if (Array.isArray(res?.models) && res.models.length > 0) {
        setAllModels(res.models);
      } else if (res?.active_model) {
        setAllModels([res.active_model]);
      }
    } catch (err) {
      const msg = err instanceof ApiRequestError ? err.message : "Failed to load ICU workspace.";
      onShowNotice?.({ type: "error", title: "Access Error", message: msg });
    } finally {
      setLoadingWorkspace(false);
    }
  }, [onShowNotice]);

  useEffect(() => {
    if (selectedStayId) {
      loadStayWorkspace(selectedStayId);
    }
  }, [selectedStayId, loadStayWorkspace]);

  // On-Demand Risk Assessment
  const handleTriggerPrediction = async () => {
    if (!selectedStayId) return;
    try {
      setPredicting(true);
      const res = await apiFetch<{
        prediction_id: string;
        risk_score: number;
        risk_tier: string;
        prediction_horizon: string;
      }>(`/api/icu/stays/${selectedStayId}/predict`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      onShowNotice?.({
        type: "success",
        title: "Prediction Complete",
        message: `Calculated 6-12h risk: ${(res.risk_score * 100).toFixed(1)}% (${res.risk_tier} Tier).`,
      });
      await loadStayWorkspace(selectedStayId);
      await loadStays();
    } catch (err) {
      const msg = err instanceof ApiRequestError ? err.message : "Inference failed.";
      onShowNotice?.({ type: "error", title: "Prediction Error", message: msg });
    } finally {
      setPredicting(false);
    }
  };

  // Acknowledge Alert
  const handleAcknowledgeAlert = async () => {
    if (!acknowledgingAlertId || !ackNotes.trim()) return;
    try {
      setSubmittingAck(true);
      await apiFetch(`/api/icu/alerts/${acknowledgingAlertId}/acknowledge`, {
        method: "POST",
        body: JSON.stringify({ notes: ackNotes }),
      });
      onShowNotice?.({
        type: "success",
        title: "Alert Acknowledged",
        message: "Clinician note recorded with permanent audit timestamp.",
      });
      setAcknowledgingAlertId(null);
      setAckNotes("");
      await loadStayWorkspace(selectedStayId);
      await loadStays();
    } catch (err) {
      const msg = err instanceof ApiRequestError ? err.message : "Failed to acknowledge alert.";
      onShowNotice?.({ type: "error", title: "Acknowledgement Error", message: msg });
    } finally {
      setSubmittingAck(false);
    }
  };

  // Latest Prediction and SHAP
  const latestPrediction = useMemo(() => {
    if (Array.isArray(predictions) && predictions.length > 0) return predictions[0];
    return activeStay?.latest_prediction || null;
  }, [predictions, activeStay]);

  const parsedShapItems: IcuShapItem[] = useMemo(() => {
    if (!latestPrediction?.shap_attributions_json) return [];
    try {
      const parsed = JSON.parse(latestPrediction.shap_attributions_json);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }, [latestPrediction]);

  // Observation Filter by selected vital
  const filteredObservations = useMemo(() => {
    if (!Array.isArray(observations)) return [];
    return observations
      .filter((o) => o && o.variable_name === selectedVitalTab)
      .sort((a, b) => (Number(a?.iculos_hour) || 0) - (Number(b?.iculos_hour) || 0));
  }, [observations, selectedVitalTab]);

  // Safe time formatting helper
  const formatAlertTime = (t?: string | null) => {
    if (!t) return "—";
    try {
      const d = new Date(t);
      return isNaN(d.getTime()) ? String(t) : d.toLocaleTimeString();
    } catch {
      return String(t);
    }
  };

  // Risk Tier Styling
  const getTierBadge = (tier: string) => {
    switch (tier) {
      case "CRITICAL":
        return "bg-rose-100 text-rose-800 border-rose-300 animate-pulse";
      case "HIGH":
        return "bg-amber-100 text-amber-800 border-amber-300";
      case "MODERATE":
        return "bg-yellow-100 text-yellow-800 border-yellow-300";
      case "LOW":
        return "bg-emerald-100 text-emerald-800 border-emerald-300";
      default:
        return "bg-slate-100 text-slate-700 border-slate-300";
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Clinical Governance Notice */}
      <div className="bg-sky-50 border border-sky-200 rounded-lg p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-sm">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-sky-600 text-white rounded-md">
            <Activity className="h-5 w-5" />
          </div>
          <div>
            <h2 className="font-bold text-sky-950 flex items-center gap-2">
              ICU Early Warning & Sepsis Deterioration System
              <span className="text-xs bg-sky-200 text-sky-800 font-semibold px-2 py-0.5 rounded">
                RESEARCH PREVIEW • 6–12h HORIZON
              </span>
            </h2>
            <p className="text-sky-800 text-xs mt-0.5">
              Multivariate time-series inference using PhysioNet 2019 Sepsis-3 definitions. Auxiliary decision-support only; not cleared for autonomous intervention.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 self-end sm:self-auto">
          {activeModel && (
            <button
              onClick={() => setShowModelModal(true)}
              className="text-xs bg-white hover:bg-slate-50 text-slate-700 border border-slate-300 px-3 py-1.5 rounded-md font-medium flex items-center gap-1.5 transition shadow-sm"
              aria-label="View Model Metrics & Provenance"
            >
              <Info className="h-3.5 w-3.5 text-sky-600" />
              Model Metrics (AUROC: {typeof activeModel.auroc === "number" ? activeModel.auroc.toFixed(3) : "—"})
            </button>
          )}
          <button
            onClick={() => loadStayWorkspace(selectedStayId)}
            disabled={loadingWorkspace}
            className="text-xs bg-white hover:bg-slate-50 text-slate-700 border border-slate-300 px-2.5 py-1.5 rounded-md transition shadow-sm flex items-center gap-1"
            title="Refresh Data"
            aria-label="Refresh Workspace"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loadingWorkspace ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* Patient & ICU Stay Selector Bar */}
      <div className="bg-white border border-slate-200 rounded-lg p-4 shadow-sm">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3 w-full sm:w-auto">
            <label htmlFor="icu-stay-select" className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Active ICU Patient:
            </label>
            <select
              id="icu-stay-select"
              value={selectedStayId}
              onChange={(e) => setSelectedStayId(e.target.value)}
              disabled={loadingStays}
              className="flex-1 sm:w-80 text-sm font-medium border border-slate-300 rounded-md px-3 py-1.5 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-sky-600"
            >
              {(stays || []).map((s) => (
                <option key={s.stay_id} value={s.stay_id}>
                  {s.patient_name} — {s.icu_unit} ({s.bed_number}) [{s.acuity_status}]
                </option>
              ))}
            </select>
          </div>

          {activeStay && (
            <div className="flex flex-wrap items-center gap-3 text-xs text-slate-600">
              <span className="font-mono bg-slate-100 px-2 py-1 rounded border border-slate-200">
                MRN: {activePatient?.mrn || activeStay.mrn}
              </span>
              <span className="bg-slate-100 px-2 py-1 rounded border border-slate-200">
                Unit: <strong className="text-slate-800">{activeStay.icu_unit}</strong> ({activeStay.bed_number})
              </span>
              <span className="bg-slate-100 px-2 py-1 rounded border border-slate-200">
                ICU LOS: <strong className="text-slate-800">{activeStay.iculos_hours}h</strong>
              </span>
              <span
                className={`font-semibold px-2.5 py-1 rounded border ${getTierBadge(
                  latestPrediction?.risk_tier || activeStay.acuity_status
                )}`}
              >
                {latestPrediction ? `${latestPrediction.risk_tier} RISK` : activeStay.acuity_status}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Main Workspace 2-Column Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Longitudinal Vitals & Observations (7 Cols) */}
        <div className="lg:col-span-7 space-y-6">
          {/* Longitudinal Vital Trends Card */}
          <div className="bg-white border border-slate-200 rounded-lg p-5 shadow-sm">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between pb-3 border-b border-slate-100 gap-2">
              <div>
                <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                  <Activity className="h-4 w-4 text-sky-600" />
                  Longitudinal Observations & Temporal Trends
                </h3>
                <p className="text-xs text-slate-500">Hourly chart measurements strictly backward-looking from ICU Hour {activeStay?.iculos_hours || 1}</p>
              </div>

              {/* Vital Selector Tabs */}
              <div className="flex flex-wrap gap-1 bg-slate-100 p-1 rounded-md">
                {["HR", "MAP", "SBP", "Resp", "Temp", "Lactate", "WBC"].map((v) => (
                  <button
                    key={v}
                    onClick={() => setSelectedVitalTab(v)}
                    className={`text-xs px-2.5 py-1 rounded font-medium transition ${
                      selectedVitalTab === v
                        ? "bg-white text-sky-700 shadow-xs font-bold"
                        : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    {v}
                  </button>
                ))}
              </div>
            </div>

            {/* Simple SVG Chart of Hourly Trends */}
            <div className="pt-4 pb-2">
              {filteredObservations.length === 0 ? (
                <div className="text-center py-10 text-xs text-slate-400 bg-slate-50 rounded-md border border-dashed border-slate-200">
                  No {selectedVitalTab} records available in current observation window.
                </div>
              ) : (
                <div>
                  <div className="flex items-center justify-between text-xs text-slate-500 mb-2">
                    <span>
                      Metric: <strong>{selectedVitalTab}</strong> ({filteredObservations[0]?.value_unit || ""})
                    </span>
                    <span>
                      Latest: <strong className="text-slate-900">{filteredObservations[filteredObservations.length - 1]?.valuenum ?? "—"}</strong> {filteredObservations[0]?.value_unit || ""}
                    </span>
                  </div>

                  {/* SVG Line Sparkline */}
                  <div className="h-44 w-full bg-slate-50 rounded-md p-3 border border-slate-200 flex flex-col justify-between relative overflow-hidden">
                    <svg className="w-full h-32 overflow-visible" viewBox="0 0 400 100" preserveAspectRatio="none">
                      {/* Grid Lines */}
                      <line x1="0" y1="20" x2="400" y2="20" stroke="#e2e8f0" strokeDasharray="3,3" />
                      <line x1="0" y1="50" x2="400" y2="50" stroke="#e2e8f0" strokeDasharray="3,3" />
                      <line x1="0" y1="80" x2="400" y2="80" stroke="#e2e8f0" strokeDasharray="3,3" />

                      {/* Points Calculation */}
                      {(() => {
                        const vals = filteredObservations.map((o) => Number(o?.valuenum ?? 0)).filter((v) => !isNaN(v));
                        const min = vals.length > 0 ? Math.min(...vals) * 0.95 : 0;
                        const max = vals.length > 0 ? Math.max(...vals) * 1.05 : 100;
                        const range = max > min ? max - min : 1;
                        const n = filteredObservations.length;
                        const points = filteredObservations.map((o, idx) => {
                          const v = Number(o?.valuenum ?? 0);
                          const x = n > 1 ? (idx / (n - 1)) * 380 + 10 : 200;
                          const y = 90 - ((v - min) / range) * 80;
                          return `${x},${isNaN(y) ? 50 : y}`;
                        });
                        return (
                          <>
                            <polyline
                              fill="none"
                              stroke="#0284c7"
                              strokeWidth="2.5"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              points={points.join(" ")}
                            />
                            {filteredObservations.map((o, idx) => {
                              const v = Number(o?.valuenum ?? 0);
                              const x = n > 1 ? (idx / (n - 1)) * 380 + 10 : 200;
                              const y = 90 - ((v - min) / range) * 80;
                              return (
                                <circle
                                  key={idx}
                                  cx={x}
                                  cy={isNaN(y) ? 50 : y}
                                  r="3"
                                  className="fill-sky-700 hover:fill-rose-600 transition"
                                />
                              );
                            })}
                          </>
                        );
                      })()}
                    </svg>
                    <div className="flex items-center justify-between text-[11px] text-slate-400 border-t border-slate-200 pt-1">
                      <span>Hour {filteredObservations[0]?.iculos_hour ?? 1}</span>
                      <span>Trend over ICU Stay</span>
                      <span>Hour {filteredObservations[filteredObservations.length - 1]?.iculos_hour ?? 1}</span>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Recent Observations Mini Table */}
            <div className="mt-4 pt-4 border-t border-slate-100">
              <h4 className="text-xs font-semibold text-slate-700 uppercase tracking-wider mb-2">
                Recent Hourly Vital Signs Log
              </h4>
              <div className="overflow-x-auto max-h-48 overflow-y-auto rounded border border-slate-200">
                <table className="w-full text-xs text-left">
                  <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200 sticky top-0">
                    <tr>
                      <th className="px-3 py-1.5">ICU Hour</th>
                      <th className="px-3 py-1.5">Variable</th>
                      <th className="px-3 py-1.5">Value</th>
                      <th className="px-3 py-1.5">Unit</th>
                      <th className="px-3 py-1.5">LOINC</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 font-mono">
                    {(observations || []).slice(-12).reverse().map((obs) => (
                      <tr key={obs.id || Math.random()} className="hover:bg-slate-50">
                        <td className="px-3 py-1 text-slate-500">{obs.iculos_hour ?? "—"}</td>
                        <td className="px-3 py-1 font-semibold text-slate-900">{obs.variable_name ?? "—"}</td>
                        <td className="px-3 py-1 text-sky-700 font-bold">{obs.valuenum ?? "—"}</td>
                        <td className="px-3 py-1 text-slate-500">{obs.value_unit ?? "—"}</td>
                        <td className="px-3 py-1 text-slate-400">{obs.loinc_code || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* Active Deterioration Alerts & Clinical Review Card */}
          <div className="bg-white border border-slate-200 rounded-lg p-5 shadow-sm">
            <h3 className="text-sm font-bold text-slate-900 flex items-center justify-between pb-3 border-b border-slate-100">
              <span className="flex items-center gap-2">
                <ShieldAlert className="h-4 w-4 text-rose-600" />
                Deterioration Alerts & Clinical Acknowledgement
              </span>
              <span className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded font-mono">
                {(alerts || []).length} Total Alerts
              </span>
            </h3>

            <div className="mt-3 space-y-3">
              {(alerts || []).length === 0 ? (
                <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-md text-xs text-emerald-800 flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-emerald-600 flex-shrink-0" />
                  No active or unacknowledged clinical deterioration alerts for this stay.
                </div>
              ) : (
                (alerts || []).map((al) => (
                  <div
                    key={al.id || Math.random()}
                    className={`p-3.5 rounded-lg border text-xs flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 ${
                      al.status === "TRIGGERED"
                        ? "bg-rose-50/80 border-rose-300 text-rose-950"
                        : "bg-slate-50 border-slate-200 text-slate-700"
                    }`}
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className={`font-bold px-2 py-0.5 rounded border text-[11px] ${getTierBadge(al.risk_tier || "MODERATE")}`}>
                          {al.risk_tier || "ALERT"} DETERIORATION ALERT
                        </span>
                        <span className="text-slate-500 text-[11px]">
                          Score: <strong>{((Number(al.risk_score) || 0) * 100).toFixed(1)}%</strong>
                        </span>
                        <span className="text-slate-400 text-[11px]">
                          Time: {formatAlertTime(al.alert_time)}
                        </span>
                      </div>
                      <p className="text-[12px] text-slate-700">
                        Target Horizon: <strong>6 to 12 Hours Lead Time</strong>. Elevated risk of septic organ dysfunction.
                      </p>
                      {al.acknowledged_by && (
                        <p className="text-[11px] text-emerald-700 flex items-center gap-1 font-medium">
                          <CheckCircle2 className="h-3 w-3" />
                          Acknowledged by {al.acknowledged_by}: &quot;{al.acknowledgement_notes}&quot;
                        </p>
                      )}
                    </div>

                    {al.status === "TRIGGERED" && user?.role !== "readonly" && (
                      <button
                        onClick={() => {
                          setAcknowledgingAlertId(al.id);
                          setAckNotes("Attending notified; ordered IV fluid bolus, repeat serum lactate, and blood cultures.");
                        }}
                        className="bg-rose-600 hover:bg-rose-700 text-white font-semibold text-xs px-3 py-1.5 rounded-md transition shadow-sm whitespace-nowrap self-end sm:self-auto flex items-center gap-1"
                      >
                        <UserCheck className="h-3.5 w-3.5" />
                        Acknowledge & Sign
                      </button>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Right Column: AI Risk Estimation & SHAP Explainability (5 Cols) */}
        <div className="lg:col-span-5 space-y-6">
          {/* Risk Prediction Panel */}
          <div className="bg-white border border-slate-200 rounded-lg p-5 shadow-sm space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                <Zap className="h-4 w-4 text-amber-500" />
                6–12h Sepsis Deterioration Risk
              </h3>
              <button
                onClick={handleTriggerPrediction}
                disabled={predicting || user?.role === "readonly"}
                className="text-xs bg-sky-600 hover:bg-sky-700 disabled:opacity-50 text-white px-3 py-1.5 rounded-md font-medium transition shadow-xs flex items-center gap-1.5"
                title="Execute LightGBM tree inference"
              >
                <RefreshCw className={`h-3 w-3 ${predicting ? "animate-spin" : ""}`} />
                {predicting ? "Estimating..." : "Run Risk Evaluation"}
              </button>
            </div>

            {/* Risk Gauge & Probability Bar */}
            {latestPrediction ? (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-xs text-slate-500">Calculated Probability:</span>
                    <div className="text-3xl font-extrabold text-slate-900">
                      {((Number(latestPrediction.risk_score) || 0) * 100).toFixed(1)}%
                    </div>
                  </div>
                  <div className="text-right">
                    <span className="text-xs text-slate-500">Stratified Tier:</span>
                    <div className="mt-0.5">
                      <span className={`text-xs font-bold px-2.5 py-1 rounded border ${getTierBadge(latestPrediction.risk_tier || "LOW")}`}>
                        {latestPrediction.risk_tier || "LOW"} RISK
                      </span>
                    </div>
                  </div>
                </div>

                {/* Probability Bar */}
                <div className="space-y-1">
                  <div className="w-full bg-slate-100 h-3 rounded-full overflow-hidden flex">
                    <div
                      className={`h-full transition-all duration-500 ${
                        latestPrediction.risk_tier === "CRITICAL"
                          ? "bg-rose-500"
                          : latestPrediction.risk_tier === "HIGH"
                          ? "bg-amber-500"
                          : latestPrediction.risk_tier === "MODERATE"
                          ? "bg-yellow-400"
                          : "bg-emerald-500"
                      }`}
                      style={{ width: `${Math.min(100, Math.max(5, (Number(latestPrediction.risk_score) || 0) * 100))}%` }}
                    />
                  </div>
                  <div className="flex justify-between text-[11px] text-slate-400">
                    <span>0.0%</span>
                    <span className="font-semibold text-slate-600">Threshold: {((Number(latestPrediction.decision_threshold) || 0.0326) * 100).toFixed(1)}%</span>
                    <span>100.0%</span>
                  </div>
                </div>

                {/* Horizon & Freshness Badges */}
                <div className="grid grid-cols-2 gap-2 pt-2 text-xs">
                  <div className="bg-slate-50 p-2.5 rounded border border-slate-200">
                    <span className="text-slate-500 block text-[11px]">Warning Horizon:</span>
                    <strong className="text-slate-800 flex items-center gap-1 mt-0.5">
                      <Clock className="h-3 w-3 text-sky-600" />
                      6 to 12 Hours
                    </strong>
                  </div>
                  <div className="bg-slate-50 p-2.5 rounded border border-slate-200">
                    <span className="text-slate-500 block text-[11px]">Data Quality:</span>
                    <strong className="text-slate-800 flex items-center gap-1 mt-0.5">
                      <Shield className="h-3 w-3 text-emerald-600" />
                      {latestPrediction.data_quality_status || "ADEQUATE"}
                    </strong>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center py-8 text-xs text-slate-400">
                No prediction recorded yet. Click &quot;Run Risk Evaluation&quot; to compute.
              </div>
            )}
          </div>

          {/* Explainable AI (SHAP Feature Attributions) */}
          <div className="bg-white border border-slate-200 rounded-lg p-5 shadow-sm space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                <Sliders className="h-4 w-4 text-indigo-600" />
                SHAP Feature Attributions
              </h3>
              <span className="text-[11px] bg-indigo-50 text-indigo-700 font-medium px-2 py-0.5 rounded border border-indigo-200">
                TreeExplainer Local
              </span>
            </div>

            <p className="text-xs text-slate-500">
              Directional contributions of patient features toward current risk score. Values show statistical tree split weights, not medical causes.
            </p>

            <div className="space-y-3">
              {(parsedShapItems || []).length === 0 ? (
                <div className="text-center py-6 text-xs text-slate-400">
                  Run a risk evaluation to inspect SHAP attributions.
                </div>
              ) : (
                (parsedShapItems || []).slice(0, 6).map((item, idx) => {
                  const isPositive = item?.direction === "INCREASES_RISK";
                  const sVal = Number(item?.shap_value || 0);
                  const cVal = Number(item?.current_value || 0);
                  return (
                    <div key={idx} className="p-2.5 bg-slate-50 rounded-md border border-slate-200 space-y-1.5">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-semibold text-slate-800 flex items-center gap-1.5">
                          {isPositive ? (
                            <>
                              <ArrowUpRight className="h-3.5 w-3.5 text-rose-500" />
                              <span className="text-[10px] font-bold text-rose-700 bg-rose-50 px-1.5 py-0.5 rounded border border-rose-200">
                                INCREASES_RISK
                              </span>
                            </>
                          ) : (
                            <>
                              <ArrowDownRight className="h-3.5 w-3.5 text-emerald-500" />
                              <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200">
                                DECREASES_RISK
                              </span>
                            </>
                          )}
                          {item?.display_name || item?.feature || "Feature"}
                        </span>
                        <span className="font-mono text-[11px] text-slate-600">
                          Val: <strong>{cVal}</strong> | SHAP:{" "}
                          <strong className={isPositive ? "text-rose-600" : "text-emerald-600"}>
                            {sVal > 0 ? `+${sVal.toFixed(3)}` : sVal.toFixed(3)}
                          </strong>
                        </span>
                      </div>

                      {/* Directional Impact Bar */}
                      <div className="w-full bg-slate-200 h-1.5 rounded-full overflow-hidden flex">
                        <div
                          className={`h-full ${isPositive ? "bg-rose-500" : "bg-emerald-500"}`}
                          style={{ width: `${Math.min(100, Math.abs(sVal) * 150)}%` }}
                        />
                      </div>

                      <p className="text-[11px] text-slate-500 leading-tight">
                        {item?.clinical_rationale || ""}
                      </p>
                    </div>
                  );
                })
              )}
            </div>

            <div className="p-3 bg-slate-100 rounded text-[11px] text-slate-500 border border-slate-200 flex items-start gap-2">
              <Info className="h-3.5 w-3.5 text-slate-400 mt-0.5 flex-shrink-0" />
              <span>
                <strong>Attribution Notice:</strong> SHAP values explain model predictions relative to the baseline population. High SHAP attribution does not prove medical causation.
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Alert Acknowledgement Modal */}
      {acknowledgingAlertId && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-lg border border-slate-200 shadow-xl max-w-lg w-full p-6 space-y-4">
            <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
              <ShieldAlert className="h-5 w-5 text-rose-600" />
              Acknowledge Clinical Deterioration Alert
            </h3>
            <p className="text-xs text-slate-600">
              Entering your review notes acknowledges that you have evaluated the 6-12h sepsis risk alert and formulated an appropriate clinical management plan.
            </p>

            <div className="space-y-1.5">
              <label htmlFor="ack-notes-input" className="text-xs font-semibold text-slate-700">
                Clinician Evaluation & Intervention Notes:
              </label>
              <textarea
                id="ack-notes-input"
                rows={3}
                value={ackNotes}
                onChange={(e) => setAckNotes(e.target.value)}
                className="w-full text-xs border border-slate-300 rounded-md p-2.5 focus:outline-none focus:ring-2 focus:ring-sky-600 font-sans"
                placeholder="Enter actions taken (e.g. bedside assessment, fluid bolus, blood cultures)..."
              />
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
              <button
                onClick={() => setAcknowledgingAlertId(null)}
                disabled={submittingAck}
                className="px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 rounded-md font-medium"
              >
                Cancel
              </button>
              <button
                onClick={handleAcknowledgeAlert}
                disabled={submittingAck || !ackNotes.trim()}
                className="px-4 py-1.5 text-xs bg-rose-600 hover:bg-rose-700 disabled:opacity-50 text-white rounded-md font-semibold transition flex items-center gap-1.5"
              >
                {submittingAck ? "Signing..." : "Confirm & Sign Off"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Model Metrics & Provenance Modal */}
      {showModelModal && activeModel && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-lg border border-slate-200 shadow-xl max-w-xl w-full p-6 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <Layers className="h-5 w-5 text-sky-600" />
                Model Specifications & Validation Metrics
              </h3>
              <button
                onClick={() => setShowModelModal(false)}
                className="text-slate-400 hover:text-slate-600 text-sm font-bold"
              >
                ✕
              </button>
            </div>

            {(allModels || []).length > 1 && (
              <div className="flex flex-wrap gap-1.5 bg-slate-100 p-1.5 rounded-md">
                {(allModels || []).map((m) => (
                  <button
                    key={m.model_id || Math.random()}
                    onClick={() => setActiveModel(m)}
                    className={`text-xs px-3 py-1.5 rounded font-medium transition flex-1 ${
                      activeModel?.model_id === m.model_id
                        ? "bg-white text-sky-800 shadow-xs font-bold border border-sky-200"
                        : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    {m.model_name || m.model_id}
                  </button>
                ))}
              </div>
            )}

            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="bg-slate-50 p-2.5 rounded border border-slate-200">
                <span className="text-slate-500 block">Model ID:</span>
                <strong className="text-slate-800 font-mono">{activeModel.model_id || "—"}</strong>
              </div>
              <div className="bg-slate-50 p-2.5 rounded border border-slate-200">
                <span className="text-slate-500 block">Algorithm:</span>
                <strong className="text-slate-800">{(activeModel.algorithm || "LightGBM").toUpperCase()} + Tree SHAP</strong>
              </div>
              <div className="bg-slate-50 p-2.5 rounded border border-slate-200">
                <span className="text-slate-500 block">Prediction Horizon:</span>
                <strong className="text-slate-800">{(activeModel.prediction_horizon || "6-12 hours").replace(/_/g, " ")}</strong>
              </div>
              <div className="bg-slate-50 p-2.5 rounded border border-slate-200">
                <span className="text-slate-500 block">Decision Threshold:</span>
                <strong className="text-slate-800 font-mono">{((Number(activeModel.decision_threshold) || 0) * 100).toFixed(2)}%</strong>
              </div>
            </div>

            <h4 className="text-xs font-semibold text-slate-700 uppercase tracking-wider pt-2">
              Measured Metrics on Held-Out Test Set:
            </h4>
            <div className="grid grid-cols-5 gap-2 text-center text-xs">
              <div className="bg-sky-50 border border-sky-200 p-2 rounded">
                <span className="text-sky-700 block text-[10px]">AUROC</span>
                <strong className="text-sky-950 text-sm font-bold">{typeof activeModel.auroc === "number" ? activeModel.auroc.toFixed(4) : "—"}</strong>
              </div>
              <div className="bg-sky-50 border border-sky-200 p-2 rounded">
                <span className="text-sky-700 block text-[10px]">AUPRC</span>
                <strong className="text-sky-950 text-sm font-bold">{typeof activeModel.auprc === "number" ? activeModel.auprc.toFixed(4) : "—"}</strong>
              </div>
              <div className="bg-sky-50 border border-sky-200 p-2 rounded">
                <span className="text-sky-700 block text-[10px]">Brier Score</span>
                <strong className="text-sky-950 text-sm font-bold">{typeof activeModel.brier_score === "number" ? activeModel.brier_score.toFixed(4) : "—"}</strong>
              </div>
              <div className="bg-sky-50 border border-sky-200 p-2 rounded">
                <span className="text-sky-700 block text-[10px]">Sensitivity</span>
                <strong className="text-sky-950 text-sm font-bold">{typeof activeModel.sensitivity === "number" ? (activeModel.sensitivity * 100).toFixed(1) + "%" : "—"}</strong>
              </div>
              <div className="bg-sky-50 border border-sky-200 p-2 rounded">
                <span className="text-sky-700 block text-[10px]">Specificity</span>
                <strong className="text-sky-950 text-sm font-bold">{typeof activeModel.specificity === "number" ? (activeModel.specificity * 100).toFixed(1) + "%" : "—"}</strong>
              </div>
            </div>

            <div className="text-[11px] text-slate-500 bg-slate-50 p-3 rounded border border-slate-200 leading-relaxed">
              {(activeModel.model_id || "").includes("cohort") ? (
                <>
                  <strong>Dataset Provenance (Archive2 Cohort):</strong> Trained and evaluated on the 5,000-patient synthetic ICU clinical cohort (83 baseline vital, laboratory, and comorbidity predictors; post-event interventions, post-stay outcomes, and synthetic target proxies strictly excluded). Secondary CHF endpoint AUROC = 0.7176.
                </>
              ) : (
                <>
                  <strong>Dataset Provenance (PhysioNet 2019):</strong> Trained and tested on 118 real ICU stays (4,615 observation hours) from the Computing in Cardiology Challenge 2019 (CC BY 4.0). Split grouped strictly by unique patient ID (70% Train, 15% Val, 15% Test) with verified zero patient overlap.
                </>
              )}
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setShowModelModal(false)}
                className="px-4 py-1.5 text-xs bg-slate-800 text-white rounded-md font-semibold hover:bg-slate-900"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

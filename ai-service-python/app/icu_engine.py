"""
OmniMed Insight — ICU Early Warning & Sepsis Deterioration Inference Engine
Loads trained LightGBM champion model and SHAP TreeExplainer, extracts backward-looking
temporal features from incoming patient observations, computes calibrated deterioration risk,
and produces local feature attribution vectors.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import joblib
import numpy as np
import pandas as pd

FEATURE_DISPLAY_NAMES = {
    "pulse_pressure": "Pulse Pressure (SBP - DBP)",
    "Temp_roll_min_6h": "6h Minimum Core Temperature",
    "Temp_roll_max_6h": "6h Peak Core Temperature",
    "Temp_latest": "Latest Core Temperature",
    "MAP_roll_std_6h": "6h Blood Pressure Variability (MAP Std)",
    "MAP_roll_min_6h": "6h Minimum Mean Arterial Pressure",
    "Lactate_latest": "Latest Serum Lactate",
    "Lactate_roll_max_6h": "6h Peak Serum Lactate (Hypoperfusion)",
    "Lactate_roll_mean_6h": "6h Mean Serum Lactate",
    "WBC_roll_min_6h": "6h Minimum White Blood Cell Count",
    "HR_roll_max_6h": "6h Peak Heart Rate (Tachycardia)",
    "HR_roll_min_6h": "6h Minimum Heart Rate",
    "Temp_roll_std_6h": "6h Thermal Volatility",
    "Resp_roll_std_6h": "6h Respiratory Rate Volatility",
    "Resp_roll_max_6h": "6h Peak Respiratory Rate (Tachypnea)",
    "SBP_roll_max_6h": "6h Peak Systolic Blood Pressure",
    "DBP_roll_max_6h": "6h Peak Diastolic Blood Pressure",
    "Glucose_roll_min_6h": "6h Minimum Blood Glucose",
    "Glucose_roll_mean_6h": "6h Mean Blood Glucose",
    "BUN_roll_min_6h": "6h Minimum Blood Urea Nitrogen (BUN)",
    "BUN_roll_mean_6h": "6h Mean Blood Urea Nitrogen (BUN)",
    "BUN_latest": "Latest Blood Urea Nitrogen (BUN)",
    "HCO3_roll_min_6h": "6h Minimum Serum Bicarbonate (HCO3)",
    "WBC_time_since_meas": "Hours Since Last WBC Lab",
    "shock_index": "Shock Index (HR / SBP)",
    "map_hypoperfusion_depth": "MAP Hypoperfusion Depth (< 65 mmHg)",
    "temp_deviation": "Core Temperature Deviation from 37.0°C",
    "qsofa_vital_score": "Vital Sign qSOFA Surrogate Score",
    "HR_latest": "Latest Heart Rate",
    "MAP_latest": "Latest Mean Arterial Pressure",
    "SBP_latest": "Latest Systolic Blood Pressure",
    "Resp_latest": "Latest Respiratory Rate",
    "O2Sat_latest": "Latest Oxygen Saturation (SpO2)",
    "Creatinine_latest": "Latest Serum Creatinine",
    "Platelets_latest": "Latest Platelet Count",
    "Age": "Patient Age at Admission",
}

FEATURE_CLINICAL_RATIONALE = {
    "pulse_pressure": "Narrowing pulse pressure indicates diminishing stroke volume, hypovolemia, or severe systemic vasoconstriction.",
    "Temp_roll_min_6h": "Hypothermia (< 36°C) is a high-risk Sepsis-3 manifestation associated with impaired immune response and shock.",
    "Temp_roll_max_6h": "Sustained pyrexia (> 38.0°C) indicates active systemic inflammatory cytokine release.",
    "Temp_latest": "Core temperature abnormalities reflect acute hypothalamic thermal dysregulation during infection.",
    "MAP_roll_std_6h": "Marked blood pressure volatility reflects autonomic dysregulation and impending hemodynamic collapse.",
    "MAP_roll_min_6h": "Transient drops in mean arterial pressure signal early loss of vascular tone.",
    "Lactate_latest": "Elevated lactate reflects cellular hypoxia and anaerobic glycolysis due to systemic microvascular hypoperfusion.",
    "Lactate_roll_max_6h": "Peak 6-hour serum lactate > 2.0 mmol/L is a hallmark Sepsis-3 criterion for cryptic or overt septic shock.",
    "Lactate_roll_mean_6h": "Sustained hyperlactatemia indicates impaired lactate clearance and ongoing tissue oxygen debt.",
    "WBC_roll_min_6h": "Leukopenia (< 4.0 x 10^3/uL) or leukocytosis reflects acute systemic immune activation or consumption.",
    "HR_roll_max_6h": "Sustained tachycardia represents compensatory sympathetic surge in response to vasodilation or pyrexia.",
    "HR_roll_min_6h": "Elevated baseline heart rate without recovery periods indicates persistent sympathetic drive.",
    "Resp_roll_std_6h": "Respiratory rate variability reflects changing ventilatory drive and compensatory response to metabolic acidosis.",
    "Resp_roll_max_6h": "Tachypnea (>= 22 breaths/min) is a core qSOFA indicator of respiratory compensation for acidemia or hypoxia.",
    "Glucose_roll_min_6h": "Glycemic fluctuations (stress hyperglycemia or sepsis-induced hypoglycemia) indicate neuroendocrine stress.",
    "BUN_roll_min_6h": "Elevated blood urea nitrogen reflects prerenal azotemia and reduced renal cortical perfusion.",
    "BUN_roll_mean_6h": "Rising BUN trajectory correlates with acute kidney injury and protein catabolism in sepsis.",
    "BUN_latest": "Blood urea nitrogen status reflects renal filtration and intravascular volume status.",
    "HCO3_roll_min_6h": "Decreased serum bicarbonate (< 22 mEq/L) signals uncompensated high-anion-gap metabolic acidosis.",
    "Temp_roll_std_6h": "Thermal instability across a 6-hour window correlates with bacteremic rigors and cytokine surges.",
    "Age": "Advanced chronological age increases baseline vulnerability to infection-induced organ dysfunction.",
    "shock_index": "Shock Index > 0.8 is an early indicator of occult circulatory failure before overt hypotension develops.",
    "map_hypoperfusion_depth": "Mean arterial pressure below 65 mmHg compromises vital organ capillary perfusion pressure.",
    "temp_deviation": "Significant thermal displacement from 37°C indicates systemic inflammatory response syndrome (SIRS).",
}

class IcuEarlyWarningEngine:
    def __init__(self, models_dir: Optional[Path] = None):
        if models_dir is None:
            models_dir = Path(__file__).resolve().parent.parent / "models" / "icu"
        self.models_dir = models_dir
        
        self.model = None
        self.explainer = None
        self.meta = {}
        self.feature_cols = []
        self.imputation_medians = {}
        self.threshold = 0.05
        
        self._load_artifacts()
        
    def _load_artifacts(self):
        meta_file = self.models_dir / "champion_model_meta.json"
        model_file = self.models_dir / "champion_model.joblib"
        explainer_file = self.models_dir / "shap_explainer.joblib"
        
        if not meta_file.exists() or not model_file.exists():
            raise FileNotFoundError(f"ICU model artifacts missing in {self.models_dir}. Please run train_models.py first.")
            
        with open(meta_file, "r", encoding="utf-8") as f:
            self.meta = json.load(f)
            
        self.feature_cols = self.meta["feature_cols"]
        self.imputation_medians = self.meta["imputation_medians"]
        self.threshold = float(self.meta.get("decision_threshold", 0.05))
        
        self.model = joblib.load(model_file)
        if explainer_file.exists():
            self.explainer = joblib.load(explainer_file)
            
    def compute_features_from_observations(
        self,
        observations: List[Dict[str, Any]],
        age: float = 65.0,
        gender: float = 0.0,
        current_iculos: int = 12
    ) -> Tuple[np.ndarray, Dict[str, Optional[float]], str]:
        """
        Builds the 119-feature vector from incoming longitudinal observations.
        Returns (feature_vector, vital_signs_summary, data_quality_status).
        """
        if not observations:
            return np.zeros((1, len(self.feature_cols))), {}, "INSUFFICIENT_DATA"
            
        obs_df = pd.DataFrame(observations)
        if "variable_name" not in obs_df.columns or "value" not in obs_df.columns:
            return np.zeros((1, len(self.feature_cols))), {}, "INSUFFICIENT_DATA"
            
        obs_df["value"] = pd.to_numeric(obs_df["value"], errors="coerce")
        obs_df = obs_df.dropna(subset=["value"])
        
        # Ensure iculos_hour is present and strictly enforce temporal causality (iculos_hour <= current_iculos)
        if "iculos_hour" not in obs_df.columns:
            obs_df["iculos_hour"] = current_iculos
        else:
            obs_df["iculos_hour"] = pd.to_numeric(obs_df["iculos_hour"], errors="coerce").fillna(current_iculos)
            
        obs_df = obs_df[obs_df["iculos_hour"] <= current_iculos].sort_values("iculos_hour").reset_index(drop=True)
        if obs_df.empty:
            return np.zeros((1, len(self.feature_cols))), {}, "INSUFFICIENT_DATA"
        
        # Track vitals summary
        vitals_summary = {}
        for var in ["HR", "O2Sat", "Temp", "SBP", "MAP", "DBP", "Resp", "Lactate", "WBC", "Creatinine", "Platelets"]:
            var_records = obs_df[obs_df["variable_name"] == var]
            vitals_summary[var] = float(var_records["value"].iloc[-1]) if not var_records.empty else None
            
        # Quality check: are core vitals available?
        core_present = sum([1 for v in ["HR", "SBP", "Resp", "Temp", "O2Sat"] if vitals_summary.get(v) is not None])
        if core_present < 2:
            data_quality = "INSUFFICIENT_DATA"
        elif core_present < 4:
            data_quality = "SPARSE_DATA"
        else:
            data_quality = "ADEQUATE"
            
        # Build features dict with defaults from training imputation medians
        feat_dict = dict(self.imputation_medians)
        feat_dict["Age"] = float(age)
        feat_dict["Gender"] = float(gender)
        
        signal_vars = ["HR", "O2Sat", "Temp", "SBP", "MAP", "DBP", "Resp",
                       "Lactate", "WBC", "Creatinine", "Platelets", "Glucose", "BUN", "HCO3"]
        
        for var in signal_vars:
            var_rows = obs_df[obs_df["variable_name"] == var]
            if not var_rows.empty:
                latest_val = float(var_rows["value"].iloc[-1])
                latest_t = float(var_rows["iculos_hour"].iloc[-1])
                hrs_since = max(0.0, current_iculos - latest_t)
                
                feat_dict[f"{var}_latest"] = latest_val
                feat_dict[f"{var}_missing"] = 0
                feat_dict[f"{var}_time_since_meas"] = min(hrs_since, 48.0)
                
                # Past 6 hours window
                w6 = var_rows[var_rows["iculos_hour"] >= current_iculos - 6]
                if not w6.empty:
                    w_vals = w6["value"].values
                    feat_dict[f"{var}_roll_mean_6h"] = float(np.mean(w_vals))
                    feat_dict[f"{var}_roll_min_6h"] = float(np.min(w_vals))
                    feat_dict[f"{var}_roll_max_6h"] = float(np.max(w_vals))
                    feat_dict[f"{var}_roll_std_6h"] = float(np.std(w_vals)) if len(w_vals) > 1 else 0.0
                else:
                    feat_dict[f"{var}_roll_mean_6h"] = latest_val
                    feat_dict[f"{var}_roll_min_6h"] = latest_val
                    feat_dict[f"{var}_roll_max_6h"] = latest_val
                    feat_dict[f"{var}_roll_std_6h"] = 0.0
                    
                # 3h Trend
                w3 = var_rows[var_rows["iculos_hour"] >= current_iculos - 3]
                if len(w3) >= 2:
                    delta_v = w3["value"].iloc[-1] - w3["value"].iloc[0]
                    delta_t = max(1.0, w3["iculos_hour"].iloc[-1] - w3["iculos_hour"].iloc[0])
                    feat_dict[f"{var}_trend_3h"] = delta_v / delta_t
                else:
                    feat_dict[f"{var}_trend_3h"] = 0.0
            else:
                feat_dict[f"{var}_missing"] = 1
                feat_dict[f"{var}_time_since_meas"] = 48.0
                
        # Clinically Grounded Interactions
        hr = feat_dict.get("HR_latest", 80.0)
        sbp = feat_dict.get("SBP_latest", 120.0)
        dbp = feat_dict.get("DBP_latest", 75.0)
        map_val = feat_dict.get("MAP_latest", 85.0)
        temp = feat_dict.get("Temp_latest", 37.0)
        resp = feat_dict.get("Resp_latest", 16.0)
        
        feat_dict["shock_index"] = hr / max(20.0, sbp)
        feat_dict["pulse_pressure"] = sbp - dbp
        feat_dict["map_hypoperfusion_depth"] = max(0.0, 65.0 - map_val)
        feat_dict["temp_deviation"] = abs(temp - 37.0)
        
        qsofa = 0
        if sbp <= 100:
            qsofa += 1
        if resp >= 22:
            qsofa += 1
        feat_dict["qsofa_vital_score"] = qsofa
        
        # Build ordered vector
        vector = np.array([feat_dict.get(c, self.imputation_medians.get(c, 0.0)) for c in self.feature_cols], dtype=float).reshape(1, -1)
        return vector, vitals_summary, data_quality

    def predict(
        self,
        stay_id: str,
        patient_id: str,
        current_iculos: int,
        observations: List[Dict[str, Any]],
        age: float = 65.0,
        gender: float = 0.0
    ) -> Dict[str, Any]:
        """
        Executes prediction and generates local SHAP explanation.
        """
        vec, vitals_summary, data_quality = self.compute_features_from_observations(
            observations, age, gender, current_iculos
        )
        
        if data_quality == "INSUFFICIENT_DATA":
            return {
                "stay_id": stay_id,
                "patient_id": patient_id,
                "prediction_time": f"ICU Hour {current_iculos}",
                "prediction_horizon": "6_to_12_hours",
                "risk_score": 0.0,
                "risk_tier": "INSUFFICIENT_DATA",
                "model_id": self.meta.get("model_id", "omnimed-icu-v1"),
                "model_version": "1.0.0",
                "decision_threshold": self.threshold,
                "data_quality_status": "INSUFFICIENT_DATA",
                "stale_observations_warning": "Fewer than 2 vital sign observations recorded in current window.",
                "top_shap_attributions": [],
                "vital_signs_summary": vitals_summary,
                "clinical_disclaimer": "Insufficient observations available to evaluate clinical deterioration risk."
            }
            
        vec_df = pd.DataFrame(vec, columns=self.feature_cols)
        prob = float(self.model.predict_proba(vec_df)[0, 1])
        
        # Risk Stratification based on validated operating threshold
        # Threshold (self.threshold) marks boundary for High Risk early warning
        tau = max(0.01, self.threshold)
        if prob < 0.3 * tau:
            risk_tier = "LOW"
        elif prob < tau:
            risk_tier = "MODERATE"
        elif prob < 2.5 * tau:
            risk_tier = "HIGH"
        else:
            risk_tier = "CRITICAL"
            
        # Compute local SHAP attribution
        top_shap_items = []
        if self.explainer is not None:
            raw_shap = self.explainer.shap_values(vec_df, check_additivity=False)
            if isinstance(raw_shap, list):
                shap_vec = raw_shap[1][0] if len(raw_shap) > 1 else raw_shap[0][0]
            elif len(raw_shap.shape) == 3:
                shap_vec = raw_shap[0, :, 1]
            else:
                shap_vec = raw_shap[0]
                
            sorted_indices = np.argsort(np.abs(shap_vec))[::-1]
            for idx in sorted_indices[:8]:
                feat_name = self.feature_cols[idx]
                s_val = float(shap_vec[idx])
                curr_val = float(vec[0, idx])
                
                direction = "INCREASES_RISK" if s_val > 0.005 else ("DECREASES_RISK" if s_val < -0.005 else "NEUTRAL")
                disp_name = FEATURE_DISPLAY_NAMES.get(feat_name, feat_name.replace("_", " ").title())
                rationale = FEATURE_CLINICAL_RATIONALE.get(feat_name, f"Feature impact measured by tree gradient attribution ({direction}).")
                
                top_shap_items.append({
                    "feature": feat_name,
                    "display_name": disp_name,
                    "current_value": round(curr_val, 2),
                    "shap_value": round(s_val, 4),
                    "direction": direction,
                    "clinical_rationale": rationale
                })
                
        return {
            "stay_id": stay_id,
            "patient_id": patient_id,
            "prediction_time": f"ICU Hour {current_iculos}",
            "prediction_horizon": "6_to_12_hours",
            "risk_score": round(prob, 4),
            "risk_tier": risk_tier,
            "model_id": self.meta.get("model_id", "omnimed-icu-v1"),
            "model_version": "1.0.0",
            "decision_threshold": round(self.threshold, 3),
            "data_quality_status": data_quality,
            "stale_observations_warning": "Some laboratory markers are older than 24h." if data_quality == "SPARSE_DATA" else None,
            "top_shap_attributions": top_shap_items,
            "vital_signs_summary": vitals_summary,
            "clinical_disclaimer": "Decision-support research feature. Not an autonomous diagnostic device."
        }

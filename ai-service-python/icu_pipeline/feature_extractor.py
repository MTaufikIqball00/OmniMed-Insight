"""
ICU Time-Series Feature Engineering & 6-12h Warning Horizon Label Generator
Calculates backward-looking rolling statistics, physiological interaction features,
and strictly leakage-free early sepsis warning labels.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple

VITAL_COLS = ["HR", "O2Sat", "Temp", "SBP", "MAP", "DBP", "Resp"]
LAB_COLS = ["Lactate", "WBC", "Creatinine", "Platelets", "Glucose", "BUN", "HCO3"]
ALL_SIGNAL_COLS = VITAL_COLS + LAB_COLS

def extract_patient_features_and_labels(patient_df: pd.DataFrame) -> pd.DataFrame:
    """
    Processes a single patient's longitudinal trajectory.
    Enforces temporal correctness: at hour t, only data from hours <= t is used.
    """
    df = patient_df.copy().sort_values("ICULOS").reset_index(drop=True)
    
    # 1. Determine Sepsis Event Timing and Censoring
    # PhysioNet SepsisLabel == 1 starts 6h before clinical recognition (t_clinical)
    # So t_first_flag is (t_clinical - 6).
    # The 6-12h warning lead time corresponds to [t_first_flag - 6, t_first_flag].
    sepsis_indices = df.index[df["SepsisLabel"] == 1].tolist()
    has_sepsis = len(sepsis_indices) > 0
    
    if has_sepsis:
        first_sepsis_idx = sepsis_indices[0]
        first_sepsis_hour = df.loc[first_sepsis_idx, "ICULOS"]
        
        # If patient has sepsis at or immediately upon admission (<= 4h), exclude
        if first_sepsis_hour <= 4:
            return pd.DataFrame() # Excluded from early warning cohort
            
        # Define 6-12h warning window: 6 hours preceding first_sepsis_hour
        target_start_hour = max(1, first_sepsis_hour - 6)
        target_end_hour = first_sepsis_hour
        
        # Censoring: rows after first_sepsis_hour are censored (sepsis already recognized)
        df = df[df["ICULOS"] <= first_sepsis_hour].copy().reset_index(drop=True)
        
        # Assign binary target label: 1 if inside 6-12h warning window
        df["target_sepsis_6_12h"] = (
            (df["ICULOS"] >= target_start_hour) & (df["ICULOS"] <= target_end_hour)
        ).astype(int)
    else:
        # Patient never develops sepsis in this ICU stay
        df["target_sepsis_6_12h"] = 0
        
    if len(df) < 4:
        return pd.DataFrame()
        
    # 2. Compute Backward-Looking Rolling Features
    # Note: Forward fill within this patient's stay ONLY to track latest observed state
    # Raw values are preserved for missingness indicator computation
    records = []
    
    # We maintain running memory for forward fill and last measurement timestamp
    last_known_vals = {col: np.nan for col in ALL_SIGNAL_COLS}
    last_measured_hour = {col: -999 for col in ALL_SIGNAL_COLS}
    
    # Pre-calculate rolling history buffers
    history_buffers = {col: [] for col in ALL_SIGNAL_COLS}
    
    for idx, row in df.iterrows():
        t = row["ICULOS"]
        row_feat = {
            "patient_id": row["patient_id"],
            "ICULOS": t,
            "Age": row["Age"] if "Age" in row and not np.isnan(row["Age"]) else 65.0,
            "Gender": row["Gender"] if "Gender" in row and not np.isnan(row["Gender"]) else 0.0,
            "target_sepsis_6_12h": row["target_sepsis_6_12h"],
        }
        
        # Process each clinical signal
        for col in ALL_SIGNAL_COLS:
            val = row[col] if col in row else np.nan
            is_missing = np.isnan(val)
            row_feat[f"{col}_missing"] = 1 if is_missing else 0
            
            if not is_missing:
                last_known_vals[col] = val
                last_measured_hour[col] = t
                
            current_val = last_known_vals[col]
            row_feat[f"{col}_latest"] = current_val
            
            # Hours since last measurement
            hrs_since = (t - last_measured_hour[col]) if last_measured_hour[col] != -999 else 48.0
            row_feat[f"{col}_time_since_meas"] = min(hrs_since, 48.0)
            
            # Update history buffer (store tuples of (hour, val))
            if not np.isnan(current_val):
                history_buffers[col].append((t, current_val))
                
            # Filter buffer to last 6 hours
            history_buffers[col] = [(th, v) for th, v in history_buffers[col] if th >= t - 6]
            buf_vals = [v for _, v in history_buffers[col]]
            
            if len(buf_vals) > 0:
                row_feat[f"{col}_roll_mean_6h"] = float(np.mean(buf_vals))
                row_feat[f"{col}_roll_min_6h"] = float(np.min(buf_vals))
                row_feat[f"{col}_roll_max_6h"] = float(np.max(buf_vals))
                row_feat[f"{col}_roll_std_6h"] = float(np.std(buf_vals)) if len(buf_vals) > 1 else 0.0
            else:
                row_feat[f"{col}_roll_mean_6h"] = np.nan
                row_feat[f"{col}_roll_min_6h"] = np.nan
                row_feat[f"{col}_roll_max_6h"] = np.nan
                row_feat[f"{col}_roll_std_6h"] = 0.0
                
            # Trend / rate of change over last 3 hours
            buf_3h = [(th, v) for th, v in history_buffers[col] if th >= t - 3]
            if len(buf_3h) >= 2:
                delta_v = buf_3h[-1][1] - buf_3h[0][1]
                delta_t = max(1.0, buf_3h[-1][0] - buf_3h[0][0])
                row_feat[f"{col}_trend_3h"] = delta_v / delta_t
            else:
                row_feat[f"{col}_trend_3h"] = 0.0

        # 3. Clinically Grounded Interaction Features
        hr = row_feat["HR_latest"]
        sbp = row_feat["SBP_latest"]
        dbp = row_feat["DBP_latest"]
        map_val = row_feat["MAP_latest"]
        temp = row_feat["Temp_latest"]
        resp = row_feat["Resp_latest"]
        
        # Shock Index (HR / SBP) - strong clinical indicator of occult hypoperfusion
        if not np.isnan(hr) and not np.isnan(sbp) and sbp > 20:
            row_feat["shock_index"] = hr / sbp
        else:
            row_feat["shock_index"] = np.nan
            
        # Pulse Pressure (SBP - DBP)
        if not np.isnan(sbp) and not np.isnan(dbp):
            row_feat["pulse_pressure"] = sbp - dbp
        else:
            row_feat["pulse_pressure"] = np.nan
            
        # MAP Hypoperfusion Delta (75.0 - MAP if MAP < 75 else 0)
        if not np.isnan(map_val):
            row_feat["map_hypoperfusion_depth"] = max(0.0, 65.0 - map_val)
        else:
            row_feat["map_hypoperfusion_depth"] = 0.0
            
        # Temperature Dysregulation (|Temp - 37.0|)
        if not np.isnan(temp):
            row_feat["temp_deviation"] = abs(temp - 37.0)
        else:
            row_feat["temp_deviation"] = 0.0
            
        # qSOFA Surrogate Score (Altered Mentation omitted if GCS not in PSV, SBP <= 100 is 1, Resp >= 22 is 1)
        qsofa = 0
        if not np.isnan(sbp) and sbp <= 100:
            qsofa += 1
        if not np.isnan(resp) and resp >= 22:
            qsofa += 1
        row_feat["qsofa_vital_score"] = qsofa

        records.append(row_feat)
        
    return pd.DataFrame(records)

if __name__ == "__main__":
    from preprocessor import load_patient_trajectory
    raw_path = Path(__file__).resolve().parent.parent.parent / "data" / "icu_raw"
    sample_files = list(raw_path.glob("*.psv"))[:5]
    for sf in sample_files:
        pdf = load_patient_trajectory(sf)
        feats = extract_patient_features_and_labels(pdf)
        if not feats.empty:
            print(f"Patient {sf.stem}: {len(feats)} feature rows. Positive labels: {feats['target_sepsis_6_12h'].sum()}")

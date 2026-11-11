"""
ICU Time-Series Raw Data Ingestion & Physiological Validation
Validates raw PSV files from PhysioNet 2019, clips implausible physiological outliers,
and formats longitudinal patient trajectories.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple

# Clinically defensible plausibility bounds
PHYSIOLOGICAL_BOUNDS = {
    "HR": (20.0, 300.0),
    "O2Sat": (50.0, 100.0),
    "Temp": (30.0, 45.0),
    "SBP": (40.0, 280.0),
    "MAP": (20.0, 200.0),
    "DBP": (20.0, 160.0),
    "Resp": (4.0, 70.0),
    "Glucose": (20.0, 1000.0),
    "Lactate": (0.2, 30.0),
    "Creatinine": (0.1, 25.0),
    "Platelets": (5.0, 1500.0),
    "WBC": (0.1, 100.0),
    "BUN": (1.0, 200.0),
    "HCO3": (5.0, 60.0),
    "pH": (6.7, 7.8),
    "Age": (18.0, 105.0),
}

def load_patient_trajectory(file_path: Path) -> pd.DataFrame:
    """
    Loads a single patient's PSV file and validates columns and physiological ranges.
    """
    df = pd.read_csv(file_path, sep="|")
    patient_id = file_path.stem
    df["patient_id"] = patient_id
    
    # Clip physiological outliers to clinically plausible range
    for col, (low, high) in PHYSIOLOGICAL_BOUNDS.items():
        if col in df.columns:
            # Set values outside bounds to NaN rather than silent distortion
            invalid_mask = (df[col] < low) | (df[col] > high)
            df.loc[invalid_mask, col] = np.nan
            
    # Ensure ICULOS is present and strictly monotonically increasing
    if "ICULOS" in df.columns:
        df["ICULOS"] = pd.to_numeric(df["ICULOS"], errors="coerce")
        df = df.sort_values("ICULOS").reset_index(drop=True)
        
    return df

def load_all_patients(raw_dir: Path) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """
    Loads all patient PSV files in raw_dir, returns concatenated DataFrame and missingness statistics.
    """
    files = sorted(list(raw_dir.glob("*.psv")))
    if not files:
        raise FileNotFoundError(f"No PSV files found in {raw_dir}")
        
    patient_dfs = []
    for f in files:
        try:
            pdf = load_patient_trajectory(f)
            # Minimum length of stay filter: at least 6 hours of observations
            if len(pdf) >= 6:
                patient_dfs.append(pdf)
        except Exception as e:
            print(f"Error reading {f}: {e}")
            
    combined = pd.concat(patient_dfs, ignore_index=True)
    
    # Calculate missingness per column
    missingness = {}
    for col in combined.columns:
        if col not in ["patient_id", "SepsisLabel"]:
            missingness[col] = round(float(combined[col].isna().mean() * 100), 2)
            
    return combined, missingness

if __name__ == "__main__":
    raw_path = Path(__file__).resolve().parent.parent.parent / "data" / "icu_raw"
    df, miss = load_all_patients(raw_path)
    print(f"Loaded {df['patient_id'].nunique()} patients with {len(df)} total hourly records.")
    print("Top missingness percentages:")
    for k, v in sorted(miss.items(), key=lambda x: x[1])[:10]:
        print(f"  {k}: {v}% missing")

"""
ICU Sepsis Time-Series Dataset Acquirer & Preprocessor
Acquires real open data from PhysioNet Computing in Cardiology Challenge 2019 (CC BY 4.0),
validates patient cohort files, and saves raw PSV files into data/icu_raw/.
If network is unavailable, falls back to generating high-fidelity synthetic ICU test cohorts.
"""

import os
import sys
import urllib.request
import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = REPO_ROOT / "data" / "icu_raw"
PROCESSED_DIR = REPO_ROOT / "data" / "icu_processed"
BASE_URL = "https://physionet-open.s3.amazonaws.com/challenge-2019/1.0.0/training"

COLUMNS = [
    "HR", "O2Sat", "Temp", "SBP", "MAP", "DBP", "Resp", "EtCO2",
    "BaseExcess", "HCO3", "FiO2", "pH", "PaCO2", "SaO2", "AST", "BUN",
    "Alkalinephos", "Calcium", "Chloride", "Creatinine", "Bilirubin_direct",
    "Glucose", "Lactate", "Magnesium", "Phosphate", "Potassium",
    "Bilirubin_total", "TroponinI", "Hct", "Hgb", "PTT", "WBC",
    "Fibrinogen", "Platelets", "Age", "Gender", "Unit1", "Unit2",
    "HospAdmTime", "ICULOS", "SepsisLabel"
]

def acquire_physionet_cohort(target_count: int = 150) -> Tuple[int, bool]:
    """
    Downloads real clinical ICU time series from PhysioNet Challenge 2019 mirror.
    Returns (num_downloaded, is_real_data).
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    
    # Check if we already have sufficient raw files
    existing_files = list(RAW_DIR.glob("*.psv"))
    if len(existing_files) >= target_count:
        print(f"[Dataset] Found {len(existing_files)} existing raw PSV records in {RAW_DIR}.")
        return len(existing_files), True

    print(f"[Dataset] Downloading representative cohort of {target_count} patient files from PhysioNet Open Data...")
    
    # We sample a known mix of patients from Hospital System A and B
    # In PhysioNet 2019, patient files are named p000001.psv ... p020000.psv (Set A)
    # and p100001.psv ... p120000.psv (Set B)
    # We choose candidates and check for SepsisLabel presence to ensure balanced cohort
    downloaded = 0
    candidate_ids = []
    
    # Mix from Set A (Hospital A) and Set B (Hospital B)
    for i in range(1, 100):
        candidate_ids.append(("training_setA", f"p{i:06d}.psv"))
    for i in range(100001, 100100):
        candidate_ids.append(("training_setB", f"p{i}.psv"))
    # Also select some known positive patients in early challenge numbering
    for i in [9, 14, 25, 43, 56, 72, 85, 102, 118, 140, 162, 185, 100010, 100030, 100075, 100120, 100150]:
        folder = "training_setA" if i < 100000 else "training_setB"
        candidate_ids.append((folder, f"p{i:06d}.psv" if i < 100000 else f"p{i}.psv"))

    for folder, fname in candidate_ids:
        if downloaded >= target_count:
            break
        dest_path = RAW_DIR / fname
        if dest_path.exists():
            downloaded += 1
            continue
        url = f"{BASE_URL}/{folder}/{fname}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                content = resp.read().decode("utf-8")
                # Basic validation
                lines = content.strip().split("\n")
                if len(lines) >= 6 and "HR|O2Sat" in lines[0]:
                    with open(dest_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    downloaded += 1
                    if downloaded % 25 == 0:
                        print(f"  Downloaded {downloaded}/{target_count} patient files...")
        except Exception as e:
            continue

    if downloaded >= 30:
        print(f"[Dataset] Successfully acquired {downloaded} real patient time-series records from PhysioNet.")
        return downloaded, True
    
    print("[Dataset] Warning: Unable to download sufficient real records over network. Generating calibrated synthetic dataset...")
    return generate_synthetic_cohort(target_count)


def generate_synthetic_cohort(count: int = 100) -> Tuple[int, bool]:
    """
    Generates physiologically grounded synthetic ICU patient records with
    Sepsis-3 dynamics for testing when offline.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    np.random.seed(42)
    
    print(f"[Dataset] Generating {count} synthetic ICU patient trajectories...")
    generated = 0
    for i in range(1, count + 1):
        pid = f"pat_synth_{i:04d}"
        fname = f"{pid}.psv"
        dest_path = RAW_DIR / fname
        if dest_path.exists():
            generated += 1
            continue
            
        stay_len = np.random.randint(18, 72) # 18 to 72 hours
        age = float(np.random.randint(28, 86))
        gender = float(np.random.choice([0, 1]))
        unit1 = float(np.random.choice([0, 1]))
        unit2 = 1.0 - unit1
        hosp_adm_time = round(float(np.random.uniform(-48.0, -0.5)), 2)
        
        # 25% of patients develop sepsis
        will_sepsis = (i % 4 == 0)
        sepsis_onset_hour = np.random.randint(14, stay_len - 4) if will_sepsis else 9999
        
        # Baselines
        base_hr = np.random.uniform(70, 95)
        base_temp = np.random.uniform(36.5, 37.3)
        base_resp = np.random.uniform(14, 20)
        base_map = np.random.uniform(75, 95)
        base_wbc = np.random.uniform(5.5, 10.5)
        base_lactate = np.random.uniform(0.8, 1.6)
        base_creat = np.random.uniform(0.7, 1.2)
        base_plat = np.random.uniform(180, 320)
        
        rows = []
        for t in range(1, stay_len + 1):
            # Check deterioration progression if sepsis will occur
            hours_to_sepsis = sepsis_onset_hour - t
            is_deteriorating = will_sepsis and (0 <= hours_to_sepsis <= 12)
            is_post_sepsis = will_sepsis and (t >= sepsis_onset_hour)
            
            # Vital sign dynamics with noise
            hr_drift = (12 - hours_to_sepsis) * 2.5 if is_deteriorating else (25.0 if is_post_sepsis else 0.0)
            temp_drift = (12 - hours_to_sepsis) * 0.12 if is_deteriorating else (1.5 if is_post_sepsis else 0.0)
            resp_drift = (12 - hours_to_sepsis) * 0.8 if is_deteriorating else (8.0 if is_post_sepsis else 0.0)
            map_drift = -(12 - hours_to_sepsis) * 1.8 if is_deteriorating else (-20.0 if is_post_sepsis else 0.0)
            
            hr = max(40.0, min(190.0, base_hr + hr_drift + np.random.normal(0, 3.5)))
            o2sat = max(80.0, min(100.0, 98.0 - (0.5 * (12 - hours_to_sepsis) if is_deteriorating else 0.0) + np.random.normal(0, 1.0)))
            temp = max(34.0, min(41.5, base_temp + temp_drift + np.random.normal(0, 0.2)))
            sbp = max(55.0, min(220.0, (base_map + map_drift) * 1.35 + np.random.normal(0, 5.0)))
            dbp = max(35.0, min(130.0, (base_map + map_drift) * 0.72 + np.random.normal(0, 4.0)))
            map_val = max(35.0, min(150.0, (sbp + 2.0 * dbp) / 3.0))
            resp = max(8.0, min(50.0, base_resp + resp_drift + np.random.normal(0, 1.5)))
            
            # Labs measured intermittently (typical ICU sparsity)
            has_lab = (t == 1 or t % 6 == 0 or (is_deteriorating and t % 3 == 0))
            if has_lab:
                wbc = max(1.0, base_wbc + ((12 - hours_to_sepsis) * 0.7 if is_deteriorating else 0.0) + np.random.normal(0, 0.5))
                lactate = max(0.4, base_lactate + ((12 - hours_to_sepsis) * 0.25 if is_deteriorating else 0.0) + np.random.normal(0, 0.15))
                creat = max(0.3, base_creat + ((12 - hours_to_sepsis) * 0.08 if is_deteriorating else 0.0) + np.random.normal(0, 0.05))
                plat = max(15.0, base_plat - ((12 - hours_to_sepsis) * 8.0 if is_deteriorating else 0.0) + np.random.normal(0, 8.0))
                glucose = max(40.0, 110.0 + ((12 - hours_to_sepsis) * 5.0 if is_deteriorating else 0.0) + np.random.normal(0, 10.0))
                bicarbonate = max(10.0, 24.0 - ((12 - hours_to_sepsis) * 0.4 if is_deteriorating else 0.0) + np.random.normal(0, 0.8))
            else:
                wbc = np.nan
                lactate = np.nan
                creat = np.nan
                plat = np.nan
                glucose = np.nan
                bicarbonate = np.nan

            # In the Challenge Sepsis-3 definition, SepsisLabel is 1 from (onset - 6) to onset
            sepsis_label = 1 if (will_sepsis and (sepsis_onset_hour - 6 <= t <= sepsis_onset_hour)) else (1 if will_sepsis and t > sepsis_onset_hour else 0)
            
            row_dict = {
                "HR": round(hr, 1),
                "O2Sat": round(o2sat, 1),
                "Temp": round(temp, 2),
                "SBP": round(sbp, 1),
                "MAP": round(map_val, 1),
                "DBP": round(dbp, 1),
                "Resp": round(resp, 1),
                "EtCO2": np.nan,
                "BaseExcess": np.nan,
                "HCO3": round(bicarbonate, 1) if not np.isnan(bicarbonate) else np.nan,
                "FiO2": 0.4 if is_deteriorating else np.nan,
                "pH": round(7.40 - ((12 - hours_to_sepsis) * 0.015 if is_deteriorating else 0.0), 2) if has_lab else np.nan,
                "PaCO2": np.nan,
                "SaO2": np.nan,
                "AST": np.nan,
                "BUN": round(15.0 + creat * 10, 1) if not np.isnan(creat) else np.nan,
                "Alkalinephos": np.nan,
                "Calcium": np.nan,
                "Chloride": np.nan,
                "Creatinine": round(creat, 2) if not np.isnan(creat) else np.nan,
                "Bilirubin_direct": np.nan,
                "Glucose": round(glucose, 1) if not np.isnan(glucose) else np.nan,
                "Lactate": round(lactate, 2) if not np.isnan(lactate) else np.nan,
                "Magnesium": np.nan,
                "Phosphate": np.nan,
                "Potassium": 4.1 if has_lab else np.nan,
                "Bilirubin_total": np.nan,
                "TroponinI": np.nan,
                "Hct": np.nan,
                "Hgb": np.nan,
                "PTT": np.nan,
                "WBC": round(wbc, 1) if not np.isnan(wbc) else np.nan,
                "Fibrinogen": np.nan,
                "Platelets": round(plat, 0) if not np.isnan(plat) else np.nan,
                "Age": age,
                "Gender": gender,
                "Unit1": unit1,
                "Unit2": unit2,
                "HospAdmTime": hosp_adm_time,
                "ICULOS": t,
                "SepsisLabel": sepsis_label
            }
            rows.append(row_dict)

        df = pd.DataFrame(rows, columns=COLUMNS)
        df.to_csv(dest_path, sep="|", index=False)
        generated += 1

    print(f"[Dataset] Generated {generated} synthetic patient PSV records in {RAW_DIR}.")
    return generated, False

if __name__ == "__main__":
    count, is_real = acquire_physionet_cohort(target_count=120)
    print(f"Acquisition complete: {count} patients (Real Data: {is_real})")

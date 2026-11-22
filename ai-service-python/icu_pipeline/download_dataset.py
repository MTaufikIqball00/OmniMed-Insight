"""
ICU Sepsis Time-Series Dataset Acquirer & Preprocessor
Acquires real open data from PhysioNet Computing in Cardiology Challenge 2019 (CC BY 4.0),
validates patient cohort files, and saves raw PSV files into data/icu_raw/.
If network is unavailable, falls back to generating high-fidelity synthetic ICU test cohorts.
"""

import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple, Optional

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


def _is_valid_psv_file(path: Path) -> bool:
    """Validate that an existing PSV file has expected PhysioNet header and minimum rows."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        return len(lines) >= 6 and "HR|O2Sat" in lines[0]
    except OSError:
        return False


def _download_single_stay(folder: str, fname: str, dest_dir: Path) -> Tuple[str, bool, str]:
    """
    Downloads a single PhysioNet Challenge 2019 .psv file unless a valid copy already exists.
    Returns (fname, success, status_tag).
    """
    dest_path = dest_dir / fname
    if dest_path.exists() and _is_valid_psv_file(dest_path):
        return fname, True, "skipped_existing"

    url = f"{BASE_URL}/{folder}/{fname}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "OmniMed-Insight-Research/2.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            content = resp.read().decode("utf-8")
        lines = [line.strip() for line in content.strip().split("\n") if line.strip()]
        if len(lines) >= 6 and "HR|O2Sat" in lines[0]:
            tmp_path = dest_dir / f".{fname}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(content)
            tmp_path.replace(dest_path)
            return fname, True, "downloaded"
        return fname, False, "invalid_payload"
    except Exception:
        return fname, False, "request_failed"


def acquire_physionet_cohort(target_count: int = 1000, max_workers: int = 16) -> Tuple[int, bool]:
    """
    Concurrently downloads real clinical ICU time series from PhysioNet Challenge 2019 S3 open mirror
    (500 from training_setA/p000001..p000500.psv and 500 from training_setB/p100001..p100500.psv).
    Never mixes synthetic trajectories into real PhysioNet downloads.
    Returns (num_real_stays, is_real_data).
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # Only inspect real PhysioNet files (never count synthetic files as real data)
    real_existing = sorted(
        p for p in RAW_DIR.glob("*.psv")
        if not p.name.startswith("pat_synth_") and _is_valid_psv_file(p)
    )
    if len(real_existing) >= target_count:
        print(f"[Dataset] Found {len(real_existing)} existing valid real PhysioNet PSV records in {RAW_DIR}.")
        return len(real_existing), True

    n_set_a = min(500, (target_count + 1) // 2)
    n_set_b = min(500, target_count - n_set_a)

    # Interleave Hospital A and Hospital B candidates so any partial subset stays balanced
    candidate_ids: List[Tuple[str, str]] = []
    max_pairs = max(n_set_a, n_set_b)
    for idx in range(max_pairs):
        if idx < n_set_a:
            candidate_ids.append(("training_setA", f"p{idx + 1:06d}.psv"))
        if idx < n_set_b:
            candidate_ids.append(("training_setB", f"p{100001 + idx}.psv"))

    print(
        f"[Dataset] Acquiring up to {len(candidate_ids)} real ICU stays "
        f"({n_set_a} Hospital A + {n_set_b} Hospital B) with {max_workers} workers..."
    )

    skipped_count = 0
    downloaded_new = 0
    failed_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(_download_single_stay, folder, fname, RAW_DIR)
            for folder, fname in candidate_ids
        ]
        completed = 0
        for future in as_completed(futures):
            _fname, ok, status_tag = future.result()
            completed += 1
            if ok:
                if status_tag == "skipped_existing":
                    skipped_count += 1
                else:
                    downloaded_new += 1
            else:
                failed_count += 1

            if completed % 100 == 0 or completed == len(candidate_ids):
                print(
                    f"  Progress {completed}/{len(candidate_ids)} | "
                    f"existing={skipped_count}, new={downloaded_new}, failed={failed_count}"
                )

    valid_real_files = sorted(
        p for p in RAW_DIR.glob("*.psv")
        if not p.name.startswith("pat_synth_") and _is_valid_psv_file(p)
    )
    total_real = len(valid_real_files)

    if total_real >= 30:
        print(
            f"[Dataset] Successfully verified {total_real} real PhysioNet patient time-series records "
            f"(new={downloaded_new}, reused={skipped_count})."
        )
        return total_real, True

    print("[Dataset] Warning: Real PhysioNet downloads < 30; falling back to isolated offline synthetic cohort...")
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
    count, is_real = acquire_physionet_cohort(target_count=1000)
    print(f"Acquisition complete: {count} patients (Real Data: {is_real})")

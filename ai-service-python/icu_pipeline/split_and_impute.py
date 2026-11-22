"""
ICU Patient-Level Splitting & Leakage-Free Imputation Pipeline
Partitions cohort into Train (70%), Val (15%), Test (15%) by unique patient IDs.
Fits medians strictly on Train and transforms Val and Test partitions without leakage.
"""

import json
from pathlib import Path
from typing import Dict, Any
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split

try:
    from preprocessor import load_patient_trajectory
    from feature_extractor import extract_patient_features_and_labels
except ImportError:
    from icu_pipeline.preprocessor import load_patient_trajectory
    from icu_pipeline.feature_extractor import extract_patient_features_and_labels

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = REPO_ROOT / "data" / "icu_raw"
PROCESSED_DIR = REPO_ROOT / "data" / "icu_processed"


def run_pipeline() -> Dict[str, Any]:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    all_psv_files = sorted(list(RAW_DIR.glob("*.psv")))
    real_psv_files = [pf for pf in all_psv_files if not pf.name.startswith("pat_synth_")]
    # Never mix synthetic trajectories with real PhysioNet downloads
    psv_files = real_psv_files if real_psv_files else all_psv_files
    using_real_data = len(real_psv_files) > 0
    print(
        f"[Pipeline] Processing {len(psv_files)} raw patient trajectories "
        f"(real_physionet={using_real_data}, excluded_synthetic={len(all_psv_files) - len(psv_files)})..."
    )

    all_patient_features = []
    patient_status = {}
    excluded_count = 0

    for pf in psv_files:
        try:
            pdf = load_patient_trajectory(pf)
            feats = extract_patient_features_and_labels(pdf)
            if not feats.empty:
                all_patient_features.append(feats)
                patient_status[pf.stem] = {
                    "num_hours": len(feats),
                    "is_positive": int(feats["target_sepsis_6_12h"].max()),
                }
            else:
                excluded_count += 1
        except Exception as e:
            print(f"Error extracting features for {pf}: {e}")

    if not all_patient_features:
        raise ValueError("No valid patient feature matrices generated.")

    full_df = pd.concat(all_patient_features, ignore_index=True)
    unique_patients = full_df["patient_id"].unique()
    print(
        f"[Pipeline] Cohort eligible: {len(unique_patients)} unique patients "
        f"(excluded={excluded_count}), {len(full_df)} total observation hours."
    )

    # 1. Stratified Patient-Level Split (70% train, 15% val, 15% test)
    # Stratify by whether patient ever has positive target
    patient_labels = [patient_status[pid]["is_positive"] for pid in unique_patients]

    train_pids, temp_pids, train_y, temp_y = train_test_split(
        unique_patients,
        patient_labels,
        test_size=0.30,
        random_state=42,
        stratify=patient_labels if sum(patient_labels) >= 2 else None,
    )

    val_pids, test_pids, val_y, test_y = train_test_split(
        temp_pids,
        temp_y,
        test_size=0.50,
        random_state=42,
        stratify=temp_y if sum(temp_y) >= 2 else None,
    )

    print(f"  Train patients: {len(train_pids)} (Positive stays: {sum(train_y)})")
    print(f"  Val patients:   {len(val_pids)} (Positive stays: {sum(val_y)})")
    print(f"  Test patients:  {len(test_pids)} (Positive stays: {sum(test_y)})")

    # Verify zero patient overlap
    assert set(train_pids).isdisjoint(set(val_pids)), "LEAKAGE ERROR: Patient overlap between train and val!"
    assert set(train_pids).isdisjoint(set(test_pids)), "LEAKAGE ERROR: Patient overlap between train and test!"
    assert set(val_pids).isdisjoint(set(test_pids)), "LEAKAGE ERROR: Patient overlap between val and test!"

    train_df = full_df[full_df["patient_id"].isin(train_pids)].copy()
    val_df = full_df[full_df["patient_id"].isin(val_pids)].copy()
    test_df = full_df[full_df["patient_id"].isin(test_pids)].copy()

    # 2. Identify Feature Columns
    non_feature_cols = ["patient_id", "ICULOS", "target_sepsis_6_12h"]
    feature_cols = [c for c in full_df.columns if c not in non_feature_cols]

    # 3. Fit Medians Strictly on Train Partition
    train_medians = {}
    for col in feature_cols:
        med = train_df[col].median()
        if pd.isna(med):
            med = 0.0  # Default if column completely unobserved in train
        train_medians[col] = float(med)

    # Impute missing values using train medians
    for col in feature_cols:
        train_df[col] = train_df[col].fillna(train_medians[col])
        val_df[col] = val_df[col].fillna(train_medians[col])
        test_df[col] = test_df[col].fillna(train_medians[col])

    # 4. Save Processed Artifacts
    train_path = PROCESSED_DIR / "train.csv"
    val_path = PROCESSED_DIR / "val.csv"
    test_path = PROCESSED_DIR / "test.csv"
    meta_path = PROCESSED_DIR / "feature_metadata.json"
    report_path = PROCESSED_DIR / "data_quality_report.json"

    train_df.to_csv(train_path, index=False)
    val_df.to_csv(val_path, index=False)
    test_df.to_csv(test_path, index=False)

    set_a_count = int(sum(1 for pid in unique_patients if str(pid).startswith("p0")))
    set_b_count = int(sum(1 for pid in unique_patients if str(pid).startswith("p1")))

    split_sizes = {
        "train_patients": len(train_pids),
        "train_positive_stays": int(sum(train_y)),
        "train_rows": len(train_df),
        "train_positive_rows": int(train_df["target_sepsis_6_12h"].sum()),
        "val_patients": len(val_pids),
        "val_positive_stays": int(sum(val_y)),
        "val_rows": len(val_df),
        "val_positive_rows": int(val_df["target_sepsis_6_12h"].sum()),
        "test_patients": len(test_pids),
        "test_positive_stays": int(sum(test_y)),
        "test_rows": len(test_df),
        "test_positive_rows": int(test_df["target_sepsis_6_12h"].sum()),
    }

    metadata = {
        "feature_cols": feature_cols,
        "imputation_medians": train_medians,
        "target_col": "target_sepsis_6_12h",
        "num_features": len(feature_cols),
        "split_sizes": split_sizes,
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    quality_report = {
        "dataset_source": "PhysioNet Challenge 2019 (CC BY 4.0)" if using_real_data else "Synthetic Fallback",
        "total_raw_files_scanned": len(psv_files),
        "excluded_patients_count": excluded_count,
        "total_patients_analyzed": len(unique_patients),
        "hospital_system_a_patients": set_a_count,
        "hospital_system_b_patients": set_b_count,
        "total_positive_stays": int(sum(patient_labels)),
        "total_negative_stays": int(len(unique_patients) - sum(patient_labels)),
        "total_hourly_records": len(full_df),
        "total_positive_rows": int(full_df["target_sepsis_6_12h"].sum()),
        "split_sizes": split_sizes,
        "train_positive_ratio": round(float(train_df["target_sepsis_6_12h"].mean()), 4),
        "val_positive_ratio": round(float(val_df["target_sepsis_6_12h"].mean()), 4),
        "test_positive_ratio": round(float(test_df["target_sepsis_6_12h"].mean()), 4),
        "patient_overlap_check": "PASSED_ZERO_OVERLAP",
        "zero_patient_overlap_verified": True,
        "synthetic_files_excluded": using_real_data,
        "imputation_strategy": "forward_fill_within_stay_then_train_median",
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(quality_report, f, indent=2)

    print(f"[Pipeline] Exported train/val/test splits and metadata to {PROCESSED_DIR}.")
    return quality_report

if __name__ == "__main__":
    rep = run_pipeline()
    print("Pipeline execution summary:")
    print(json.dumps(rep, indent=2))

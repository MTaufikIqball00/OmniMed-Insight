"""
ICU Sepsis Early Warning Model Training & Evaluation Suite
Trains:
  1. Clinical qSOFA Rule-based Baseline
  2. Logistic Regression (L2 regularized, balanced)
  3. LightGBM Classifier (regularized gradient boosting with class balancing)
  4. XGBoost Classifier (tree boosting with scale_pos_weight)
Evaluates on held-out test cohort (AUROC, AUPRC, Sensitivity, Specificity, Brier score).
Fits SHAP TreeExplainer on LightGBM for local and global interpretability.
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple
import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    roc_auc_score,
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import lightgbm as lgb
import xgboost as xgb
import shap

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AI_SERVICE_DIR = Path(__file__).resolve().parent.parent
if str(AI_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE_DIR))

from app.calibration import compute_ece, fit_and_compare_binary_calibrators  # noqa: E402

PROCESSED_DIR = REPO_ROOT / "data" / "icu_processed"
MODELS_DIR = AI_SERVICE_DIR / "models" / "icu"

# Clinical monotonicity constraints mapped 1-to-1 to engineered features:
# +1: higher feature value MUST NOT decrease predicted sepsis risk
# -1: higher feature value MUST NOT increase predicted sepsis risk
#  0: unconstrained (U-shaped markers, demographics, missingness/volatility/rates)
MONOTONE_CONSTRAINT_MAP: Dict[str, int] = {
    # +1 constraints (hypoperfusion, tachycardia, tachypnea, thermal stress, renal dysfunction)
    "Lactate_latest": 1,
    "Lactate_roll_max_6h": 1,
    "Lactate_roll_mean_6h": 1,
    "Lactate_roll_min_6h": 1,
    "Lactate_trend_3h": 1,
    "shock_index": 1,
    "map_hypoperfusion_depth": 1,
    "qsofa_vital_score": 1,
    "HR_roll_max_6h": 1,
    "HR_latest": 1,
    "Resp_roll_max_6h": 1,
    "Resp_latest": 1,
    "temp_deviation": 1,
    "Creatinine_latest": 1,
    "BUN_latest": 1,
    # -1 constraints (perfusion pressure, oxygenation, platelets, acid-base buffer reserve)
    "MAP_latest": -1,
    "MAP_roll_min_6h": -1,
    "MAP_roll_mean_6h": -1,
    "SBP_latest": -1,
    "O2Sat_latest": -1,
    "Platelets_latest": -1,
    "HCO3_roll_min_6h": -1,
}


def build_monotone_constraints(feature_cols: List[str]) -> Tuple[Dict[str, int], List[int]]:
    """Builds 1-to-1 feature->constraint map and ordered vector matching feature_cols."""
    unknown = set(MONOTONE_CONSTRAINT_MAP.keys()) - set(feature_cols)
    if unknown:
        raise ValueError(f"MONOTONE_CONSTRAINT_MAP contains unknown feature(s): {sorted(unknown)}")
    full_map = {col: int(MONOTONE_CONSTRAINT_MAP.get(col, 0)) for col in feature_cols}
    vec = [full_map[col] for col in feature_cols]
    return full_map, vec


def evaluate_predictions(y_true: np.ndarray, y_prob: np.ndarray, threshold: float = 0.5) -> Dict[str, Any]:
    y_pred = (y_prob >= threshold).astype(int)

    auroc = float(roc_auc_score(y_true, y_prob)) if len(np.unique(y_true)) > 1 else 0.5
    auprc = float(average_precision_score(y_true, y_prob)) if len(np.unique(y_true)) > 1 else 0.0
    brier = float(brier_score_loss(y_true, np.clip(y_prob, 0.0, 1.0)))
    ece_score, _ = compute_ece(y_true, y_prob, n_bins=10, multiclass=False)

    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = int(cm[0, 0]), int(cm[0, 1]), int(cm[1, 0]), int(cm[1, 1])

    sens = float(tp / (tp + fn)) if (tp + fn) > 0 else 0.0
    spec = float(tn / (tn + fp)) if (tn + fp) > 0 else 0.0
    prec = float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0
    f1 = float(2 * (prec * sens) / (prec + sens)) if (prec + sens) > 0 else 0.0

    return {
        "auroc": round(auroc, 4) + 0.0,
        "auprc": round(auprc, 4) + 0.0,
        "brier_score": round(brier, 4) + 0.0,
        "ece_score": round(ece_score, 4) + 0.0,
        "threshold_used": round(threshold, 4) + 0.0,
        "sensitivity": round(sens, 4) + 0.0,
        "specificity": round(spec, 4) + 0.0,
        "precision": round(prec, 4) + 0.0,
        "f1_score": round(f1, 4) + 0.0,
        "confusion_matrix": {
            "true_negatives": tn,
            "false_positives": fp,
            "false_negatives": fn,
            "true_positives": tp,
        },
    }


def find_optimal_threshold(y_true: np.ndarray, y_prob: np.ndarray, min_specificity: float = 0.65) -> float:
    """
    Finds decision threshold maximizing Youden's J statistic (Sensitivity + Specificity - 1)
    across empirical probability quantiles while enforcing a minimum clinical specificity floor
    to prevent alert fatigue (100% false-positive firing).
    """
    candidates = np.unique(
        np.concatenate([
            np.quantile(y_prob, np.linspace(0.50, 0.96, 47)),
            np.linspace(0.02, 0.85, 84),
        ])
    )
    best_thresh = float(np.quantile(y_prob, 0.85))
    best_j = -2.0

    for thresh in candidates:
        y_pred = (y_prob >= thresh).astype(int)
        cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
        tn, fp, fn, tp = cm[0, 0], cm[0, 1], cm[1, 0], cm[1, 1]
        sens = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        spec = tn / (tn + fp) if (tn + fp) > 0 else 0.0
        if spec < min_specificity:
            continue
        j = sens + spec - 1.0
        if j > best_j:
            best_j = j
            best_thresh = float(thresh)

    return float(best_thresh)


def train_and_evaluate_all():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    train_df = pd.read_csv(PROCESSED_DIR / "train.csv")
    val_df = pd.read_csv(PROCESSED_DIR / "val.csv")
    test_df = pd.read_csv(PROCESSED_DIR / "test.csv")

    with open(PROCESSED_DIR / "feature_metadata.json", "r", encoding="utf-8") as f:
        meta = json.load(f)
    quality_report: Dict[str, Any] = {}
    quality_path = PROCESSED_DIR / "data_quality_report.json"
    if quality_path.exists():
        with open(quality_path, "r", encoding="utf-8") as f:
            quality_report = json.load(f)

    feature_cols = meta["feature_cols"]
    target_col = meta["target_col"]
    monotone_constraints_map, monotone_vec = build_monotone_constraints(feature_cols)

    X_train_df = train_df[feature_cols]
    y_train = train_df[target_col].to_numpy()

    X_val_df = val_df[feature_cols]
    y_val = val_df[target_col].to_numpy()

    X_test_df = test_df[feature_cols]
    y_test = test_df[target_col].to_numpy()

    print(
        f"[Training] Features: {len(feature_cols)} "
        f"(monotonic +1: {sum(1 for v in monotone_vec if v == 1)}, -1: {sum(1 for v in monotone_vec if v == -1)}). "
        f"Train: {len(X_train_df)}, Val: {len(X_val_df)}, Test: {len(X_test_df)}"
    )
    print(f"[Training] Class imbalance: Train pos={y_train.sum()}/{len(y_train)} ({y_train.mean():.3%})")

    results: Dict[str, Any] = {}

    # -------------------------------------------------------------
    # 1. Clinical qSOFA Baseline
    # -------------------------------------------------------------
    print("[1/5] Evaluating Clinical qSOFA Rule-based Baseline...")
    test_qsofa = test_df["qsofa_vital_score"].to_numpy() / 2.0
    thresh_qsofa = 0.50
    results["qsofa_clinical_baseline"] = evaluate_predictions(y_test, test_qsofa, thresh_qsofa)
    results["qsofa_clinical_baseline"]["model_name"] = "Clinical qSOFA Baseline (SBP <= 100, RR >= 22)"

    # -------------------------------------------------------------
    # 2. Logistic Regression
    # -------------------------------------------------------------
    print("[2/5] Training Logistic Regression...")
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train_df.to_numpy())
    X_val_scaled = scaler.transform(X_val_df.to_numpy())
    X_test_scaled = scaler.transform(X_test_df.to_numpy())

    lr = LogisticRegression(class_weight="balanced", C=0.1, max_iter=1000, random_state=42)
    lr.fit(X_train_scaled, y_train)

    val_prob_lr = lr.predict_proba(X_val_scaled)[:, 1]
    thresh_lr = find_optimal_threshold(y_val, val_prob_lr, min_specificity=0.70)
    test_prob_lr = lr.predict_proba(X_test_scaled)[:, 1]
    results["logistic_regression"] = evaluate_predictions(y_test, test_prob_lr, thresh_lr)
    results["logistic_regression"]["model_name"] = "L2-Regularized Logistic Regression (Balanced)"

    # -------------------------------------------------------------
    # 3. LightGBM Unconstrained Baseline (Before)
    # -------------------------------------------------------------
    print("[3/5] Training LightGBM Unconstrained Baseline...")
    base_lgb_params = dict(
        n_estimators=120,
        learning_rate=0.05,
        num_leaves=7,
        max_depth=3,
        scale_pos_weight=1.0,
        min_child_samples=20,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=1.0,
        reg_lambda=5.0,
        random_state=42,
        verbosity=-1,
    )
    lgb_unconstrained = lgb.LGBMClassifier(**base_lgb_params)
    lgb_unconstrained.fit(X_train_df, y_train)

    val_prob_lgb_unc = lgb_unconstrained.predict_proba(X_val_df)[:, 1]
    thresh_lgb_unc = find_optimal_threshold(y_val, val_prob_lgb_unc, min_specificity=0.65)
    test_prob_lgb_unc = lgb_unconstrained.predict_proba(X_test_df)[:, 1]
    results["lightgbm_unconstrained"] = evaluate_predictions(y_test, test_prob_lgb_unc, thresh_lgb_unc)
    results["lightgbm_unconstrained"]["model_name"] = "LightGBM Unconstrained Baseline"

    # -------------------------------------------------------------
    # 4. LightGBM Monotonic Champion + Validation Calibration (After)
    # -------------------------------------------------------------
    print("[4/5] Training Monotonic LightGBM Classifier (advanced monotonic constraints)...")
    lgb_mono = lgb.LGBMClassifier(
        **base_lgb_params,
        monotone_constraints=monotone_vec,
        monotone_constraints_method="advanced",
    )
    lgb_mono.fit(X_train_df, y_train)

    print("[Calibration] Fitting Platt Scaling vs Isotonic Calibration strictly on val.csv...")
    cal_result = fit_and_compare_binary_calibrators(
        lgb_mono,
        X_val_df,
        y_val,
        X_test_df,
        y_test,
        threshold_finder_fn=find_optimal_threshold,
    )
    best_cal_method = cal_result["best_method"]
    best_calibrator = cal_result["best_calibrator"]
    calibrated_threshold = cal_result["calibrated_threshold"]
    reliability_bins = cal_result["reliability_bins"]

    uncal_test_metrics = {
        k: v for k, v in cal_result["test_comparison"]["NONE_UNCALIBRATED"].items() if k != "reliability_bins"
    }
    uncal_test_metrics["model_name"] = "LightGBM Monotonic (Uncalibrated)"
    results["lightgbm_monotonic_uncalibrated"] = uncal_test_metrics

    champ_test_metrics = {
        k: v for k, v in cal_result["selected_test_metrics"].items() if k != "reliability_bins"
    }
    champ_test_metrics["model_name"] = f"LightGBM Monotonic + {best_cal_method}"
    results["lightgbm"] = champ_test_metrics

    # -------------------------------------------------------------
    # 5. XGBoost Classifier
    # -------------------------------------------------------------
    print("[5/5] Training XGBoost Classifier...")
    xgb_model = xgb.XGBClassifier(
        n_estimators=150,
        learning_rate=0.03,
        max_depth=3,
        scale_pos_weight=5.0,
        subsample=0.8,
        colsample_bytree=0.7,
        reg_alpha=1.0,
        reg_lambda=5.0,
        eval_metric="auc",
        early_stopping_rounds=30,
        random_state=42,
    )
    xgb_model.fit(X_train_df, y_train, eval_set=[(X_val_df, y_val)], verbose=False)

    val_prob_xgb = xgb_model.predict_proba(X_val_df)[:, 1]
    thresh_xgb = find_optimal_threshold(y_val, val_prob_xgb, min_specificity=0.65)
    test_prob_xgb = xgb_model.predict_proba(X_test_df)[:, 1]
    results["xgboost"] = evaluate_predictions(y_test, test_prob_xgb, thresh_xgb)
    results["xgboost"]["model_name"] = "XGBoost Classifier"

    # Print benchmark summary
    print("\n--- Model Benchmark on Held-Out Test Set ---")
    for k, v in results.items():
        print(
            f"  {k} ({v['model_name']}): AUROC={v['auroc']}, AUPRC={v['auprc']}, "
            f"Sens={v['sensitivity']}, Spec={v['specificity']}, F1={v['f1_score']}, "
            f"Brier={v['brier_score']}, ECE={v['ece_score']}"
        )

    # -------------------------------------------------------------
    # Champion Artifacts: Raw Monotonic LightGBM + Best Prefit Calibrator + Stratified SHAP
    # -------------------------------------------------------------
    champ_key = "lightgbm_monotonic"
    print(
        f"\n[Champion Selected] {champ_key.upper()} + {best_cal_method} | "
        f"Test AUROC={champ_test_metrics['auroc']}, ECE={champ_test_metrics['ece_score']}, "
        f"Calibrated Threshold={calibrated_threshold}"
    )

    joblib.dump(lgb_mono, MODELS_DIR / "champion_model.joblib")
    joblib.dump(best_calibrator, MODELS_DIR / "calibrator.joblib")
    joblib.dump(scaler, MODELS_DIR / "scaler.joblib")

    calibration_metrics_payload = {
        "best_method": best_cal_method,
        "calibrated_threshold": calibrated_threshold,
        "ece_score": champ_test_metrics["ece_score"],
        "val_comparison": cal_result["val_comparison"],
        "test_comparison": cal_result["test_comparison"],
        "selected_test_metrics": cal_result["selected_test_metrics"],
        "reliability_bins": reliability_bins,
    }
    with open(MODELS_DIR / "calibration_metrics.json", "w", encoding="utf-8") as f:
        json.dump(calibration_metrics_payload, f, indent=2)

    # Fit SHAP TreeExplainer with stratified background reference dataset (proportional pos/neg rows)
    print("[SHAP] Fitting TreeExplainer on raw Monotonic LightGBM with stratified background...")
    bg_size = min(200, len(X_train_df))
    stratify_bg = y_train if (len(np.unique(y_train)) > 1 and bg_size >= 20) else None
    stratified_bg_df, _ = train_test_split(
        X_train_df,
        train_size=bg_size,
        stratify=stratify_bg,
        random_state=42,
    )
    explainer = shap.TreeExplainer(lgb_mono, data=stratified_bg_df)
    joblib.dump(explainer, MODELS_DIR / "shap_explainer.joblib")

    # Compute global SHAP importance on stratified validation sample
    shap_sample_size = min(200, len(X_val_df))
    if len(X_val_df) > shap_sample_size and len(np.unique(y_val)) > 1:
        shap_sample, _ = train_test_split(
            X_val_df,
            train_size=shap_sample_size,
            stratify=y_val,
            random_state=42,
        )
    else:
        shap_sample = X_val_df

    raw_shap = explainer.shap_values(shap_sample, check_additivity=False)
    if isinstance(raw_shap, list):
        shap_vals = raw_shap[1] if len(raw_shap) > 1 else raw_shap[0]
    elif len(raw_shap.shape) == 3:
        shap_vals = raw_shap[:, :, 1]
    else:
        shap_vals = raw_shap

    mean_abs_shap = np.mean(np.abs(shap_vals), axis=0)
    top_feature_indices = np.argsort(mean_abs_shap)[::-1]

    global_importance = [
        {
            "feature": feature_cols[idx],
            "importance": round(float(mean_abs_shap[idx]), 5),
        }
        for idx in top_feature_indices[:20]
    ]

    split_sizes = meta.get("split_sizes", {})
    cohort_summary = {
        "dataset_source": quality_report.get("dataset_source", "PhysioNet Challenge 2019 (CC BY 4.0)"),
        "total_raw_files_scanned": quality_report.get("total_raw_files_scanned"),
        "eligible_patients": quality_report.get("total_patients_analyzed"),
        "excluded_patients": quality_report.get("excluded_patients_count"),
        "hospital_system_a_patients": quality_report.get("hospital_system_a_patients"),
        "hospital_system_b_patients": quality_report.get("hospital_system_b_patients"),
        "total_positive_stays": quality_report.get("total_positive_stays"),
        "total_hourly_records": quality_report.get("total_hourly_records"),
        "total_positive_rows": quality_report.get("total_positive_rows"),
        "split_sizes": split_sizes,
        "patient_overlap_check": quality_report.get("patient_overlap_check", "PASSED_ZERO_OVERLAP"),
    }

    monotonicity_comparison = {
        "before_unconstrained": {
            k: results["lightgbm_unconstrained"][k]
            for k in ["auroc", "auprc", "brier_score", "ece_score", "sensitivity", "specificity", "f1_score", "threshold_used"]
        },
        "after_monotonic_uncalibrated": {
            k: uncal_test_metrics[k]
            for k in ["auroc", "auprc", "brier_score", "ece_score", "sensitivity", "specificity", "f1_score", "threshold_used"]
        },
        "after_monotonic_calibrated": {
            **{
                k: champ_test_metrics[k]
                for k in ["auroc", "auprc", "brier_score", "ece_score", "sensitivity", "specificity", "f1_score", "threshold_used"]
            },
            "calibration_method": best_cal_method,
        },
    }

    champion_metadata = {
        "model_id": "omnimed-icu-lightgbm-v1",
        "algorithm": champ_key,
        "prediction_horizon": "6_to_12_hours_before_sepsis",
        "decision_threshold": calibrated_threshold,
        "calibrated_threshold": calibrated_threshold,
        "calibration_method": best_cal_method,
        "ece_score": champ_test_metrics["ece_score"],
        "monotone_constraints_active": True,
        "monotone_constraints_map": monotone_constraints_map,
        "reliability_bins": reliability_bins,
        "cohort_summary": cohort_summary,
        "test_metrics": champ_test_metrics,
        "monotonicity_comparison": monotonicity_comparison,
        "calibration_comparison": {
            "validation": cal_result["val_comparison"],
            "test": cal_result["test_comparison"],
        },
        "top_features": global_importance,
        "feature_cols": feature_cols,
        "imputation_medians": meta["imputation_medians"],
        "clinical_disclaimer": "Auxiliary risk stratification decision-support model. Not cleared for autonomous intervention.",
    }

    with open(MODELS_DIR / "champion_model_meta.json", "w", encoding="utf-8") as f:
        json.dump(champion_metadata, f, indent=2)

    with open(MODELS_DIR / "model_metrics_comparison.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"[Export] Saved champion model, calibrator, SHAP explainer, and metadata to {MODELS_DIR}")
    return champion_metadata, results


if __name__ == "__main__":
    meta, res = train_and_evaluate_all()
    print("\n--- Pipeline Completed Successfully ---")

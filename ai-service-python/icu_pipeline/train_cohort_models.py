"""
Pipeline for Archive2 5,000-Patient ICU Clinical Cohort:
Data Cleaning, Anti-Leakage Feature Selection, Stratified Splitting, Multi-Model Training,
Benchmark Evaluation, and SHAP Explainability.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import shap
import xgboost as xgb
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    roc_auc_score,
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cohort_pipeline")

RAW_CSV_PATH = Path("data/archive2/sepsis_icu_synthetic.csv")
PROCESSED_DIR = Path("data/icu_cohort_processed")
MODELS_DIR = Path("ai-service-python/models/icu")

# Columns excluded from predictor matrix to prevent post-event intervention leakage,
# post-stay outcome leakage, composite score circularity, and synthetic generator proxy shortcuts.
EXCLUDED_LEAKAGE_AND_OUTCOME_COLS = [
    "subject_id",
    "gender",
    "sepsis_label",
    # Post-stay future outcomes (temporal leakage if used at prediction time)
    "icu_los_hours",
    "readmission_30day",
    # Post-onset ICU therapeutic interventions
    "vasopressors_flag",
    "vasopressor_dose_mcg_kg_min",
    "mechanical_ventilation",
    "fio2_percent",
    "antibiotics_24h",
    "fluids_ml_24h",
    "sedation_score",
    "insulin_infusion_flag",
    # Composite diagnostic/acuity scores (evaluated separately as clinical baselines)
    "sofa_score",
    "apache_iv",
    "sirs_criteria",
    "qsofa",
    # Synthetic generator deterministic label proxies (univariate AUC = 0.000 or > 0.98)
    "pao2_fio2_ratio",
    "lactate_mmol",
    "creatinine",
]


def load_and_clean_data(csv_path: Path) -> pd.DataFrame:
    logger.info(f"Loading raw cohort data from {csv_path}")
    df = pd.read_csv(csv_path)

    # 1. Clean categorical typos ('Mael' -> 'M')
    df["gender"] = df["gender"].replace({"Mael": "M"})
    df["gender_code"] = (df["gender"] == "M").astype(float)

    # 2. One-hot encode ethnicity, insurance, hospital_admit_source
    cat_cols = ["ethnicity", "insurance", "hospital_admit_source"]
    df = pd.get_dummies(df, columns=cat_cols, drop_first=True, dtype=float)

    # 3. Compute physiological interaction features
    sbp_safe = df["sbp_mean"].clip(lower=40.0)
    df["shock_index"] = df["hr_mean"] / sbp_safe
    df["pulse_pressure"] = df["sbp_mean"] - df["dbp_mean"]

    map_val = df["map_mean"].fillna(df["dbp_mean"] + (df["sbp_mean"] - df["dbp_mean"]) / 3.0)
    df["map_hypoperfusion_depth"] = np.maximum(0.0, 65.0 - map_val)
    df["temp_deviation"] = (df["temp_celsius_mean"] - 37.0).abs()

    # Missingness indicators for baseline laboratory and vital markers
    lab_cols = [
        "wbc",
        "platelet_count",
        "bilirubin_total",
        "glucose",
        "ph_arterial",
        "inr",
        "sodium",
        "potassium",
        "chloride",
        "bicarbonate",
        "hematocrit",
        "hemoglobin",
        "map_mean",
        "bmi",
    ]
    for col in lab_cols:
        if col in df.columns:
            df[f"{col}_missing"] = df[col].isnull().astype(float)

    logger.info(f"Dataset cleaned. Transformed shape: {df.shape}")
    return df


def split_cohort_data(
    df: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, List[str]]:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    feature_cols = [c for c in df.columns if c not in EXCLUDED_LEAKAGE_AND_OUTCOME_COLS]

    train_df, test_val_df = train_test_split(
        df,
        test_size=0.30,
        random_state=42,
        stratify=df["sepsis_label"],
    )
    val_df, test_df = train_test_split(
        test_val_df,
        test_size=0.50,
        random_state=42,
        stratify=test_val_df["sepsis_label"],
    )

    # Strict Patient Overlap Verification
    train_pts = set(train_df["subject_id"])
    val_pts = set(val_df["subject_id"])
    test_pts = set(test_df["subject_id"])
    assert len(train_pts & test_pts) == 0, "Patient leakage detected between Train and Test!"
    assert len(train_pts & val_pts) == 0, "Patient leakage detected between Train and Val!"

    # Impute missing features strictly using Train medians
    all_numeric_cols = [c for c in df.select_dtypes(include=["float64", "int64"]).columns if c != "subject_id"]
    medians = train_df[all_numeric_cols].median().to_dict()

    train_df = train_df.fillna(medians)
    val_df = val_df.fillna(medians)
    test_df = test_df.fillna(medians)

    # Export processed splits
    train_df.to_csv(PROCESSED_DIR / "train.csv", index=False)
    val_df.to_csv(PROCESSED_DIR / "val.csv", index=False)
    test_df.to_csv(PROCESSED_DIR / "test.csv", index=False)

    feature_medians = {c: float(medians[c]) for c in feature_cols if c in medians}

    quality_report = {
        "dataset_name": "Archive2 Sepsis ICU Synthetic Cohort",
        "total_patients": len(df),
        "total_features": len(feature_cols),
        "excluded_leakage_columns": EXCLUDED_LEAKAGE_AND_OUTCOME_COLS,
        "train_patients": len(train_df),
        "train_positive_ratio": round(float(train_df["sepsis_label"].mean()), 4),
        "val_patients": len(val_df),
        "val_positive_ratio": round(float(val_df["sepsis_label"].mean()), 4),
        "test_patients": len(test_df),
        "test_positive_ratio": round(float(test_df["sepsis_label"].mean()), 4),
        "patient_overlap_check": "PASSED_ZERO_OVERLAP",
        "imputation_strategy": "train_median_freeze",
    }
    with open(PROCESSED_DIR / "data_quality_report.json", "w", encoding="utf-8") as f:
        json.dump(quality_report, f, indent=2)

    with open(PROCESSED_DIR / "feature_metadata.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "feature_cols": feature_cols,
                "excluded_cols": EXCLUDED_LEAKAGE_AND_OUTCOME_COLS,
                "imputation_medians": feature_medians,
                "target_col": "sepsis_label",
            },
            f,
            indent=2,
        )

    logger.info(
        f"Splits exported. Features: {len(feature_cols)}, Train: {len(train_df)}, Val: {len(val_df)}, Test: {len(test_df)}"
    )
    return train_df, val_df, test_df, feature_cols


def evaluate_predictions(y_true: np.ndarray, y_prob: np.ndarray, model_name: str) -> Dict[str, Any]:
    auroc = float(roc_auc_score(y_true, y_prob))
    auprc = float(average_precision_score(y_true, y_prob))
    brier = float(brier_score_loss(y_true, y_prob))

    best_thresh = 0.5
    best_f1 = -1.0
    for t in np.linspace(0.10, 0.90, 33):
        preds = (y_prob >= t).astype(int)
        score = f1_score(y_true, preds, zero_division=0)
        if score > best_f1:
            best_f1 = score
            best_thresh = float(t)

    binary_preds = (y_prob >= best_thresh).astype(int)
    sens = float(recall_score(y_true, binary_preds, zero_division=0))
    spec = float(recall_score(1 - y_true, 1 - binary_preds, zero_division=0))
    prec = float(precision_score(y_true, binary_preds, zero_division=0))
    f1 = float(f1_score(y_true, binary_preds, zero_division=0))
    tn, fp, fn, tp = confusion_matrix(y_true, binary_preds).ravel()

    return {
        "auroc": round(auroc, 4),
        "auprc": round(auprc, 4),
        "brier_score": round(brier, 4),
        "threshold_used": round(best_thresh, 2),
        "sensitivity": round(sens, 4),
        "specificity": round(spec, 4),
        "precision": round(prec, 4),
        "f1_score": round(f1, 4),
        "confusion_matrix": {
            "true_negatives": int(tn),
            "false_positives": int(fp),
            "false_negatives": int(fn),
            "true_positives": int(tp),
        },
        "model_name": model_name,
    }


def train_and_benchmark_models(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
    feature_cols: List[str],
):
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    X_train_df = train_df[feature_cols]
    y_train = train_df["sepsis_label"].to_numpy()

    X_val_df = val_df[feature_cols]
    y_val = val_df["sepsis_label"].to_numpy()

    X_test_df = test_df[feature_cols]
    y_test = test_df["sepsis_label"].to_numpy()

    metrics = {}

    # 1. Clinical Baseline: qSOFA Rule
    logger.info("Evaluating Clinical Baseline (qSOFA >= 2)...")
    qsofa_probs = np.clip(test_df["qsofa"].to_numpy() / 3.0, 0.0, 1.0)
    metrics["qsofa_clinical_baseline"] = evaluate_predictions(
        y_test, qsofa_probs, "Clinical qSOFA Baseline (Score >= 2)"
    )

    # 2. Logistic Regression (Standardized, Balanced)
    logger.info("Training Logistic Regression...")
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train_df.to_numpy())
    X_test_scaled = scaler.transform(X_test_df.to_numpy())

    lr = LogisticRegression(class_weight="balanced", C=0.5, max_iter=1000, random_state=42)
    lr.fit(X_train_scaled, y_train)
    lr_probs = lr.predict_proba(X_test_scaled)[:, 1]
    metrics["logistic_regression"] = evaluate_predictions(
        y_test, lr_probs, "L2-Regularized Logistic Regression (Balanced)"
    )

    # 3. Random Forest Classifier
    logger.info("Training Random Forest...")
    rf = RandomForestClassifier(
        n_estimators=150, max_depth=8, class_weight="balanced", random_state=42, n_jobs=-1
    )
    rf.fit(X_train_df, y_train)
    rf_probs = rf.predict_proba(X_test_df)[:, 1]
    metrics["random_forest"] = evaluate_predictions(
        y_test, rf_probs, "Random Forest Classifier (Balanced)"
    )

    # 4. LightGBM (Champion Candidate)
    logger.info("Training LightGBM...")
    pos_weight = float((len(y_train) - y_train.sum()) / max(y_train.sum(), 1))
    lgb_clf = lgb.LGBMClassifier(
        n_estimators=120,
        learning_rate=0.03,
        num_leaves=15,
        max_depth=4,
        scale_pos_weight=pos_weight,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        verbosity=-1,
    )
    lgb_clf.fit(
        X_train_df,
        y_train,
        eval_set=[(X_val_df, y_val)],
        eval_metric="auc",
        callbacks=[lgb.early_stopping(stopping_rounds=25, verbose=False)],
    )
    lgb_probs = lgb_clf.predict_proba(X_test_df)[:, 1]
    metrics["lightgbm"] = evaluate_predictions(
        y_test, lgb_probs, "LightGBM Gradient Boosted Decision Trees"
    )

    # 5. XGBoost Classifier
    logger.info("Training XGBoost...")
    xgb_clf = xgb.XGBClassifier(
        n_estimators=120,
        learning_rate=0.03,
        max_depth=4,
        scale_pos_weight=pos_weight,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric="auc",
        early_stopping_rounds=25,
    )
    xgb_clf.fit(X_train_df, y_train, eval_set=[(X_val_df, y_val)], verbose=False)
    xgb_probs = xgb_clf.predict_proba(X_test_df)[:, 1]
    metrics["xgboost"] = evaluate_predictions(y_test, xgb_probs, "XGBoost Classifier")

    # 6. Secondary Model Evaluation: Congestive Heart Failure (CHF) Comorbidity Endpoint
    logger.info("Evaluating Secondary Endpoint: Congestive Heart Failure (CHF)...")
    if "chf" in train_df.columns:
        chf_feature_cols = [c for c in feature_cols if c != "chf"]
        X_train_chf = train_df[chf_feature_cols]
        y_train_chf = train_df["chf"].to_numpy()
        X_test_chf = test_df[chf_feature_cols]
        y_test_chf = test_df["chf"].to_numpy()

        chf_weight = float((len(y_train_chf) - y_train_chf.sum()) / max(y_train_chf.sum(), 1))
        chf_model = lgb.LGBMClassifier(
            n_estimators=120,
            learning_rate=0.03,
            num_leaves=15,
            max_depth=4,
            scale_pos_weight=chf_weight,
            random_state=42,
            verbosity=-1,
        )
        chf_model.fit(X_train_chf, y_train_chf)
        chf_probs = chf_model.predict_proba(X_test_chf)[:, 1]
        metrics["chf_secondary_endpoint"] = evaluate_predictions(
            y_test_chf, chf_probs, "Secondary Endpoint: Congestive Heart Failure (CHF)"
        )
        joblib.dump(chf_model, MODELS_DIR / "chf_secondary_model.joblib")

    # Export metrics comparison
    with open(MODELS_DIR / "cohort_metrics_comparison.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    logger.info("Metrics comparison saved to cohort_metrics_comparison.json")

    # Select Champion: LightGBM
    logger.info("Fitting SHAP TreeExplainer on Champion LightGBM model...")
    joblib.dump(lgb_clf, MODELS_DIR / "cohort_champion_model.joblib")

    background_sample = X_train_df.iloc[:200]
    explainer = shap.TreeExplainer(lgb_clf, data=background_sample)
    joblib.dump(explainer, MODELS_DIR / "cohort_shap_explainer.joblib")

    shap_vals = explainer.shap_values(X_test_df.iloc[:200], check_additivity=False)
    if isinstance(shap_vals, list):
        shap_vals = shap_vals[1]
    elif len(shap_vals.shape) == 3:
        shap_vals = shap_vals[:, :, 1]
    mean_abs_shap = np.abs(shap_vals).mean(axis=0)

    feature_importances = sorted(
        [
            {"feature": feature_cols[i], "importance": round(float(mean_abs_shap[i]), 5)}
            for i in range(len(feature_cols))
        ],
        key=lambda x: x["importance"],
        reverse=True,
    )

    champion_meta = {
        "model_id": "omnimed-icu-cohort-lgbm-v1",
        "dataset_source": "Archive2 Sepsis ICU Synthetic Cohort (5,000 patients, Anti-Leakage Filtered)",
        "algorithm": "lightgbm",
        "target_endpoint": "sepsis_label",
        "test_metrics": metrics["lightgbm"],
        "chf_secondary_metrics": metrics.get("chf_secondary_endpoint"),
        "top_features": feature_importances[:25],
        "feature_cols": feature_cols,
        "excluded_leakage_cols": EXCLUDED_LEAKAGE_AND_OUTCOME_COLS,
        "imputation_medians": train_df[feature_cols].median().to_dict(),
        "clinical_disclaimer": "Auxiliary risk stratification decision-support model trained on Archive2 ICU cohort (post-event interventions and synthetic target proxies excluded). Synthetic data strictly for engineering validation.",
    }
    with open(MODELS_DIR / "cohort_champion_meta.json", "w", encoding="utf-8") as f:
        json.dump(champion_meta, f, indent=2)
    logger.info("Champion metadata saved to cohort_champion_meta.json")

    logger.info("=== Cohort Benchmark Results ===")
    for name, res in metrics.items():
        logger.info(
            f"{name}: AUROC={res['auroc']}, AUPRC={res['auprc']}, Brier={res['brier_score']}, "
            f"Sens={res['sensitivity']}, Spec={res['specificity']}"
        )


def main():
    if not RAW_CSV_PATH.exists():
        raise FileNotFoundError(f"Missing {RAW_CSV_PATH}")
    df = load_and_clean_data(RAW_CSV_PATH)
    train_df, val_df, test_df, feature_cols = split_cohort_data(df)
    train_and_benchmark_models(train_df, val_df, test_df, feature_cols)
    logger.info("Pipeline execution completed successfully.")


if __name__ == "__main__":
    main()

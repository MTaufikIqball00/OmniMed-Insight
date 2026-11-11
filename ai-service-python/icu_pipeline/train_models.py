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
from pathlib import Path
from typing import Dict, Any
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
from sklearn.preprocessing import StandardScaler
import lightgbm as lgb
import xgboost as xgb
import shap

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PROCESSED_DIR = REPO_ROOT / "data" / "icu_processed"
MODELS_DIR = REPO_ROOT / "ai-service-python" / "models" / "icu"


def evaluate_predictions(y_true: np.ndarray, y_prob: np.ndarray, threshold: float = 0.5) -> Dict[str, Any]:
    y_pred = (y_prob >= threshold).astype(int)

    auroc = float(roc_auc_score(y_true, y_prob)) if len(np.unique(y_true)) > 1 else 0.5
    auprc = float(average_precision_score(y_true, y_prob)) if len(np.unique(y_true)) > 1 else 0.0
    brier = float(brier_score_loss(y_true, y_prob))

    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = int(cm[0, 0]), int(cm[0, 1]), int(cm[1, 0]), int(cm[1, 1])

    sens = float(tp / (tp + fn)) if (tp + fn) > 0 else 0.0
    spec = float(tn / (tn + fp)) if (tn + fp) > 0 else 0.0
    prec = float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0
    f1 = float(2 * (prec * sens) / (prec + sens)) if (prec + sens) > 0 else 0.0

    return {
        "auroc": round(auroc, 4),
        "auprc": round(auprc, 4),
        "brier_score": round(brier, 4),
        "threshold_used": round(threshold, 4),
        "sensitivity": round(sens, 4),
        "specificity": round(spec, 4),
        "precision": round(prec, 4),
        "f1_score": round(f1, 4),
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
    feature_cols = meta["feature_cols"]
    target_col = meta["target_col"]

    X_train_df = train_df[feature_cols]
    y_train = train_df[target_col].to_numpy()

    X_val_df = val_df[feature_cols]
    y_val = val_df[target_col].to_numpy()

    X_test_df = test_df[feature_cols]
    y_test = test_df[target_col].to_numpy()

    print(f"[Training] Features: {len(feature_cols)}. Train rows: {len(X_train_df)}, Val: {len(X_val_df)}, Test: {len(X_test_df)}")
    print(f"[Training] Class imbalance: Train pos={y_train.sum()}/{len(y_train)} ({y_train.mean():.3%})")

    pos_weight = (len(y_train) - y_train.sum()) / max(1, y_train.sum())

    results = {}

    # -------------------------------------------------------------
    # 1. Clinical qSOFA Baseline
    # -------------------------------------------------------------
    print("[1/4] Evaluating Clinical qSOFA Rule-based Baseline...")
    val_qsofa = val_df["qsofa_vital_score"].to_numpy() / 2.0
    test_qsofa = test_df["qsofa_vital_score"].to_numpy() / 2.0
    thresh_qsofa = 0.50
    results["qsofa_clinical_baseline"] = evaluate_predictions(y_test, test_qsofa, thresh_qsofa)
    results["qsofa_clinical_baseline"]["model_name"] = "Clinical qSOFA Baseline (SBP <= 100, RR >= 22)"

    # -------------------------------------------------------------
    # 2. Logistic Regression
    # -------------------------------------------------------------
    print("[2/4] Training Logistic Regression...")
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
    # 3. LightGBM Classifier (Regularized Shallow Trees)
    # -------------------------------------------------------------
    print("[3/4] Training LightGBM Classifier...")
    lgb_clf = lgb.LGBMClassifier(
        n_estimators=60,
        learning_rate=0.03,
        num_leaves=7,
        max_depth=3,
        scale_pos_weight=5.0,
        min_child_samples=20,
        subsample=0.8,
        colsample_bytree=0.7,
        reg_alpha=1.0,
        reg_lambda=5.0,
        random_state=42,
        verbosity=-1,
    )
    lgb_clf.fit(X_train_df, y_train)

    val_prob_lgb = lgb_clf.predict_proba(X_val_df)[:, 1]
    thresh_lgb = find_optimal_threshold(y_val, val_prob_lgb, min_specificity=0.65)
    test_prob_lgb = lgb_clf.predict_proba(X_test_df)[:, 1]
    results["lightgbm"] = evaluate_predictions(y_test, test_prob_lgb, thresh_lgb)
    results["lightgbm"]["model_name"] = "LightGBM Gradient Boosted Decision Trees"

    # -------------------------------------------------------------
    # 4. XGBoost Classifier
    # -------------------------------------------------------------
    print("[4/4] Training XGBoost Classifier...")
    xgb_model = xgb.XGBClassifier(
        n_estimators=60,
        learning_rate=0.03,
        max_depth=3,
        scale_pos_weight=5.0,
        subsample=0.8,
        colsample_bytree=0.7,
        reg_alpha=1.0,
        reg_lambda=5.0,
        eval_metric="auc",
        random_state=42,
    )
    xgb_model.fit(X_train_df, y_train, verbose=False)

    val_prob_xgb = xgb_model.predict_proba(X_val_df)[:, 1]
    thresh_xgb = find_optimal_threshold(y_val, val_prob_xgb, min_specificity=0.65)
    test_prob_xgb = xgb_model.predict_proba(X_test_df)[:, 1]
    results["xgboost"] = evaluate_predictions(y_test, test_prob_xgb, thresh_xgb)
    results["xgboost"]["model_name"] = "XGBoost Classifier"

    # Print benchmark summary
    print("\n--- Model Benchmark on Test Set ---")
    for k, v in results.items():
        print(
            f"  {v['model_name']}: AUROC = {v['auroc']}, AUPRC = {v['auprc']}, "
            f"Sens = {v['sensitivity']}, Spec = {v['specificity']}, Brier = {v['brier_score']}"
        )

    # -------------------------------------------------------------
    # Select Champion Model: LightGBM for robust SHAP TreeExplainer
    # -------------------------------------------------------------
    champ_key = "lightgbm"
    champ_obj = lgb_clf
    champ_thresh = thresh_lgb

    print(f"\n[Champion Selected] {champ_key.upper()} with Test AUROC = {results[champ_key]['auroc']}")

    # Save Model Artifacts
    joblib.dump(champ_obj, MODELS_DIR / "champion_model.joblib")
    joblib.dump(scaler, MODELS_DIR / "scaler.joblib")

    # Fit SHAP TreeExplainer with background reference dataset to avoid warnings
    print("[SHAP] Fitting TreeExplainer on Champion LightGBM model...")
    bg_df = X_train_df.iloc[:100]
    explainer = shap.TreeExplainer(champ_obj, data=bg_df)
    joblib.dump(explainer, MODELS_DIR / "shap_explainer.joblib")

    # Compute background SHAP values on validation sample
    shap_sample = X_val_df.iloc[: min(100, len(X_val_df))]
    raw_shap = explainer.shap_values(shap_sample, check_additivity=False)
    if isinstance(raw_shap, list):
        shap_vals = raw_shap[1] if len(raw_shap) > 1 else raw_shap[0]
    elif len(raw_shap.shape) == 3:
        shap_vals = raw_shap[:, :, 1]
    else:
        shap_vals = raw_shap

    mean_abs_shap = np.mean(np.abs(shap_vals), axis=0)
    top_feature_indices = np.argsort(mean_abs_shap)[::-1]

    global_importance = []
    for idx in top_feature_indices[:20]:
        global_importance.append(
            {
                "feature": feature_cols[idx],
                "importance": round(float(mean_abs_shap[idx]), 5),
            }
        )

    champion_metadata = {
        "model_id": f"omnimed-icu-{champ_key}-v1",
        "algorithm": champ_key,
        "prediction_horizon": "6_to_12_hours_before_sepsis",
        "decision_threshold": round(champ_thresh, 4),
        "test_metrics": results[champ_key],
        "top_features": global_importance,
        "feature_cols": feature_cols,
        "imputation_medians": meta["imputation_medians"],
        "clinical_disclaimer": "Auxiliary risk stratification decision-support model. Not cleared for autonomous intervention.",
    }

    with open(MODELS_DIR / "champion_model_meta.json", "w", encoding="utf-8") as f:
        json.dump(champion_metadata, f, indent=2)

    with open(MODELS_DIR / "model_metrics_comparison.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"[Export] Saved champion model, SHAP explainer, and metadata to {MODELS_DIR}")
    return champion_metadata, results


if __name__ == "__main__":
    meta, res = train_and_evaluate_all()
    print("\n--- Pipeline Completed Successfully ---")

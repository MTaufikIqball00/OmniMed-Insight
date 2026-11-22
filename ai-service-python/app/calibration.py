"""
OmniMed Insight — Post-Hoc Probability Calibration & Reliability Telemetry

Implements leakage-free probability calibration and calibration evaluation for both:
1. Multiclass medical imaging logits (Temperature Scaling, Multiclass Platt Scaling, ECE/Brier/NLL).
2. Binary ICU risk probabilities (Platt Scaling / Sigmoid and Isotonic Regression via FrozenEstimator).

All calibrator parameters and operating thresholds are fitted EXCLUSIVELY on validation splits;
held-out test splits are used strictly for final unbiased evaluation.
"""

from typing import Any, Callable, Dict, List, Literal, Optional, Tuple

import numpy as np
from scipy.optimize import minimize
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    log_loss,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold

try:
    from sklearn.frozen import FrozenEstimator
except ImportError:  # pragma: no cover - fallback for older scikit-learn
    FrozenEstimator = None  # type: ignore[assignment]


def _softmax_np(logits: np.ndarray) -> np.ndarray:
    """Numerically stable row-wise softmax over 2D array (N, C)."""
    arr = np.asarray(logits, dtype=np.float64)
    shifted = arr - np.max(arr, axis=1, keepdims=True)
    exp_z = np.exp(shifted)
    return exp_z / np.sum(exp_z, axis=1, keepdims=True)


def _log_softmax_np(logits: np.ndarray) -> np.ndarray:
    """Numerically stable row-wise log-softmax over 2D array (N, C)."""
    arr = np.asarray(logits, dtype=np.float64)
    max_z = np.max(arr, axis=1, keepdims=True)
    shifted = arr - max_z
    return shifted - np.log(np.sum(np.exp(shifted), axis=1, keepdims=True))


def _compute_ece_raw(
    y_true: Any,
    y_prob: Any,
    n_bins: int = 10,
    multiclass: bool = False,
) -> Tuple[float, List[Dict[str, Any]]]:
    """
    Computes unrounded Expected Calibration Error (ECE) and non-empty reliability bins
    across `n_bins` uniform intervals in [0.0, 1.0].
    """
    y_true_arr = np.asarray(y_true)
    y_prob_arr = np.asarray(y_prob, dtype=np.float64)
    n = int(y_true_arr.size)
    if n == 0:
        return 0.0, []

    if multiclass:
        if y_prob_arr.ndim != 2:
            raise ValueError("multiclass=True requires 2D probability array of shape (N, C).")
        labels = y_true_arr.astype(int).ravel()
        confidences = np.clip(np.max(y_prob_arr, axis=1), 0.0, 1.0)
        correctness = (np.argmax(y_prob_arr, axis=1) == labels).astype(np.float64)
    else:
        if y_prob_arr.ndim == 2 and y_prob_arr.shape[1] == 2:
            confidences = np.clip(y_prob_arr[:, 1], 0.0, 1.0)
        else:
            confidences = np.clip(y_prob_arr.ravel(), 0.0, 1.0)
        correctness = y_true_arr.astype(np.float64).ravel()

    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    bins: List[Dict[str, Any]] = []

    for idx in range(n_bins):
        bin_lower = float(bin_edges[idx])
        bin_upper = float(bin_edges[idx + 1])
        if idx < n_bins - 1:
            mask = (confidences >= bin_lower) & (confidences < bin_upper)
        else:
            mask = (confidences >= bin_lower) & (confidences <= bin_upper)

        count = int(np.sum(mask))
        if count == 0:
            continue

        avg_conf = float(np.mean(confidences[mask]))
        emp_acc = float(np.mean(correctness[mask]))
        gap = abs(emp_acc - avg_conf)
        ece += (count / float(n)) * gap

        bins.append(
            {
                "bin_lower": round(bin_lower, 4) + 0.0,
                "bin_upper": round(bin_upper, 4) + 0.0,
                "avg_confidence": round(avg_conf, 4) + 0.0,
                "empirical_accuracy": round(emp_acc, 4) + 0.0,
                "count": count,
                "gap": round(gap, 4) + 0.0,
            }
        )

    return float(ece), bins


def compute_ece(
    y_true: Any,
    y_prob: Any,
    n_bins: int = 10,
    multiclass: bool = False,
) -> Tuple[float, List[Dict[str, Any]]]:
    """
    Computes Expected Calibration Error (ECE) over uniform confidence bins [0, 0.1) .. [0.9, 1.0].
    Empty bins (count == 0) are omitted from the returned reliability_bins list.
    """
    ece_raw, bins = _compute_ece_raw(y_true, y_prob, n_bins=n_bins, multiclass=multiclass)
    return round(float(ece_raw), 4) + 0.0, bins


def _compute_multiclass_metrics_raw(y_true: Any, probs: Any) -> Dict[str, Any]:
    y_true_int = np.asarray(y_true, dtype=int).ravel()
    probs_arr = np.asarray(probs, dtype=np.float64)
    if probs_arr.ndim != 2:
        raise ValueError("probs must be a 2D array of shape (N, C).")
    n, num_classes = probs_arr.shape
    if n == 0:
        return {
            "accuracy": 0.0,
            "ece_score": 0.0,
            "brier_score": 0.0,
            "nll_score": 0.0,
            "reliability_bins": [],
        }

    row_sums = np.sum(probs_arr, axis=1, keepdims=True)
    probs_norm = np.where(row_sums > 0, probs_arr / np.maximum(row_sums, 1e-12), 1.0 / num_classes)

    accuracy = float(np.mean(np.argmax(probs_norm, axis=1) == y_true_int))
    one_hot = np.eye(num_classes, dtype=np.float64)[y_true_int]
    brier_score = float(np.mean((probs_norm - one_hot) ** 2))
    nll_score = float(-np.mean(np.log(np.clip(probs_norm[np.arange(n), y_true_int], 1e-12, 1.0))))
    ece_raw, reliability_bins = _compute_ece_raw(y_true_int, probs_norm, n_bins=10, multiclass=True)

    return {
        "accuracy": accuracy,
        "ece_score": ece_raw,
        "brier_score": brier_score,
        "nll_score": nll_score,
        "reliability_bins": reliability_bins,
    }


def compute_multiclass_metrics(y_true: Any, probs: Any) -> Dict[str, Any]:
    """
    Computes multiclass classification & calibration metrics:
    accuracy, ece_score, brier_score (mean squared error across classes against one-hot),
    nll_score, and non-empty reliability_bins.
    """
    raw = _compute_multiclass_metrics_raw(y_true, probs)
    return {
        "accuracy": round(float(raw["accuracy"]), 4) + 0.0,
        "ece_score": round(float(raw["ece_score"]), 4) + 0.0,
        "brier_score": round(float(raw["brier_score"]), 4) + 0.0,
        "nll_score": round(float(raw["nll_score"]), 4) + 0.0,
        "reliability_bins": raw["reliability_bins"],
    }


class TemperatureScaler:
    """
    Post-hoc single-parameter temperature scaling (Guo et al., ICML 2017) minimizing
    validation negative log-likelihood with T bounded in [0.05, 20.0].
    """

    def __init__(self, temperature: float = 1.0) -> None:
        self.temperature: float = float(np.clip(temperature, 0.05, 20.0))

    def fit(self, val_logits: Any, val_labels: Any) -> "TemperatureScaler":
        logits = np.asarray(val_logits, dtype=np.float64)
        labels = np.asarray(val_labels, dtype=int).ravel()
        if logits.ndim != 2 or len(labels) != logits.shape[0]:
            raise ValueError("val_logits must be (N, C) matching val_labels of length N.")
        n = logits.shape[0]
        row_idx = np.arange(n)

        def objective(params: np.ndarray) -> float:
            temp = float(params[0])
            log_probs = _log_softmax_np(logits / temp)
            return float(-np.mean(log_probs[row_idx, labels]))

        best_val = float("inf")
        best_temp = 1.0
        for init_t in (1.0, 0.5, 2.0):
            res = minimize(
                objective,
                x0=np.array([init_t], dtype=np.float64),
                method="L-BFGS-B",
                bounds=[(0.05, 20.0)],
            )
            cand_temp = float(np.clip(res.x[0], 0.05, 20.0))
            cand_val = float(objective(np.array([cand_temp], dtype=np.float64)))
            if cand_val < best_val:
                best_val = cand_val
                best_temp = cand_temp

        self.temperature = best_temp
        return self

    def predict_proba(self, logits: Any) -> np.ndarray:
        arr = np.asarray(logits, dtype=np.float64)
        is_1d = arr.ndim == 1
        if is_1d:
            arr = arr[None, :]
        probs = _softmax_np(arr / self.temperature)
        return probs[0] if is_1d else probs

    def to_dict(self) -> Dict[str, Any]:
        return {
            "method": "TEMPERATURE_SCALING",
            "temperature": float(self.temperature),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TemperatureScaler":
        return cls(temperature=float(d["temperature"]))


class MulticlassPlattScaler:
    """
    Diagonal multiclass Platt scaling fitting per-class affine transforms (a_k * z_k + b_k)
    followed by softmax to minimize multiclass NLL on validation logits.
    """

    def __init__(
        self,
        num_classes: Optional[int] = None,
        scales: Optional[List[float]] = None,
        biases: Optional[List[float]] = None,
    ) -> None:
        self.num_classes: Optional[int] = num_classes
        self.scales: Optional[np.ndarray] = np.asarray(scales, dtype=np.float64) if scales is not None else None
        self.biases: Optional[np.ndarray] = np.asarray(biases, dtype=np.float64) if biases is not None else None

    def fit(self, val_logits: Any, val_labels: Any) -> "MulticlassPlattScaler":
        logits = np.asarray(val_logits, dtype=np.float64)
        labels = np.asarray(val_labels, dtype=int).ravel()
        if logits.ndim != 2 or len(labels) != logits.shape[0]:
            raise ValueError("val_logits must be (N, C) matching val_labels of length N.")

        n, c = logits.shape
        self.num_classes = int(c)
        one_hot = np.eye(c, dtype=np.float64)[labels]
        row_idx = np.arange(n)
        l2_reg = 1e-4

        def objective_and_grad(theta: np.ndarray) -> Tuple[float, np.ndarray]:
            a = theta[:c]
            b = theta[c:]
            scaled = logits * a[None, :] + b[None, :]
            log_probs = _log_softmax_np(scaled)
            probs = np.exp(log_probs)
            nll = -float(np.mean(log_probs[row_idx, labels]))
            reg = 0.5 * l2_reg * float(np.sum((a - 1.0) ** 2) + np.sum(b ** 2))

            diff = (probs - one_hot) / float(n)
            grad_a = np.sum(diff * logits, axis=0) + l2_reg * (a - 1.0)
            grad_b = np.sum(diff, axis=0) + l2_reg * b
            return nll + reg, np.concatenate([grad_a, grad_b])

        x0 = np.concatenate([np.ones(c, dtype=np.float64), np.zeros(c, dtype=np.float64)])
        bounds = [(0.05, 20.0)] * c + [(-10.0, 10.0)] * c
        res = minimize(
            objective_and_grad,
            x0=x0,
            jac=True,
            method="L-BFGS-B",
            bounds=bounds,
        )
        self.scales = np.clip(res.x[:c], 0.05, 20.0)
        self.biases = np.clip(res.x[c:], -10.0, 10.0)
        return self

    def predict_proba(self, logits: Any) -> np.ndarray:
        if self.scales is None or self.biases is None:
            raise RuntimeError("MulticlassPlattScaler must be fitted or loaded via from_dict before predict_proba.")
        arr = np.asarray(logits, dtype=np.float64)
        is_1d = arr.ndim == 1
        if is_1d:
            arr = arr[None, :]
        scaled = arr * self.scales[None, :] + self.biases[None, :]
        probs = _softmax_np(scaled)
        return probs[0] if is_1d else probs

    def to_dict(self) -> Dict[str, Any]:
        if self.scales is None or self.biases is None or self.num_classes is None:
            raise RuntimeError("MulticlassPlattScaler is not fitted.")
        return {
            "method": "PLATT_SCALING",
            "num_classes": int(self.num_classes),
            "scales": [float(x) for x in self.scales],
            "biases": [float(x) for x in self.biases],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MulticlassPlattScaler":
        scales = d.get("scales", d.get("a"))
        biases = d.get("biases", d.get("b"))
        if scales is None or biases is None:
            raise ValueError("MulticlassPlattScaler dict requires 'scales' and 'biases'.")
        num_classes = int(d.get("num_classes", len(scales)))
        return cls(num_classes=num_classes, scales=list(scales), biases=list(biases))


def make_prefit_calibrator(
    base_estimator: Any,
    method: Literal["sigmoid", "isotonic"],
) -> CalibratedClassifierCV:
    """
    Wraps a pre-fitted estimator with CalibratedClassifierCV without triggering
    scikit-learn 1.7+ deprecation warnings for `cv="prefit"`.
    """
    if FrozenEstimator is not None:
        return CalibratedClassifierCV(FrozenEstimator(base_estimator), method=method)
    return CalibratedClassifierCV(base_estimator, cv="prefit", method=method)


def _evaluate_binary_raw(
    y_true: np.ndarray,
    y_prob: np.ndarray,
) -> Tuple[Dict[str, Any], Dict[str, float]]:
    y_true_arr = np.asarray(y_true, dtype=int).ravel()
    y_prob_arr = np.asarray(y_prob, dtype=np.float64).ravel()
    y_prob_clipped = np.clip(y_prob_arr, 1e-12, 1.0 - 1e-12)

    has_two_classes = len(np.unique(y_true_arr)) > 1
    auroc = float(roc_auc_score(y_true_arr, y_prob_arr)) if has_two_classes else 0.5
    auprc = float(average_precision_score(y_true_arr, y_prob_arr)) if has_two_classes else 0.0
    brier = float(brier_score_loss(y_true_arr, np.clip(y_prob_arr, 0.0, 1.0)))
    nll = float(log_loss(y_true_arr, y_prob_clipped, labels=[0, 1]))
    ece_raw, bins = _compute_ece_raw(y_true_arr, y_prob_arr, n_bins=10, multiclass=False)

    rounded = {
        "auroc": round(auroc, 4) + 0.0,
        "auprc": round(auprc, 4) + 0.0,
        "brier_score": round(brier, 4) + 0.0,
        "nll_score": round(nll, 4) + 0.0,
        "ece_score": round(ece_raw, 4) + 0.0,
        "reliability_bins": bins,
    }
    raw_scores = {
        "ece": ece_raw,
        "brier": brier,
        "nll": nll,
        "auroc": auroc,
        "auprc": auprc,
    }
    return rounded, raw_scores


def _default_youden_threshold(y_true: np.ndarray, y_prob: np.ndarray, min_specificity: float = 0.65) -> float:
    candidates = np.unique(
        np.concatenate(
            [
                np.quantile(y_prob, np.linspace(0.50, 0.96, 47)),
                np.linspace(0.02, 0.85, 84),
            ]
        )
    )
    best_thresh = float(np.quantile(y_prob, 0.85)) if len(y_prob) > 0 else 0.5
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


def _threshold_metrics(y_true: np.ndarray, y_prob: np.ndarray, threshold: float) -> Dict[str, Any]:
    y_pred = (y_prob >= threshold).astype(int)
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = int(cm[0, 0]), int(cm[0, 1]), int(cm[1, 0]), int(cm[1, 1])
    sens = float(tp / (tp + fn)) if (tp + fn) > 0 else 0.0
    spec = float(tn / (tn + fp)) if (tn + fp) > 0 else 0.0
    prec = float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0
    f1 = float(2.0 * prec * sens / (prec + sens)) if (prec + sens) > 0 else 0.0
    return {
        "threshold_used": round(float(threshold), 4) + 0.0,
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


def _oof_val_calibration_probs(
    base_estimator: Any,
    X_val_df: Any,
    y_val_arr: np.ndarray,
    method: Literal["sigmoid", "isotonic"],
) -> np.ndarray:
    """
    Computes out-of-fold validation calibration probabilities strictly inside the validation split
    so non-parametric isotonic regression cannot win selection via in-sample step memorization.
    Falls back to direct val fit only when validation split has too few minority samples for CV.
    """
    pos_count = int(np.sum(y_val_arr == 1))
    neg_count = int(np.sum(y_val_arr == 0))
    n_splits = min(5, pos_count, neg_count)
    if n_splits < 2 or len(y_val_arr) < 40:
        cal = make_prefit_calibrator(base_estimator, method=method)
        cal.fit(X_val_df, y_val_arr)
        return np.asarray(cal.predict_proba(X_val_df)[:, 1], dtype=np.float64)

    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    oof_probs = np.zeros(len(y_val_arr), dtype=np.float64)
    for fit_idx, eval_idx in skf.split(X_val_df, y_val_arr):
        X_fit = X_val_df.iloc[fit_idx] if hasattr(X_val_df, "iloc") else X_val_df[fit_idx]
        X_eval = X_val_df.iloc[eval_idx] if hasattr(X_val_df, "iloc") else X_val_df[eval_idx]
        cal_fold = make_prefit_calibrator(base_estimator, method=method)
        cal_fold.fit(X_fit, y_val_arr[fit_idx])
        oof_probs[eval_idx] = cal_fold.predict_proba(X_eval)[:, 1]
    return oof_probs


def fit_and_compare_binary_calibrators(
    base_estimator: Any,
    X_val_df: Any,
    y_val: Any,
    X_test_df: Any,
    y_test: Any,
    threshold_finder_fn: Optional[Callable[[np.ndarray, np.ndarray], float]] = None,
) -> Dict[str, Any]:
    """
    Fits Platt Scaling (`sigmoid`) and Isotonic Calibration (`isotonic`) EXCLUSIVELY on
    `(X_val_df, y_val)`, compares uncalibrated vs Platt vs Isotonic strictly on validation
    metrics (out-of-fold within val for candidate calibrators) to select the winner without
    peeking at test, fits the final calibrators on full `(X_val_df, y_val)`, derives
    `calibrated_threshold` strictly on `val`, and evaluates all 3 on held-out `(X_test_df, y_test)`.
    """
    y_val_arr = np.asarray(y_val, dtype=int).ravel()
    y_test_arr = np.asarray(y_test, dtype=int).ravel()

    # 1. Validation comparison (strictly within validation split, never touching test)
    val_uncal_probs = np.asarray(base_estimator.predict_proba(X_val_df)[:, 1], dtype=np.float64)
    val_platt_oof = _oof_val_calibration_probs(base_estimator, X_val_df, y_val_arr, method="sigmoid")
    val_iso_oof = _oof_val_calibration_probs(base_estimator, X_val_df, y_val_arr, method="isotonic")

    val_uncal_metrics, _ = _evaluate_binary_raw(y_val_arr, val_uncal_probs)
    val_platt_metrics, val_platt_raw = _evaluate_binary_raw(y_val_arr, val_platt_oof)
    val_iso_metrics, val_iso_raw = _evaluate_binary_raw(y_val_arr, val_iso_oof)

    val_comparison = {
        "NONE_UNCALIBRATED": val_uncal_metrics,
        "PLATT_SCALING": val_platt_metrics,
        "ISOTONIC_CALIBRATION": val_iso_metrics,
    }

    # Winner selection strictly by validation ECE + Brier + 0.2 * NLL
    def _val_selection_loss(raw: Dict[str, float]) -> Tuple[float, float, float]:
        composite = raw["ece"] + raw["brier"] + 0.2 * raw["nll"]
        return (composite, raw["ece"], raw["brier"])

    if _val_selection_loss(val_platt_raw) <= _val_selection_loss(val_iso_raw):
        best_method = "PLATT_SCALING"
    else:
        best_method = "ISOTONIC_CALIBRATION"

    # 2. Fit final calibrators on full validation split
    platt_cal = make_prefit_calibrator(base_estimator, method="sigmoid")
    platt_cal.fit(X_val_df, y_val_arr)

    iso_cal = make_prefit_calibrator(base_estimator, method="isotonic")
    iso_cal.fit(X_val_df, y_val_arr)

    best_calibrator = platt_cal if best_method == "PLATT_SCALING" else iso_cal

    # 3. Compute calibrated_threshold strictly on the selected calibrator's validation probabilities
    best_val_probs = np.asarray(best_calibrator.predict_proba(X_val_df)[:, 1], dtype=np.float64)
    finder = threshold_finder_fn if threshold_finder_fn is not None else _default_youden_threshold
    calibrated_threshold = round(float(finder(y_val_arr, best_val_probs)), 4) + 0.0

    # Compute uncalibrated threshold strictly on val for fair before-vs-after reporting
    uncal_val_threshold = round(float(finder(y_val_arr, val_uncal_probs)), 4) + 0.0

    # 4. Held-out test evaluation (strictly read-only evaluation after all fitting & selection)
    test_uncal_probs = np.asarray(base_estimator.predict_proba(X_test_df)[:, 1], dtype=np.float64)
    test_platt_probs = np.asarray(platt_cal.predict_proba(X_test_df)[:, 1], dtype=np.float64)
    test_iso_probs = np.asarray(iso_cal.predict_proba(X_test_df)[:, 1], dtype=np.float64)

    test_uncal_metrics, _ = _evaluate_binary_raw(y_test_arr, test_uncal_probs)
    test_uncal_metrics.update(_threshold_metrics(y_test_arr, test_uncal_probs, uncal_val_threshold))

    platt_val_thresh = round(float(finder(y_val_arr, platt_cal.predict_proba(X_val_df)[:, 1])), 4) + 0.0
    test_platt_metrics, _ = _evaluate_binary_raw(y_test_arr, test_platt_probs)
    test_platt_metrics.update(_threshold_metrics(y_test_arr, test_platt_probs, platt_val_thresh))

    iso_val_thresh = round(float(finder(y_val_arr, iso_cal.predict_proba(X_val_df)[:, 1])), 4) + 0.0
    test_iso_metrics, _ = _evaluate_binary_raw(y_test_arr, test_iso_probs)
    test_iso_metrics.update(_threshold_metrics(y_test_arr, test_iso_probs, iso_val_thresh))

    test_comparison = {
        "NONE_UNCALIBRATED": test_uncal_metrics,
        "PLATT_SCALING": test_platt_metrics,
        "ISOTONIC_CALIBRATION": test_iso_metrics,
    }

    selected_test_metrics = dict(test_comparison[best_method])
    return {
        "best_method": best_method,
        "best_calibrator": best_calibrator,
        "calibrated_threshold": calibrated_threshold,
        "val_comparison": val_comparison,
        "test_comparison": test_comparison,
        "selected_test_metrics": selected_test_metrics,
        "reliability_bins": selected_test_metrics["reliability_bins"],
    }

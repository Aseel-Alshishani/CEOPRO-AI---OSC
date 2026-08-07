"""
CEOPRO AI - Demand Forecasting Evaluation (spec S25: MAE, RMSE, MASE for forecasting).
"""

from typing import Sequence

import numpy as np


def mae(actual: Sequence[float], predicted: Sequence[float]) -> float:
    actual, predicted = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    return float(np.mean(np.abs(actual - predicted)))


def rmse(actual: Sequence[float], predicted: Sequence[float]) -> float:
    actual, predicted = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    return float(np.sqrt(np.mean((actual - predicted) ** 2)))


def mase(actual: Sequence[float], predicted: Sequence[float], training_series: Sequence[float]) -> float:
    """
    Mean Absolute Scaled Error: MAE of the model divided by the MAE of a naive
    one-step-ahead forecast on the training series. Values < 1 mean the model
    beats a naive forecast; values >= 1 mean it doesn't.
    """
    training_series = np.asarray(training_series, dtype=float)
    if len(training_series) < 2:
        return float("nan")

    naive_errors = np.abs(np.diff(training_series))
    scale = float(np.mean(naive_errors))
    if scale == 0:
        return float("nan")

    return mae(actual, predicted) / scale


def pinball_loss(actual: Sequence[float], predicted_quantile: Sequence[float], quantile: float) -> float:
    """
    Quantile ("pinball") loss (spec S25: "Pinball Loss where applicable"). Only
    meaningful for a quantile forecast (e.g. a model trained to predict the
    10th/90th percentile of demand), not the point forecast this module
    currently produces - the pipeline's confidence_range_lower/upper today is
    a heuristic spread, not a quantile-regression output. Provided so it's
    ready to use the moment quantile forecasts exist, per "where applicable".
    """
    if not 0 < quantile < 1:
        raise ValueError(f"quantile must be between 0 and 1, got {quantile}")

    actual, predicted_quantile = np.asarray(actual, dtype=float), np.asarray(predicted_quantile, dtype=float)
    error = actual - predicted_quantile
    return float(np.mean(np.maximum(quantile * error, (quantile - 1) * error)))


def compare_to_baselines(model_predictions: Sequence[float], actual: Sequence[float], baseline_forecasts: dict) -> dict:
    """
    Returns each candidate's MAE plus which one is best (lowest MAE), including
    the model itself as a candidate named "model". Per spec S18, the model must
    outperform every baseline before its forecast is trusted over theirs.
    """
    candidates = {"model": mae(actual, model_predictions)}
    for name, forecast in baseline_forecasts.items():
        candidates[name] = mae(actual, forecast)

    best_name = min(candidates, key=candidates.get)
    return {
        "scores": candidates,
        "best": best_name,
        "model_beats_all_baselines": best_name == "model",
    }

"""
CEOPRO AI - Demand Forecasting Baselines (spec S18).
Every trained model must be validated against these before its forecast is
trusted; if it doesn't beat them, the pipeline falls back to the best baseline.
"""

from typing import List

import numpy as np
import pandas as pd


def naive_forecast(history: pd.Series, horizon_days: int) -> np.ndarray:
    """Repeats the last observed value for the entire horizon."""
    last_value = float(history.iloc[-1])
    return np.full(horizon_days, last_value)


def seasonal_naive_forecast(history: pd.Series, horizon_days: int, season_length: int = 7) -> np.ndarray:
    """Repeats the same weekday's value from the last full season."""
    if len(history) < season_length:
        return naive_forecast(history, horizon_days)

    last_season = history.iloc[-season_length:].to_numpy()
    reps = int(np.ceil(horizon_days / season_length))
    return np.tile(last_season, reps)[:horizon_days]


def moving_average_forecast(history: pd.Series, horizon_days: int, window: int = 7) -> np.ndarray:
    """Repeats the mean of the trailing window for the entire horizon."""
    window = min(window, len(history))
    avg = float(history.iloc[-window:].mean())
    return np.full(horizon_days, avg)


def previous_period_forecast(history: pd.Series, horizon_days: int) -> np.ndarray:
    """Reuses the immediately preceding `horizon_days`-length period as the forecast."""
    if len(history) < horizon_days:
        return naive_forecast(history, horizon_days)
    return history.iloc[-horizon_days:].to_numpy()


BASELINE_FUNCTIONS = {
    "naive": naive_forecast,
    "seasonal_naive": seasonal_naive_forecast,
    "moving_average": moving_average_forecast,
    "previous_period": previous_period_forecast,
}


def all_baseline_forecasts(history: pd.Series, horizon_days: int) -> dict:
    return {name: fn(history, horizon_days) for name, fn in BASELINE_FUNCTIONS.items()}


def baseline_in_sample_predictions(history: pd.Series, name: str) -> List[float]:
    """
    One-step-ahead in-sample predictions for a baseline, used to backtest which
    baseline is strongest on this series before comparing against XGBoost.
    """
    values = history.to_numpy()
    preds = []
    for i in range(1, len(values)):
        window = pd.Series(values[:i])
        preds.append(float(BASELINE_FUNCTIONS[name](window, 1)[0]))
    return preds

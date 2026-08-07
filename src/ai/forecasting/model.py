"""
CEOPRO AI - XGBoost Demand Forecaster (spec S18).
CPU-only by design; no GPU parameters are set anywhere in this module.
"""

from typing import List, Tuple

import numpy as np
import pandas as pd
import xgboost as xgb

from src.ai.forecasting.features import feature_columns

DEFAULT_PARAMS = {
    "objective": "reg:squarederror",
    "n_estimators": 200,
    "max_depth": 4,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "n_jobs": -1,
    "tree_method": "hist",  # CPU histogram method - no GPU dependency
}

MODEL_NAME = "demand_forecast_xgboost"


class XGBoostDemandForecaster:
    def __init__(self, params: dict = None):
        self.params = {**DEFAULT_PARAMS, **(params or {})}
        self.model = xgb.XGBRegressor(**self.params)
        self.columns = feature_columns()

    def fit(self, feature_frame: pd.DataFrame) -> "XGBoostDemandForecaster":
        X = feature_frame[self.columns].astype(float)
        y = feature_frame["quantity"].astype(float)
        self.model.fit(X, y)
        return self

    def predict(self, feature_frame: pd.DataFrame) -> np.ndarray:
        X = feature_frame[self.columns].astype(float)
        return self.model.predict(X)


def expanding_window_splits(n_rows: int, min_train_size: int, n_splits: int) -> List[Tuple[range, range]]:
    """
    Walk-forward (expanding window) split indices: each fold trains on
    everything up to a point and validates on the single next row, per spec
    S18's walk-forward validation requirement.
    """
    if n_rows <= min_train_size:
        return []

    max_splits = n_rows - min_train_size
    n_splits = min(n_splits, max_splits)

    splits = []
    for i in range(n_splits):
        train_end = min_train_size + i
        splits.append((range(0, train_end), range(train_end, train_end + 1)))
    return splits


def walk_forward_validate(feature_frame: pd.DataFrame, min_train_size: int, n_splits: int, params: dict = None) -> dict:
    """
    Runs expanding-window walk-forward validation and returns predicted vs.
    actual pairs for the validation points, plus the full training series (for
    MASE scaling).
    """
    splits = expanding_window_splits(len(feature_frame), min_train_size, n_splits)

    predictions, actuals = [], []
    for train_idx, val_idx in splits:
        train_frame = feature_frame.iloc[list(train_idx)]
        val_frame = feature_frame.iloc[list(val_idx)]

        forecaster = XGBoostDemandForecaster(params)
        forecaster.fit(train_frame)
        predictions.extend(forecaster.predict(val_frame).tolist())
        actuals.extend(val_frame["quantity"].tolist())

    return {
        "predictions": predictions,
        "actuals": actuals,
        "n_folds": len(splits),
        "training_series": feature_frame["quantity"].tolist(),
    }

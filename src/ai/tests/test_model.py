import numpy as np
import pandas as pd

from src.ai.forecasting.features import build_feature_frame
from src.ai.forecasting.model import XGBoostDemandForecaster, expanding_window_splits, walk_forward_validate


def _synthetic_daily(n_days: int, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2026-01-01", periods=n_days)
    day_of_week = dates.dayofweek.to_numpy()
    weekly_pattern = np.where(np.isin(day_of_week, [4, 5]), 18.0, 10.0)  # higher on Fri/Sat
    noise = rng.normal(0, 1.5, size=n_days)
    quantity = np.clip(weekly_pattern + noise, 0, None)
    return pd.DataFrame({"date": dates, "quantity": quantity, "avg_unit_price": 20.0})


def test_expanding_window_splits_grow_and_stop_at_n_rows():
    splits = expanding_window_splits(n_rows=20, min_train_size=14, n_splits=6)
    assert len(splits) == 6
    for i, (train_idx, val_idx) in enumerate(splits):
        assert len(train_idx) == 14 + i
        assert list(val_idx) == [14 + i]


def test_expanding_window_splits_empty_when_not_enough_rows():
    assert expanding_window_splits(n_rows=10, min_train_size=14, n_splits=3) == []


def test_forecaster_fits_and_predicts_without_error():
    daily = _synthetic_daily(60)
    feature_frame = build_feature_frame(daily)
    forecaster = XGBoostDemandForecaster().fit(feature_frame)

    predictions = forecaster.predict(feature_frame)
    assert len(predictions) == len(feature_frame)
    assert np.all(np.isfinite(predictions))


def test_walk_forward_validate_learns_the_weekly_pattern():
    """
    On a clean synthetic weekly-seasonal series, walk-forward validation should
    produce low error - this is a correctness check, not just a no-crash check.
    """
    daily = _synthetic_daily(90)
    feature_frame = build_feature_frame(daily)

    result = walk_forward_validate(feature_frame, min_train_size=30, n_splits=10)

    assert result["n_folds"] == 10
    assert len(result["predictions"]) == 10
    assert len(result["actuals"]) == 10

    mae = float(np.mean(np.abs(np.array(result["actuals"]) - np.array(result["predictions"]))))
    assert mae < 4.0  # weekly pattern has ~8-unit swing; a working model should track it well within that


def test_walk_forward_validate_returns_empty_when_insufficient_rows():
    daily = _synthetic_daily(20)
    feature_frame = build_feature_frame(daily)  # ~6 usable rows after 14-day lag drop
    result = walk_forward_validate(feature_frame, min_train_size=14, n_splits=5)
    assert result["n_folds"] == 0
    assert result["predictions"] == []

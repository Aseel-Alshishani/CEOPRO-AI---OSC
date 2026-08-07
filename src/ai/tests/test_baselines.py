import numpy as np
import pandas as pd
import pytest

from src.ai.forecasting import baselines


@pytest.fixture
def history():
    return pd.Series([10, 12, 11, 13, 12, 14, 13, 10, 12, 11, 13, 12, 14, 13])


def test_naive_forecast_repeats_last_value(history):
    result = baselines.naive_forecast(history, horizon_days=5)
    assert len(result) == 5
    assert np.all(result == history.iloc[-1])


def test_seasonal_naive_forecast_repeats_last_season(history):
    result = baselines.seasonal_naive_forecast(history, horizon_days=7, season_length=7)
    np.testing.assert_array_equal(result, history.iloc[-7:].to_numpy())


def test_seasonal_naive_falls_back_when_not_enough_history():
    short_history = pd.Series([5, 6])
    result = baselines.seasonal_naive_forecast(short_history, horizon_days=3, season_length=7)
    assert np.all(result == short_history.iloc[-1])


def test_moving_average_forecast_uses_trailing_window(history):
    result = baselines.moving_average_forecast(history, horizon_days=3, window=7)
    expected = history.iloc[-7:].mean()
    assert np.allclose(result, expected)


def test_previous_period_forecast_reuses_prior_window(history):
    result = baselines.previous_period_forecast(history, horizon_days=4)
    np.testing.assert_array_equal(result, history.iloc[-4:].to_numpy())


def test_baseline_in_sample_predictions_length(history):
    preds = baselines.baseline_in_sample_predictions(history, "naive")
    assert len(preds) == len(history) - 1

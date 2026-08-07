import math

import pytest

from src.ai.forecasting import evaluation


def test_mae_zero_for_perfect_predictions():
    assert evaluation.mae([1, 2, 3], [1, 2, 3]) == 0.0


def test_mae_basic():
    assert evaluation.mae([1, 2, 3], [2, 2, 2]) == pytest.approx(2 / 3)


def test_rmse_basic():
    result = evaluation.rmse([0, 0], [3, 4])
    assert math.isclose(result, math.sqrt((9 + 16) / 2))


def test_mase_below_one_when_model_beats_naive():
    training_series = [10, 11, 9, 12, 10, 11, 9, 12]
    actual = [10, 11]
    good_predictions = [10, 11]  # perfect
    result = evaluation.mase(actual, good_predictions, training_series)
    assert result == 0.0


def test_mase_nan_when_training_series_too_short():
    result = evaluation.mase([1], [1], [5])
    assert math.isnan(result)


def test_compare_to_baselines_identifies_model_as_best():
    comparison = evaluation.compare_to_baselines(
        model_predictions=[10, 10, 10],
        actual=[10, 10, 10],
        baseline_forecasts={"naive": [5, 5, 5], "seasonal_naive": [7, 7, 7]},
    )
    assert comparison["best"] == "model"
    assert comparison["model_beats_all_baselines"] is True


def test_compare_to_baselines_identifies_baseline_as_best():
    comparison = evaluation.compare_to_baselines(
        model_predictions=[0, 0, 0],
        actual=[10, 10, 10],
        baseline_forecasts={"naive": [10, 10, 10]},
    )
    assert comparison["best"] == "naive"
    assert comparison["model_beats_all_baselines"] is False

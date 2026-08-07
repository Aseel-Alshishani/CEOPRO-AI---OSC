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


def test_pinball_loss_zero_for_perfect_quantile_prediction():
    assert evaluation.pinball_loss([10, 20, 30], [10, 20, 30], quantile=0.5) == 0.0


def test_pinball_loss_penalizes_under_prediction_more_at_high_quantile():
    # 90th percentile forecast that undershoots should cost more than one that overshoots
    under = evaluation.pinball_loss(actual=[100], predicted_quantile=[80], quantile=0.9)
    over = evaluation.pinball_loss(actual=[100], predicted_quantile=[120], quantile=0.9)
    assert under > over


def test_pinball_loss_penalizes_over_prediction_more_at_low_quantile():
    under = evaluation.pinball_loss(actual=[100], predicted_quantile=[80], quantile=0.1)
    over = evaluation.pinball_loss(actual=[100], predicted_quantile=[120], quantile=0.1)
    assert over > under


def test_pinball_loss_at_median_quantile_matches_half_mae():
    result = evaluation.pinball_loss(actual=[10, 20], predicted_quantile=[12, 18], quantile=0.5)
    assert result == pytest.approx(evaluation.mae([10, 20], [12, 18]) / 2)


def test_pinball_loss_rejects_invalid_quantile():
    with pytest.raises(ValueError):
        evaluation.pinball_loss([1], [1], quantile=1.5)


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

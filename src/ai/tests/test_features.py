import pandas as pd

from src.ai.forecasting.features import build_feature_frame, feature_columns


def _sample_daily(n_days: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=n_days),
            "quantity": [float(i % 10) for i in range(n_days)],
            "avg_unit_price": [15.0] * n_days,
        }
    )


def test_drops_rows_without_full_lag_history():
    daily = _sample_daily(20)
    result = build_feature_frame(daily)
    # first 14 rows can't have a full 14-day lag/rolling window
    assert len(result) == 20 - 14


def test_output_contains_all_expected_feature_columns():
    daily = _sample_daily(30)
    result = build_feature_frame(daily, current_price=9.99, current_stock=42)
    for column in feature_columns():
        assert column in result.columns
    assert (result["current_stock"] == 42).all()


def test_empty_input_returns_empty_frame():
    daily = _sample_daily(5)  # fewer than required lag window
    result = build_feature_frame(daily)
    assert result.empty

import pandas as pd

from src.ai.forecasting import cold_start


def test_insufficient_data_reports_building_status():
    short_history = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=5), "quantity": [1, 2, 3, 4, 5]})
    result = cold_start.assess(short_history)
    assert result.sufficient is False
    assert result.confidence_status == "BUILDING"
    assert result.available_days == 5
    assert result.minimum_required == cold_start.MIN_HISTORY_DAYS


def test_sufficient_data_reports_ok_status():
    long_history = pd.DataFrame(
        {"date": pd.date_range("2026-01-01", periods=cold_start.MIN_HISTORY_DAYS), "quantity": range(cold_start.MIN_HISTORY_DAYS)}
    )
    result = cold_start.assess(long_history)
    assert result.sufficient is True
    assert result.confidence_status == "OK"

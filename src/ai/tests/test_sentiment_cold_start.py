from src.ai.sentiment import cold_start


def test_insufficient_sample_reports_low_sample_size():
    result = cold_start.assess(3)
    assert result.sufficient is False
    assert result.status == "LOW_SAMPLE_SIZE"
    assert result.analyzed_count == 3
    assert result.minimum_required == cold_start.MIN_SAMPLE_SIZE


def test_sufficient_sample_reports_ok_status():
    result = cold_start.assess(cold_start.MIN_SAMPLE_SIZE)
    assert result.sufficient is True
    assert result.status == "OK"


def test_zero_sample_is_insufficient():
    result = cold_start.assess(0)
    assert result.sufficient is False
    assert result.status == "LOW_SAMPLE_SIZE"

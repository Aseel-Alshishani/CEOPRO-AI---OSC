from unittest.mock import MagicMock

from src.ai.pricing import currency


def test_get_latest_rate_same_currency_is_identity_without_touching_db():
    """base == target should short-circuit to rate 1.0 without ever querying."""
    fake_conn = MagicMock()
    rate = currency.get_latest_rate(fake_conn, "JOD", "JOD")

    assert rate.rate == 1.0
    assert rate.source == "identity"
    fake_conn.cursor.assert_not_called()


def _mock_conn_returning(row):
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = row
    conn.cursor.return_value.__enter__.return_value = cursor
    return conn


def test_get_latest_rate_returns_none_when_no_rate_exists():
    conn = _mock_conn_returning(None)
    assert currency.get_latest_rate(conn, "SAR", "JOD") is None


def test_get_latest_rate_parses_row():
    import datetime

    conn = _mock_conn_returning((0.9500, datetime.date(2026, 8, 1), "central_bank_feed"))
    rate = currency.get_latest_rate(conn, "SAR", "JOD")

    assert rate.rate == 0.95
    assert rate.rate_date == datetime.date(2026, 8, 1)
    assert rate.source == "central_bank_feed"


def test_convert_returns_none_when_no_rate_available():
    conn = _mock_conn_returning(None)
    assert currency.convert(conn, 100.0, "EGP", "JOD") is None


def test_convert_computes_converted_amount_and_preserves_original():
    import datetime

    conn = _mock_conn_returning((0.9500, datetime.date(2026, 8, 1), "central_bank_feed"))
    result = currency.convert(conn, 100.0, "SAR", "JOD")

    assert result.original_amount == 100.0
    assert result.original_currency == "SAR"
    assert result.converted_amount == 95.0
    assert result.converted_currency == "JOD"
    assert result.rate == 0.95


def test_convert_same_currency_is_a_no_op():
    fake_conn = MagicMock()
    result = currency.convert(fake_conn, 50.0, "JOD", "JOD")

    assert result.converted_amount == 50.0
    assert result.rate == 1.0
    fake_conn.cursor.assert_not_called()

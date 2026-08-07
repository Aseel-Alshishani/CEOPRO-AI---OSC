from unittest.mock import MagicMock, patch

import pytest

from src.ai.pricing import pipeline


@pytest.fixture
def fake_conn():
    return MagicMock()


def _competitor_price(entry_id: str, competitor_id: str, price: float) -> dict:
    return {
        "price_entry_id": entry_id,
        "competitor_id": competitor_id,
        "product_name_captured": "Sunscreen SPF 50",
        "price_found": price,
        "currency": "JOD",
        "captured_at": None,
    }


def test_missing_product_raises(fake_conn):
    with patch.object(pipeline.data_access, "load_own_product", return_value=None):
        with pytest.raises(ValueError, match="No product found"):
            pipeline.run_price_recommendation(fake_conn, "tenant-1", "product-1")


def test_no_matched_competitors_records_unknown_evidence(fake_conn):
    own = {"product_name": "Sunscreen SPF 50", "current_price": 20.0, "currency": "JOD"}

    with patch.object(pipeline.data_access, "load_own_product", return_value=own), \
         patch.object(pipeline.data_access, "load_competitor_prices", return_value=[]), \
         patch.object(pipeline.evidence, "insert_evidence_record", return_value="evidence-1") as mock_evidence:
        result = pipeline.run_price_recommendation(fake_conn, "tenant-1", "product-1")

    assert result == {"status": "UNKNOWN", "evidence_id": "evidence-1"}
    assert mock_evidence.call_args.args[2] == "UNKNOWN"
    fake_conn.commit.assert_called_once()


def test_matched_competitors_produce_recommendation_and_outcome_row(fake_conn):
    own = {"product_name": "Sunscreen SPF 50", "current_price": 30.0, "currency": "JOD"}
    competitor_prices = [_competitor_price("p1", "c1", 18.0), _competitor_price("p2", "c2", 20.0)]

    with patch.object(pipeline.data_access, "load_own_product", return_value=own), \
         patch.object(pipeline.data_access, "load_competitor_prices", return_value=competitor_prices), \
         patch.object(pipeline.evidence, "insert_evidence_record", return_value="evidence-1") as mock_evidence, \
         patch.object(pipeline.evidence, "insert_recommendation_outcome", return_value="outcome-1") as mock_outcome:
        result = pipeline.run_price_recommendation(fake_conn, "tenant-1", "product-1")

    assert result["status"] == "OK"
    assert result["action"] == "lower"  # 30.0 is well above the ~19.0 market average
    assert result["evidence_id"] == "evidence-1"
    assert result["outcome_id"] == "outcome-1"
    assert mock_evidence.call_args.args[2] == "RECOMMENDATION"
    mock_outcome.assert_called_once_with(fake_conn, "evidence-1", "tenant-1")
    fake_conn.commit.assert_called_once()


def test_recommendation_respects_price_change_guardrail(fake_conn):
    own = {"product_name": "Sunscreen SPF 50", "current_price": 100.0, "currency": "JOD"}
    # market average ~10.0, a 90% drop - the guardrail (default 15%) must clamp this
    competitor_prices = [_competitor_price("p1", "c1", 10.0)]

    with patch.object(pipeline.data_access, "load_own_product", return_value=own), \
         patch.object(pipeline.data_access, "load_competitor_prices", return_value=competitor_prices), \
         patch.object(pipeline.evidence, "insert_evidence_record", return_value="evidence-1"), \
         patch.object(pipeline.evidence, "insert_recommendation_outcome", return_value="outcome-1"):
        result = pipeline.run_price_recommendation(fake_conn, "tenant-1", "product-1")

    assert result["guardrail_clamped"] is True
    assert result["suggested_price"] == 85.0  # 100 * (1 - 0.15)

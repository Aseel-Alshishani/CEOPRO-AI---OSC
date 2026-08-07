from unittest.mock import MagicMock, patch

import pytest

from src.ai.sentiment import pipeline
from src.ai.sentiment.model import SentimentPrediction


@pytest.fixture
def fake_conn():
    return MagicMock()


def _review(review_id: str, text: str = "Great product") -> dict:
    return {
        "review_id": review_id,
        "review_text": text,
        "subject_type": "PRODUCT",
        "product_id": "product-1",
        "competitor_id": None,
        "review_language": "en",
    }


def _prediction(label: str = "positive") -> SentimentPrediction:
    probs = {"positive": 0.1, "neutral": 0.1, "negative": 0.1}
    probs[label] = 0.8
    return SentimentPrediction(
        label=label,
        positive_probability=probs["positive"],
        neutral_probability=probs["neutral"],
        negative_probability=probs["negative"],
        confidence=0.8,
        model_version="fake-model",
    )


def test_classify_and_store_reviews_no_unanalyzed_reviews(fake_conn):
    with patch.object(pipeline.data_access, "load_unanalyzed_reviews", return_value=[]):
        result = pipeline.classify_and_store_reviews(fake_conn, "tenant-1")

    assert result == {"status": "OK", "analyzed_count": 0}
    fake_conn.commit.assert_not_called()


def test_classify_and_store_reviews_writes_one_sentiment_result_per_review(fake_conn):
    reviews = [_review("r1"), _review("r2")]
    predictions = [_prediction("positive"), _prediction("negative")]

    with patch.object(pipeline.data_access, "load_unanalyzed_reviews", return_value=reviews), \
         patch.object(pipeline.model, "classify", return_value=predictions), \
         patch.object(pipeline.evidence, "insert_sentiment_result", return_value="sentiment-1") as mock_insert:
        result = pipeline.classify_and_store_reviews(fake_conn, "tenant-1")

    assert result == {"status": "OK", "analyzed_count": 2}
    assert mock_insert.call_count == 2
    mock_insert.assert_any_call(fake_conn, "r1", "tenant-1", "positive", 0.8, 0.1, 0.1, 0.8, "fake-model")
    fake_conn.commit.assert_called_once()


def test_summary_with_no_analyzed_reviews_records_unknown_evidence(fake_conn):
    aggregate = {"analyzed_count": 0, "label_counts": {"positive": 0, "neutral": 0, "negative": 0}, "sentiment_score": None}

    with patch.object(pipeline.data_access, "load_aggregate_sentiment", return_value=aggregate), \
         patch.object(pipeline.evidence, "insert_evidence_record", return_value="evidence-1") as mock_evidence:
        result = pipeline.get_subject_sentiment_summary(fake_conn, "tenant-1", "PRODUCT", "product-1")

    assert result["status"] == "UNKNOWN"
    assert mock_evidence.call_args.args[2] == "UNKNOWN"
    fake_conn.commit.assert_called_once()


def test_summary_below_min_sample_size_flags_low_sample_size(fake_conn):
    aggregate = {
        "analyzed_count": 2,
        "label_counts": {"positive": 1, "neutral": 0, "negative": 1},
        "sentiment_score": 0.0,
    }

    with patch.object(pipeline.data_access, "load_aggregate_sentiment", return_value=aggregate), \
         patch.object(pipeline.evidence, "insert_evidence_record", return_value="evidence-1") as mock_evidence:
        result = pipeline.get_subject_sentiment_summary(fake_conn, "tenant-1", "PRODUCT", "product-1")

    assert result["status"] == "OK"
    assert result["sample_size"]["status"] == "LOW_SAMPLE_SIZE"
    explanation = mock_evidence.call_args.args[6]
    assert "LOW SAMPLE SIZE" in explanation
    assert mock_evidence.call_args.args[5] == pipeline.CONFIDENCE_LOW_SAMPLE


def test_summary_with_sufficient_sample_reports_ok(fake_conn):
    n = pipeline.cold_start.MIN_SAMPLE_SIZE
    aggregate = {
        "analyzed_count": n,
        "label_counts": {"positive": n, "neutral": 0, "negative": 0},
        "sentiment_score": 0.9,
    }

    with patch.object(pipeline.data_access, "load_aggregate_sentiment", return_value=aggregate), \
         patch.object(pipeline.evidence, "insert_evidence_record", return_value="evidence-1") as mock_evidence:
        result = pipeline.get_subject_sentiment_summary(fake_conn, "tenant-1", "PRODUCT", "product-1")

    assert result["status"] == "OK"
    assert result["sample_size"]["status"] == "OK"
    assert result["sentiment_score"] == 0.9
    assert mock_evidence.call_args.args[2] == "FACT"
    assert mock_evidence.call_args.args[5] == pipeline.CONFIDENCE_SUFFICIENT_SAMPLE

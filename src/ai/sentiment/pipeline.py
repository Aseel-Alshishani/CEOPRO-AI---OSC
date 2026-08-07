"""
CEOPRO AI - Sentiment Analysis Pipeline (spec S16, S22, S23).
Two entry points:
  - classify_and_store_reviews: runs the classifier over unanalyzed reviews
    and writes sentiment_results rows. Bulk/background labeling, not itself
    a user-facing conclusion, so it writes no evidence_records (mirrors how
    src/ai/rag/embeddings.py's embedding step is infrastructure, not an
    evidence-bearing output).
  - get_subject_sentiment_summary: aggregates already-analyzed sentiment for
    one subject (a product, a competitor, or the business overall), applies
    the LOW SAMPLE SIZE policy (spec S16), and is the only function here
    that writes to evidence_records - this is the user-facing conclusion.
"""

import logging
from typing import Optional

from src.ai.sentiment import cold_start, data_access, evidence, model

logger = logging.getLogger("CEOPRO_AI_SENTIMENT_PIPELINE")

SOURCE_MODULE = "ai.sentiment"

# Aggregate FACT evidence isn't a per-observation model score, so this
# reflects sample-size trust in the aggregate rather than any single
# prediction's probability - deliberately coarse, same style as
# src/ai/forecasting/pipeline.py's baseline-path confidence assignment.
CONFIDENCE_SUFFICIENT_SAMPLE = 0.8
CONFIDENCE_LOW_SAMPLE = 0.3


def classify_and_store_reviews(conn, tenant_id: str, batch_size: int = 100) -> dict:
    reviews = data_access.load_unanalyzed_reviews(conn, tenant_id, limit=batch_size)
    if not reviews:
        return {"status": "OK", "analyzed_count": 0}

    predictions = model.classify([r["review_text"] for r in reviews])

    for review, prediction in zip(reviews, predictions):
        evidence.insert_sentiment_result(
            conn,
            review["review_id"],
            tenant_id,
            prediction.label,
            prediction.positive_probability,
            prediction.neutral_probability,
            prediction.negative_probability,
            prediction.confidence,
            prediction.model_version,
        )
    conn.commit()

    logger.info(f"Classified {len(reviews)} reviews for tenant={tenant_id}")
    return {"status": "OK", "analyzed_count": len(reviews)}


def get_subject_sentiment_summary(
    conn,
    tenant_id: str,
    subject_type: str,
    subject_id: Optional[str] = None,
    country_context: Optional[str] = None,
) -> dict:
    aggregate = data_access.load_aggregate_sentiment(conn, tenant_id, subject_type, subject_id)
    sample_assessment = cold_start.assess(aggregate["analyzed_count"])

    if aggregate["analyzed_count"] == 0:
        explanation = f"No analyzed reviews are available yet for this {subject_type.lower()}."
        evidence_id = evidence.insert_evidence_record(
            conn,
            tenant_id,
            "UNKNOWN",
            SOURCE_MODULE,
            {"subject_type": subject_type, "subject_id": subject_id},
            None,
            explanation,
            None,
            country_context,
        )
        conn.commit()
        logger.info(f"No analyzed reviews for tenant={tenant_id} subject={subject_type}/{subject_id}")
        return {"status": "UNKNOWN", "evidence_id": evidence_id, "sample_size": sample_assessment.as_dict()}

    if sample_assessment.sufficient:
        confidence_score = CONFIDENCE_SUFFICIENT_SAMPLE
        explanation = (
            f"Aggregated from {aggregate['analyzed_count']} analyzed reviews: "
            f"{aggregate['label_counts']['positive']} positive, {aggregate['label_counts']['neutral']} neutral, "
            f"{aggregate['label_counts']['negative']} negative (sentiment_score={aggregate['sentiment_score']})."
        )
    else:
        confidence_score = CONFIDENCE_LOW_SAMPLE
        explanation = (
            f"LOW SAMPLE SIZE: only {aggregate['analyzed_count']} analyzed review(s) available "
            f"(minimum {sample_assessment.minimum_required} required) - this result should not be treated as a "
            f"reliable market conclusion."
        )

    evidence_id = evidence.insert_evidence_record(
        conn,
        tenant_id,
        "FACT",
        SOURCE_MODULE,
        {
            "subject_type": subject_type,
            "subject_id": subject_id,
            "analyzed_count": aggregate["analyzed_count"],
            "sentiment_score": aggregate["sentiment_score"],
        },
        confidence_score,
        explanation,
        None,
        country_context,
    )
    conn.commit()

    logger.info(
        f"Sentiment summary written tenant={tenant_id} subject={subject_type}/{subject_id} "
        f"status={sample_assessment.status} evidence_id={evidence_id}"
    )

    return {
        "status": "OK",
        "evidence_id": evidence_id,
        "sentiment_score": aggregate["sentiment_score"],
        "label_counts": aggregate["label_counts"],
        "sample_size": sample_assessment.as_dict(),
    }

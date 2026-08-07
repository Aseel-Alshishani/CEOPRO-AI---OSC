"""
CEOPRO AI - Sentiment Analysis Evidence Writers.
Writes only to tables this track owns per DATA_OWNERSHIP_AND_CONTRACTS.md:
sentiment_results, evidence_records. Never writes to reviews (owned by the
review-collection service).
"""

import json
from typing import Optional


def insert_sentiment_result(
    conn,
    review_id: str,
    tenant_id: str,
    label: str,
    positive_probability: float,
    neutral_probability: float,
    negative_probability: float,
    confidence: float,
    model_version: str,
) -> str:
    query = """
        INSERT INTO sentiment_results
            (review_id, tenant_id, label, positive_probability, neutral_probability,
             negative_probability, confidence, model_version)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING sentiment_id;
    """
    with conn.cursor() as cursor:
        cursor.execute(
            query,
            (
                review_id,
                tenant_id,
                label,
                positive_probability,
                neutral_probability,
                negative_probability,
                confidence,
                model_version,
            ),
        )
        sentiment_id = cursor.fetchone()[0]
    return str(sentiment_id)


def insert_evidence_record(
    conn,
    tenant_id: str,
    category: str,
    source_module: str,
    source_record_ids: dict,
    confidence_score: Optional[float],
    explanation_text: str,
    model_version: Optional[str],
    country_context: Optional[str] = None,
) -> str:
    query = """
        INSERT INTO evidence_records
            (tenant_id, category, source_module, source_record_ids,
             confidence_score, explanation_text, model_version, country_context)
        VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s)
        RETURNING evidence_id;
    """
    with conn.cursor() as cursor:
        cursor.execute(
            query,
            (
                tenant_id,
                category,
                source_module,
                json.dumps(source_record_ids),
                confidence_score,
                explanation_text,
                model_version,
                country_context,
            ),
        )
        evidence_id = cursor.fetchone()[0]
    return str(evidence_id)

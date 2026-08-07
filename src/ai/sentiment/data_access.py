"""
CEOPRO AI - Sentiment Analysis Data Access.
Reads reviews - owned by the review-collection service per
DATA_OWNERSHIP_AND_CONTRACTS.md, this module only reads from it. Writes
only to sentiment_results/evidence_records, this track's own tables
(handled in evidence.py).
"""

from typing import Optional

import psycopg2


def load_unanalyzed_reviews(conn: "psycopg2.extensions.connection", tenant_id: str, limit: int = 100) -> list:
    """
    Reviews with no matching sentiment_results row yet, restricted to
    ALLOWED-source reviews with non-empty text - a RESTRICTED/BLOCKED review
    (spec S13's Collection Policy Engine) shouldn't silently feed a model.
    """
    query = """
        SELECT r.review_id, r.review_text, r.subject_type, r.product_id, r.competitor_id, r.review_language
        FROM reviews r
        LEFT JOIN sentiment_results sr ON sr.review_id = r.review_id
        WHERE r.tenant_id = %s
          AND sr.sentiment_id IS NULL
          AND r.source_status = 'ALLOWED'
          AND r.review_text IS NOT NULL
          AND length(trim(r.review_text)) > 0
        ORDER BY r.collected_at
        LIMIT %s;
    """
    with conn.cursor() as cursor:
        cursor.execute(query, (tenant_id, limit))
        rows = cursor.fetchall()

    return [
        {
            "review_id": str(row[0]),
            "review_text": row[1],
            "subject_type": row[2],
            "product_id": str(row[3]) if row[3] else None,
            "competitor_id": str(row[4]) if row[4] else None,
            "review_language": row[5],
        }
        for row in rows
    ]


def load_aggregate_sentiment(
    conn: "psycopg2.extensions.connection", tenant_id: str, subject_type: str, subject_id: Optional[str] = None
) -> dict:
    """
    Aggregates already-analyzed sentiment_results for one subject: a
    label -> count breakdown plus the continuous sentiment score spec S16
    allows (avg(positive_probability) - avg(negative_probability), weighted
    by each label group's count) across all analyzed reviews for that
    subject. subject_id is ignored (and must be None) for BUSINESS, since
    that reads overall business-level reviews.
    """
    if subject_type == "BUSINESS":
        subject_filter = ""
        params = [tenant_id, subject_type]
    elif subject_type == "PRODUCT":
        subject_filter = "AND r.product_id = %s"
        params = [tenant_id, subject_type, subject_id]
    elif subject_type == "COMPETITOR":
        subject_filter = "AND r.competitor_id = %s"
        params = [tenant_id, subject_type, subject_id]
    else:
        raise ValueError(f"Unknown subject_type '{subject_type}'")

    query = f"""
        SELECT sr.label, COUNT(*), AVG(sr.positive_probability), AVG(sr.negative_probability)
        FROM reviews r
        JOIN sentiment_results sr ON sr.review_id = r.review_id
        WHERE r.tenant_id = %s AND r.subject_type = %s {subject_filter}
        GROUP BY sr.label;
    """
    with conn.cursor() as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()

    label_counts = {"positive": 0, "neutral": 0, "negative": 0}
    weighted_pos_sum = 0.0
    weighted_neg_sum = 0.0
    total = 0
    for label, count, avg_pos, avg_neg in rows:
        label_counts[label] = int(count)
        total += int(count)
        weighted_pos_sum += float(avg_pos) * int(count)
        weighted_neg_sum += float(avg_neg) * int(count)

    sentiment_score = round((weighted_pos_sum - weighted_neg_sum) / total, 4) if total else None

    return {
        "analyzed_count": total,
        "label_counts": label_counts,
        "sentiment_score": sentiment_score,
    }

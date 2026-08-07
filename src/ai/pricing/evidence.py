"""
CEOPRO AI - Price Recommendation Evidence Writers.
Reuses insert_evidence_record from forecasting.evidence rather than
duplicating it - evidence_records is a shared, cross-module table (spec S22:
"Confidence must not be implemented independently by every AI module. The
system must have one consistent evidence architecture"), and the function is
already generic (not forecast-specific). Only recommendation_outcomes writing
is new here, since forecasting doesn't need it.
"""

from src.ai.forecasting.evidence import insert_evidence_record  # noqa: F401 (re-exported for pricing callers)


def insert_recommendation_outcome(conn, evidence_id: str, tenant_id: str) -> str:
    """
    Spec S24: "Every recommendation must create a RECOMMENDATION_OUTCOME
    record." Created at recommendation time with action_taken left to the
    table's default ('ignored') - it's updated later when a human actually
    acts on the recommendation, which is outside this module's scope.
    """
    query = """
        INSERT INTO recommendation_outcomes (evidence_id, tenant_id)
        VALUES (%s, %s)
        RETURNING outcome_id;
    """
    with conn.cursor() as cursor:
        cursor.execute(query, (evidence_id, tenant_id))
        outcome_id = cursor.fetchone()[0]
    return str(outcome_id)

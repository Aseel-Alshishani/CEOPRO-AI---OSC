"""
CEOPRO AI - Price Recommendation Pipeline (spec S19, S20, S22, S23, S24).
Orchestrates: load own product -> load same-currency competitor prices ->
name-match -> rule-based recommendation -> price-change guardrail -> persist
evidence + recommendation_outcomes. Only module here that writes to the
database.
"""

import logging

from src.ai.pricing import data_access, evidence, guardrails, matching, recommendation

logger = logging.getLogger("CEOPRO_AI_PRICING_PIPELINE")

SOURCE_MODULE = "ai.pricing"


def run_price_recommendation(conn, tenant_id: str, product_id: str) -> dict:
    own = data_access.load_own_product(conn, tenant_id, product_id)
    if own is None:
        raise ValueError(f"No product found for tenant={tenant_id} product_id={product_id}")

    competitor_prices = data_access.load_competitor_prices(conn, tenant_id, own["currency"])
    matched = matching.match_competitor_records(own["product_name"], competitor_prices)

    if not matched:
        explanation = (
            f"No competitor price data matched '{own['product_name']}' in {own['currency']} "
            f"within the freshness/allow-list filters."
        )
        evidence_id = evidence.insert_evidence_record(
            conn, tenant_id, "UNKNOWN", SOURCE_MODULE, {"product_id": product_id}, None, explanation, None
        )
        conn.commit()
        logger.info(f"No matched competitors for tenant={tenant_id} product={product_id}; evidence={evidence_id}")
        return {"status": "UNKNOWN", "evidence_id": evidence_id}

    rec = recommendation.build_recommendation(own["current_price"], matched)
    guardrail = guardrails.apply_price_change_guardrail(own["current_price"], rec.raw_suggested_price)

    explanation = rec.explanation
    if guardrail.clamped:
        explanation += (
            f" Suggested price {rec.raw_suggested_price:.2f} was outside the "
            f"{guardrail.max_change_pct:.0%} price-change guardrail and was capped to "
            f"{guardrail.suggested_price:.2f}."
        )

    evidence_id = evidence.insert_evidence_record(
        conn,
        tenant_id,
        "RECOMMENDATION",
        SOURCE_MODULE,
        {"product_id": product_id, "competitor_price_entry_ids": rec.source_record_ids},
        rec.confidence_score,
        explanation,
        None,
    )
    outcome_id = evidence.insert_recommendation_outcome(conn, evidence_id, tenant_id)
    conn.commit()

    logger.info(
        f"Price recommendation written tenant={tenant_id} product={product_id} "
        f"action={rec.action} evidence_id={evidence_id}"
    )

    return {
        "status": "OK",
        "action": rec.action,
        "current_price": own["current_price"],
        "suggested_price": guardrail.suggested_price,
        "guardrail_clamped": guardrail.clamped,
        "matched_competitor_count": rec.matched_competitor_count,
        "confidence_score": rec.confidence_score,
        "evidence_id": evidence_id,
        "outcome_id": outcome_id,
    }

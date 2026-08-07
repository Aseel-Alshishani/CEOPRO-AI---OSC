"""
CEOPRO AI - Competitor Product Matching (spec S19, S37).
competitor_prices.product_name_captured is free text (no product_id FK), so
matching to our own catalog is name-similarity based, not a join. Pure
function - no I/O - independently unit-testable.
"""

import os
from difflib import SequenceMatcher
from typing import List

DEFAULT_MATCH_THRESHOLD = float(os.getenv("PRICING_MATCH_THRESHOLD", "0.82"))


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.strip().lower(), b.strip().lower()).ratio()


def match_competitor_records(product_name: str, competitor_records: List[dict], threshold: float = None) -> List[dict]:
    """
    Returns the subset of competitor_records whose product_name_captured is
    similar enough to `product_name` to be considered the same product.
    Deliberately conservative (spec S37: "Cold-start handling ... Product
    Matching: Use rules and fuzzy matching with more manual confirmation") -
    a high default threshold trades recall for not silently comparing prices
    of different products.
    """
    threshold = DEFAULT_MATCH_THRESHOLD if threshold is None else threshold

    matched = []
    for record in competitor_records:
        score = similarity(product_name, record["product_name_captured"])
        if score >= threshold:
            matched.append({**record, "match_score": score})

    return sorted(matched, key=lambda r: r["match_score"], reverse=True)

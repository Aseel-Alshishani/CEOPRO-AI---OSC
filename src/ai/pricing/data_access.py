"""
CEOPRO AI - Price Intelligence Data Access.
Reads own product price and competitor price records. Read-only against
tables owned by other services/teams (products, competitors, competitor_prices
- the latter per DATA_OWNERSHIP_AND_CONTRACTS.md is written by the "AI Market
Scraper Service", a separate service this module only reads from).
"""

import os
from typing import Optional

# Stale competitor price data is worse than none - an old price silently
# treated as current would violate spec S19's "Date of collection" requirement.
MAX_PRICE_AGE_DAYS = int(os.getenv("PRICING_MAX_PRICE_AGE_DAYS", "30"))


def load_own_product(conn, tenant_id: str, product_id: str) -> Optional[dict]:
    query = """
        SELECT product_name, current_price, currency
        FROM products
        WHERE tenant_id = %s AND product_id = %s;
    """
    with conn.cursor() as cursor:
        cursor.execute(query, (tenant_id, product_id))
        row = cursor.fetchone()

    if not row:
        return None

    return {"product_name": row[0], "current_price": float(row[1]), "currency": row[2]}


def load_competitor_prices(conn, tenant_id: str, currency: str, max_age_days: int = None) -> list:
    """
    Only same-currency records are returned - cross-currency comparison needs
    currency_rates (spec S9), which doesn't exist yet (PENDING_ACTIONS.md #3).
    Only ALLOWED-source, exact-data records within the freshness window are
    returned, per the Collection Policy Engine (spec S13) and S19's
    "Date of collection" requirement.
    """
    max_age_days = MAX_PRICE_AGE_DAYS if max_age_days is None else max_age_days

    query = """
        SELECT price_entry_id, competitor_id, product_name_captured, price_found, currency, captured_at
        FROM competitor_prices
        WHERE tenant_id = %s
          AND currency = %s
          AND is_exact_data = TRUE
          AND source_status = 'ALLOWED'
          AND captured_at >= NOW() - (%s || ' days')::interval;
    """
    with conn.cursor() as cursor:
        cursor.execute(query, (tenant_id, currency, str(max_age_days)))
        rows = cursor.fetchall()

    return [
        {
            "price_entry_id": str(row[0]),
            "competitor_id": str(row[1]),
            "product_name_captured": row[2],
            "price_found": float(row[3]),
            "currency": row[4],
            "captured_at": row[5],
        }
        for row in rows
    ]

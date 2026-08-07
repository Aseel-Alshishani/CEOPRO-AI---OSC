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
        WHERE tenant_id = %s AND product_id = %s AND deleted_at IS NULL;
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
    "Date of collection" requirement. Also excludes prices captured against a
    competitor since deactivated (competitors.is_active) - a stale price from
    a competitor the tenant has since marked inactive/removed shouldn't
    influence a live recommendation.
    """
    max_age_days = MAX_PRICE_AGE_DAYS if max_age_days is None else max_age_days

    query = """
        SELECT cp.price_entry_id, cp.competitor_id, cp.product_name_captured, cp.price_found, cp.currency, cp.captured_at
        FROM competitor_prices cp
        JOIN competitors c ON c.competitor_id = cp.competitor_id
        WHERE cp.tenant_id = %s
          AND cp.currency = %s
          AND cp.is_exact_data = TRUE
          AND cp.source_status = 'ALLOWED'
          AND c.is_active = TRUE
          AND cp.captured_at >= NOW() - (%s || ' days')::interval;
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


def load_cross_currency_competitor_prices(conn, tenant_id: str, exclude_currency: str, max_age_days: int = None) -> list:
    """
    Same filters as load_competitor_prices, but for every OTHER currency -
    i.e. candidates for cross-country reference (spec S19's "CROSS-COUNTRY
    COMPARISON"), never blended into the same-currency "LOCAL MARKET
    COMPARISON" set load_competitor_prices returns.
    """
    max_age_days = MAX_PRICE_AGE_DAYS if max_age_days is None else max_age_days

    query = """
        SELECT cp.price_entry_id, cp.competitor_id, cp.product_name_captured, cp.price_found, cp.currency, cp.captured_at
        FROM competitor_prices cp
        JOIN competitors c ON c.competitor_id = cp.competitor_id
        WHERE cp.tenant_id = %s
          AND cp.currency != %s
          AND cp.is_exact_data = TRUE
          AND cp.source_status = 'ALLOWED'
          AND c.is_active = TRUE
          AND cp.captured_at >= NOW() - (%s || ' days')::interval;
    """
    with conn.cursor() as cursor:
        cursor.execute(query, (tenant_id, exclude_currency, str(max_age_days)))
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

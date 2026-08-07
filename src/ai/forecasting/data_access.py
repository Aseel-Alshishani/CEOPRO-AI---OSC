"""
CEOPRO AI - Demand Forecasting Data Access.
Reads daily aggregated demand history and product context. Read-only against
tables owned by other services (transactions, products, inventory); this module
never writes outside forecasting's own tables (handled in evidence.py).
"""

from typing import Optional

import pandas as pd
import psycopg2


def load_daily_demand(conn: "psycopg2.extensions.connection", tenant_id: str, product_id: str) -> pd.DataFrame:
    """
    Returns a daily-indexed DataFrame with columns [date, quantity, avg_unit_price],
    aggregated from transactions. Days with zero sales are filled with quantity=0
    so the series has no implicit gaps (required for lag/rolling features and for
    walk-forward validation to see a true daily cadence).
    """
    query = """
        SELECT
            transaction_date::date AS sale_date,
            SUM(quantity_sold) AS quantity,
            AVG(unit_price) AS avg_unit_price
        FROM transactions
        WHERE tenant_id = %s AND product_id = %s
        GROUP BY transaction_date::date
        ORDER BY sale_date;
    """
    with conn.cursor() as cursor:
        cursor.execute(query, (tenant_id, product_id))
        rows = cursor.fetchall()

    if not rows:
        return pd.DataFrame(columns=["date", "quantity", "avg_unit_price"])

    raw = pd.DataFrame(rows, columns=["date", "quantity", "avg_unit_price"])
    raw["date"] = pd.to_datetime(raw["date"])

    full_index = pd.date_range(start=raw["date"].min(), end=raw["date"].max(), freq="D")
    daily = raw.set_index("date").reindex(full_index)
    daily.index.name = "date"

    daily["quantity"] = daily["quantity"].fillna(0.0)
    daily["avg_unit_price"] = daily["avg_unit_price"].ffill().bfill()

    return daily.reset_index()


def load_product_context(conn: "psycopg2.extensions.connection", tenant_id: str, product_id: str) -> Optional[dict]:
    """
    Returns static product/inventory context used as constant features.
    Inventory only tracks current_stock (no history), so this is necessarily a
    snapshot, not a time-varying signal.
    """
    query = """
        SELECT p.current_price, p.category, i.current_stock
        FROM products p
        LEFT JOIN inventory i ON i.product_id = p.product_id
        WHERE p.tenant_id = %s AND p.product_id = %s AND p.deleted_at IS NULL;
    """
    with conn.cursor() as cursor:
        cursor.execute(query, (tenant_id, product_id))
        row = cursor.fetchone()

    if not row:
        return None

    return {
        "current_price": float(row[0]) if row[0] is not None else None,
        "category": row[1],
        "current_stock": int(row[2]) if row[2] is not None else None,
    }

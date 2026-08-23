"""
CEOPRO AI - Demand Forecasting Data Access.
Reads daily aggregated demand history and product context. Read-only against
tables owned by other services (invoices, invoice_items, products, inventory);
this module never writes outside forecasting's own tables (handled in evidence.py).

SCHEMA UPDATE: the standalone `transactions` table no longer exists. Sales
history now lives in `invoices` (has the date, via issue_date) joined with
`invoice_items` (has product_id/quantity/unit_price). CANCELLED invoices are
excluded from demand history since they don't represent fulfilled demand -
this is an assumption, not something the schema states explicitly.
"""

from typing import Optional

import pandas as pd
import psycopg2


def load_daily_demand(conn: "psycopg2.extensions.connection", tenant_id: str, product_id: str) -> pd.DataFrame:
    """
    Returns a daily-indexed DataFrame with columns [date, quantity, avg_unit_price],
    aggregated from invoices/invoice_items. Days with zero sales are filled with
    quantity=0 so the series has no implicit gaps (required for lag/rolling
    features and for walk-forward validation to see a true daily cadence).
    """
    query = """
        SELECT
            i.issue_date::date AS sale_date,
            SUM(ii.quantity) AS quantity,
            AVG(ii.unit_price) AS avg_unit_price
        FROM invoice_items ii
        JOIN invoices i ON i.tenant_id = ii.tenant_id AND i.invoice_id = ii.invoice_id
        WHERE ii.tenant_id = %s AND ii.product_id = %s AND i.payment_status != 'CANCELLED'
        GROUP BY i.issue_date::date
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
    Inventory only tracks stock_quantity (no history), so this is necessarily a
    snapshot, not a time-varying signal.

    NOTE: products.category is JSONB (multi-language, e.g. {"en": ..., "ar": ...})
    per the current schema, not a plain string - it's passed through as-is
    since forecasting doesn't currently feature-engineer on it.
    """
    query = """
        SELECT p.current_price, p.category, i.stock_quantity
        FROM products p
        LEFT JOIN inventory i ON i.tenant_id = p.tenant_id AND i.product_id = p.product_id
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

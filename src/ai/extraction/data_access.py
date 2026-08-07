"""
CEOPRO AI - Extraction Catalog Data Access.
Reads known product/competitor names to match against (read-only, existing
tables). Nothing is written here - there is no `extracted_entity` table yet
(PENDING_ACTIONS.md #4), so extraction results have nowhere to persist to.
"""

from typing import List


def load_known_product_names(conn, tenant_id: str) -> List[str]:
    with conn.cursor() as cursor:
        cursor.execute("SELECT product_name FROM products WHERE tenant_id = %s;", (tenant_id,))
        return [row[0] for row in cursor.fetchall()]


def load_known_competitor_names(conn, tenant_id: str) -> List[str]:
    with conn.cursor() as cursor:
        cursor.execute("SELECT competitor_name FROM competitors WHERE tenant_id = %s;", (tenant_id,))
        return [row[0] for row in cursor.fetchall()]

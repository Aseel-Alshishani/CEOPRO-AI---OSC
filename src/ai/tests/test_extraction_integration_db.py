"""
Integration test for extraction/data_access.py against a real PostgreSQL
instance running the actual init_schema.sql. Same convention as the other
*_integration_db.py files: skipped unless AI_TEST_DATABASE_URL is set.
"""

import os
import uuid

import psycopg2
import pytest

from src.ai.extraction import data_access

DATABASE_URL = os.getenv("AI_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="AI_TEST_DATABASE_URL not set - skipping live-DB integration test")


@pytest.fixture
def conn():
    connection = psycopg2.connect(DATABASE_URL)
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()


@pytest.fixture
def seeded_tenant(conn):
    tenant_id = str(uuid.uuid4())
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO companies (tenant_id, business_name, country_code, primary_currency)
            VALUES (%s, 'Extraction Test Co', 'JO', 'JOD');
            """,
            (tenant_id,),
        )
        cursor.execute(
            """
            INSERT INTO products (product_id, tenant_id, product_name, current_price, currency)
            VALUES (%s, %s, 'Sunscreen SPF 50', 18.00, 'JOD');
            """,
            (str(uuid.uuid4()), tenant_id),
        )
        cursor.execute(
            """
            INSERT INTO competitors (competitor_id, tenant_id, competitor_name, country_code)
            VALUES (%s, %s, 'Rival Pharmacy', 'JO');
            """,
            (str(uuid.uuid4()), tenant_id),
        )
    conn.commit()
    return tenant_id


def test_load_known_product_names(conn, seeded_tenant):
    names = data_access.load_known_product_names(conn, seeded_tenant)
    assert names == ["Sunscreen SPF 50"]


def test_load_known_competitor_names(conn, seeded_tenant):
    names = data_access.load_known_competitor_names(conn, seeded_tenant)
    assert names == ["Rival Pharmacy"]


def test_load_known_names_empty_for_tenant_with_no_products(conn):
    other_tenant_id = str(uuid.uuid4())
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO companies (tenant_id, business_name, country_code, primary_currency)
            VALUES (%s, 'Empty Catalog Co', 'JO', 'JOD');
            """,
            (other_tenant_id,),
        )
    conn.commit()
    assert data_access.load_known_product_names(conn, other_tenant_id) == []
    assert data_access.load_known_competitor_names(conn, other_tenant_id) == []

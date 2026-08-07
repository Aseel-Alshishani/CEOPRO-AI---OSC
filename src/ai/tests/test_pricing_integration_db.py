"""
Integration test for the pricing pipeline against a real PostgreSQL instance
running the actual init_schema.sql. Same convention as test_integration_db.py:
skipped unless AI_TEST_DATABASE_URL is set.
"""

import os
import uuid
from datetime import date, datetime, timezone

import psycopg2
import pytest

from src.ai.pricing import currency, data_access, pipeline

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
def seeded_tenant_product_and_competitor(conn):
    tenant_id = str(uuid.uuid4())
    product_id = str(uuid.uuid4())
    competitor_id = str(uuid.uuid4())

    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO companies (tenant_id, business_name, country_code, primary_currency)
            VALUES (%s, 'Pricing Test Co', 'JO', 'JOD');
            """,
            (tenant_id,),
        )
        cursor.execute(
            """
            INSERT INTO products (product_id, tenant_id, product_name, current_price, currency)
            VALUES (%s, %s, 'Sunscreen SPF 50', 30.00, 'JOD');
            """,
            (product_id, tenant_id),
        )
        cursor.execute(
            """
            INSERT INTO competitors (competitor_id, tenant_id, competitor_name, country_code)
            VALUES (%s, %s, 'Rival Pharmacy', 'JO');
            """,
            (competitor_id, tenant_id),
        )
        for price in (18.00, 19.50, 20.00):
            cursor.execute(
                """
                INSERT INTO competitor_prices
                    (tenant_id, competitor_id, product_name_captured, price_found, currency,
                     is_exact_data, collection_method, source_status, captured_at)
                VALUES (%s, %s, 'Sunscreen SPF 50', %s, 'JOD', TRUE, 'MANUAL', 'ALLOWED', %s);
                """,
                (tenant_id, competitor_id, price, datetime.now(timezone.utc)),
            )
    conn.commit()

    return tenant_id, product_id, competitor_id


def test_load_competitor_prices_reads_seeded_rows(conn, seeded_tenant_product_and_competitor):
    tenant_id, product_id, _ = seeded_tenant_product_and_competitor
    records = data_access.load_competitor_prices(conn, tenant_id, "JOD")
    assert len(records) == 3
    assert {r["price_found"] for r in records} == {18.00, 19.50, 20.00}


def test_load_competitor_prices_excludes_wrong_currency(conn, seeded_tenant_product_and_competitor):
    tenant_id, product_id, _ = seeded_tenant_product_and_competitor
    records = data_access.load_competitor_prices(conn, tenant_id, "USD")
    assert records == []


def test_load_own_product_excludes_soft_deleted_product(conn, seeded_tenant_product_and_competitor):
    """products.deleted_at (added after this module was first built) must be respected."""
    tenant_id, product_id, _ = seeded_tenant_product_and_competitor
    with conn.cursor() as cursor:
        cursor.execute("UPDATE products SET deleted_at = NOW() WHERE product_id = %s;", (product_id,))
    conn.commit()

    assert data_access.load_own_product(conn, tenant_id, product_id) is None


def test_load_competitor_prices_excludes_deactivated_competitor(conn, seeded_tenant_product_and_competitor):
    """competitors.is_active (added after this module was first built) must be respected."""
    tenant_id, product_id, competitor_id = seeded_tenant_product_and_competitor
    with conn.cursor() as cursor:
        cursor.execute("UPDATE competitors SET is_active = FALSE WHERE competitor_id = %s;", (competitor_id,))
    conn.commit()

    records = data_access.load_competitor_prices(conn, tenant_id, "JOD")
    assert records == []


def test_run_price_recommendation_end_to_end_against_real_db(conn, seeded_tenant_product_and_competitor):
    tenant_id, product_id, _ = seeded_tenant_product_and_competitor

    result = pipeline.run_price_recommendation(conn, tenant_id, product_id)

    assert result["status"] == "OK"
    assert result["action"] == "lower"  # 30.00 is well above the ~19.17 market average
    assert result["matched_competitor_count"] == 3

    with conn.cursor() as cursor:
        cursor.execute("SELECT category FROM evidence_records WHERE evidence_id = %s;", (result["evidence_id"],))
        assert cursor.fetchone()[0] == "RECOMMENDATION"

        cursor.execute(
            "SELECT evidence_id, tenant_id, action_taken FROM recommendation_outcomes WHERE outcome_id = %s;",
            (result["outcome_id"],),
        )
        row = cursor.fetchone()
        assert row[0] == result["evidence_id"]
        assert row[1] == tenant_id
        assert row[2] == "ignored"  # DB default, not yet acted on


def _upsert_currency_rate(conn, base: str, target: str, rate: float, rate_date_value: date, source: str) -> None:
    """
    currency_rates has no tenant_id (rates aren't tenant-scoped) and a unique
    constraint on (base, target, rate_date) - a plain INSERT would collide
    with whatever a previous run of this same test already committed. Upsert
    instead so these tests are idempotent regardless of prior runs.
    """
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO currency_rates (base_currency, target_currency, rate, rate_date, source)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (base_currency, target_currency, rate_date)
            DO UPDATE SET rate = EXCLUDED.rate, source = EXCLUDED.source;
            """,
            (base, target, rate, rate_date_value, source),
        )
    conn.commit()


def test_get_latest_rate_reads_seeded_currency_rate(conn):
    _upsert_currency_rate(conn, "SAR", "JOD", 0.9500, date(2026, 8, 1), "test_feed")

    rate = currency.get_latest_rate(conn, "SAR", "JOD")
    assert rate.rate == 0.95
    assert rate.source == "test_feed"


def test_get_latest_rate_picks_most_recent_when_multiple_dates_exist(conn):
    _upsert_currency_rate(conn, "SAR", "JOD", 0.9000, date(2026, 1, 1), "old_feed")
    _upsert_currency_rate(conn, "SAR", "JOD", 0.9500, date(2026, 8, 1), "new_feed")

    rate = currency.get_latest_rate(conn, "SAR", "JOD")
    assert rate.rate == 0.95
    assert rate.source == "new_feed"


def test_run_price_recommendation_includes_cross_currency_reference_against_real_db(conn):
    tenant_id = str(uuid.uuid4())
    product_id = str(uuid.uuid4())
    competitor_id = str(uuid.uuid4())

    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO companies (tenant_id, business_name, country_code, primary_currency)
            VALUES (%s, 'Cross Currency Test Co', 'JO', 'JOD');
            """,
            (tenant_id,),
        )
        cursor.execute(
            """
            INSERT INTO products (product_id, tenant_id, product_name, current_price, currency)
            VALUES (%s, %s, 'Sunscreen SPF 50', 20.00, 'JOD');
            """,
            (product_id, tenant_id),
        )
        cursor.execute(
            """
            INSERT INTO competitors (competitor_id, tenant_id, competitor_name, country_code)
            VALUES (%s, %s, 'Gulf Pharmacy', 'SA');
            """,
            (competitor_id, tenant_id),
        )
        cursor.execute(
            """
            INSERT INTO competitor_prices
                (tenant_id, competitor_id, product_name_captured, price_found, currency,
                 is_exact_data, collection_method, source_status, captured_at)
            VALUES (%s, %s, 'Sunscreen SPF 50', 75.00, 'SAR', TRUE, 'MANUAL', 'ALLOWED', %s);
            """,
            (tenant_id, competitor_id, datetime.now(timezone.utc)),
        )
    conn.commit()
    _upsert_currency_rate(conn, "SAR", "JOD", 0.9500, date(2026, 8, 1), "test_feed")

    result = pipeline.run_price_recommendation(conn, tenant_id, product_id)

    assert result["status"] == "UNKNOWN"  # no same-currency competitors matched
    with conn.cursor() as cursor:
        cursor.execute("SELECT explanation_text FROM evidence_records WHERE evidence_id = %s;", (result["evidence_id"],))
        explanation = cursor.fetchone()[0]
        assert "reference only" in explanation
        assert "75.00 SAR" in explanation
        assert "71.25 JOD" in explanation  # 75.00 * 0.95


def test_run_price_recommendation_with_no_competitor_data_writes_unknown_evidence(conn):
    tenant_id = str(uuid.uuid4())
    product_id = str(uuid.uuid4())

    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO companies (tenant_id, business_name, country_code, primary_currency)
            VALUES (%s, 'No Competitors Co', 'JO', 'JOD');
            """,
            (tenant_id,),
        )
        cursor.execute(
            """
            INSERT INTO products (product_id, tenant_id, product_name, current_price, currency)
            VALUES (%s, %s, 'Rare Widget', 40.00, 'JOD');
            """,
            (product_id, tenant_id),
        )
    conn.commit()

    result = pipeline.run_price_recommendation(conn, tenant_id, product_id)

    assert result["status"] == "UNKNOWN"
    with conn.cursor() as cursor:
        cursor.execute("SELECT category FROM evidence_records WHERE evidence_id = %s;", (result["evidence_id"],))
        assert cursor.fetchone()[0] == "UNKNOWN"
        cursor.execute("SELECT COUNT(*) FROM recommendation_outcomes WHERE tenant_id = %s;", (tenant_id,))
        assert cursor.fetchone()[0] == 0  # no outcome row when there's no recommendation

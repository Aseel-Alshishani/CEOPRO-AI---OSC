"""
Integration test against a real PostgreSQL instance running the actual
init_schema.sql - not mocks. Exercises the raw SQL in data_access.py and
evidence.py, which unit tests (with the DB mocked out) cannot validate:
column types, JSONB casts, foreign key constraints, and INT rounding on
demand_forecasts.expected_demand.

Skipped automatically unless AI_TEST_DATABASE_URL is set, so it never runs in
CI or on a machine without a disposable test Postgres instance available.
Point it at a throwaway database - this test inserts and deletes rows.
"""

import os
import uuid
from datetime import date, timedelta

import psycopg2
import pytest

from src.ai.forecasting import data_access, evidence, pipeline

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
def seeded_tenant_and_product(conn):
    """Inserts a tenant/product/transaction history, yields (tenant_id, product_id), rolls back after."""
    tenant_id = str(uuid.uuid4())
    product_id = str(uuid.uuid4())

    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO companies (tenant_id, business_name, country_code, primary_currency)
            VALUES (%s, 'AI Integration Test Co', 'JO', 'JOD');
            """,
            (tenant_id,),
        )
        cursor.execute(
            """
            INSERT INTO products (product_id, tenant_id, product_name, current_price, currency)
            VALUES (%s, %s, 'Integration Test Widget', 15.00, 'JOD');
            """,
            (product_id, tenant_id),
        )

        base_date = date(2026, 1, 1)
        for day_offset in range(45):
            transaction_date = base_date + timedelta(days=day_offset)
            weekday = transaction_date.weekday()
            quantity = 18 if weekday in (4, 5) else 10  # Fri/Sat higher, matching features.py's weekend rule
            cursor.execute(
                """
                INSERT INTO transactions
                    (transaction_id, tenant_id, product_id, quantity_sold, unit_price,
                     total_price, original_currency, sale_source, transaction_date)
                VALUES (%s, %s, %s, %s, 15.00, %s, 'JOD', 'POS', %s);
                """,
                (str(uuid.uuid4()), tenant_id, product_id, quantity, quantity * 15.00, transaction_date),
            )
    conn.commit()

    return tenant_id, product_id


def test_load_daily_demand_reads_seeded_transactions(conn, seeded_tenant_and_product):
    tenant_id, product_id = seeded_tenant_and_product
    daily = data_access.load_daily_demand(conn, tenant_id, product_id)

    assert len(daily) == 45
    assert daily["quantity"].sum() > 0
    assert not daily["quantity"].isna().any()  # gap-filling must leave no NaNs


def test_load_product_context_reads_price_and_stock(conn, seeded_tenant_and_product):
    tenant_id, product_id = seeded_tenant_and_product
    context = data_access.load_product_context(conn, tenant_id, product_id)

    assert context["current_price"] == 15.0
    assert context["current_stock"] is None  # no inventory row seeded


def test_load_product_context_excludes_soft_deleted_product(conn, seeded_tenant_and_product):
    """
    products.deleted_at (soft-delete, added to the schema after this module was
    first built) must be respected - a deleted product's context shouldn't be
    silently returned as if it were still active.
    """
    tenant_id, product_id = seeded_tenant_and_product
    with conn.cursor() as cursor:
        cursor.execute("UPDATE products SET deleted_at = NOW() WHERE product_id = %s;", (product_id,))
    conn.commit()

    context = data_access.load_product_context(conn, tenant_id, product_id)
    assert context is None


def test_evidence_writers_round_trip_through_real_tables(conn, seeded_tenant_and_product):
    tenant_id, product_id = seeded_tenant_and_product

    forecast_id = evidence.insert_demand_forecast(
        conn, tenant_id, product_id, expected_demand=12.7, confidence_range_lower=8.0,
        confidence_range_upper=16.0, forecast_target_date=date(2026, 3, 1), model_version="test-baseline",
    )
    evidence_id = evidence.insert_evidence_record(
        conn, tenant_id, "PREDICTION", "ai.forecasting", {"forecast_id": forecast_id},
        confidence_score=0.42, explanation_text="Integration test evidence row.", model_version="test-baseline",
    )
    model_version_id = evidence.insert_model_version(
        conn, "demand_forecast_xgboost", "test-version", "candidate", {"mae": 1.23, "n_folds": 5},
    )
    conn.commit()

    with conn.cursor() as cursor:
        cursor.execute("SELECT expected_demand, model_version FROM demand_forecasts WHERE forecast_id = %s;", (forecast_id,))
        row = cursor.fetchone()
        assert row == (13, "test-baseline")  # INT column rounds 12.7 -> 13

        cursor.execute(
            "SELECT category, confidence_score, source_record_ids FROM evidence_records WHERE evidence_id = %s;",
            (evidence_id,),
        )
        row = cursor.fetchone()
        assert row[0] == "PREDICTION"
        assert float(row[1]) == 0.42
        assert row[2] == {"forecast_id": forecast_id}  # JSONB round-trips as a dict

        cursor.execute("SELECT status, metrics FROM model_versions WHERE model_version_id = %s;", (model_version_id,))
        row = cursor.fetchone()
        assert row[0] == "candidate"
        assert row[1] == {"mae": 1.23, "n_folds": 5}


def test_run_forecast_end_to_end_against_real_db(conn, seeded_tenant_and_product):
    tenant_id, product_id = seeded_tenant_and_product

    result = pipeline.run_forecast(conn, tenant_id, product_id, horizon_days=7)

    assert result["status"] == "OK"
    assert result["source"] in ("baseline", "xgboost")

    with conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM demand_forecasts WHERE tenant_id = %s;", (tenant_id,))
        assert cursor.fetchone()[0] == 1
        cursor.execute("SELECT COUNT(*) FROM evidence_records WHERE tenant_id = %s;", (tenant_id,))
        assert cursor.fetchone()[0] == 1


def test_run_forecast_with_no_transactions_writes_unknown_evidence(conn):
    tenant_id = str(uuid.uuid4())
    product_id = str(uuid.uuid4())

    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO companies (tenant_id, business_name, country_code, primary_currency)
            VALUES (%s, 'Empty Co', 'JO', 'JOD');
            """,
            (tenant_id,),
        )
        cursor.execute(
            """
            INSERT INTO products (product_id, tenant_id, product_name, current_price, currency)
            VALUES (%s, %s, 'No Sales Widget', 5.00, 'JOD');
            """,
            (product_id, tenant_id),
        )
    conn.commit()

    result = pipeline.run_forecast(conn, tenant_id, product_id, horizon_days=7)

    assert result["status"] == "UNKNOWN"

    with conn.cursor() as cursor:
        cursor.execute("SELECT category FROM evidence_records WHERE evidence_id = %s;", (result["evidence_id"],))
        assert cursor.fetchone()[0] == "UNKNOWN"
        cursor.execute("SELECT COUNT(*) FROM demand_forecasts WHERE tenant_id = %s;", (tenant_id,))
        assert cursor.fetchone()[0] == 0  # no forecast row when there's nothing to forecast from

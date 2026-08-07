"""
CEOPRO AI - Demand Forecasting Evidence Writers.
Writes only to tables this track owns per DATA_OWNERSHIP_AND_CONTRACTS.md:
demand_forecasts, evidence_records, model_versions. Never writes to tables
owned by other services.
"""

import json
from datetime import date
from typing import Optional


def insert_demand_forecast(
    conn,
    tenant_id: str,
    product_id: str,
    expected_demand: float,
    confidence_range_lower: Optional[float],
    confidence_range_upper: Optional[float],
    forecast_target_date: date,
    model_version: str,
) -> str:
    query = """
        INSERT INTO demand_forecasts
            (tenant_id, product_id, expected_demand, confidence_range_lower,
             confidence_range_upper, forecast_target_date, model_version)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING forecast_id;
    """
    with conn.cursor() as cursor:
        cursor.execute(
            query,
            (
                tenant_id,
                product_id,
                int(round(expected_demand)),
                int(round(confidence_range_lower)) if confidence_range_lower is not None else None,
                int(round(confidence_range_upper)) if confidence_range_upper is not None else None,
                forecast_target_date,
                model_version,
            ),
        )
        forecast_id = cursor.fetchone()[0]
    return str(forecast_id)


def insert_evidence_record(
    conn,
    tenant_id: str,
    category: str,
    source_module: str,
    source_record_ids: dict,
    confidence_score: Optional[float],
    explanation_text: str,
    model_version: Optional[str],
    country_context: Optional[str] = None,
) -> str:
    query = """
        INSERT INTO evidence_records
            (tenant_id, category, source_module, source_record_ids,
             confidence_score, explanation_text, model_version, country_context)
        VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s)
        RETURNING evidence_id;
    """
    with conn.cursor() as cursor:
        cursor.execute(
            query,
            (
                tenant_id,
                category,
                source_module,
                json.dumps(source_record_ids),
                confidence_score,
                explanation_text,
                model_version,
                country_context,
            ),
        )
        evidence_id = cursor.fetchone()[0]
    return str(evidence_id)


def insert_model_version(conn, model_name: str, version: str, status: str, metrics: dict) -> str:
    query = """
        INSERT INTO model_versions (model_name, version, status, trained_at, metrics)
        VALUES (%s, %s, %s, NOW(), %s::jsonb)
        RETURNING model_version_id;
    """
    with conn.cursor() as cursor:
        cursor.execute(query, (model_name, version, status, json.dumps(metrics)))
        model_version_id = cursor.fetchone()[0]
    return str(model_version_id)

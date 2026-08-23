"""
CEOPRO AI - Demand Forecasting Evidence Writers.
Writes only to tables this track owns per DATA_OWNERSHIP_AND_CONTRACTS.md:
demand_forecasts, evidence_records, system_alerts. Never writes to tables
owned by other services.

SCHEMA UPDATE (major):
- demand_forecasts is now period-based (forecast_start_date/forecast_end_date)
  instead of a single forecast_target_date, columns were renamed
  (expected_demand -> predicted_quantity, confidence_range_lower/upper ->
  confidence_lower_bound/upper_bound), and it gained a `features_used` JSONB
  column that now carries the explanation/config metadata that used to live
  as free text in evidence_records.
- evidence_records is no longer a generic "category + explanation_text +
  confidence_score" table. It is now strictly per-metric evidence tied to one
  forecast_id: (metric_name, metric_value_json, contribution_weight). It can
  no longer be written without an existing forecast (forecast_id is NOT
  NULL + FK), so cases with no forecast (e.g. "no historical data") are now
  reported through system_alerts instead.
- The `model_versions` table has been removed from the schema entirely. Model
  identity/version now lives only as the `model_version` string on each
  demand_forecasts row; there's no separate versioned model registry to write
  to anymore.
"""

import json
from datetime import date
from typing import Iterable, Optional, Tuple


def insert_demand_forecast(
    conn,
    tenant_id: str,
    product_id: str,
    predicted_quantity: float,
    confidence_lower_bound: Optional[float],
    confidence_upper_bound: Optional[float],
    forecast_start_date: date,
    forecast_end_date: date,
    model_version: str,
    features_used: Optional[dict] = None,
) -> str:
    """
    `features_used` is a free-form JSONB bag for whatever explains this
    forecast (feature columns used, baseline name/params, cold-start status,
    a human-readable explanation, etc.) since the schema no longer has a
    dedicated explanation_text/confidence_score column.
    """
    query = """
        INSERT INTO demand_forecasts
            (tenant_id, product_id, forecast_start_date, forecast_end_date,
             predicted_quantity, confidence_lower_bound, confidence_upper_bound,
             model_version, features_used)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        RETURNING forecast_id;
    """
    with conn.cursor() as cursor:
        cursor.execute(
            query,
            (
                tenant_id,
                product_id,
                forecast_start_date,
                forecast_end_date,
                round(float(predicted_quantity), 2),
                round(float(confidence_lower_bound), 2) if confidence_lower_bound is not None else None,
                round(float(confidence_upper_bound), 2) if confidence_upper_bound is not None else None,
                model_version,
                json.dumps(features_used or {}),
            ),
        )
        forecast_id = cursor.fetchone()[0]
    return str(forecast_id)


def insert_evidence_metric(
    conn,
    tenant_id: str,
    forecast_id: str,
    metric_name: str,
    metric_value: dict,
    contribution_weight: float,
) -> str:
    """
    Writes a single evidence row for one metric/feature tied to an existing
    forecast. `contribution_weight` is clamped to the schema's [-1, 1] range
    (e.g. normalized feature importance, or +/-1 for "beats baseline" style
    boolean signals).
    """
    clamped_weight = max(-1.0, min(1.0, float(contribution_weight)))

    query = """
        INSERT INTO evidence_records
            (tenant_id, forecast_id, metric_name, metric_value_json, contribution_weight)
        VALUES (%s, %s, %s, %s::jsonb, %s)
        RETURNING evidence_id;
    """
    with conn.cursor() as cursor:
        cursor.execute(
            query,
            (tenant_id, forecast_id, metric_name, json.dumps(metric_value), clamped_weight),
        )
        evidence_id = cursor.fetchone()[0]
    return str(evidence_id)


def insert_evidence_metrics(
    conn,
    tenant_id: str,
    forecast_id: str,
    metrics: Iterable[Tuple[str, dict, float]],
) -> list:
    """Convenience wrapper: writes several (metric_name, metric_value, contribution_weight) rows."""
    return [
        insert_evidence_metric(conn, tenant_id, forecast_id, name, value, weight)
        for name, value, weight in metrics
    ]


def insert_system_alert(
    conn,
    tenant_id: str,
    alert_type: str,
    severity: str,
    message: str,
) -> str:
    """
    Used for forecasting situations that can't attach to a forecast_id, e.g.
    "no historical data available yet" - evidence_records now requires a real
    forecast_id, so these are logged as system_alerts instead.
    """
    query = """
        INSERT INTO system_alerts (tenant_id, alert_type, severity, message)
        VALUES (%s, %s, %s, %s)
        RETURNING alert_id;
    """
    with conn.cursor() as cursor:
        cursor.execute(query, (tenant_id, alert_type, severity, message))
        alert_id = cursor.fetchone()[0]
    return str(alert_id)

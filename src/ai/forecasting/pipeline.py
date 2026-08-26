"""
CEOPRO AI - Demand Forecasting Pipeline (spec S18, S22, S23, S25).
Orchestrates: load history -> cold-start check -> baseline (+ XGBoost when
enough data) -> pick whichever actually beats the baseline -> persist forecast
+ evidence. This is the only module that writes to the database.

SCHEMA UPDATE: demand_forecasts is now a *period* forecast
(forecast_start_date -> forecast_end_date) rather than a single target date,
so `predicted_quantity` here is the total demand expected over the whole
horizon (sum of the daily forecasts), not just the value on the last day as
before. The old free-text `explanation` and single `confidence_score` no
longer have dedicated columns; they're now folded into the `features_used`
JSONB bag on demand_forecasts. Per-metric/per-feature evidence now requires a
real forecast_id (evidence_records FK), so the "no data at all" case - which
never produces a forecast - is now reported via a system_alert instead of an
evidence record.
"""

import logging
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from src.ai.forecasting import baselines, cold_start, data_access, evaluation, evidence
from src.ai.forecasting.features import build_feature_frame, feature_columns
from src.ai.forecasting.model import MODEL_NAME, XGBoostDemandForecaster, expanding_window_splits, walk_forward_validate

logger = logging.getLogger("CEOPRO_AI_FORECASTING_PIPELINE")

SOURCE_MODULE = "ai.forecasting"
MIN_TRAIN_SIZE_FOR_VALIDATION = 14


def _best_baseline(history: pd.Series, horizon_days: int) -> tuple:
    """Backtests every baseline on in-sample one-step predictions and returns (name, horizon_forecast)."""
    if len(history) < 2:
        name = "naive"
        return name, baselines.BASELINE_FUNCTIONS[name](history, horizon_days)

    scores = {}
    for name in baselines.BASELINE_FUNCTIONS:
        preds = baselines.baseline_in_sample_predictions(history, name)
        actual = history.iloc[1:].to_numpy()
        scores[name] = evaluation.mae(actual, preds) if preds else float("inf")

    best_name = min(scores, key=scores.get)
    horizon_forecast = baselines.BASELINE_FUNCTIONS[best_name](history, horizon_days)
    return best_name, horizon_forecast


def _recursive_xgboost_forecast(
    forecaster: XGBoostDemandForecaster,
    daily_history: pd.DataFrame,
    current_price: Optional[float],
    current_stock: Optional[float],
    horizon_days: int,
) -> np.ndarray:
    """
    Lag/rolling features mean a tree model can only predict one day at a time.
    Predicts one step, appends it to the working series, rebuilds features, and
    repeats until `horizon_days` steps are produced.
    """
    working = daily_history[["date", "quantity", "avg_unit_price"]].copy()
    predictions = []

    for _ in range(horizon_days):
        feature_frame = build_feature_frame(working, current_price, current_stock)
        if feature_frame.empty:
            break
        next_features = feature_frame.iloc[[-1]]
        next_prediction = float(forecaster.predict(next_features)[0])
        next_prediction = max(0.0, next_prediction)  # demand can't be negative
        predictions.append(next_prediction)

        next_date = working["date"].iloc[-1] + timedelta(days=1)
        next_row = {
            "date": next_date,
            "quantity": next_prediction,
            "avg_unit_price": working["avg_unit_price"].iloc[-1],
        }
        working = pd.concat([working, pd.DataFrame([next_row])], ignore_index=True)

    return np.array(predictions)


def run_forecast(conn, tenant_id: str, product_id: str, horizon_days: int = 7) -> dict:
    daily = data_access.load_daily_demand(conn, tenant_id, product_id)

    if daily.empty:
        message = f"No historical transaction data is available yet for product {product_id}."
        alert_id = evidence.insert_system_alert(conn, tenant_id, "FORECAST_NO_DATA", "INFO", message)
        evidence.insert_audit_log(
            conn,
            tenant_id,
            action_type="FORECAST_ALERT_RAISED",
            target_table="system_alerts",
            record_id=alert_id,
            changed_data={"alert_type": "FORECAST_NO_DATA", "product_id": product_id, "message": message},
        )
        conn.commit()
        logger.info(f"No data for tenant={tenant_id} product={product_id}; recorded alert={alert_id}")
        return {"status": "UNKNOWN", "alert_id": alert_id}

    sufficiency = cold_start.assess(daily)
    product_context = data_access.load_product_context(conn, tenant_id, product_id) or {}
    current_price = product_context.get("current_price")
    current_stock = product_context.get("current_stock")

    history = daily["quantity"]
    best_baseline_name, baseline_forecast = _best_baseline(history, horizon_days)

    last_history_date = daily["date"].iloc[-1].date()
    forecast_start_date = last_history_date + timedelta(days=1)
    forecast_end_date = last_history_date + timedelta(days=horizon_days)

    chosen_source = "baseline"
    chosen_name = best_baseline_name
    forecast_values = baseline_forecast
    metrics = None
    trained_model_version_str = None
    forecaster_for_evidence = None

    min_rows_for_validation = MIN_TRAIN_SIZE_FOR_VALIDATION + cold_start.MIN_VALIDATION_FOLDS
    feature_frame = build_feature_frame(daily, current_price, current_stock)
    can_validate = sufficiency.sufficient and len(feature_frame) >= min_rows_for_validation

    if can_validate:
        validation = walk_forward_validate(feature_frame, MIN_TRAIN_SIZE_FOR_VALIDATION, cold_start.MIN_VALIDATION_FOLDS)

        baseline_val_predictions = {}
        splits = expanding_window_splits(len(feature_frame), MIN_TRAIN_SIZE_FOR_VALIDATION, cold_start.MIN_VALIDATION_FOLDS)
        for name in baselines.BASELINE_FUNCTIONS:
            in_sample = baselines.baseline_in_sample_predictions(feature_frame["quantity"], name)
            aligned = [in_sample[val_idx[0] - 1] for _, val_idx in splits if val_idx[0] - 1 < len(in_sample)]
            baseline_val_predictions[name] = aligned

        comparison = evaluation.compare_to_baselines(
            validation["predictions"], validation["actuals"], baseline_val_predictions
        )
        mase_value = evaluation.mase(
            validation["actuals"], validation["predictions"], validation["training_series"]
        )

        metrics = {
            "mae": evaluation.mae(validation["actuals"], validation["predictions"]),
            "rmse": evaluation.rmse(validation["actuals"], validation["predictions"]),
            "mase": mase_value,
            "n_folds": validation["n_folds"],
            "baseline_scores": comparison["scores"],
            "model_beats_all_baselines": comparison["model_beats_all_baselines"],
        }

        if comparison["model_beats_all_baselines"]:
            forecaster = XGBoostDemandForecaster().fit(feature_frame)
            recursive = _recursive_xgboost_forecast(forecaster, daily, current_price, current_stock, horizon_days)
            if len(recursive) == horizon_days:
                forecast_values = recursive
                chosen_source = "xgboost"
                chosen_name = MODEL_NAME
                trained_model_version_str = date.today().isoformat()
                forecaster_for_evidence = forecaster

    predicted_quantity = float(np.sum(forecast_values)) if len(forecast_values) else 0.0
    model_version = trained_model_version_str if chosen_source == "xgboost" else chosen_name

    if chosen_source == "xgboost":
        mase_is_valid = metrics["mase"] == metrics["mase"]  # False for NaN
        confidence_score = round(max(0.3, min(0.95, 1 - min(metrics["mase"], 1.0))), 2) if mase_is_valid else 0.5
        daily_spread = max(metrics["rmse"], 1.0)
        explanation = (
            f"XGBoost forecast (trained {trained_model_version_str}) outperformed all baselines "
            f"over {metrics['n_folds']} walk-forward validation folds "
            f"(MAE={metrics['mae']:.2f}, MASE={metrics['mase']:.2f})."
        )
    else:
        recent_std = float(history.tail(14).std()) if len(history) > 1 else 0.0
        daily_spread = recent_std if recent_std == recent_std else 0.0
        confidence_score = 0.4 if sufficiency.sufficient else 0.2
        reason = (
            "did not outperform the baseline"
            if (metrics is not None and not metrics["model_beats_all_baselines"])
            else "insufficient historical data"
        )
        explanation = (
            f"Using '{best_baseline_name}' baseline forecast because {reason} "
            f"(available_days={sufficiency.available_days}, minimum_required={sufficiency.minimum_required})."
        )

    # Daily forecast errors are treated as independent, so the period-level
    # spread scales with sqrt(horizon_days) rather than horizon_days directly.
    period_spread = daily_spread * (horizon_days ** 0.5)
    confidence_lower_bound = max(0.0, predicted_quantity - 1.28 * period_spread)
    confidence_upper_bound = predicted_quantity + 1.28 * period_spread

    features_used = {
        "chosen_source": chosen_source,
        "confidence_status": sufficiency.confidence_status,
        "confidence_score": confidence_score,
        "explanation": explanation,
        "best_baseline_name": best_baseline_name,
        "horizon_days": horizon_days,
        "feature_columns": feature_columns() if chosen_source == "xgboost" else None,
    }

    demand_forecasts_id = evidence.insert_demand_forecast(
        conn,
        tenant_id,
        product_id,
        predicted_quantity,
        confidence_lower_bound,
        confidence_upper_bound,
        forecast_start_date,
        forecast_end_date,
        model_version,
        features_used,
    )

    evidence_rows = [
        ("data_sufficiency", sufficiency.as_dict(), 0.0),
    ]
    if metrics is not None:
        evidence_rows.append(("validation_mae", {"value": metrics["mae"]}, 0.0))
        evidence_rows.append(("validation_rmse", {"value": metrics["rmse"]}, 0.0))
        evidence_rows.append(("validation_mase", {"value": metrics["mase"]}, 0.0))
        evidence_rows.append(("baseline_scores", metrics["baseline_scores"], 0.0))
        evidence_rows.append((
            "model_beats_all_baselines",
            {"value": metrics["model_beats_all_baselines"]},
            1.0 if metrics["model_beats_all_baselines"] else -1.0,
        ))

    if forecaster_for_evidence is not None:
        for feature_name, importance in forecaster_for_evidence.feature_importances().items():
            evidence_rows.append((f"feature_importance:{feature_name}", {"importance": importance}, importance))

    evidence.insert_evidence_metrics(conn, tenant_id, demand_forecasts_id, evidence_rows)

    evidence.insert_audit_log(
        conn,
        tenant_id,
        action_type="FORECAST_GENERATED",
        target_table="demand_forecasts",
        record_id=demand_forecasts_id,
        changed_data={
            "product_id": product_id,
            "source": chosen_source,
            "model_version": model_version,
            "predicted_quantity": predicted_quantity,
            "confidence_score": confidence_score,
            "horizon_days": horizon_days,
        },
    )

    conn.commit()
    logger.info(
        f"Forecast written tenant={tenant_id} product={product_id} "
        f"source={chosen_source} forecast_id={demand_forecasts_id}"
    )

    return {
        "status": "OK",
        "source": chosen_source,
        "forecast_id": demand_forecasts_id,
        "predicted_quantity": predicted_quantity,
        "forecast_start_date": forecast_start_date.isoformat(),
        "forecast_end_date": forecast_end_date.isoformat(),
        "confidence_score": confidence_score,
        "data_sufficiency": sufficiency.as_dict(),
    }

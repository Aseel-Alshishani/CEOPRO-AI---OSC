"""
CEOPRO AI - Demand Forecasting Pipeline (spec S18, S22, S23, S25).
Orchestrates: load history -> cold-start check -> baseline (+ XGBoost when
enough data) -> pick whichever actually beats the baseline -> persist forecast
+ evidence. This is the only module that writes to the database.
"""

import logging
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from src.ai.forecasting import baselines, cold_start, data_access, evaluation, evidence
from src.ai.forecasting.features import build_feature_frame
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
        working = pd.concat(
            [working, pd.DataFrame([{"date": next_date, "quantity": next_prediction, "avg_unit_price": working["avg_unit_price"].iloc[-1]}])],
            ignore_index=True,
        )

    return np.array(predictions)


def run_forecast(conn, tenant_id: str, product_id: str, horizon_days: int = 7) -> dict:
    daily = data_access.load_daily_demand(conn, tenant_id, product_id)

    if daily.empty:
        explanation = "No historical transaction data is available for this product yet."
        evidence_id = evidence.insert_evidence_record(
            conn, tenant_id, "UNKNOWN", SOURCE_MODULE, {"product_id": product_id}, None, explanation, None
        )
        conn.commit()
        logger.info(f"No data for tenant={tenant_id} product={product_id}; recorded UNKNOWN evidence={evidence_id}")
        return {"status": "UNKNOWN", "evidence_id": evidence_id}

    sufficiency = cold_start.assess(daily)
    product_context = data_access.load_product_context(conn, tenant_id, product_id) or {}
    current_price = product_context.get("current_price")
    current_stock = product_context.get("current_stock")

    history = daily["quantity"]
    best_baseline_name, baseline_forecast = _best_baseline(history, horizon_days)
    forecast_target_date = daily["date"].iloc[-1].date() + timedelta(days=horizon_days)

    chosen_source = "baseline"
    chosen_name = best_baseline_name
    forecast_values = baseline_forecast
    metrics = None
    trained_model_version_str = None

    feature_frame = build_feature_frame(daily, current_price, current_stock)
    can_validate = sufficiency.sufficient and len(feature_frame) >= MIN_TRAIN_SIZE_FOR_VALIDATION + cold_start.MIN_VALIDATION_FOLDS

    if can_validate:
        validation = walk_forward_validate(feature_frame, MIN_TRAIN_SIZE_FOR_VALIDATION, cold_start.MIN_VALIDATION_FOLDS)

        baseline_val_predictions = {}
        for name in baselines.BASELINE_FUNCTIONS:
            in_sample = baselines.baseline_in_sample_predictions(feature_frame["quantity"], name)
            splits = expanding_window_splits(len(feature_frame), MIN_TRAIN_SIZE_FOR_VALIDATION, cold_start.MIN_VALIDATION_FOLDS)
            aligned = [in_sample[val_idx[0] - 1] for _, val_idx in splits if val_idx[0] - 1 < len(in_sample)]
            baseline_val_predictions[name] = aligned

        comparison = evaluation.compare_to_baselines(validation["predictions"], validation["actuals"], baseline_val_predictions)
        mase_value = evaluation.mase(validation["actuals"], validation["predictions"], validation["training_series"])

        metrics = {
            "mae": evaluation.mae(validation["actuals"], validation["predictions"]),
            "rmse": evaluation.rmse(validation["actuals"], validation["predictions"]),
            "mase": mase_value,
            "n_folds": validation["n_folds"],
            "baseline_scores": comparison["scores"],
        }

        if comparison["model_beats_all_baselines"]:
            forecaster = XGBoostDemandForecaster().fit(feature_frame)
            recursive = _recursive_xgboost_forecast(forecaster, daily, current_price, current_stock, horizon_days)
            if len(recursive) == horizon_days:
                forecast_values = recursive
                chosen_source = "xgboost"
                chosen_name = MODEL_NAME
                trained_model_version_str = date.today().isoformat()
                evidence.insert_model_version(
                    conn, MODEL_NAME, trained_model_version_str, "candidate", metrics
                )

    expected_demand = float(forecast_values[-1]) if len(forecast_values) else 0.0

    if chosen_source == "xgboost":
        spread = max(metrics["rmse"], 1.0)
        confidence_score = round(max(0.3, min(0.95, 1 - min(metrics["mase"], 1.0))), 2) if metrics["mase"] == metrics["mase"] else 0.5
        explanation = (
            f"XGBoost forecast (trained {trained_model_version_str}) outperformed all baselines "
            f"({', '.join(f'{k}={v:.2f}' for k, v in metrics['baseline_scores']['scores'].items())}) "
            f"over {metrics['n_folds']} walk-forward validation folds (MAE={metrics['mae']:.2f}, MASE={metrics['mase']:.2f})."
        )
    else:
        recent_std = float(history.tail(14).std()) if len(history) > 1 else 0.0
        spread = recent_std if recent_std == recent_std else 0.0
        confidence_score = 0.4 if sufficiency.sufficient else 0.2
        reason = "did not outperform the baseline" if sufficiency.sufficient else "insufficient historical data"
        explanation = (
            f"Using '{best_baseline_name}' baseline forecast because {reason} "
            f"(available_days={sufficiency.available_days}, minimum_required={sufficiency.minimum_required})."
        )

    confidence_range_lower = max(0.0, expected_demand - 1.28 * spread)
    confidence_range_upper = expected_demand + 1.28 * spread

    demand_forecasts_id = evidence.insert_demand_forecast(
        conn, tenant_id, product_id, expected_demand, confidence_range_lower, confidence_range_upper,
        forecast_target_date, chosen_name,
    )

    evidence_id = evidence.insert_evidence_record(
        conn,
        tenant_id,
        "PREDICTION",
        SOURCE_MODULE,
        {"forecast_id": demand_forecasts_id, "product_id": product_id},
        confidence_score,
        explanation,
        chosen_name,
    )

    conn.commit()
    logger.info(f"Forecast written tenant={tenant_id} product={product_id} source={chosen_source} forecast_id={demand_forecasts_id}")

    return {
        "status": "OK",
        "source": chosen_source,
        "forecast_id": demand_forecasts_id,
        "evidence_id": evidence_id,
        "expected_demand": expected_demand,
        "forecast_target_date": forecast_target_date.isoformat(),
        "confidence_score": confidence_score,
        "data_sufficiency": sufficiency.as_dict(),
    }

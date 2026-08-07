"""
CEOPRO AI - Demand Forecasting Feature Engineering.
Builds lag/rolling/calendar features from a daily demand series (spec S18).
Pure functions - no I/O - so they're independently unit-testable.
"""

from typing import Optional

import pandas as pd

LAG_DAYS = (1, 7, 14)
ROLLING_WINDOWS = (7, 14)


def build_feature_frame(daily: pd.DataFrame, current_price: Optional[float] = None, current_stock: Optional[float] = None) -> pd.DataFrame:
    """
    `daily` must have columns [date, quantity, avg_unit_price], sorted ascending
    with no gaps (see data_access.load_daily_demand). Returns a frame with the
    original columns plus engineered features; rows whose lag/rolling features
    can't be computed yet (start of series) are dropped, since XGBoost can't
    train on incomplete feature rows.
    """
    frame = daily.copy().sort_values("date").reset_index(drop=True)

    for lag in LAG_DAYS:
        frame[f"lag_{lag}"] = frame["quantity"].shift(lag)

    for window in ROLLING_WINDOWS:
        frame[f"rolling_mean_{window}"] = frame["quantity"].shift(1).rolling(window=window).mean()

    frame["day_of_week"] = frame["date"].dt.dayofweek
    frame["day_of_month"] = frame["date"].dt.day
    frame["month"] = frame["date"].dt.month
    frame["is_weekend"] = frame["day_of_week"].isin([4, 5]).astype(int)  # Fri/Sat weekend (spec targets MENA/Africa)

    frame["unit_price"] = frame["avg_unit_price"] if current_price is None else frame["avg_unit_price"].fillna(current_price)
    frame["current_stock"] = current_stock if current_stock is not None else pd.NA

    feature_columns = (
        [f"lag_{lag}" for lag in LAG_DAYS]
        + [f"rolling_mean_{w}" for w in ROLLING_WINDOWS]
        + ["day_of_week", "day_of_month", "month", "is_weekend", "unit_price", "current_stock"]
    )

    usable = frame.dropna(subset=[f"lag_{max(LAG_DAYS)}", f"rolling_mean_{max(ROLLING_WINDOWS)}"]).reset_index(drop=True)

    return usable[["date", "quantity"] + feature_columns]


def feature_columns() -> list:
    return (
        [f"lag_{lag}" for lag in LAG_DAYS]
        + [f"rolling_mean_{w}" for w in ROLLING_WINDOWS]
        + ["day_of_week", "day_of_month", "month", "is_weekend", "unit_price", "current_stock"]
    )

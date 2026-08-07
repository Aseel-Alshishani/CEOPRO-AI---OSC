"""
CEOPRO AI - Shared Cold-Start Policy for Demand Forecasting (spec S23).
When data is insufficient, the pipeline must use a baseline, reduce automation,
and display low-confidence status rather than silently serving an undertrained
model as if it were reliable.
"""

import os
from dataclasses import dataclass

import pandas as pd

# Needs enough history for the longest lag/rolling feature (14 days) plus a
# meaningful walk-forward validation window; 30 days is a practical floor, not
# a value derived from the spec (which leaves the exact threshold unspecified).
MIN_HISTORY_DAYS = int(os.getenv("FORECAST_MIN_HISTORY_DAYS", "30"))
MIN_VALIDATION_FOLDS = int(os.getenv("FORECAST_MIN_VALIDATION_FOLDS", "3"))


@dataclass
class DataSufficiency:
    sufficient: bool
    available_days: int
    minimum_required: int
    confidence_status: str  # "BUILDING" | "OK"

    def as_dict(self) -> dict:
        return {
            "sufficient": self.sufficient,
            "available_days": self.available_days,
            "minimum_required": self.minimum_required,
            "confidence_status": self.confidence_status,
        }


def assess(daily_history: pd.DataFrame) -> DataSufficiency:
    available_days = len(daily_history)
    sufficient = available_days >= MIN_HISTORY_DAYS
    return DataSufficiency(
        sufficient=sufficient,
        available_days=available_days,
        minimum_required=MIN_HISTORY_DAYS,
        confidence_status="OK" if sufficient else "BUILDING",
    )

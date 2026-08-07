"""
CEOPRO AI - Sentiment Sample-Size Policy (spec S16, S23).
Spec S16: "If a country has insufficient review data, the system must
display LOW SAMPLE SIZE" and "must not present a statistically weak result
as a reliable market conclusion." Applied here per-subject (product,
competitor, or business overall) rather than strictly per-country, since
reviews aren't collected with a country column - see
src/ai/sentiment/data_access.py's subject_type handling.
"""

import os
from dataclasses import dataclass

MIN_SAMPLE_SIZE = int(os.getenv("SENTIMENT_MIN_SAMPLE_SIZE", "10"))


@dataclass
class SampleSizeAssessment:
    sufficient: bool
    analyzed_count: int
    minimum_required: int
    status: str  # "LOW_SAMPLE_SIZE" | "OK"

    def as_dict(self) -> dict:
        return {
            "sufficient": self.sufficient,
            "analyzed_count": self.analyzed_count,
            "minimum_required": self.minimum_required,
            "status": self.status,
        }


def assess(analyzed_count: int) -> SampleSizeAssessment:
    sufficient = analyzed_count >= MIN_SAMPLE_SIZE
    return SampleSizeAssessment(
        sufficient=sufficient,
        analyzed_count=analyzed_count,
        minimum_required=MIN_SAMPLE_SIZE,
        status="OK" if sufficient else "LOW_SAMPLE_SIZE",
    )

"""
CEOPRO AI - Pricing Guardrails (spec S19: "Pricing must use ... Guardrails";
"The system must never automatically change prices without explicit
authorization").

This is a price-CHANGE-magnitude guardrail, not a margin guardrail. Spec S19
also calls for margin-based guardrails, which need a cost/COGS basis -
`products` has no cost column (see PENDING_ACTIONS.md #14) - so margin
guardrails aren't implemented here; only bounding how far a suggestion can
move from the current price is.
"""

import os
from dataclasses import dataclass

MAX_PRICE_CHANGE_PCT = float(os.getenv("PRICING_MAX_CHANGE_PCT", "0.15"))


@dataclass
class GuardrailResult:
    suggested_price: float
    clamped: bool
    max_change_pct: float

    def as_dict(self) -> dict:
        return {"suggested_price": self.suggested_price, "clamped": self.clamped, "max_change_pct": self.max_change_pct}


def apply_price_change_guardrail(
    current_price: float, raw_suggested_price: float, max_change_pct: float = None
) -> GuardrailResult:
    max_change_pct = MAX_PRICE_CHANGE_PCT if max_change_pct is None else max_change_pct

    lower_bound = current_price * (1 - max_change_pct)
    upper_bound = current_price * (1 + max_change_pct)

    clamped_price = min(max(raw_suggested_price, lower_bound), upper_bound)
    was_clamped = clamped_price != raw_suggested_price

    return GuardrailResult(suggested_price=round(clamped_price, 2), clamped=was_clamped, max_change_pct=max_change_pct)

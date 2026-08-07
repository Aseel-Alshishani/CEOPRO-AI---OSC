"""
CEOPRO AI - Currency Conversion Service (spec S9: Multi-Currency Architecture).

"The system must NEVER silently convert money without preserving the
original value." Every conversion here carries its original amount/currency
alongside the converted figure, plus the rate, its date, and its source -
none of that is dropped once converted.

"If exchange-rate data is unavailable, the system must explicitly indicate
that conversion cannot be verified." convert() returns None rather than
guessing or falling back to a stale/unrelated rate - callers must handle
the "no rate available" case explicitly, not silently skip it.

Deliberately does not invert rates (e.g. using a stored JOD->SAR rate to
serve a SAR->JOD request) - that's an inference this module isn't in a
position to make about whatever service populates currency_rates, and
spec S9 already asks for explicit fallback behavior, not silent guessing.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class ExchangeRate:
    base_currency: str
    target_currency: str
    rate: float
    rate_date: date
    source: Optional[str]


@dataclass
class ConversionResult:
    original_amount: float
    original_currency: str
    converted_amount: float
    converted_currency: str
    rate: float
    rate_date: date
    source: Optional[str]

    def as_dict(self) -> dict:
        return {
            "original_amount": self.original_amount,
            "original_currency": self.original_currency,
            "converted_amount": self.converted_amount,
            "converted_currency": self.converted_currency,
            "rate": self.rate,
            "rate_date": self.rate_date.isoformat(),
            "source": self.source,
        }


def get_latest_rate(conn, base_currency: str, target_currency: str) -> Optional[ExchangeRate]:
    if base_currency == target_currency:
        return ExchangeRate(base_currency, target_currency, 1.0, date.today(), "identity")

    query = """
        SELECT rate, rate_date, source
        FROM currency_rates
        WHERE base_currency = %s AND target_currency = %s
        ORDER BY rate_date DESC
        LIMIT 1;
    """
    with conn.cursor() as cursor:
        cursor.execute(query, (base_currency, target_currency))
        row = cursor.fetchone()

    if not row:
        return None

    return ExchangeRate(
        base_currency=base_currency, target_currency=target_currency, rate=float(row[0]), rate_date=row[1], source=row[2]
    )


def convert(conn, amount: float, from_currency: str, to_currency: str) -> Optional[ConversionResult]:
    rate_info = get_latest_rate(conn, from_currency, to_currency)
    if rate_info is None:
        return None

    return ConversionResult(
        original_amount=amount,
        original_currency=from_currency,
        converted_amount=round(amount * rate_info.rate, 2),
        converted_currency=to_currency,
        rate=rate_info.rate,
        rate_date=rate_info.rate_date,
        source=rate_info.source,
    )

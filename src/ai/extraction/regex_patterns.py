"""
CEOPRO AI - Rule-Based Information Extraction (spec S15).
"NER may use: Pretrained multilingual transformer. EntityRuler. Regex
patterns. Fuzzy matching. Domain-specific rules." This module implements the
regex/rule tier - the spec's own explicitly-sanctioned low-resource option,
not a fallback bolted on afterward. No trained model, no GPU.

Covers the structurally-regular entity types from spec S15's target list
(MONEY, CURRENCY, PERCENT, DISCOUNT, DATE, PHONE, EMAIL, INVOICE_ID,
ORDER_ID). Free-form entity types that need world knowledge or a trained
model to extract reliably (ORG, PERSON, GPE, ADDRESS) are out of scope here.
PRODUCT/SUPPLIER/COMPETITOR are handled separately in catalog_matching.py,
since those are look-ups against known names, not pattern matches.
"""

import os
import re
from dataclasses import dataclass
from typing import List

# Spec S9's supported currency list, made configuration-driven (spec S9: "The
# actual supported currency list must be configuration-driven") rather than
# hardcoded into extraction logic.
DEFAULT_CURRENCY_CODES = ["JOD", "EGP", "SAR", "AED", "QAR", "KWD", "BHD", "OMR", "MAD", "TND", "DZD", "USD", "EUR", "ZAR"]
CURRENCY_CODES = os.getenv("EXTRACTION_CURRENCY_CODES", ",".join(DEFAULT_CURRENCY_CODES)).split(",")

CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP"}


@dataclass
class ExtractedEntity:
    entity_type: str
    text: str
    start: int
    end: int
    normalized_value: str = None

    def as_dict(self) -> dict:
        return {
            "entity_type": self.entity_type,
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "normalized_value": self.normalized_value,
        }


_CURRENCY_CODE_PATTERN = re.compile(r"\b(" + "|".join(re.escape(c) for c in CURRENCY_CODES) + r")\b")
_MONEY_WITH_CODE_PATTERN = re.compile(
    r"(?P<amount>\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(?P<currency>" + "|".join(re.escape(c) for c in CURRENCY_CODES) + r")\b"
)
_MONEY_WITH_SYMBOL_PATTERN = re.compile(r"(?P<symbol>[$€£])\s?(?P<amount>\d{1,3}(?:,\d{3})*(?:\.\d+)?)")
_PERCENT_PATTERN = re.compile(r"\b(\d{1,3}(?:\.\d+)?)\s?%")
_DISCOUNT_PATTERN = re.compile(r"(\d{1,3}(?:\.\d+)?)\s?%\s*(?:off|discount|OFF|DISCOUNT)|discount of (\d{1,3}(?:\.\d+)?)\s?%")
_EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PHONE_PATTERN = re.compile(r"(?<!\w)(\+?\d{1,3}[\s.-]?)?(\(?\d{2,4}\)?[\s.-]?){2,4}\d{2,4}(?!\w)")
_INVOICE_ID_PATTERN = re.compile(r"\b(?:INV|INVOICE)\s?[-#]?\s?([A-Z0-9]{3,})\b", re.IGNORECASE)
_ORDER_ID_PATTERN = re.compile(r"\b(?:ORD|ORDER)\s?[-#]?\s?([A-Z0-9]{3,})\b", re.IGNORECASE)
_DATE_ISO_PATTERN = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_DATE_SLASH_PATTERN = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b")


def _matches_to_entities(pattern: re.Pattern, text: str, entity_type: str, group: int = 0) -> List[ExtractedEntity]:
    entities = []
    for m in pattern.finditer(text):
        matched_text = m.group(group) if group else m.group(0)
        if matched_text is None:
            continue
        entities.append(ExtractedEntity(entity_type=entity_type, text=matched_text, start=m.start(group), end=m.end(group)))
    return entities


def extract_money(text: str) -> List[ExtractedEntity]:
    entities = []
    for m in _MONEY_WITH_CODE_PATTERN.finditer(text):
        entities.append(
            ExtractedEntity(
                entity_type="MONEY", text=m.group(0), start=m.start(), end=m.end(),
                normalized_value=f"{m.group('amount').replace(',', '')} {m.group('currency')}",
            )
        )
    for m in _MONEY_WITH_SYMBOL_PATTERN.finditer(text):
        currency = CURRENCY_SYMBOLS.get(m.group("symbol"), m.group("symbol"))
        entities.append(
            ExtractedEntity(
                entity_type="MONEY", text=m.group(0), start=m.start(), end=m.end(),
                normalized_value=f"{m.group('amount').replace(',', '')} {currency}",
            )
        )
    return entities


def extract_currency(text: str) -> List[ExtractedEntity]:
    return _matches_to_entities(_CURRENCY_CODE_PATTERN, text, "CURRENCY", group=1)


def extract_percent(text: str) -> List[ExtractedEntity]:
    return _matches_to_entities(_PERCENT_PATTERN, text, "PERCENT", group=0)


def extract_discount(text: str) -> List[ExtractedEntity]:
    entities = []
    for m in _DISCOUNT_PATTERN.finditer(text):
        value = m.group(1) or m.group(2)
        entities.append(
            ExtractedEntity(
                entity_type="DISCOUNT", text=m.group(0), start=m.start(), end=m.end(), normalized_value=f"{value}%"
            )
        )
    return entities


def extract_email(text: str) -> List[ExtractedEntity]:
    return _matches_to_entities(_EMAIL_PATTERN, text, "EMAIL")


def extract_phone(text: str) -> List[ExtractedEntity]:
    entities = []
    for m in _PHONE_PATTERN.finditer(text):
        digits_only = re.sub(r"\D", "", m.group(0))
        if len(digits_only) < 7:  # avoid matching short numbers like years/quantities
            continue
        entities.append(ExtractedEntity(entity_type="PHONE", text=m.group(0).strip(), start=m.start(), end=m.end()))
    return entities


def extract_invoice_id(text: str) -> List[ExtractedEntity]:
    return _matches_to_entities(_INVOICE_ID_PATTERN, text, "INVOICE_ID")


def extract_order_id(text: str) -> List[ExtractedEntity]:
    return _matches_to_entities(_ORDER_ID_PATTERN, text, "ORDER_ID")


def extract_date(text: str) -> List[ExtractedEntity]:
    return _matches_to_entities(_DATE_ISO_PATTERN, text, "DATE", group=1) + _matches_to_entities(
        _DATE_SLASH_PATTERN, text, "DATE", group=1
    )


EXTRACTORS = {
    "MONEY": extract_money,
    "CURRENCY": extract_currency,
    "PERCENT": extract_percent,
    "DISCOUNT": extract_discount,
    "EMAIL": extract_email,
    "PHONE": extract_phone,
    "INVOICE_ID": extract_invoice_id,
    "ORDER_ID": extract_order_id,
    "DATE": extract_date,
}


def extract_all(text: str) -> List[ExtractedEntity]:
    entities = []
    for extractor in EXTRACTORS.values():
        entities.extend(extractor(text))
    return sorted(entities, key=lambda e: e.start)

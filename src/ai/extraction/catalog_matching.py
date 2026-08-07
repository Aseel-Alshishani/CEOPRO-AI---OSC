"""
CEOPRO AI - Catalog-Based Entity Matching (spec S15: PRODUCT, SUPPLIER,
COMPETITOR entity types). These aren't pattern-shaped like MONEY/DATE/EMAIL -
they're look-ups against a tenant's own known names, so they're matched
against a catalog rather than a regex. Reuses the same name-similarity
approach already used for competitor price matching (spec S22: shared,
consistent approach rather than reinventing per module) rather than
duplicating a second fuzzy-matching implementation.
"""

import re
from typing import List

from src.ai.pricing.matching import similarity
from src.ai.extraction.regex_patterns import ExtractedEntity

DEFAULT_MATCH_THRESHOLD = 0.80


def find_catalog_mentions(
    text: str, known_names: List[str], entity_type: str, threshold: float = None
) -> List[ExtractedEntity]:
    """
    Scans `text` for substrings that closely match one of `known_names`
    (e.g. a tenant's own product names, or their tracked competitors).
    Candidate spans are generated from capitalized word runs (a simple,
    language-agnostic heuristic for "probably a proper noun / product name"),
    then scored against the catalog - conservative by design (spec S37:
    "Product Matching: Use rules and fuzzy matching with more manual
    confirmation"), not exhaustive substring search, which would be far too
    slow and far too prone to false positives on ordinary text.
    """
    threshold = DEFAULT_MATCH_THRESHOLD if threshold is None else threshold
    if not known_names:
        return []

    candidate_spans = _capitalized_run_spans(text)
    entities = []
    for start, end, candidate_text in candidate_spans:
        best_name, best_score = None, 0.0
        for name in known_names:
            score = similarity(candidate_text, name)
            if score > best_score:
                best_name, best_score = name, score

        if best_score >= threshold:
            entities.append(
                ExtractedEntity(entity_type=entity_type, text=candidate_text, start=start, end=end, normalized_value=best_name)
            )

    return entities


_CAPITALIZED_RUN_PATTERN = re.compile(r"\b[A-Z][\w'-]*(?:\s+[A-Z0-9][\w'-]*)*\b")


def _capitalized_run_spans(text: str):
    for m in _CAPITALIZED_RUN_PATTERN.finditer(text):
        yield m.start(), m.end(), m.group(0)

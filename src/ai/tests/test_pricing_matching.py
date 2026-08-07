from src.ai.pricing.matching import match_competitor_records, similarity


def test_similarity_identical_strings_is_one():
    assert similarity("Sunscreen SPF 50", "Sunscreen SPF 50") == 1.0


def test_similarity_is_case_and_whitespace_insensitive():
    assert similarity("  Sunscreen SPF 50 ", "sunscreen spf 50") == 1.0


def test_similarity_different_products_is_low():
    assert similarity("Sunscreen SPF 50", "Moisturizer Lotion") < 0.5


def test_match_competitor_records_filters_by_threshold():
    records = [
        {"price_entry_id": "1", "product_name_captured": "Sunscreen SPF 50"},
        {"price_entry_id": "2", "product_name_captured": "Sunscreen SPF 50 Sensitive"},
        {"price_entry_id": "3", "product_name_captured": "Moisturizer Lotion"},
    ]
    matched = match_competitor_records("Sunscreen SPF 50", records, threshold=0.85)

    matched_ids = {m["price_entry_id"] for m in matched}
    assert "1" in matched_ids
    assert "3" not in matched_ids


def test_match_competitor_records_returns_empty_for_no_match():
    records = [{"price_entry_id": "1", "product_name_captured": "Completely Unrelated Item"}]
    assert match_competitor_records("Sunscreen SPF 50", records, threshold=0.82) == []


def test_match_competitor_records_sorted_by_score_descending():
    records = [
        {"price_entry_id": "1", "product_name_captured": "Sunscreen SPF 50 Extra"},
        {"price_entry_id": "2", "product_name_captured": "Sunscreen SPF 50"},
    ]
    matched = match_competitor_records("Sunscreen SPF 50", records, threshold=0.5)
    assert matched[0]["price_entry_id"] == "2"  # exact match should rank first
    assert matched[0]["match_score"] >= matched[1]["match_score"]


def test_match_competitor_records_preserves_original_fields():
    records = [{"price_entry_id": "1", "product_name_captured": "Sunscreen SPF 50", "price_found": 18.0}]
    matched = match_competitor_records("Sunscreen SPF 50", records, threshold=0.5)
    assert matched[0]["price_found"] == 18.0
    assert "match_score" in matched[0]

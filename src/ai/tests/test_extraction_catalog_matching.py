from src.ai.extraction.catalog_matching import find_catalog_mentions


def test_finds_exact_catalog_match():
    text = "Customer asked about Sunscreen SPF 50 availability"
    matches = find_catalog_mentions(text, known_names=["Sunscreen SPF 50", "Moisturizer Lotion"], entity_type="PRODUCT")
    assert len(matches) == 1
    assert matches[0].normalized_value == "Sunscreen SPF 50"
    assert matches[0].entity_type == "PRODUCT"


def test_finds_near_match_above_threshold():
    text = "Do you have Sunscreen SPF50 in stock"  # missing space, close but not exact
    matches = find_catalog_mentions(text, known_names=["Sunscreen SPF 50"], entity_type="PRODUCT", threshold=0.85)
    assert len(matches) == 1


def test_no_match_below_threshold():
    text = "We saw Rival Pharmacy advertising a sale"
    matches = find_catalog_mentions(text, known_names=["Totally Different Company"], entity_type="COMPETITOR")
    assert matches == []


def test_empty_catalog_returns_no_matches():
    text = "Sunscreen SPF 50 is popular"
    assert find_catalog_mentions(text, known_names=[], entity_type="PRODUCT") == []


def test_lowercase_text_is_not_scanned_as_candidate():
    # candidate spans require a capitalized run - plain lowercase mentions aren't scanned
    text = "the sunscreen spf 50 is popular"
    matches = find_catalog_mentions(text, known_names=["Sunscreen SPF 50"], entity_type="PRODUCT")
    assert matches == []


def test_competitor_entity_type_is_used():
    text = "Rival Pharmacy dropped their prices"
    matches = find_catalog_mentions(text, known_names=["Rival Pharmacy"], entity_type="COMPETITOR")
    assert len(matches) == 1
    assert matches[0].entity_type == "COMPETITOR"

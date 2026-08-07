from src.ai.extraction.extractor import extract_entities


def test_extract_entities_without_catalogs_still_runs_regex():
    text = "Invoice INV-1001 for 18.00 JOD dated 2026-07-27"
    entities = extract_entities(text)
    types = {e.entity_type for e in entities}
    assert "INVOICE_ID" in types
    assert "MONEY" in types
    assert "DATE" in types


def test_extract_entities_includes_catalog_matches_when_provided():
    text = "Sunscreen SPF 50 is priced at 18.00 JOD, ahead of Rival Pharmacy"
    entities = extract_entities(text, known_product_names=["Sunscreen SPF 50"], known_competitor_names=["Rival Pharmacy"])
    types = {e.entity_type for e in entities}
    assert "PRODUCT" in types
    assert "COMPETITOR" in types
    assert "MONEY" in types


def test_extract_entities_sorted_by_position():
    text = "Rival Pharmacy sells Sunscreen SPF 50 for 18.00 JOD"
    entities = extract_entities(text, known_product_names=["Sunscreen SPF 50"], known_competitor_names=["Rival Pharmacy"])
    assert all(entities[i].start <= entities[i + 1].start for i in range(len(entities) - 1))

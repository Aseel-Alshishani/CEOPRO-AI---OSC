from src.ai.extraction.regex_patterns import (
    extract_all,
    extract_currency,
    extract_date,
    extract_discount,
    extract_email,
    extract_invoice_id,
    extract_money,
    extract_order_id,
    extract_percent,
    extract_phone,
)


def test_extract_money_with_currency_code():
    entities = extract_money("The sunscreen costs 18.00 JOD at our store")
    assert len(entities) == 1
    assert entities[0].entity_type == "MONEY"
    assert entities[0].normalized_value == "18.00 JOD"


def test_extract_money_with_symbol():
    entities = extract_money("Priced at $25.50 this week")
    assert len(entities) == 1
    assert entities[0].normalized_value == "25.50 USD"


def test_extract_money_with_thousands_separator():
    entities = extract_money("Total invoice: 1,250.00 SAR")
    assert entities[0].normalized_value == "1250.00 SAR"


def test_extract_money_with_currency_code_before_amount():
    """Code-before-amount ("JOD 18.00") is at least as common as code-after for MENA currencies."""
    entities = extract_money("The price is JOD 18.00 for this item")
    assert len(entities) == 1
    assert entities[0].normalized_value == "18.00 JOD"


def test_extract_money_with_currency_code_before_amount_no_decimal():
    entities = extract_money("Total: SAR 500")
    assert len(entities) == 1
    assert entities[0].normalized_value == "500 SAR"


def test_extract_currency_codes():
    entities = extract_currency("We accept JOD, USD, and EUR for this product")
    codes = {e.text for e in entities}
    assert codes == {"JOD", "USD", "EUR"}


def test_extract_percent():
    entities = extract_percent("The margin improved by 15% this quarter")
    assert len(entities) == 1
    assert entities[0].text == "15%"


def test_extract_discount():
    entities = extract_discount("Get 20% off on all sunscreen products")
    assert len(entities) == 1
    assert entities[0].entity_type == "DISCOUNT"
    assert entities[0].normalized_value == "20%"


def test_extract_discount_alternate_phrasing():
    entities = extract_discount("We are offering a discount of 15% this weekend")
    assert len(entities) == 1
    assert entities[0].normalized_value == "15%"


def test_extract_discount_is_case_insensitive():
    """Title-case marketing phrasing ("30% Off") must match, not just lowercase/all-caps."""
    entities = extract_discount("Big 30% Off Sale This Weekend")
    assert len(entities) == 1
    assert entities[0].normalized_value == "30%"


def test_extract_email():
    entities = extract_email("Contact us at sales@ceopro.example for more info")
    assert len(entities) == 1
    assert entities[0].text == "sales@ceopro.example"


def test_extract_phone_with_country_code():
    entities = extract_phone("Call us at +962 7 9012 3456 for support")
    assert len(entities) == 1
    assert entities[0].entity_type == "PHONE"


def test_extract_phone_ignores_short_numbers():
    entities = extract_phone("We sold 12 units in Q3")
    assert entities == []


def test_extract_invoice_id():
    entities = extract_invoice_id("Please reference INV-20458 for this payment")
    assert len(entities) == 1
    assert entities[0].entity_type == "INVOICE_ID"


def test_extract_order_id_hash_style():
    entities = extract_order_id("Your order #A4821X has shipped")
    assert len(entities) == 1
    assert entities[0].entity_type == "ORDER_ID"


def test_extract_invoice_id_does_not_false_positive_on_plain_word():
    """
    "INV" (tried as the first alternative under IGNORECASE) previously matched
    as a prefix of the plain word "invoice" itself, with the rest of the word
    ("oice") captured as a fake ID. Also covers the related fix that the ID
    group must contain a digit - ordinary words aren't IDs.
    """
    assert extract_invoice_id("Total invoice amount: 500") == []
    assert extract_invoice_id("Please send me my invoice") == []
    assert extract_invoice_id("Please review the invoicing process") == []


def test_extract_order_id_does_not_false_positive_on_plain_word():
    assert extract_order_id("the order was placed yesterday") == []
    assert extract_order_id("in order to proceed") == []
    assert extract_order_id("reorder level is low") == []
    assert extract_order_id("disorder in the queue") == []


def test_extract_invoice_id_matches_real_id_without_dash():
    entities = extract_invoice_id("Invoice: INV20458")
    assert len(entities) == 1
    assert entities[0].text == "INV20458"


def test_extract_order_id_matches_real_id_with_full_word_label():
    entities = extract_order_id("ORDER: ORD99231 confirmed")
    assert len(entities) == 1
    assert entities[0].text == "ORD99231"


def test_extract_date_iso():
    entities = extract_date("The shipment arrived on 2026-07-27")
    assert len(entities) == 1
    assert entities[0].text == "2026-07-27"


def test_extract_date_slash_format():
    entities = extract_date("Delivery expected 27/07/2026")
    assert len(entities) == 1
    assert entities[0].text == "27/07/2026"


def test_extract_all_combines_and_sorts_by_position():
    text = "Invoice INV-1001 for 18.00 JOD, dated 2026-07-27, email sales@ceopro.example"
    entities = extract_all(text)
    types = [e.entity_type for e in entities]
    assert "INVOICE_ID" in types
    assert "MONEY" in types
    assert "DATE" in types
    assert "EMAIL" in types
    # sorted by start position
    assert all(entities[i].start <= entities[i + 1].start for i in range(len(entities) - 1))


def test_extract_all_handles_arabic_context_around_entities():
    text = "السعر 18.00 JOD والخصم 15% صالح حتى 2026-07-27"
    entities = extract_all(text)
    types = [e.entity_type for e in entities]
    assert "MONEY" in types
    assert "PERCENT" in types
    assert "DATE" in types

from src.ai.pricing.guardrails import apply_price_change_guardrail


def test_suggestion_within_bounds_is_not_clamped():
    result = apply_price_change_guardrail(current_price=100.0, raw_suggested_price=105.0, max_change_pct=0.15)
    assert result.suggested_price == 105.0
    assert result.clamped is False


def test_suggestion_above_upper_bound_is_clamped():
    result = apply_price_change_guardrail(current_price=100.0, raw_suggested_price=150.0, max_change_pct=0.15)
    assert result.suggested_price == 115.0
    assert result.clamped is True


def test_suggestion_below_lower_bound_is_clamped():
    result = apply_price_change_guardrail(current_price=100.0, raw_suggested_price=50.0, max_change_pct=0.15)
    assert result.suggested_price == 85.0
    assert result.clamped is True


def test_suggestion_equal_to_current_price_is_never_clamped():
    result = apply_price_change_guardrail(current_price=100.0, raw_suggested_price=100.0, max_change_pct=0.15)
    assert result.suggested_price == 100.0
    assert result.clamped is False


def test_custom_max_change_pct_is_respected():
    result = apply_price_change_guardrail(current_price=100.0, raw_suggested_price=110.0, max_change_pct=0.05)
    assert result.suggested_price == 105.0
    assert result.clamped is True

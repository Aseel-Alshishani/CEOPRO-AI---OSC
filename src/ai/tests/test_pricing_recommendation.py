from src.ai.pricing.recommendation import build_recommendation


def _competitors(prices, id_prefix="c"):
    return [{"price_entry_id": f"{id_prefix}{i}", "price_found": p} for i, p in enumerate(prices)]


def test_returns_none_for_no_matched_competitors():
    assert build_recommendation(current_price=20.0, matched_competitors=[]) is None


def test_suggests_lowering_when_priced_well_above_market():
    rec = build_recommendation(current_price=30.0, matched_competitors=_competitors([18.0, 19.0, 20.0]))
    assert rec.action == "lower"
    assert rec.raw_suggested_price == round((18.0 + 19.0 + 20.0) / 3, 2)
    assert rec.matched_competitor_count == 3


def test_suggests_raising_when_priced_well_below_market():
    rec = build_recommendation(current_price=10.0, matched_competitors=_competitors([18.0, 19.0, 20.0]))
    assert rec.action == "raise"
    assert rec.raw_suggested_price == round((18.0 + 19.0 + 20.0) / 3, 2)


def test_holds_when_already_within_threshold_of_market_average():
    # market average is 19.0; within default 5% band (18.05-19.95)
    rec = build_recommendation(current_price=19.2, matched_competitors=_competitors([18.0, 19.0, 20.0]))
    assert rec.action == "hold"
    assert rec.raw_suggested_price == 19.2  # unchanged


def test_market_stats_are_correct():
    rec = build_recommendation(current_price=25.0, matched_competitors=_competitors([10.0, 20.0, 30.0]))
    assert rec.market_min == 10.0
    assert rec.market_max == 30.0
    assert rec.market_avg == 20.0
    assert rec.market_median == 20.0


def test_confidence_increases_with_more_matched_competitors():
    few = build_recommendation(current_price=30.0, matched_competitors=_competitors([18.0, 19.0]))
    many = build_recommendation(current_price=30.0, matched_competitors=_competitors([18.0] * 10))
    assert many.confidence_score > few.confidence_score


def test_source_record_ids_track_matched_competitors():
    rec = build_recommendation(current_price=30.0, matched_competitors=_competitors([18.0, 19.0], id_prefix="p"))
    assert rec.source_record_ids == ["p0", "p1"]

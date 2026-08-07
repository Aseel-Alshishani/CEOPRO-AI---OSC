"""
Tests the real sentiment classifier - downloads/loads an actual ~1.1GB
XLM-RoBERTa model on first use and needs network access, so this is gated
behind an explicit opt-in (AI_TEST_SENTIMENT=1) rather than running by
default, mirroring test_rag_embeddings.py's AI_TEST_EMBEDDINGS convention.
Confirmed manually: id2label = {0: 'negative', 1: 'neutral', 2: 'positive'}
for the default model (cardiffnlp/twitter-xlm-roberta-base-sentiment) - a
different index order than a naive alphabetical/enum guess, which is exactly
why model.py reads id2label from the model instead of hardcoding it.
"""

import os

import pytest

from src.ai.sentiment.model import classify

pytestmark = pytest.mark.skipif(
    not os.getenv("AI_TEST_SENTIMENT"), reason="AI_TEST_SENTIMENT not set - skipping (downloads a real model)"
)


def test_classify_empty_list_returns_empty():
    assert classify([]) == []


def test_classify_english_positive_review():
    predictions = classify(["This product is amazing, I love it!"])
    assert predictions[0].label == "positive"
    assert predictions[0].positive_probability > 0.8


def test_classify_arabic_negative_review():
    predictions = classify(["خدمة سيئة جدا ولن أشتري مرة أخرى"])  # "very bad service, won't buy again"
    assert predictions[0].label == "negative"
    assert predictions[0].negative_probability > 0.8


def test_classify_arabic_positive_review():
    predictions = classify(["التوصيل كان سريعا وممتازا"])  # "delivery was fast and excellent"
    assert predictions[0].label == "positive"


def test_classify_probabilities_sum_to_one():
    predictions = classify(["It is okay, nothing special."])
    total = (
        predictions[0].positive_probability + predictions[0].neutral_probability + predictions[0].negative_probability
    )
    assert abs(total - 1.0) < 1e-2


def test_classify_batch_of_mixed_language_reviews_matches_single_calls():
    mixed = classify(["This product is amazing, I love it!", "خدمة سيئة جدا ولن أشتري مرة أخرى"])
    assert mixed[0].label == "positive"
    assert mixed[1].label == "negative"

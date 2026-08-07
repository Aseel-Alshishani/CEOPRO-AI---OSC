"""
Tests the real embedding model - downloads/loads an actual ~470MB model on
first use and needs network access, so this is gated behind an explicit
opt-in (AI_TEST_EMBEDDINGS=1) rather than running by default like the pure
offline tests. Confirmed manually: ~140s on first download, ~30s on a fresh
process even with the model cached locally (still checks the HF Hub), fast
for repeat calls within the same process (see embeddings.py's model cache).
"""

import os

import numpy as np
import pytest

from src.ai.rag.embeddings import embed

pytestmark = pytest.mark.skipif(
    not os.getenv("AI_TEST_EMBEDDINGS"), reason="AI_TEST_EMBEDDINGS not set - skipping (downloads a real model)"
)


def test_embed_returns_correct_shape():
    vectors = embed(["hello world", "another sentence", "a third one"])
    assert vectors.shape[0] == 3
    assert vectors.shape[1] > 0


def test_embed_empty_list_returns_empty_array():
    vectors = embed([])
    assert vectors.shape[0] == 0


def test_embeddings_are_l2_normalized():
    vectors = embed(["some text to embed"])
    norm = np.linalg.norm(vectors[0])
    assert abs(norm - 1.0) < 1e-4


def test_similar_sentences_have_higher_similarity_than_unrelated_ones():
    vectors = embed(
        [
            "Sunscreen SPF 50 is our best selling summer product",
            "Sun protection cream is very popular in summer",
            "The quarterly financial audit was completed yesterday",
        ]
    )
    sim_related = float(np.dot(vectors[0], vectors[1]))
    sim_unrelated = float(np.dot(vectors[0], vectors[2]))
    assert sim_related > sim_unrelated


def test_arabic_and_english_of_same_topic_are_more_similar_than_unrelated_topics():
    vectors = embed(
        [
            "Sunscreen is our best selling product",
            "واقي الشمس هو المنتج الأكثر مبيعا لدينا",  # Arabic: sunscreen is our best-selling product
            "The quarterly financial audit was completed yesterday",
        ]
    )
    sim_cross_lingual_same_topic = float(np.dot(vectors[0], vectors[1]))
    sim_same_language_different_topic = float(np.dot(vectors[0], vectors[2]))
    assert sim_cross_lingual_same_topic > sim_same_language_different_topic

"""
Tests FAISSIndex with synthetic vectors - doesn't need the real embedding
model (that's covered separately, gated behind AI_TEST_EMBEDDINGS since it
needs a real model download on first use).
"""

import numpy as np

from src.ai.rag.faiss_index import FAISSIndex


def _unit_vector(*components) -> np.ndarray:
    v = np.array(components, dtype=np.float32)
    return v / np.linalg.norm(v)


def test_empty_index_returns_no_results():
    index = FAISSIndex([], np.empty((0, 4), dtype=np.float32))
    assert len(index) == 0
    assert index.query(_unit_vector(1, 0, 0, 0)) == []


def test_query_returns_closest_vector_first():
    chunks = [("c1", "about cats"), ("c2", "about dogs"), ("c3", "about spaceships")]
    embeddings = np.array(
        [_unit_vector(1, 0, 0), _unit_vector(0.9, 0.1, 0), _unit_vector(0, 0, 1)], dtype=np.float32
    )
    index = FAISSIndex(chunks, embeddings)

    results = index.query(_unit_vector(1, 0, 0), top_k=3)

    assert len(results) == 3
    assert results[0].chunk_id == "c1"  # exact match
    assert results[0].score > results[1].score > results[2].score


def test_top_k_limits_result_count():
    chunks = [(f"c{i}", f"text {i}") for i in range(10)]
    embeddings = np.tile(_unit_vector(1, 0), (10, 1)).astype(np.float32)
    index = FAISSIndex(chunks, embeddings)

    results = index.query(_unit_vector(1, 0), top_k=3)
    assert len(results) == 3


def test_mismatched_chunks_and_embeddings_length_raises():
    chunks = [("c1", "text"), ("c2", "text2")]
    embeddings = np.array([_unit_vector(1, 0)], dtype=np.float32)  # only 1 row for 2 chunks
    try:
        FAISSIndex(chunks, embeddings)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_len_reflects_chunk_count():
    chunks = [("c1", "text one"), ("c2", "text two")]
    embeddings = np.tile(_unit_vector(1, 0), (2, 1)).astype(np.float32)
    assert len(FAISSIndex(chunks, embeddings)) == 2

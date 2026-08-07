from src.ai.rag.hybrid_retrieval import reciprocal_rank_fusion
from src.ai.rag.retrieval_types import ScoredChunk


def sc(chunk_id, text, score):
    return ScoredChunk(chunk_id=chunk_id, text=text, score=score)


def test_chunk_found_by_both_retrievers_ranks_above_single_source():
    bm25 = [sc("a", "text a", 5.0), sc("b", "text b", 3.0)]
    faiss = [sc("a", "text a", 0.9), sc("c", "text c", 0.8)]

    fused = reciprocal_rank_fusion(bm25, faiss, top_k=3)

    assert fused[0].chunk_id == "a"  # appears first in both lists


def test_empty_bm25_results_still_returns_faiss_results():
    fused = reciprocal_rank_fusion([], [sc("a", "text a", 0.9)], top_k=5)
    assert len(fused) == 1
    assert fused[0].chunk_id == "a"


def test_empty_faiss_results_still_returns_bm25_results():
    fused = reciprocal_rank_fusion([sc("a", "text a", 5.0)], [], top_k=5)
    assert len(fused) == 1
    assert fused[0].chunk_id == "a"


def test_both_empty_returns_empty():
    assert reciprocal_rank_fusion([], [], top_k=5) == []


def test_top_k_limits_result_count():
    bm25 = [sc(f"c{i}", f"text {i}", float(10 - i)) for i in range(10)]
    fused = reciprocal_rank_fusion(bm25, [], top_k=3)
    assert len(fused) == 3


def test_fused_score_is_sum_of_reciprocal_ranks():
    bm25 = [sc("a", "text a", 1.0)]  # rank 1
    faiss = [sc("x", "text x", 1.0), sc("a", "text a", 0.5)]  # rank 2
    fused = reciprocal_rank_fusion(bm25, faiss, top_k=5, k=60)

    expected_score_a = 1 / (60 + 1) + 1 / (60 + 2)
    a_result = next(r for r in fused if r.chunk_id == "a")
    assert abs(a_result.score - expected_score_a) < 1e-9

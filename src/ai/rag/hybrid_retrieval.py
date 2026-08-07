"""
CEOPRO AI - Hybrid Retrieval Fusion (spec S4, S21: "STRUCTURED DATABASE QUERY
+ BM25 + FAISS" -> "RESULT FUSION"). Combines BM25 (lexical) and FAISS
(semantic) rankings via Reciprocal Rank Fusion - a well-established, simple,
parameter-light fusion method (no training, no tuning), matching this
module's rule-based, non-learned approach elsewhere. Pure function - no I/O.
"""

from typing import List

from src.ai.rag.retrieval_types import ScoredChunk

DEFAULT_RRF_K = 60  # standard default from the original RRF paper; not spec-mandated


def reciprocal_rank_fusion(
    bm25_results: List[ScoredChunk], faiss_results: List[ScoredChunk], top_k: int = 5, k: int = DEFAULT_RRF_K
) -> List[ScoredChunk]:
    """
    Each result list contributes 1/(k + rank) to a chunk's fused score,
    1-indexed by rank. A chunk found by both retrievers outranks one found by
    only one, without needing BM25 and FAISS scores (which live on
    incomparable scales) to be normalized against each other.
    """
    fused_scores = {}
    chunk_texts = {}

    for results in (bm25_results, faiss_results):
        for rank, result in enumerate(results, start=1):
            fused_scores[result.chunk_id] = fused_scores.get(result.chunk_id, 0.0) + 1.0 / (k + rank)
            chunk_texts[result.chunk_id] = result.text

    ranked_ids = sorted(fused_scores, key=fused_scores.get, reverse=True)
    return [ScoredChunk(chunk_id=cid, text=chunk_texts[cid], score=fused_scores[cid]) for cid in ranked_ids[:top_k]]

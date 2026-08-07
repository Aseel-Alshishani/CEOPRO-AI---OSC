"""
CEOPRO AI - FAISS Semantic Retrieval Index (spec S4, S6, S21).
CPU-only (faiss-cpu). Embeddings are L2-normalized (see embeddings.py), so a
flat inner-product index is equivalent to cosine similarity - exact search,
no approximate-index tuning needed at the corpus sizes a single tenant will
realistically have.
"""

from typing import List, Tuple

import faiss
import numpy as np

from src.ai.rag.retrieval_types import ScoredChunk


class FAISSIndex:
    def __init__(self, chunks: List[Tuple[str, str]], embeddings: np.ndarray):
        """
        `chunks` is a list of (chunk_id, text) pairs; `embeddings` is an
        (n, dim) array in the same order, e.g. from embeddings.embed().
        """
        if len(chunks) != len(embeddings):
            raise ValueError(f"chunks ({len(chunks)}) and embeddings ({len(embeddings)}) must have the same length")

        self._chunk_ids = [chunk_id for chunk_id, _ in chunks]
        self._texts = [text for _, text in chunks]

        if len(chunks) == 0:
            self._index = None
            self._dim = None
        else:
            self._dim = embeddings.shape[1]
            self._index = faiss.IndexFlatIP(self._dim)
            self._index.add(embeddings)

    def __len__(self) -> int:
        return len(self._chunk_ids)

    def query(self, query_embedding: np.ndarray, top_k: int = 5) -> List[ScoredChunk]:
        if self._index is None or len(self._chunk_ids) == 0:
            return []

        query_vector = query_embedding.reshape(1, -1).astype(np.float32)
        top_k = min(top_k, len(self._chunk_ids))
        scores, indices = self._index.search(query_vector, top_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            results.append(ScoredChunk(chunk_id=self._chunk_ids[idx], text=self._texts[idx], score=float(score)))
        return results

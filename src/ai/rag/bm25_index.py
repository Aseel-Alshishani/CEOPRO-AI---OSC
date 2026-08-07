"""
CEOPRO AI - BM25 Lexical Retrieval Index (spec S4, S6, S21).
Pure-Python, no trained model, no GPU - the lightest tier of the RAG
retrieval stack. Regex word tokenization (Unicode-aware by default in
Python's re module) works for both Arabic and English without a
language-specific tokenizer, matching chunking.py's approach.
"""

import re
from typing import List, Tuple

from rank_bm25 import BM25Plus

from src.ai.rag.retrieval_types import ScoredChunk

_TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> List[str]:
    return _TOKEN_PATTERN.findall(text.lower())


class BM25Index:
    """
    In-memory per-build index. Not persisted across process restarts by this
    class - callers needing persistence must rebuild from source chunks (see
    data_access.py) or serialize separately. Kept in-memory here because BM25
    index state doesn't belong in PostgreSQL (spec S37: "Redis is not
    permanent storage. The LLM is not the database" - by the same logic, an
    in-memory search index isn't a system of record either; the chunks
    themselves are the source of truth).
    """

    def __init__(self, chunks: List[Tuple[str, str]]):
        """
        `chunks` is a list of (chunk_id, text) pairs. Uses BM25Plus rather
        than the classic BM25Okapi: Okapi's IDF formula (log((N-df+0.5)/(df+0.5)))
        is exactly zero for any term appearing in precisely half of a
        corpus - trivially reachable with tenants that have only 2-3
        documents uploaded (a realistic cold-start state for an SME, spec
        S23), which silently zeroed out otherwise-obvious matches. BM25Plus's
        added delta term keeps IDF strictly positive regardless of corpus
        size.
        """
        self._chunk_ids = [chunk_id for chunk_id, _ in chunks]
        self._texts = [text for _, text in chunks]
        tokenized_corpus = [tokenize(text) for text in self._texts]
        self._bm25 = BM25Plus(tokenized_corpus) if tokenized_corpus else None

    def __len__(self) -> int:
        return len(self._chunk_ids)

    def query(self, query_text: str, top_k: int = 5) -> List[ScoredChunk]:
        if self._bm25 is None:
            return []

        tokenized_query = tokenize(query_text)
        scores = self._bm25.get_scores(tokenized_query)

        ranked = sorted(zip(self._chunk_ids, self._texts, scores), key=lambda r: r[2], reverse=True)
        return [ScoredChunk(chunk_id=cid, text=text, score=float(score)) for cid, text, score in ranked[:top_k] if score > 0]

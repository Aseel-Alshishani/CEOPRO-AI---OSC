"""Shared types for src/ai/rag/ retrieval modules."""

from dataclasses import dataclass


@dataclass
class ScoredChunk:
    chunk_id: str
    text: str
    score: float

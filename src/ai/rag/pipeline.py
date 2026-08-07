"""
CEOPRO AI - RAG Ingestion + Retrieval Pipeline (spec S21 groundwork).

There is no knowledge_chunks table (PENDING_ACTIONS.md #1 - blocked on
pgvector) and this module deliberately doesn't add one (schema changes are
infra's call, not this module's). Consequence: chunk text isn't persisted
anywhere of its own - indexes are rebuilt from MinIO on every call to
build_tenant_index()/build_hybrid_index(). That's correct and testable at
small/moderate document counts, but re-fetching, re-chunking, and
re-embedding every document on every retrieval call clearly doesn't scale -
which is itself a concrete argument for why the knowledge_chunks ask
matters, not just a workaround for its absence.

This module implements retrieval only (lexical + semantic + fusion), not the
"LLM reasoning" step of spec S21's RAG workflow - that requires a local LLM
decision, out of scope here (see AI_PROGRESS.md).
"""

import logging
from dataclasses import dataclass
from typing import List

from src.ai.rag import data_access
from src.ai.rag.bm25_index import BM25Index
from src.ai.rag.chunking import chunk_text
from src.ai.rag.embeddings import embed
from src.ai.rag.faiss_index import FAISSIndex
from src.ai.rag.hybrid_retrieval import reciprocal_rank_fusion
from src.ai.rag.retrieval_types import ScoredChunk

logger = logging.getLogger("CEOPRO_AI_RAG_PIPELINE")

DEFAULT_BUCKET = "ceopro-rag-knowledge"


@dataclass
class TenantIndex:
    bm25: BM25Index
    faiss: FAISSIndex


def ingest_pending_documents(conn, minio_client, tenant_id: str, bucket: str = DEFAULT_BUCKET) -> int:
    """
    Marks every 'Pending' document as 'Processed' once its text is
    successfully fetched and chunkable, or 'Failed' if fetching/decoding
    fails - spec S12: "The system must never silently discard invalid data."
    Returns the count of documents successfully processed.
    """
    pending = data_access.list_documents(conn, tenant_id, status="Pending")
    processed_count = 0

    for doc in pending:
        try:
            text = data_access.fetch_document_text(minio_client, bucket, doc["minio_object_key"])
            if not chunk_text(text):
                raise ValueError("document produced no chunks (empty or whitespace-only content)")
            data_access.mark_document_status(conn, doc["document_id"], "Processed")
            processed_count += 1
        except Exception as err:
            logger.error(f"Failed to ingest document={doc['document_id']} file={doc['file_name']}: {err}")
            data_access.mark_document_status(conn, doc["document_id"], "Failed")

    conn.commit()
    logger.info(f"Ingestion complete for tenant={tenant_id}: {processed_count}/{len(pending)} processed")
    return processed_count


def _gather_chunks(conn, minio_client, tenant_id: str, bucket: str) -> List[tuple]:
    """Fetches and chunks every 'Processed' document's current MinIO content. Shared by both index builders below."""
    documents = data_access.list_documents(conn, tenant_id, status="Processed")

    chunks = []
    for doc in documents:
        try:
            text = data_access.fetch_document_text(minio_client, bucket, doc["minio_object_key"])
        except Exception as err:
            logger.error(f"Failed to fetch document={doc['document_id']} for indexing: {err}")
            continue

        for i, chunk in enumerate(chunk_text(text)):
            chunks.append((f"{doc['document_id']}:{i}", chunk))

    logger.info(f"Gathered chunks for tenant={tenant_id}: {len(documents)} documents, {len(chunks)} chunks")
    return chunks


def build_tenant_index(conn, minio_client, tenant_id: str, bucket: str = DEFAULT_BUCKET) -> BM25Index:
    """Lexical-only index (no embedding model needed) - kept for callers that only need BM25."""
    chunks = _gather_chunks(conn, minio_client, tenant_id, bucket)
    return BM25Index(chunks)


def build_hybrid_index(conn, minio_client, tenant_id: str, bucket: str = DEFAULT_BUCKET) -> TenantIndex:
    """Builds both the lexical (BM25) and semantic (FAISS) indexes from the same chunk set."""
    chunks = _gather_chunks(conn, minio_client, tenant_id, bucket)
    texts = [text for _, text in chunks]
    embeddings = embed(texts)
    return TenantIndex(bm25=BM25Index(chunks), faiss=FAISSIndex(chunks, embeddings))


def retrieve(index: BM25Index, query_text: str, top_k: int = 5) -> List[ScoredChunk]:
    return index.query(query_text, top_k=top_k)


def retrieve_hybrid(tenant_index: TenantIndex, query_text: str, top_k: int = 5) -> List[ScoredChunk]:
    """Result fusion per spec S21's RAG workflow: STRUCTURED QUERY + BM25 + FAISS -> RESULT FUSION."""
    bm25_results = tenant_index.bm25.query(query_text, top_k=top_k)
    query_embedding = embed([query_text])[0]
    faiss_results = tenant_index.faiss.query(query_embedding, top_k=top_k)
    return reciprocal_rank_fusion(bm25_results, faiss_results, top_k=top_k)

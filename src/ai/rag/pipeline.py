"""
CEOPRO AI - RAG Ingestion + Retrieval Pipeline (spec S21 groundwork).

There is no knowledge_chunks table (PENDING_ACTIONS.md #1 - blocked on
pgvector) and this module deliberately doesn't add one (schema changes are
infra's call, not this module's). Consequence: chunk text isn't persisted
anywhere of its own - the BM25 index is rebuilt from MinIO on every call to
build_tenant_index(). That's correct and testable at small/moderate document
counts, but re-fetching and re-chunking every document on every retrieval
call clearly doesn't scale - which is itself a concrete argument for why the
knowledge_chunks ask matters, not just a workaround for its absence.

This module implements retrieval only (chunking + BM25), not the "LLM
reasoning" step of spec S21's RAG workflow - that requires a local LLM
decision, out of scope here (see AI_PROGRESS.md).
"""

import logging

from src.ai.rag import data_access
from src.ai.rag.bm25_index import BM25Index, ScoredChunk
from src.ai.rag.chunking import chunk_text

logger = logging.getLogger("CEOPRO_AI_RAG_PIPELINE")

DEFAULT_BUCKET = "ceopro-rag-knowledge"


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


def build_tenant_index(conn, minio_client, tenant_id: str, bucket: str = DEFAULT_BUCKET) -> BM25Index:
    """Rebuilds an in-memory BM25 index from every 'Processed' document's current MinIO content."""
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

    logger.info(f"Built BM25 index for tenant={tenant_id}: {len(documents)} documents, {len(chunks)} chunks")
    return BM25Index(chunks)


def retrieve(index: BM25Index, query_text: str, top_k: int = 5) -> list[ScoredChunk]:
    return index.query(query_text, top_k=top_k)

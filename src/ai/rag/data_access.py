"""
CEOPRO AI - RAG Document Data Access.
Reads/updates rag_documents_metadata (existing table, no schema change) and
fetches raw object bytes from MinIO's ceopro-rag-knowledge bucket (per
MINIO_STORAGE_ARCHITECTURE.md - this bucket is already AI-owned).

Text extraction here handles plain text (.txt) content only. PDF/DOCX
extraction is a follow-up (needs pypdf/python-docx, not added yet) - flagged
in PENDING_ACTIONS.md rather than silently mishandled.
"""

from typing import List


def list_documents(conn, tenant_id: str, status: str = None) -> List[dict]:
    query = """
        SELECT document_id, file_name, minio_object_key, processed_status
        FROM rag_documents_metadata
        WHERE tenant_id = %s
    """
    params = [tenant_id]
    if status is not None:
        query += " AND processed_status = %s"
        params.append(status)
    query += " ORDER BY uploaded_at;"

    with conn.cursor() as cursor:
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()

    return [
        {"document_id": str(row[0]), "file_name": row[1], "minio_object_key": row[2], "processed_status": row[3]}
        for row in rows
    ]


def mark_document_status(conn, document_id: str, status: str) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            "UPDATE rag_documents_metadata SET processed_status = %s WHERE document_id = %s;",
            (status, document_id),
        )


def fetch_document_text(minio_client, bucket: str, object_key: str) -> str:
    """Fetches an object from MinIO and decodes it as UTF-8 text (plain-text documents only)."""
    response = minio_client.get_object(bucket, object_key)
    try:
        return response.read().decode("utf-8")
    finally:
        response.close()
        response.release_conn()

"""
Integration test for the RAG ingestion/retrieval pipeline against a real
PostgreSQL instance (actual init_schema.sql) and a real MinIO instance.
Skipped unless both AI_TEST_DATABASE_URL and AI_TEST_MINIO_ENDPOINT are set.
"""

import io
import os
import uuid

import psycopg2
import pytest
from minio import Minio

from src.ai.rag import data_access, pipeline

DATABASE_URL = os.getenv("AI_TEST_DATABASE_URL")
MINIO_ENDPOINT = os.getenv("AI_TEST_MINIO_ENDPOINT")
MINIO_ACCESS_KEY = os.getenv("AI_TEST_MINIO_ACCESS_KEY", "minio_admin")
MINIO_SECRET_KEY = os.getenv("AI_TEST_MINIO_SECRET_KEY", "local_test_password_only")
TEST_BUCKET = "ceopro-rag-knowledge-test"

pytestmark = pytest.mark.skipif(
    not (DATABASE_URL and MINIO_ENDPOINT), reason="AI_TEST_DATABASE_URL and AI_TEST_MINIO_ENDPOINT not both set"
)


@pytest.fixture
def conn():
    connection = psycopg2.connect(DATABASE_URL)
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()


@pytest.fixture
def minio_client():
    client = Minio(MINIO_ENDPOINT, access_key=MINIO_ACCESS_KEY, secret_key=MINIO_SECRET_KEY, secure=False)
    if not client.bucket_exists(TEST_BUCKET):
        client.make_bucket(TEST_BUCKET)
    yield client


def _upload_text(minio_client, object_key: str, text: str) -> None:
    data = text.encode("utf-8")
    minio_client.put_object(TEST_BUCKET, object_key, io.BytesIO(data), length=len(data))


@pytest.fixture
def seeded_tenant(conn):
    tenant_id = str(uuid.uuid4())
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO companies (tenant_id, business_name, country_code, primary_currency)
            VALUES (%s, 'RAG Test Co', 'JO', 'JOD');
            """,
            (tenant_id,),
        )
    conn.commit()
    return tenant_id


def _insert_document(conn, tenant_id, file_name, object_key, status="Pending"):
    document_id = str(uuid.uuid4())
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO rag_documents_metadata (document_id, tenant_id, file_name, minio_object_key, processed_status)
            VALUES (%s, %s, %s, %s, %s);
            """,
            (document_id, tenant_id, file_name, object_key, status),
        )
    conn.commit()
    return document_id


def test_fetch_document_text_round_trips_through_minio(minio_client):
    _upload_text(minio_client, "test/doc1.txt", "Sunscreen SPF 50 is our best selling product.")
    text = data_access.fetch_document_text(minio_client, TEST_BUCKET, "test/doc1.txt")
    assert text == "Sunscreen SPF 50 is our best selling product."


def test_ingest_pending_documents_marks_processed(conn, minio_client, seeded_tenant):
    object_key = f"test/{uuid.uuid4()}.txt"
    _upload_text(minio_client, object_key, "Our return policy allows returns within 30 days of purchase.")
    document_id = _insert_document(conn, seeded_tenant, "policy.txt", object_key)

    processed_count = pipeline.ingest_pending_documents(conn, minio_client, seeded_tenant, bucket=TEST_BUCKET)

    assert processed_count == 1
    docs = data_access.list_documents(conn, seeded_tenant, status="Processed")
    assert len(docs) == 1
    assert docs[0]["document_id"] == document_id


def test_ingest_pending_documents_marks_failed_on_missing_object(conn, minio_client, seeded_tenant):
    _insert_document(conn, seeded_tenant, "missing.txt", "test/does-not-exist.txt")

    processed_count = pipeline.ingest_pending_documents(conn, minio_client, seeded_tenant, bucket=TEST_BUCKET)

    assert processed_count == 0
    docs = data_access.list_documents(conn, seeded_tenant, status="Failed")
    assert len(docs) == 1


def test_build_tenant_index_and_retrieve_end_to_end(conn, minio_client, seeded_tenant):
    doc1_key = f"test/{uuid.uuid4()}.txt"
    doc2_key = f"test/{uuid.uuid4()}.txt"
    _upload_text(minio_client, doc1_key, "Sunscreen SPF 50 is our best selling summer product with high UV protection.")
    _upload_text(minio_client, doc2_key, "Our warehouse policy covers moisturizer lotion storage for winter climates.")
    _insert_document(conn, seeded_tenant, "doc1.txt", doc1_key)
    _insert_document(conn, seeded_tenant, "doc2.txt", doc2_key)

    processed_count = pipeline.ingest_pending_documents(conn, minio_client, seeded_tenant, bucket=TEST_BUCKET)
    assert processed_count == 2

    index = pipeline.build_tenant_index(conn, minio_client, seeded_tenant, bucket=TEST_BUCKET)
    assert len(index) == 2  # one chunk per short document

    results = pipeline.retrieve(index, "sunscreen summer UV protection", top_k=5)
    assert len(results) > 0
    assert "Sunscreen" in results[0].text

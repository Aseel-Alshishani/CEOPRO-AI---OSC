# CEOPRO AI - Phase 1 MinIO Object Storage Architecture

## 1. Core Service Parameters
- **S3 API Port**: `9000` (Used by Backend and AI Python microservices)
- **Web Console Port**: `9001` (Used by developers for visual file inspection)
- **Root User**: `minio_admin`

## 2. Shared Isolation Rule (PostgreSQL vs MinIO)
- **PostgreSQL**: Stores structured metadata only (e.g., file name, file size, processing status, database row id, and the exact MinIO storage key).
- **MinIO**: Stores the actual raw multi-gigabyte binary files (`.csv`, `.xlsx`, `.pdf`) and heavy AI model outputs.

## 3. Production Bucket Layout & Naming Conventions
To maintain strict multi-tenancy isolation and clear data pipelines, three dedicated buckets are initialized:

### A. Bucket Name: `ceopro-raw-ingestion`
- **Purpose**: Stores all raw, unmodified user uploads (Excel sheets, POS dumps, database exports).
- **Strict Storage Path Format**: `tenant_{tenant_id}/ingestion/{file_id}_{original_name}`
- **Retention**: Read-only once written. Cleaned by the pipeline, never overwritten.

### B. Bucket Name: `ceopro-rag-knowledge`
- **Purpose**: Stores unstructured market documents, supplier PDFs, and business text files meant for the SentenceTransformers and RAG hybrid search pipeline.
- **Strict Storage Path Format**: `tenant_{tenant_id}/rag/{document_id}.pdf`

### C. Bucket Name: `ceopro-ai-artifacts`
- **Purpose**: Stores saved, trained versions of the `XGBoost` demand prediction models and text classification assets.
- **Strict Storage Path Format**: `tenant_{tenant_id}/models/{model_type}_v{version}.bin`

# CEOPRO AI - Phase 1 Complete Infrastructure Blueprint

This directory contains the production-grade foundation architecture for **CEOPRO AI Phase 1**.

## 1. Managed Technical Services (Item 1.1)
- **PostgreSQL**: Relational storage engine with multi-tenancy logical partitioning (Port `5432`).
- **Redis**: Low-latency cache memory, rate-limiter, and async transaction status coordinator (Port `6379`).
- **MinIO**: S3-compatible cloud-ready storage for raw file ingestions and model weights (Ports `9000/9001`).

## 2. Infrastructure Operations Command Checklist
Use these native Docker Compose commands to manage the infrastructure locally:
- **Launch Services Asynchronously**: `docker compose up -d`
- **Verify Operational Container States**: `docker compose ps`
- **Inspect Infrastructure Logs**: `docker compose logs -f`
- **Strict Data Reset (Wipe Volumes)**: `docker compose down -v`

## 3. Deployment Schemas & Specifications Attached
- `init_schema.sql`: Production-ready PostgreSQL tables establishing multi-tenancy isolation via the explicit `tenant_id` foreign keys (Item 1.2).
- `REDIS_ARCHITECTURE.md`: Technical documentation defining memory expiration keys and tracking patterns (Item 1.3).
- `MINIO_STORAGE_ARCHITECTURE.md`: Target bucket isolation rules and file storage paths (Item 1.4).
- `DATA_OWNERSHIP_AND_CONTRACTS.md`: Explicit microservice permissions matrix and data-transfer payloads (Items 1.5 & 1.6).
- `.env.example`: Secure production-safe template configuration file (Item 1.7).
- `check_connectivity.py`: Python automation health check confirming real-time connections pass successfully (Item 1.8).

## 4. Run Connectivity Health Check
To prove real-time access before handing over to Web App and AI teams, run:
```bash
pip install psycopg2-binary redis
python check_connectivity.py
```

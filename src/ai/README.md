# CEOPRO AI — AI/ML Service (`src/ai/`)

Owned by the AI/ML engineering track. Scope is limited to what this team owns per
[`src/infrastructure/DATA_OWNERSHIP_AND_CONTRACTS.md`](../infrastructure/DATA_OWNERSHIP_AND_CONTRACTS.md):
reading business data written by other services, producing ML model outputs, and writing to the
tables this track owns (`demand_forecasts`, `evidence_records`, `model_versions`,
`recommendation_outcomes`).

This directory intentionally does **not** touch:
- `docker-compose.yml` / any `Dockerfile.*` — infra owns container/deployment wiring.
- `src/infrastructure/database/init_schema.sql` — schema changes are infra/DB's call.
- Frontend/dashboard code — UI team's responsibility.

Dependencies for this module are isolated in [`requirements.txt`](requirements.txt) so they don't
get bundled into the backend's dependency set.

## Modules

### `forecasting/` — Phase 2, Demand Intelligence (spec §18, §23, §25)

Implements per-product daily demand forecasting against the existing `transactions` /
`products` / `demand_forecasts` / `evidence_records` / `model_versions` tables — no schema
changes required.

- `data_access.py` — reads daily aggregated demand history and product/inventory context from Postgres.
- `features.py` — builds lag/rolling/calendar features from the daily series.
- `baselines.py` — naive, seasonal-naive, and moving-average forecasts (spec §18: the model must beat these).
- `model.py` — XGBoost forecaster + expanding-window walk-forward validation.
- `evaluation.py` — MAE / RMSE / MASE, and baseline-comparison logic.
- `cold_start.py` — data-sufficiency check (spec §23 unified cold-start policy). Below the
  configured history threshold, the pipeline stays on baseline forecasts and reports low confidence
  instead of training/serving an XGBoost model.
- `evidence.py` — writes `demand_forecasts` + `evidence_records` (category `PREDICTION`) rows, and a
  `model_versions` row whenever a model is actually trained.
- `pipeline.py` — orchestrates the above: load → cold-start check → baseline (+ XGBoost if enough
  data) → pick whichever beats the baseline → persist.
- `consumer.py` — Redis Streams consumer for the `demand_forecast_requested` event contract
  (topic key `ceopro:stream:forecast_requested`, already provisioned by
  `src/infrastructure/init_broker.py`). This is the "AI / ML Forecast Engine" consumer named in the
  event contract in `DATA_OWNERSHIP_AND_CONTRACTS.md` — it does not touch or replace
  `src/infrastructure/messaging/ai_consumer.py`, which is a separate, still-unresolved ownership
  question (market-intelligence stream, not demand forecasting).

Runs CPU-only by design — no GPU dependency anywhere in this module.

### `pricing/` — Phase 5, Price Intelligence (spec §19, §23, §24)

Implements same-currency competitor price comparison against the existing `products` /
`competitors` / `competitor_prices` / `evidence_records` / `recommendation_outcomes` tables — no
schema changes required.

- `matching.py` — name-similarity matching (`difflib`) between our `products.product_name` and
  `competitor_prices.product_name_captured` (free text, no FK between them).
- `data_access.py` — reads own product price/currency and same-currency, `ALLOWED`-source, exact,
  fresh (default 30-day window) competitor prices.
- `recommendation.py` — transparent rule-based raise/lower/hold recommendation vs. the matched
  competitors' market average. Not a learned model — spec §19 requires enough price-change history
  to exist first, and there isn't any yet.
- `guardrails.py` — bounds how far a suggested price can move from the current price (default 15%).
  **Not** a margin guardrail — `products` has no cost column (see blockers below).
- `evidence.py` — reuses `forecasting.evidence.insert_evidence_record` (spec §22: one shared evidence
  architecture, not reimplemented per module) and adds `insert_recommendation_outcome`.
- `pipeline.py` — orchestrates: load own product → load same-currency competitor prices → match by
  name → no matches: `UNKNOWN` evidence (cold-start) → matches: recommendation → guardrail → persist.

Only handles spec §19's "LOCAL MARKET COMPARISON" (same currency) — "CROSS-COUNTRY COMPARISON" needs
`currency_rates`, which doesn't exist (see blockers below). CPU-only, no ML model at all currently —
purely rule-based per spec's explicit cold-start requirement for pricing.

### `rag/` — Phase 3 groundwork, retrieval only (spec §4, §6, §21)

Implements document ingestion and lexical (BM25) retrieval against the existing
`rag_documents_metadata` table and the `ceopro-rag-knowledge` MinIO bucket — no schema changes.
**Not** the full RAG chatbot: no semantic (embedding/FAISS) retrieval, no LLM reasoning step, no chat
history persistence (would need a new table). CPU-only, no transformer model at all — the lightest
tier of the stack, by design, since neither pgvector nor a chat-history table exist yet.

- `chunking.py` — word-boundary overlapping-window text chunking. Works for Arabic and English alike
  (no language-specific tokenizer, spec §8's Arabic-English code-switching requirement).
- `bm25_index.py` — in-memory BM25 index (`rank_bm25`, pure Python, no ML model). Uses **BM25Plus**,
  not the more common BM25Okapi — see the note in the file: Okapi's IDF formula is exactly zero for
  any term appearing in precisely half a small corpus, which silently zeroed out obvious matches for
  tenants with only 2-3 documents (a realistic cold-start state). Found via the live-MinIO
  integration test, not by code review.
- `data_access.py` — reads/updates `rag_documents_metadata`, fetches raw MinIO object bytes. Handles
  plain-text (`.txt`) content only — PDF/DOCX extraction isn't implemented (flagged in
  `PENDING_ACTIONS.md`).
- `pipeline.py` — `ingest_pending_documents()` (fetch → chunk-check → mark Processed/Failed, never
  silently drops a document per spec §12) and `build_tenant_index()` (rebuild a BM25 index from every
  Processed document's *current* MinIO content, since there's no `knowledge_chunks` table to persist
  chunk text in — chunks aren't stored anywhere of their own, they're recomputed on every retrieval
  call). That's correct but doesn't scale, which is itself a concrete argument for the pgvector ask
  in `PENDING_ACTIONS.md` #1, not just a workaround for its absence.

### `extraction/` — Phase 4 groundwork, rule-based NER (spec §15)

Implements the regex/rule tier of information extraction — spec §15's own explicitly-sanctioned
low-resource option ("NER may use: ... EntityRuler. Regex patterns. Fuzzy matching. Domain-specific
rules."), not a pretrained transformer. No trained model, no GPU, the lightest possible NER tier.

- `regex_patterns.py` — MONEY, CURRENCY, PERCENT, DISCOUNT, EMAIL, PHONE, INVOICE_ID, ORDER_ID, DATE.
  Currency codes are configuration-driven (spec §9), defaulting to spec's own list (JOD, EGP, SAR,
  AED, QAR, KWD, BHD, OMR, MAD, TND, DZD, USD, EUR, ZAR).
- `catalog_matching.py` — PRODUCT/COMPETITOR entity types, matched against a tenant's own known
  names rather than pattern-extracted (there's no regular pattern for a product name). Reuses
  `pricing.matching.similarity()` directly rather than a second fuzzy-matching implementation.
- `data_access.py` — reads known product/competitor names from the existing `products`/`competitors`
  tables. Nothing is written — there's no `extracted_entity` table yet (`PENDING_ACTIONS.md` #4), so
  this produces a result list with nowhere to persist to until that table exists.
- `extractor.py` — combines both into one call.

Out of scope here: ORG, PERSON, GPE, ADDRESS (spec §15's other target types) — these need world
knowledge or a trained model to extract reliably; regex/catalog-matching can't do them justice.

### Known upstream blockers (not fixed here — flagged in [`PENDING_ACTIONS.md`](../../PENDING_ACTIONS.md))

- No real transaction volume yet (`mocks/sales_transactions_mock.csv` has 3 rows) — `forecasting/`'s
  cold-start path is exercised by default until real data lands.
- No real competitor price data or scraper running — `competitor_prices` exists but is empty, so
  `pricing/`'s `UNKNOWN`-evidence path is what actually executes today.
- `model_versions` has no `artifact_path` column yet, so trained model binaries aren't persisted to
  MinIO (`ceopro-ai-artifacts`) in this first version — metrics/version metadata are still recorded
  in `model_versions` on every training run. Wiring artifact storage is a follow-up once that column
  exists.
- `products` has no `cost` column, so `pricing/guardrails.py` can only bound price-change magnitude,
  not enforce a real margin floor as spec §19 also asks for.
- pgvector / `knowledge_chunks` / Row-Level Security / `currency_rates` remain infra-owned blocking
  asks for later phases (RAG chatbot, cross-currency pricing) — out of scope for this module.
- `rag/data_access.py` decodes MinIO objects as plain UTF-8 text only — PDF/DOCX documents (which
  `MINIO_STORAGE_ARCHITECTURE.md` explicitly expects in `ceopro-rag-knowledge`) aren't extracted.
- No chat-history table exists, so RAG conversation persistence isn't implemented.
- No `extracted_entity` table exists, so `extraction/`'s output has nowhere to persist to yet —
  `extractor.py` is called directly and its result used in-memory, not written anywhere.

## Running tests

Tested against Python 3.11 (matching `Dockerfile.backend`'s target) in a clean venv — not just the
system interpreter, since dependency pins here (numpy/xgboost) don't have wheels for every Python
version. `pip install -r src/ai/requirements.txt` on anything newer than 3.11/3.12 may fail to build
numpy from source; use a 3.11 interpreter if that happens.

Pure-function modules (`baselines`, `evaluation`, `features`, `cold_start`) plus `model.py` and
`pipeline.py` (DB calls mocked out) run without a live database:

```bash
pip install -r src/ai/requirements.txt
pytest src/ai/tests
```

`test_integration_db.py` (forecasting), `test_pricing_integration_db.py` (pricing), and
`test_extraction_integration_db.py` (extraction) additionally validate the raw SQL in each module's
`data_access.py`/`evidence.py` against a real PostgreSQL instance running the actual
`init_schema.sql` — column types, JSONB casts, FK constraints, and INT rounding on
`demand_forecasts.expected_demand` are things a mocked connection can't catch. All are
skipped unless `AI_TEST_DATABASE_URL` is set, so none ever run in CI or block anyone without
Docker available. Point it at a disposable database — the tests insert and roll back rows, but don't
aim it at a shared dev database:

```bash
docker run -d --name ceopro_postgres_aitest -e POSTGRES_USER=ceopro_admin \
  -e POSTGRES_PASSWORD=local_test_password_only -e POSTGRES_DB=ceopro_platform \
  -p 5433:5432 postgres:15-alpine
psql "postgresql://ceopro_admin:local_test_password_only@localhost:5433/ceopro_platform" \
  -f src/infrastructure/database/init_schema.sql
AI_TEST_DATABASE_URL="postgresql://ceopro_admin:local_test_password_only@localhost:5433/ceopro_platform" \
  pytest src/ai/tests
docker rm -f ceopro_postgres_aitest
```

`test_consumer.py` covers `ForecastRequestConsumer` (payload validation, and the same
publish/xreadgroup/handle/xack cycle `listen()` uses) against a real Redis — constructing the
consumer calls `xgroup_create` eagerly, so a mocked client can't stand in for this one. Skipped
unless `AI_TEST_REDIS_HOST` is set:

```bash
docker run -d --name ceopro_redis_aitest -p 6380:6379 redis:7-alpine
AI_TEST_REDIS_HOST=localhost AI_TEST_REDIS_PORT=6380 pytest src/ai/tests/test_consumer.py
docker rm -f ceopro_redis_aitest
```

`test_rag_integration.py` covers `rag/data_access.py` and `rag/pipeline.py` against real Postgres
*and* real MinIO together — skipped unless both `AI_TEST_DATABASE_URL` and `AI_TEST_MINIO_ENDPOINT`
are set:

```bash
docker run -d --name ceopro_minio_aitest -p 9002:9000 \
  -e MINIO_ROOT_USER=minio_admin -e MINIO_ROOT_PASSWORD=local_test_password_only \
  minio/minio server /data
# ... plus the disposable postgres container from above, with its schema loaded ...
AI_TEST_DATABASE_URL="postgresql://ceopro_admin:local_test_password_only@localhost:5433/ceopro_platform" \
AI_TEST_MINIO_ENDPOINT="localhost:9002" \
  pytest src/ai/tests/test_rag_integration.py
docker rm -f ceopro_minio_aitest
```

See [`AI_PROGRESS.md`](../../AI_PROGRESS.md) at the repo root for the dated log of what's been built,
what tests found, and what's still blocked. Items that need action from another team or a human
outside this track are tracked separately in [`PENDING_ACTIONS.md`](../../PENDING_ACTIONS.md).

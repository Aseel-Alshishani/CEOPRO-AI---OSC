# CEOPRO AI — AI/ML Service (`src/ai/`)

Owned by the AI/ML engineering track. Scope is limited to what this team owns per
[`src/infrastructure/DATA_OWNERSHIP_AND_CONTRACTS.md`](../infrastructure/DATA_OWNERSHIP_AND_CONTRACTS.md):
reading business data written by other services, producing ML model outputs, and writing to the
tables this track owns (`demand_forecasts`, `evidence_records`, `model_versions`).

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

### Known upstream blockers (not fixed here — flagged for the relevant owning team)

- No real transaction volume yet (`mocks/sales_transactions_mock.csv` has 3 rows) — the cold-start
  path is exercised by default until real data lands.
- `model_versions` has no `artifact_path` column yet, so trained model binaries aren't persisted to
  MinIO (`ceopro-ai-artifacts`) in this first version — metrics/version metadata are still recorded
  in `model_versions` on every training run. Wiring artifact storage is a follow-up once that column
  exists.
- pgvector / `knowledge_chunks` / Row-Level Security / `currency_rates` remain infra-owned blocking
  asks for later phases (RAG chatbot, cross-currency pricing) — out of scope for this module.

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

`test_integration_db.py` additionally validates the raw SQL in `data_access.py`/`evidence.py`
against a real PostgreSQL instance running the actual `init_schema.sql` — column types, JSONB
casts, FK constraints, and INT rounding on `demand_forecasts.expected_demand` are things a mocked
connection can't catch. It's skipped unless `AI_TEST_DATABASE_URL` is set, so it never runs in CI or
blocks anyone without Docker available. Point it at a disposable database — the test inserts and
rolls back rows, but don't aim it at a shared dev database:

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

See [`AI_PROGRESS.md`](../../AI_PROGRESS.md) at the repo root for the dated log of what's been built,
what tests found, and what's still blocked.

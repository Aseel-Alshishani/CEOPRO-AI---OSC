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

Pure-function modules (`baselines`, `evaluation`, `features`, `cold_start`) are unit-testable
without a live database:

```bash
pip install -r src/ai/requirements.txt
pytest src/ai/tests
```

`pipeline.py` and `consumer.py` require `DATABASE_URL` / `REDIS_HOST` / `REDIS_PORT` (same env vars
as the rest of the platform, see `.env.example`) and are not covered by the offline test suite.

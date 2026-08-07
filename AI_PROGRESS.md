# CEOPRO AI — AI/ML Engineering Progress Log

**Owner:** AI/ML Engineering
**Tracks:** implementation progress against `MASTER_SPEC_v4.md`'s AI phases (§18–§27, Phase 2 onward).
**Update convention:** append-only, date-stamped entries at the bottom. Don't edit or delete past
entries — if something is superseded, add a new entry that says so and link back. Mirrors the
convention in `AI_PLAN_AND_CONTRACT_UPDATES.md` and `src/infrastructure/CONTRACT_CHANGELOG.md`.

This file lives at the repo root so it stays alongside `MASTER_SPEC_v4.md` and
`AI_PLAN_AND_CONTRACT_UPDATES.md`. Module-level implementation detail lives in
[`src/ai/README.md`](src/ai/README.md); this file tracks status and history, not how the code works.

---

## Module status

| Spec phase | Module | Status | Notes |
|---|---|---|---|
| Phase 2 — Demand Intelligence (§18, §23, §25) | `src/ai/forecasting/` | 🟢 Built, tested (unit + integration) | Baselines, XGBoost + walk-forward validation, cold-start policy, evidence writers, Redis consumer. See entries below. |
| Phase 3 — RAG Chatbot (§21) | — | ⚪ Not started | Blocked: needs pgvector + `knowledge_chunks` (infra-owned blocking ask, see `AI_PLAN_AND_CONTRACT_UPDATES.md`). |
| Phase 4 — Market Intelligence (§15, §16, §17) | — | ⚪ Not started | Blocked: schema has no `reviews`/`news_record`/`social_mention`/`extracted_entity`/`sentiment_result` tables yet. |
| Phase 5 — Price Intelligence (§19) | — | ⚪ Not started | `competitors`/`competitor_prices`/`recommendation_outcomes` tables exist, but `competitor_prices` is empty (no scraper/ingestion running yet) — nothing to build against. |
| Phase 6 — Competitor Ranking (§20) | — | ⚪ Not started | Same data gap as Phase 5. |

Legend: 🟢 built and tested · 🟡 in progress · 🟠 blocked on another team · ⚪ not started.

---

## 2026-08-07 — Phase 2 Demand Forecasting: built, bug-fixed, and verified against a real database

**Built** `src/ai/forecasting/` (spec §18 Demand Forecasting, §23 Cold-Start Policy, §25 Model
Evaluation) — self-contained, no changes to `docker-compose.yml`, `Dockerfile.*`, schema, or
frontend. Reads `transactions`/`products`/`inventory`, writes `demand_forecasts`/
`evidence_records`/`model_versions` — all pre-existing tables, no migration needed.

- Baseline forecasters (naive, seasonal-naive, moving-average, previous-period) — spec requires the
  model to beat these before its forecast is trusted.
- XGBoost forecaster with expanding-window walk-forward validation (MAE/RMSE/MASE).
- Cold-start policy (§23): below a configurable history threshold (default 30 days), the pipeline
  stays on the best-backtested baseline and reports `confidence_status: BUILDING` instead of
  training/serving a model on insufficient data.
- Evidence writers: every forecast produces a `demand_forecasts` row plus an `evidence_records` row
  (category `PREDICTION`, per spec §22's shared evidence schema) explaining which source was used
  and why.
- Redis consumer (`consumer.py`) for the `demand_forecast_requested` event contract (topic
  `ceopro:stream:forecast_requested`, already provisioned by `src/infrastructure/init_broker.py`).
  This is a separate consumer from `src/infrastructure/messaging/ai_consumer.py` (market-intelligence
  stream) — that file's ownership is a separate open question tracked in
  `AI_PLAN_AND_CONTRACT_UPDATES.md`, not touched here.

**Testing surfaced two real bugs**, both fixed:
1. `features.py` set a missing `current_stock` to `pd.NA`; pandas/XGBoost can't cast that to
   `float` (`TypeError: float() argument must be ... not 'NAType'`). Fixed to `np.nan`.
2. `pipeline.py` double-nested a dict lookup building the XGBoost explanation string
   (`metrics["baseline_scores"]["scores"]` when `metrics["baseline_scores"]` was already the scores
   dict) — a `KeyError` that only fired on the path where the model actually won.

Neither bug was visible from a `py_compile` syntax check or code review alone — both only surfaced
once the code actually ran (`test_model.py`'s walk-forward correctness test, and `test_pipeline.py`'s
mocked-DB run of the XGBoost-wins branch).

**Verified against a real PostgreSQL instance**, not just mocks: spun up an isolated, disposable
`postgres:15-alpine` container (port 5433, separate from the existing long-running `ceopro_postgres`
dev container — that one was left untouched), loaded the actual `init_schema.sql`, and ran
`test_integration_db.py` against it. This exercises the raw SQL in `data_access.py`/`evidence.py`
that unit tests with a mocked connection cannot validate: column types, JSONB round-tripping,
foreign key constraints, and `demand_forecasts.expected_demand` being an `INT` column (confirmed
`12.7` rounds to `13`, not silently truncated or rejected). All 5 integration tests passed; the test
file is skipped automatically (`AI_TEST_DATABASE_URL` unset) everywhere else, so it doesn't affect
CI or require Docker on every machine.

**Full local verification, Python 3.11.9 (matching `Dockerfile.backend`'s target)**:
- `pytest src/ai/tests`: 31 passed (26 unit/offline + 5 live-DB integration), 0 failed.
- `flake8 --select=E9,F63,F7,F82` (the CI's blocking check): 0 errors.
- `flake8 --max-complexity=10 --max-line-length=127` (CI's non-blocking check): 0 issues after
  cleanup (11 line-length violations fixed).

**Commits:** `4d812fc` (initial module), `f5f9e7a` (bug fixes + model/pipeline test coverage). This
entry's integration test work lands in the next commit.

**Still open / blocked (not fixed here, flagged for the owning team — see
`AI_PLAN_AND_CONTRACT_UPDATES.md` for the full list):**
- pgvector / `knowledge_chunks` / Row-Level Security / `currency_rates` — infra-owned, blocking
  Phases 3 and cross-currency logic.
- `model_versions.artifact_path` column doesn't exist yet, so trained model binaries aren't
  persisted to MinIO (`ceopro-ai-artifacts`) — metrics/version metadata are still recorded on every
  training run, just not the binary itself.
- `src/infrastructure/messaging/ai_consumer.py` ownership collision — unresolved, needs a decision
  from whoever owns both sides.
- No real transaction volume anywhere yet (`mocks/sales_transactions_mock.csv` has 3 rows) — the
  cold-start path is what actually runs until real data lands; the XGBoost path is validated against
  synthetic data (`test_model.py`) and a seeded integration DB (`test_integration_db.py`), not yet
  against production data because none exists.

## 2026-08-07 — Redis consumer verified against a real Redis instance

Extended the same "verify against real infra, not mocks" approach from the earlier entry today to
`consumer.py`: `ForecastRequestConsumer.__init__` calls `xgroup_create` eagerly against a real Redis
connection (a `ConnectionError` there isn't caught), so it can't be constructed against a mocked
client the way `pipeline.run_forecast`'s DB calls could be mocked in `test_pipeline.py`.

Spun up an isolated, disposable `redis:7-alpine` container (port 6380 — separate from the existing
long-running `ceopro_redis` dev container, which was left untouched, same as the Postgres container
in the earlier entry). Added `src/ai/tests/test_consumer.py`, 6 tests:
- Consumer group is actually created on the stream at construction time.
- Payload validation (`_handle_message`) rejects messages missing `tenant_id`/`product_id`.
- `horizon_days` is correctly parsed from the payload string and defaults to 7 when absent.
- A full publish → `xreadgroup` → handle → `xack` cycle — the same sequence `listen()`'s loop uses —
  leaves zero pending messages afterward, confirmed via `XPENDING`.

All 6 passed on the first run — no bugs found this time (the consumer's logic is small and the
earlier `pipeline.py`/`features.py` fixes had already been exercised by `test_pipeline.py`).

Skipped automatically unless `AI_TEST_REDIS_HOST` is set, so this doesn't affect CI or require
Docker on every machine, matching the `test_integration_db.py` convention.

**Full suite after this addition:** 37 tests total (26 fully offline, 5 live-Postgres, 6 live-Redis).
Confirmed via two runs: all 11 integration/consumer tests skip cleanly with no env vars set
(26 passed, 11 skipped), and all 37 pass when both `AI_TEST_DATABASE_URL` and `AI_TEST_REDIS_HOST`
are set against disposable containers. `flake8` (both the CI's blocking and non-blocking checks):
0 issues.

**Still not covered by any test:** the `listen()` method's own `while True` loop, `KeyboardInterrupt`
handling, and its `finally`-block cleanup — only the per-message handling logic it calls is tested.
Low risk (it's a thin wrapper around already-tested pieces) but worth naming explicitly rather than
leaving it implied.

## How to add an entry

1. New date-stamped `##` section at the bottom (never edit history).
2. State what was built/changed, what testing was done, and what it found.
3. Update the Module status table above to match.
4. If it closes or reopens an item in `AI_PLAN_AND_CONTRACT_UPDATES.md`, say so there too, in that
   file's own dated-entry convention.

# CEOPRO AI — AI/ML Engineering Progress Log

**Owner:** AI/ML Engineering
**Tracks:** implementation progress against `MASTER_SPEC_v4.md`'s AI phases (§18–§27, Phase 2 onward).
**Update convention:** append-only, date-stamped entries at the bottom. Don't edit or delete past
entries — if something is superseded, add a new entry that says so and link back. Mirrors the
convention in `AI_PLAN_AND_CONTRACT_UPDATES.md` and `src/infrastructure/CONTRACT_CHANGELOG.md`.

This file lives at the repo root so it stays alongside `MASTER_SPEC_v4.md` and
`AI_PLAN_AND_CONTRACT_UPDATES.md`. Module-level implementation detail lives in
[`src/ai/README.md`](src/ai/README.md); this file tracks status and history, not how the code works.
Anything that needs action from a different team or a human outside this track (schema asks,
ownership decisions, broken CI references, security flags) is **not** duplicated here — it's tracked
in [`PENDING_ACTIONS.md`](PENDING_ACTIONS.md) so it stays visible without digging through this log.

---

## Module status

| Spec phase | Module | Status | Notes |
|---|---|---|---|
| Phase 2 — Demand Intelligence (§18, §23, §25) | `src/ai/forecasting/` | 🟢 Built, tested (unit + integration) | Baselines, XGBoost + walk-forward validation, cold-start policy, evidence writers, Redis consumer. See entries below. |
| Phase 3 — RAG Chatbot (§21) | `src/ai/rag/` | 🟡 Retrieval built/tested; chatbot itself not started | Document ingestion + BM25 lexical retrieval built against existing `rag_documents_metadata` + MinIO — doesn't need pgvector. Still missing: semantic/FAISS retrieval, LLM reasoning step, chat history (needs a new table). See entry below. |
| Phase 4 — Market Intelligence (§15, §16, §17) | `src/ai/extraction/` | 🟡 Rule-based NER built/tested; sentiment + persistence not started | Regex extraction (MONEY/CURRENCY/PERCENT/DISCOUNT/EMAIL/PHONE/INVOICE_ID/ORDER_ID/DATE) + catalog matching (PRODUCT/COMPETITOR) built. No `extracted_entity` table to write results to yet; sentiment analysis and ORG/PERSON/GPE entity types not started (need a heavier pretrained model — deferred, see `AI_PROGRESS.md`'s compute-tier discussion). See entry below. |
| Phase 5 — Price Intelligence (§19) | `src/ai/pricing/` | 🟢 Built, tested (unit + integration) | Product matching, rule-based recommendation, price-change guardrail, evidence + recommendation_outcomes writers. See entry below. Margin guardrails are weaker than spec'd — `products` has no cost column (`PENDING_ACTIONS.md` #14). Real competitor price data still doesn't exist (`PENDING_ACTIONS.md` #5), so the cold-start/UNKNOWN path is what actually runs today, same as Phase 2. |
| Phase 6 — Competitor Ranking (§20) | — | ⚪ Not started | Same data gap as Phase 5 (`PENDING_ACTIONS.md` #5). |

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

## 2026-08-07 — `listen()` loop coverage gap (flagged in the previous entry) closed

The previous entry named an explicit gap: `listen()`'s own `while True` loop, `KeyboardInterrupt`
handling, and `finally`-block cleanup weren't tested, only the per-message logic it calls. Closed
that with 4 more tests in `test_consumer.py`, using the already-live disposable Redis container plus
`psycopg2.connect` mocked out (no live Postgres needed for these):

- `xreadgroup` raising `KeyboardInterrupt` (simulating Ctrl+C during the blocking read) is caught
  internally — `listen()` doesn't raise — and both the DB connection and the Redis client get
  `.close()`d in the `finally` block.
- An empty `xreadgroup` response (`[]`, i.e. the poll timed out with nothing new) doesn't stop the
  loop — it just polls again.
- A malformed message (missing `tenant_id`) inside the loop triggers a rollback and the loop
  continues to the next poll, without the bad message ever being acked.
- A successfully processed message is acked exactly once, with the right stream/group/message-id
  arguments, and does not trigger a rollback.

All 4 passed. Full suite is now 41 tests (26 offline, 5 live-Postgres, 10 live-Redis). Verified: with
only Redis available (no `AI_TEST_DATABASE_URL`), 36 pass and 5 skip; with neither live-infra env var
set, all 26 offline tests pass and the remaining 15 skip cleanly. `flake8` clean on both checks.

No further known test gaps in `src/ai/forecasting/` as of this entry.

## 2026-08-07 — Phase 5 Price Intelligence built and tested: `src/ai/pricing/`

Built `src/ai/pricing/` (spec §19 Price Intelligence, relevant parts of §20's normalization
principle, §23 cold-start, §24 recommendation outcomes) against the existing `products`,
`competitors`, `competitor_prices`, `evidence_records`, and `recommendation_outcomes` tables — again
no schema changes, no infra/UI files touched.

- `matching.py` — name-similarity product matching (`difflib.SequenceMatcher`, no new dependency).
  `competitor_prices.product_name_captured` is free text with no `product_id` FK, so matching to our
  own catalog can't be a join; spec §37's cold-start guidance for product matching ("use rules and
  fuzzy matching with more manual confirmation") calls for exactly this, with a conservative default
  threshold (0.82) that trades recall for not silently comparing different products.
- `data_access.py` — reads own product price/currency, and competitor prices filtered to
  same-currency, `ALLOWED` source status, exact data, and a freshness window (default 30 days).
  Cross-currency comparison is explicitly out of scope here — it needs `currency_rates`
  (`PENDING_ACTIONS.md` #3), which doesn't exist. This only ever does spec §19's "LOCAL MARKET
  COMPARISON", never "CROSS-COUNTRY COMPARISON".
- `recommendation.py` — transparent, rule-based market-average comparison (raise/lower/hold),
  deliberately not a learned model: spec §19 says "Learned pricing must remain disabled until enough
  historical price-change data exists," and `recommendation_outcomes` is currently empty, so there
  is no such history yet.
- `guardrails.py` — bounds how far a suggested price can move from the current price (default 15%).
  **This is not the margin guardrail spec §19 also asks for** — that needs a cost/COGS basis, and
  `products` has no cost column. Flagged as a new item, `PENDING_ACTIONS.md` #14.
- `evidence.py` — reuses `insert_evidence_record` from `forecasting.evidence` directly rather than
  duplicating it (spec §22: "one consistent evidence architecture," and the function was already
  generic, not forecast-specific). Adds `insert_recommendation_outcome`, writing a
  `recommendation_outcomes` row at recommendation time per spec §24 ("every recommendation must
  create a RECOMMENDATION_OUTCOME record"), `action_taken` left at the table's `ignored` default
  until a human actually acts on it.
- `pipeline.py` — orchestrates: load own product → load same-currency competitor prices → match by
  name → no matches: `UNKNOWN` evidence (cold-start path, same pattern as forecasting) → matches:
  rule-based recommendation → guardrail → persist evidence + outcome row.

**Testing:** 23 offline tests (matching, guardrails, recommendation math, pipeline with DB mocked
out) plus 4 live-Postgres integration tests (real schema, seeded competitor prices, checks the
`RECOMMENDATION`/`UNKNOWN` evidence category and the `recommendation_outcomes` row land correctly,
including the `ignored` default). All 27 passed — no bugs found this time, unlike the forecasting
module's first pass; the pattern established there (mocked unit tests + a real seeded database) may
simply be catching more before code is even run for the first time.

**Full combined suite verified**: 68 tests total (forecasting 41 + pricing 27). Ran three ways: no
live-infra env vars (49 pass, 19 skip), Postgres only (58 pass, 10 skip — Redis-only tests skip), and
both Postgres + Redis up (all 68 pass). `flake8` clean on both checks after fixing 9 line-length
violations introduced by this addition.

**Commit:** lands in the next commit after this entry.

**Known limitations (flagged in `PENDING_ACTIONS.md`, not fixed here):**
- Margin guardrails are weaker than spec'd — no `cost` column on `products` (#14).
- Nothing to actually run this against yet — `competitor_prices` is empty; the cold-start/`UNKNOWN`
  path is what executes today, same situation forecasting is in with real transaction volume (#5).
- Cross-currency comparison isn't implemented — blocked on `currency_rates` (#3), same as before.

## 2026-08-07 — Pinball Loss added; Phase 3 RAG retrieval groundwork built (CPU-only, no pgvector)

Asked to prioritize and build everything possible without needing heavy compute (no GPU, nothing
"super computer"-scale). Two pieces landed:

**Pinball Loss** (`forecasting/evaluation.py`, spec §25's "Pinball Loss where applicable"): standard
quantile-loss metric, added alongside MAE/RMSE/MASE. Not currently wired into `pipeline.py` — the
forecaster produces point forecasts, not quantile forecasts, so there's nothing to score with it yet.
It's there for when/if quantile regression is added. 5 new tests, all offline.

**`src/ai/rag/`** (spec §4/§6/§21): document ingestion + BM25 lexical retrieval, deliberately **not**
the full RAG chatbot. This is retrieval-only groundwork:

- `chunking.py` — word-boundary overlapping chunking, works for Arabic and English without a
  language-specific tokenizer.
- `bm25_index.py` — BM25 index, `rank_bm25` (pure Python, no trained model, the lightest possible
  tier).
- `data_access.py` — reads/updates `rag_documents_metadata` (existing table), fetches raw bytes from
  the `ceopro-rag-knowledge` MinIO bucket (existing, AI-owned per `MINIO_STORAGE_ARCHITECTURE.md`).
  Plain-text only for now — PDF/DOCX extraction not implemented (new item, `PENDING_ACTIONS.md`).
- `pipeline.py` — ingest (fetch → chunk-check → mark Processed/Failed, spec §12's "never silently
  discard invalid data") and retrieval (rebuild a BM25 index from every Processed document's current
  MinIO content). No `knowledge_chunks` table exists, so chunk text isn't persisted anywhere - the
  index is recomputed from MinIO on every call. Documented plainly as a scaling limitation, and as a
  concrete argument *for* the pgvector ask rather than a reason it's unnecessary.

**A key finding: none of this needed pgvector.** `MASTER_SPEC_v4.md` §4 and §6 name **FAISS + BM25**
as the platform's default retrieval stack - standalone libraries, not a Postgres extension. The
pgvector/`knowledge_chunks` ask comes from the still-missing `AI_CONTRACT_CHANGES_AND_CLARIFICATIONS.md`,
not the master spec itself. So lexical (BM25) retrieval was buildable today; semantic (embedding +
FAISS) retrieval is a separate, still-open follow-up - lighter than an LLM, but not done in this pass.

**Testing caught a real bug, again by running against real infra rather than mocks:** with only 2
documents in the corpus, `rank_bm25`'s default `BM25Okapi` computed an IDF of exactly `0.0` for every
term (each term appeared in precisely 1 of 2 documents, and Okapi's classic IDF formula
`log((N-df+0.5)/(df+0.5))` is exactly zero at that ratio) - meaning **obviously relevant results
scored zero and were silently dropped**. This is a real risk for the actual use case: SME tenants
with only a handful of uploaded documents is a realistic cold-start state, not a test artifact.
Switched to `BM25Plus`, which adds a delta term guaranteeing strictly positive IDF regardless of
corpus size. Caught by `test_rag_integration.py` (live Postgres + live MinIO), not by the 14 offline
unit tests, which used corpora too small to trigger it until the integration test's realistic
2-document scenario.

**Full suite: 91 tests** (forecasting 46, pricing 27, rag 18). Verified passing/skipping correctly
with no live infra (68 pass, 23 skip), and with Postgres + MinIO up (all applicable tests pass).
`flake8` clean.

**New/updated items in `PENDING_ACTIONS.md`:** PDF/DOCX extraction not implemented (new); the
pgvector ask (#1) now has a concrete efficiency argument attached, not just the semantic-search one.

## 2026-08-07 — Phase 4 rule-based NER built: `src/ai/extraction/`

Third item off the "no heavy compute" prioritized list. Implements spec §15's own explicitly-named
low-resource option — "NER may use: ... EntityRuler. Regex patterns. Fuzzy matching. Domain-specific
rules." — not a placeholder ahead of a transformer, but the spec's sanctioned starting tier.

- `regex_patterns.py` — MONEY, CURRENCY, PERCENT, DISCOUNT, EMAIL, PHONE, INVOICE_ID, ORDER_ID, DATE.
  Currency list is configuration-driven (spec §9), defaulting to spec's own 14-currency list.
- `catalog_matching.py` — PRODUCT/COMPETITOR entity types, matched against a tenant's own known
  names (candidate spans from capitalized word runs, scored via `pricing.matching.similarity()` —
  reused directly rather than reimplemented, spec §22's "one consistent approach" principle applied
  beyond just evidence records).
- `data_access.py` — reads known product/competitor names from existing tables. Writes nothing —
  there's no `extracted_entity` table (`PENDING_ACTIONS.md` #4), so results have nowhere to persist.
- `extractor.py` — combines both into one call.

Out of scope: ORG, PERSON, GPE, ADDRESS (spec §15's other target types) — these need world knowledge
or a trained model; regex/catalog-matching can't do them justice. Sentiment analysis (spec §16) also
not started this round — both are the "medium compute" tier flagged when this prioritized list was
first laid out, deliberately after the lighter items.

**Testing caught a real bug**, this time in the very first full test run rather than needing live
infra to surface it: `extract_order_id("Your order #A4821X has shipped")` returned nothing. The
regex required the `-`/`#` separator to immediately follow `ORDER` with no space
(`(?:ORD|ORDER)[-#]?\s?(...)`), but real text has the separator *after* a space (`"order #A4821X"`,
not `"order#A4821X"`). Fixed by allowing optional whitespace before the separator too, in both the
`INVOICE_ID` and `ORDER_ID` patterns (the latter's test happened not to exercise this, but the same
bug was latent there).

**Full suite: 119 tests** (forecasting 46, pricing 27, rag 18, extraction 28: 25 offline + 3
live-Postgres). Verified passing/skipping correctly with no live infra (93 pass, 26 skip) and with
Postgres up (all applicable pass). `flake8` clean.

No new `PENDING_ACTIONS.md` items — the `extracted_entity` table gap was already implied by item #4,
now made concrete: the extraction logic itself is no longer the blocker, only the persistence table.

## How to add an entry

1. New date-stamped `##` section at the bottom (never edit history).
2. State what was built/changed, what testing was done, and what it found.
3. Update the Module status table above to match.
4. If it closes or reopens an item in `AI_PLAN_AND_CONTRACT_UPDATES.md`, say so there too, in that
   file's own dated-entry convention.

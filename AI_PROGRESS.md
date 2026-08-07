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
| Phase 3 — RAG Chatbot (§21) | `src/ai/rag/` | 🟡 Hybrid (lexical + semantic) retrieval built/tested; chatbot itself not started | Document ingestion + BM25 + FAISS semantic retrieval + Reciprocal Rank Fusion, all against existing `rag_documents_metadata` + MinIO — none of it needs pgvector. Still missing: LLM reasoning step, chat history (needs a new table). A real fusion edge case found and documented (not fixed — inherent BM25 behavior on very short chunks). See entries below. |
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

## 2026-08-07 — Semantic (FAISS) retrieval + hybrid fusion added to `src/ai/rag/`

Fourth and final item off the original no-heavy-compute prioritized list (item 5, sentiment, is a
separate, heavier follow-up — see note at the end of this entry). Confirmed feasibility first: a real
multilingual embedding model (`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, 384-dim,
~470MB) downloads and runs on CPU in this environment — ~140s first download, ~20-30s per fresh
process even cached (still checks the HF Hub), fast for repeat calls within one process. Confirmed
cross-lingual understanding directly: English "Sunscreen is our best selling product" vs. Arabic
"واقي الشمس هو المنتج الأكثر مبيعا لدينا" (same meaning) scored 0.64 cosine similarity — clearly
higher than an unrelated sentence in either language.

Built:
- `embeddings.py` — thin wrapper, lazy-loaded and cached per model name.
- `faiss_index.py` — flat inner-product index (embeddings are L2-normalized, so this is cosine
  similarity; exact search, no approximate-index tuning needed at per-tenant corpus sizes).
- `hybrid_retrieval.py` — Reciprocal Rank Fusion, unweighted, combining BM25 + FAISS rankings.
- `pipeline.py` extended with `build_hybrid_index()`/`retrieve_hybrid()` alongside the existing
  BM25-only path (kept, for callers that don't need the embedding model at all).
- Deduplicated `ScoredChunk` (previously defined identically in both `bm25_index.py` and the new
  `faiss_index.py`) into a shared `retrieval_types.py`.

**A real, documented (not "fixed") limitation found via the live-embeddings integration test**: with
very short chunks (single sentences, 10-13 tokens) and a query with exactly one genuine keyword match
to one document, BM25's own document-length normalization can rank a *zero-match* document above the
one-match document — completely standard, correct BM25 behavior (shorter documents get a length-norm
boost), but counterintuitive at sentence-length chunks where BM25's normalization assumptions (tuned
for paragraph/page-length documents) have an outsized effect. When this happened, FAISS ranked the
opposite way, and unweighted Reciprocal Rank Fusion produced a near-tie that didn't reliably surface
the "obviously correct to a human" answer. This isn't a coding bug — verified BM25Plus's `idf`/`delta`
math by hand — it's a property of applying paragraph-tuned BM25 to sentence-length chunks. **Not
fixed** (would mean either a length-normalization tweak or a weighted, tuned fusion — both real design
decisions, not obvious defaults, and out of scope for what was asked). Documented in `rag/README`
(`src/ai/README.md`) and in the integration test itself, with a query chosen to demonstrate hybrid
retrieval's real value (zero-lexical-overlap query, letting FAISS's semantic ranking pass through
cleanly) rather than one that happened to hit the fragile case.

**Full suite: 136 tests** (forecasting 46, pricing 27, rag 35, extraction 28). Verified three ways: no
live infra/opt-in flags (104 pass, 32 skip), Postgres+MinIO+embeddings all up (126 pass, 10 skip —
only the Redis consumer tests, not requested this round), confirming nothing regressed. `flake8`
clean.

**On item 5 (sentiment) from the original prioritized list**: not started this round. It needs a
noticeably heavier pretrained transformer (~250-550M params, vs. the ~470MB/fast-CPU embedding model
here) and — more fundamentally — there's no source text to run it on yet (`reviews`, `news_record`,
`social_mention` tables don't exist, `PENDING_ACTIONS.md` #4). Building the classifier wrapper alone
without any real text to validate it against would be much lower-confidence work than everything
built so far, all of which was verified against real data through real infra.

## 2026-08-07 — Rechecked repo for team changes; two schema blockers closed, two new issues found

`git fetch` showed 2 new commits on `main` since last checked (`537a207` watchdog.py, `01d7d43`
init_schema.sql), from the infra track — not this branch. Audited both directly rather than assuming
from the commit messages. No AI/ML code was written this round; investigation and doc updates only.

**Schema update (`01d7d43`) — good news first:**
- `currency_rates` table landed. **`PENDING_ACTIONS.md` #3 closed.** Cross-currency pricing is now
  schema-buildable (not yet wired into `src/ai/pricing/`, which still only does same-currency
  comparison — that's now unblocked future work, not a pending action anymore).
- `reviews` and `sentiment_results` tables landed. **`PENDING_ACTIONS.md` #4 partially closed** —
  sentiment analysis (spec §16) is now fully unblocked: there's source text to run it on and a table
  to write results to. `extracted_entity`, `news_record`, `social_mention` are still missing, so NER
  persistence and news/social-based intelligence remain blocked.
- `pgvector` extension + a `rag_document_chunks` table (with a `VECTOR(1024)` column) were added,
  aimed at `PENDING_ACTIONS.md` #1. **Tested this directly rather than trusting it works**: loaded
  the new `init_schema.sql` against a real, plain `postgres:15-alpine` container (the same image
  `docker-compose.yml` still references) and got `ERROR: extension "vector" is not available` —
  `docker-compose.yml`'s postgres service was never switched to a pgvector-enabled image (e.g.
  `pgvector/pgvector:pg15`). The schema change alone doesn't make item #1 deployable; logged as new
  item #17. `products`/`competitors` also gained audit columns (`source`, `created_by_user_id`,
  soft-delete on products, `is_active` on competitors) and a new `product_price_history` table —
  none of these change anything in `src/ai/`, no action needed.

**watchdog.py update (`537a207`) — mixed:**
- The hardcoded Postgres password fallback flagged in `PENDING_ACTIONS.md` #10 is fixed —
  `DATABASE_URL` is now required, no embedded credential. **#10 closed.**
- But the same commit broke the file: it literally committed the PowerShell here-string wrapper used
  to write it (`@'` as line 1, `'@ | Out-File -FilePath ... -Encoding utf8` as the last line) instead
  of just the Python content inside it. Confirmed with `ast.parse()`:
  `SyntaxError: invalid non-printable character U+FEFF` at line 1 — the file won't import or run at
  all. This isn't cosmetic: `.github/workflows/staging-deployment.yml` runs
  `python src/infrastructure/monitoring/watchdog.py` directly as a deploy step. Logged as new item
  #16.

**Still open, unchanged**: RLS (#2), `ai_consumer.py` ownership question (#6), `model_versions.artifact_path`
(#7), `Dockerfile.ai`/CI reference (#8), root `requirements.txt` (#9), `products.cost` (#14), PDF/DOCX
extraction (#15, self-flagged), the three missing AI planning docs (#11), `MASTER_SPEC_v4.md`/
`AI_PLAN_AND_CONTRACT_UPDATES.md` still unmerged to `main` (#12, `noorhassouneh-patch-1` unchanged),
Orange infra confirmation (#13, deferred).

**PR #2** (this branch's work) is still open on GitHub, mergeable, no reviews or comments yet.

**No implementation started this round** per instruction — newly-unblocked work (wiring
`currency_rates` into pricing, building the sentiment classifier now that `reviews`/`sentiment_results`
exist) is real future work, not done here, since this was a status check, not a build round.

## 2026-08-07 — Fixed real conflicts from the team's schema update; PR #2 confirmed merged

Since the last entry, PR #2 was merged into `main` (2026-08-07 16:04 UTC, merge commit `d908fd3`) — all
of `src/ai/` is now on `main`. Went looking for bugs/conflicts the team's schema update (previous
entry) might have introduced against our existing queries, rather than assuming the additive-looking
columns were harmless.

**Found real ones**: the schema update added `products.deleted_at` (soft-delete) and
`competitors.is_active`, with partial indexes on both (`WHERE deleted_at IS NULL`,
`WHERE is_active = TRUE`) signaling the intended query pattern. None of our existing `SELECT` queries
against `products`/`competitors` filtered on either column, meaning a soft-deleted product or a
deactivated competitor would silently still show up in forecasting context, price recommendations, and
NER catalog matching — not a crash, a quiet correctness bug that would only surface as "why is this
deleted product still being forecasted" days later.

Fixed in four queries across three modules:
- `forecasting/data_access.py::load_product_context` — added `AND p.deleted_at IS NULL`.
- `pricing/data_access.py::load_own_product` — added `AND deleted_at IS NULL`.
- `pricing/data_access.py::load_competitor_prices` — joined to `competitors` and added
  `AND c.is_active = TRUE` (a stale price from a since-deactivated competitor shouldn't influence a
  live recommendation).
- `extraction/data_access.py::load_known_product_names` / `load_known_competitor_names` — added the
  same two filters respectively.

Verified against the real, current schema (not the version this module was originally tested
against) — reloaded `init_schema.sql` from `main` into a disposable Postgres and confirmed all 20
non-pgvector tables still create cleanly (the `rag_document_chunks`/`vector` failure from the previous
entry is isolated to that one table; everything else is unaffected). Added 5 regression tests (one per
fixed query) that soft-delete/deactivate a row mid-test and assert it's excluded — all pass, and the
full existing suite (136 tests) still passes unchanged against the new schema, confirming nothing else
broke.

**Infra fixes skipped this round on request** (`docker-compose.yml`'s Postgres image not being
pgvector-enabled, item #17; the broken `watchdog.py` syntax, item #16) — started drafting both (image
swap to `pgvector/pgvector:pg15`, confirmed it pulls and would resolve #17) but was asked to leave
infra files alone for now. Both remain open in `PENDING_ACTIONS.md`, unstarted.

**Full suite: 141 tests** (5 new regression tests added). Verified three ways: no live infra (104
pass, 37 skip), Postgres up (121 pass, 20 skip). `flake8` clean. This work is on branch
`claude/ai-schema-conflict-fixes` (off latest `main`, since PR #2 already merged) — opened as
[PR #3](https://github.com/Huda-Hassouneh/CEOPRO-AI/pull/3).

## 2026-08-07 — Exhaustive line-by-line audit of every module against the live schema; 3 more real bugs found

Asked to "track every line and every output" and check for any other issues, on top of the schema-
conflict fixes above (same PR #3 branch, not a new one — still under review). Re-read every source
file in `forecasting/`, `pricing/`, `rag/`, and `extraction/` fresh against the current, real schema
(quoted in full at the top of this entry's investigation, not from memory), rather than assuming the
earlier fixes covered everything.

**`forecasting/`, `pricing/`, `rag/`**: no new bugs found. Re-verified every query against every
table it touches (`transactions`, `inventory`, `competitor_prices`, `evidence_records`,
`demand_forecasts`, `recommendation_outcomes`, `model_versions`, `rag_documents_metadata` — all
unchanged by the schema update) and re-checked edge cases in `baselines.py`, `model.py`,
`recommendation.py`, `guardrails.py`, `hybrid_retrieval.py`, `faiss_index.py`. All sound.

**`extraction/regex_patterns.py`: three more real bugs**, found by testing actual behavior against
realistic text, not by reading the regex and assuming it was right:

1. **`_DISCOUNT_PATTERN` was case-sensitive in a way that missed common phrasing.** It hardcoded
   `off|discount|OFF|DISCOUNT` instead of using `re.IGNORECASE`, so title-case marketing text like
   "Big 30% Off Sale" or "Get 15% Discount today" silently didn't match, while `"20% off"` and
   `"20% OFF"` did. Fixed: single case-insensitive pattern.

2. **`INVOICE_ID`/`ORDER_ID` extraction had a false-positive bug serious enough to matter**: with
   `re.IGNORECASE`, the shorter alternative in `(?:INV|INVOICE)` matched as a *prefix of the plain
   English word* "invoice" itself, with the rest of the word ("oice") captured as a fake ID. Verified:
   `extract_invoice_id("Please send me my invoice")` returned an `INVOICE_ID` entity with value
   `"oice"`. Root cause was two compounding issues: (a) alternation tried the short form before the
   long form, and (b) the ID-capture group (`[A-Z0-9]{3,}`) matched *any* 3+-letter word
   case-insensitively, not just genuine ID-shaped tokens — so even a correctly-scoped label match
   would go on to capture the next ordinary word ("amount", "today") as if it were the ID. Fixed both:
   reordered the alternation (`INVOICE|INV`), and required the captured group to contain at least one
   digit (`(?=[A-Z0-9]*\d)[A-Z0-9]{3,}`) — real IDs always have one, ordinary words never do. Verified
   the fix doesn't regress genuine matches (`"INV-20458"`, `"INV20458"`, `"ORDER: ORD99231"`, etc.)
   and does suppress the false positives (`"invoice"`, `"invoicing"`, `"the order was placed"`,
   `"in order to proceed"`, `"reorder level"`, `"disorder"`).

3. **`extract_money` only handled amount-then-code ("18.00 JOD"), never code-then-amount
   ("JOD 18.00")** — a gap, not a false positive, but a real one: code-before-amount is at least as
   common a convention as code-after for the MENA currencies this platform targets (spec §9), and
   `"JOD 18.00"`, `"SAR 500"`, `"AED 1,250.00"` all silently extracted nothing. Added a second pattern
   for the code-before ordering.

All three were confirmed with direct interpreter testing before touching the source (not assumed from
reading the regex), and each got a targeted regression test rather than a vague "does it work now"
check: 7 new tests (1 case-insensitivity, 2 false-positive-suppression, 2 real-match-preservation,
2 code-before-amount).

**Full suite: 148 tests, run with every live service up simultaneously** (Postgres with the real
current schema, Redis, MinIO, and the real embedding model, all at once for the first time this
session) — confirms nothing regressed across the whole module set together, not just per-module in
isolation. `flake8` clean. All still on `claude/ai-schema-conflict-fixes` / PR #3.

**A near-miss worth recording**: continuing the audit, `grep`ing for `sklearn` imports across
`src/ai/` found none, so `scikit-learn` in `requirements.txt` looked like dead weight and was
removed. Before committing that, tested it properly instead of trusting the grep result alone: built
a throwaway venv with only `xgboost`/`numpy`/`pandas` (no scikit-learn) and tried the exact
`XGBRegressor` construction+fit+predict call `model.py` uses. It failed:
`ImportError: sklearn needs to be installed in order to use this module` — `xgboost`'s
sklearn-compatible wrapper (`XGBRegressor`, which `model.py` uses directly) hard-requires
`scikit-learn` internally, even though nothing in this codebase ever writes `import sklearn` itself.
Reverted the removal immediately and added a comment in `requirements.txt` explaining why the
dependency is there, so this exact mistake doesn't get made again by grep-based reasoning alone. This
is exactly the kind of thing "looks unused" static analysis misses and only running the actual code
catches — logged as a reminder to verify empirically before removing anything that looks unused,
not just this once.

## 2026-08-07 — Pushed, pulled for team updates, reanalyzed schema/data-flow/integration

Confirmed everything from the prior entries was committed and pushed (clean working tree, branch in
sync with `origin/claude/ai-schema-conflict-fixes`). Fetched `main`: one new commit since last check
(`a58ce6f`, another `watchdog.py` update), no schema/`docker-compose.yml`/data-contract changes
(confirmed with an explicit diff — empty).

**`watchdog.py` is still broken, but with a different specific defect than previously logged.** The
commit that fixed the PowerShell-heredoc-wrapper bug (`PENDING_ACTIONS.md` #16, previous entries)
also deleted the module docstring's opening and closing `"""` lines in the same edit, leaving the
docstring text as bare top-level statements — still a `SyntaxError`, confirmed with `ast.parse()` on
the actual git blob piped directly via `git show | python3 -c '...'`, not a local copy (a first
attempt via `Out-File -Encoding utf8` falsely reported a BOM error that traced back to PowerShell's
`utf8` encoding adding its own BOM to the local copy, not something present in the real file — worth
noting as its own small lesson: verify against the real git blob, not a roundtripped local copy, when
the exact bytes matter). Updated `PENDING_ACTIONS.md` #16 with the corrected diagnosis. Also confirmed
via `git merge-tree` that this change doesn't conflict with PR #3 — clean auto-merge, watchdog.py
untouched on this branch.

**Practical impact check, not just "is it broken"**: read `staging-deployment.yml` again — the
`python watchdog.py` step is in a job that only runs after a `Dockerfile.ai` build step, and
`Dockerfile.ai` still doesn't exist anywhere in the repo (`PENDING_ACTIONS.md` #8). So the pipeline
fails there first; `watchdog.py`'s brokenness is currently unreachable in CI, not currently blocking
anything of ours. Still logged as open rather than downgraded, since it becomes live the moment #8 is
fixed.

**Schema/data-flow/integration reanalysis**: since the schema is unchanged since the previous full
audit, re-ran the full offline test suite (111 passed, 37 skipped — consistent with the last known
count) as a sanity check rather than repeating the entire live-infra verification from scratch, since
nothing that verification depends on had changed. No new issues found in `forecasting/`, `pricing/`,
`rag/`, or `extraction/`.

## How to add an entry

1. New date-stamped `##` section at the bottom (never edit history).
2. State what was built/changed, what testing was done, and what it found.
3. Update the Module status table above to match.
4. If it closes or reopens an item in `AI_PLAN_AND_CONTRACT_UPDATES.md`, say so there too, in that
   file's own dated-entry convention.

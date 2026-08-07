# CEOPRO AI — Pending Actions for Other Teams / Humans

Things discovered during AI/ML-track work that need a decision or action from **someone other than
the AI/ML track** — a different team, or a human with permissions this session doesn't have. Nothing
in this file gets fixed by AI/ML work; it's a visibility list so the right owner notices it.

**Convention:** unlike `AI_PROGRESS.md` (strictly append-only), rows here get their **Status**
updated in place once resolved — add a one-line resolution note rather than deleting the row, so
there's still a record of what happened. New items get added to the bottom of their section.

---

## Blocking (something can't be built until this lands)

| # | Item | Owner | Blocks | Status |
|---|---|---|---|---|

| 4 | No real competitor price data or scraper running (`competitor_prices` table exists but is empty) | AI Market Scraper Service owner (per `DATA_OWNERSHIP_AND_CONTRACTS.md`) | Phase 6 Competitor Ranking (spec §20); Phase 5 Price Intelligence logic is now built and tested against seeded data (see `AI_PROGRESS.md`, `src/ai/pricing/`) but has nothing real to run against | 🟡 Open — AI/ML side is ready and waiting; the scraper itself is still the blocker |

## Needs a decision (not blocking yet, but ambiguous/contested)

| # | Item | Owner | Why it matters | Status |
|---|---|---|---|---|
| 6 | `src/infrastructure/messaging/ai_consumer.py` already consumes `market.intelligence.raw` and writes to `evidence_records` under infra's ownership — functionally overlaps with where a future AI market-intelligence module would live | Whoever owns both infra/messaging and the AI roadmap | Two systems risk double-writing `evidence_records` once that AI module is built | 🟠 Open — needs an explicit call, not resolvable by either side alone |
| 7 | `model_versions` has no `artifact_path` column, so trained model binaries can't be pointed at their MinIO location (`ceopro-ai-artifacts`) yet | Backend/DB | Small, additive schema change (`ALTER TABLE model_versions ADD COLUMN artifact_path VARCHAR(500);`) — low risk, just needs someone to run it | 🟡 Open — small ask, easy to unblock |
| 8 | `.github/workflows/staging-deployment.yml` builds/deploys `Dockerfile.ai` and a `docker compose ... ai` service — **neither exists anywhere in the repo, on any branch** | Infra/DevOps | CI will fail the first time this workflow actually runs end-to-end (currently only triggers on push to `main`) | 🟠 Open — discovered during this session's repo audit, not caused by AI/ML work |
| 9 | No root-level `requirements.txt`, but `Dockerfile.backend` runs `pip install -r requirements.txt` | Backend/Infra | Backend Docker build is currently broken | 🟠 Open — discovered during this session's repo audit |
| 14 | `products` table has no `cost`/COGS column | Backend/DB | Spec §19 calls for margin-based pricing guardrails; without a cost basis, `src/ai/pricing/guardrails.py` can only bound *how much a suggested price can move*, not *whether it stays profitable* — a materially weaker guardrail | 🟡 Open — small ask (`ALTER TABLE products ADD COLUMN cost NUMERIC(10, 2);`), same shape as item #7 |
| 15 | `src/ai/rag/data_access.py` only decodes MinIO objects as plain UTF-8 text — PDF/DOCX aren't extracted, though `MINIO_STORAGE_ARCHITECTURE.md` explicitly expects "supplier PDFs, business text files" in `ceopro-rag-knowledge` | AI/ML (self-flagged — not someone else's blocker, but noted here so it isn't silently assumed done) | Any uploaded PDF/DOCX in that bucket is currently invisible to RAG ingestion, not an error, just silently unmatched by any document row that references it | 🟡 Open — needs `pypdf`/`python-docx` added; not started |

## Security

| # | Item | Owner | Status |
|---|---|---|---|
| 10 | Hardcoded Postgres password fallback in `src/infrastructure/monitoring/watchdog.py` (`DATABASE_URL` default embedded a real-looking password in a public repo) | Whoever owns `watchdog.py` (Infra) | ✅ Resolved 2026-08-07 — `DATABASE_URL` now required (raises `RuntimeError` if unset), no hardcoded fallback. |
| 16 | `watchdog.py` still doesn't parse as valid Python — **a different defect than originally reported**. The original PowerShell-heredoc-wrapper bug (`@'`/`'@ \| Out-File ...`) was fixed in a later commit (2026-08-07), but that same fix also deleted the module docstring's opening and closing `"""` lines, leaving the docstring text as bare top-level statements. Confirmed via `ast.parse()` on the actual git blob (not a local copy — an earlier check of a `PowerShell Out-File`-written copy falsely reported a BOM error that wasn't in the real file): `SyntaxError: invalid syntax` at line 2. Also confirmed via `git merge-tree` that this doesn't conflict with PR #3 (unrelated file), just still broken on `main`. | Whoever owns `watchdog.py` (Infra) | 🔴 Open — still won't import or run. **Currently moot in practice**: `staging-deployment.yml` fails earlier anyway, at the `Dockerfile.ai` build step (item #8), before it would ever reach the `python watchdog.py` step — but will matter the moment #8 is fixed, so still worth fixing rather than leaving as a second landmine. |
| 17 | `docker-compose.yml`'s `postgres` service uses plain `postgres:15-alpine`, which doesn't include pgvector — confirmed by loading the current `init_schema.sql` against a real `postgres:15-alpine` container: `ERROR: extension "vector" is not available`, and `rag_document_chunks` (which needs the `VECTOR` type) fails to create as a result | Infra/DevOps | 🔴 Open — needs the image swapped to a pgvector-enabled variant (e.g. `pgvector/pgvector:pg15`); until then item #1 isn't actually deployable despite the schema being ready |

## Waiting on documents / approvals (not code)

| # | Item | Owner | Status |
|---|---|---|---|
| 11 | `AI_ENGINEERING_PLAN.md`, `AI_CONTRACT_CHANGES_AND_CLARIFICATIONS.md`, and the original `AI_PROGRESS.md` referenced by `AI_PLAN_AND_CONTRACT_UPDATES.md` (module-level detail, "Module E/J/K" references) don't exist anywhere in this repo's git history | Whoever authored `AI_PLAN_AND_CONTRACT_UPDATES.md` | 🟡 Open — acknowledged as "will provide later"; AI/ML work in the meantime is going directly off `MASTER_SPEC_v4.md` |
| 12 | `MASTER_SPEC_v4.md` and `AI_PLAN_AND_CONTRACT_UPDATES.md` are staged locally / pushed to `noorhassouneh-patch-1` but not yet merged to `main` (reported as pending approval, pusher lacks `main` permissions) | Whoever holds merge rights on `main` | 🟡 Open — not blocking AI/ML work (content already available on the patch branch), but other teams won't see these docs until merged |
| 13 | Orange infrastructure environment (CPU/GPU availability, on-prem vs. cloud) not yet confirmed (spec §28) | Whoever owns the Orange deployment relationship | ⚪ Deferred — confirmed CPU-only / no GPU "for now" for this track; revisit if/when GPU becomes available |

---

## How to update this file

- Resolving an item: change its Status cell (e.g. `🔴 Open` → `✅ Resolved 2026-08-10 — <one-line note, link to commit/PR if applicable>`). Don't delete the row.
- New item: add a row to the relevant section (or add a new section if it doesn't fit the existing three). Keep the Owner column specific enough that someone reading it knows who to ping.
- If an item turns out to already be resolved elsewhere, still record it here rather than silently dropping it — same reasoning as `AI_PLAN_AND_CONTRACT_UPDATES.md`'s precedence rule: the record matters even after the fact.

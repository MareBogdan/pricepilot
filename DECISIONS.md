# DECISIONS

Append-only architecture decision records. Context → decision → alternatives rejected → date.
Read this when you cannot remember why something is the way it is, and before an interview.

---

## ADR-0001 — uv as the package and Python-version manager
**Context.** The machine has Python 3.14 on PATH and a uv-managed 3.12. Torch and
sentence-transformers lag new CPython releases by months, so 3.14 is not usable for Phases 3–4.
**Decision.** Pin 3.12 via `.python-version`; manage dependencies with `uv sync`. `pyproject.toml`
declares `requires-python = ">=3.11,<3.13"` so an accidental 3.13/3.14 env fails loudly.
**Rejected.** pip + venv (slower, no lockfile), Poetry (heavier, no Python management), conda.
**Date.** 2026-09-12

## ADR-0002 — The mock store holds state in memory, not in Postgres
**Context.** `services/mock_store` is a fixture standing in for Shopify/WooCommerce, not a feature.
**Decision.** Catalogue and history are generated deterministically from a fixed seed at process
start. Price updates persist only for the life of the process.
**Consequence.** It runs with no database and no Docker, which matters because Docker is not
installed on the dev machine. The Phase 6 action log — the part that must survive — lives in
Postgres on our side, which is also where a real integration would keep it.
**Rejected.** Backing it with Postgres (couples a fixture to infrastructure, and invites the
pipeline to query the shop's tables directly instead of its API, which a real integration cannot do).
**Date.** 2026-09-12

## ADR-0003 — A Makefile plus a PowerShell shim, with the logic in `scripts/`
**Context.** CLAUDE.md §11 specifies `make status`. `make` is not installed on Windows and
installing GNU Make is a poor dependency to impose on the dev machine.
**Decision.** Keep a real `Makefile` (used by CI and by the Phase 7 VPS) and add `make.ps1`
mirroring every target. Neither is a source of truth: real logic lives in `scripts/*.py` and in uv,
so the two dispatchers cannot drift in behaviour, only in coverage.
**Rejected.** Make-only (does not run here), a Python task runner such as `invoke`/`just` (another
dependency, and CI/VPS both have make anyway).
**Date.** 2026-09-12

## ADR-0004 — Only Phase 0–2 tables exist in migration 0001
**Context.** The full system needs tables for matches, embeddings, demand forecasts,
recommendations and actions.
**Decision.** Migration 0001 creates `products`, `scrape_runs`, `raw_listings`, `llm_calls` only.
Later tables arrive in the phase that first writes to them.
**Rationale.** A schema designed before the data is seen is a schema designed wrong; in particular
the embedding dimension is not known until the Phase 3 model is chosen. The pgvector *extension*
is still enabled in 0001, so a broken image is discovered now rather than mid-matching.
**Rejected.** One big upfront schema (guaranteed rework), no migrations until Phase 3 (no history).
**Date.** 2026-09-12

## ADR-0005 — `raw_listings` is append-only; one row per (listing, observation)
**Context.** Phase 4 needs a daily price series. History cannot be backfilled.
**Decision.** Every scrape run inserts new rows; nothing is upserted or overwritten. Deduplication
and current-state views happen downstream in Phase 2, not at ingest.
**Consequence.** The table grows at roughly (listings × days). At 5,000 listings daily that is
~1.8M rows/year — trivial for Postgres, and the cost of losing history is unrecoverable.
**Rejected.** Upsert-on-(source, source_product_id) with a separate price-history table (two
sources of truth, and a parsing change silently rewrites the past).
**Date.** 2026-09-12

## ADR-0006 — The LLM transport is not implemented in Phase 0
**Context.** CLAUDE.md §5.4 requires one wrapper module for all LLM calls, and §0.4 forbids
inventing numbers — including per-token prices.
**Decision.** `src/pricepilot/llm/client.py` ships the budget cap, the content-hash cache key and
the `llm_calls` logging in Phase 0. `complete()` raises `NotImplementedError`. The transport and the
real price table land in Phase 2, in the same commit as the first `SPEND:` approval.
**Enforcement.** ruff bans importing `anthropic`/`openai` anywhere but that module, and a test
asserts the same, so the §9 rule fails CI instead of relying on memory.
**Rejected.** Implementing the client now with placeholder prices (would put a fabricated number
into the cost ledger, which is exactly what §0.4 exists to prevent).
**Date.** 2026-09-12

## ADR-0007 — Money is `Numeric`, never `float`, everywhere
**Context.** The margin floor in Phase 5 is a Python comparison, and Phase 6 writes real prices.
**Decision.** `Numeric(12, 2)` for prices and costs, `Numeric(12, 6)` for LLM cost; `Decimal` in
Python. A test asserts this across every money column.
**Rejected.** Float with rounding at the boundary (`0.1 + 0.2 != 0.3` is a real margin-check bug,
not a theoretical one), integer cents (correct but noisy to read in SQL).
**Date.** 2026-09-12

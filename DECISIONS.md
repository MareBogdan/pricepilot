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

## ADR-0008 — Postgres is published on host port 5433, not 5432
**Context.** Closing the Phase 0 gate, `docker compose up -d` succeeded and the API reached the
database over the compose network, but `make migrate` from the host failed with
`password authentication failed for user "pricepilot"`. Two processes were listening on 5432: the
Docker proxy and a pre-existing native Windows Postgres service, which won host connections.
**Decision.** The container publishes `${POSTGRES_PORT:-5433}:5432`. Inside Docker the port is
unchanged at 5432; only the host mapping moves. `.env.example`, `.env` and the `Settings` default
all say 5433.
**Rationale.** A collision like this fails as an authentication error, not a connection error, which
reads as a credentials bug and costs an hour. Defaulting off 5432 means a machine with a native
Postgres works on first clone.
**Rejected.** Stopping the native Postgres service (breaks whatever else uses it, and only on this
machine), binding to 127.0.0.1 only (does not resolve the collision).
**Date.** 2026-09-12

## ADR-0009 — Cross-shop overlap is a Phase 1 gate condition, measured by a proxy key
**Context.** `docs/AUDIT.md` concern 2: Phase 3 is a matching problem, so if the same product does
not appear on two shops there is no positive class and Phases 3–6 are unfounded. Overlap was
verified by hand for exactly one product, which is an existence proof, not a base rate.
**Decision.** The Phase 1 gate requires **≥400 products appearing on two or more shops**, measured
by a normalized proxy key of `(brand, product-line tokens, net weight in grams)` colliding across
sources — plain SQL, no matching model. `make status` reports the count from day one. If 400 is
unreachable, a source is added **before leaving Phase 1**.
**Rationale.** The proxy errs in both directions and is a floor estimate, which is all that is
needed to make one decision. Discovering thin overlap in week 6 costs the project; discovering it in
week 2 costs one adapter.
**Rejected.** Assuming overlap from the single hand-verified product; building a matching model to
measure it (circular — the model is what the overlap is supposed to justify); deferring the check to
Phase 3 (too late to react).
**Date.** 2026-09-12

## ADR-0010 — One scraper on a schedule before the other two are written
**Context.** `docs/AUDIT.md` concern 2/change 2. Phase 4 needs daily price history and CLAUDE.md §7
states it cannot be backfilled. The original ordering builds three adapters, then schedules them.
**Decision.** Build `petmax.ro` only — the anchor source, richest raw data — put it on a daily
schedule immediately, and write the other adapters while it collects. Each further adapter joins the
schedule as it is finished.
**Rationale.** History is wall-clock. Every day spent building adapters before collecting is a day of
price series permanently lost. The reordering costs nothing.
**Rejected.** Three adapters then schedule (loses ~2–3 weeks of history); scheduling a half-finished
adapter (ingests data that a later parsing fix would silently invalidate — but note ADR-0005 keeps
`raw_listings` append-only, so a fix re-parses forward, never rewrites the past).
**Date.** 2026-09-12

## ADR-0011 — Hosting is reserved first; GPU fine-tuning is a week-5 decision, and starts with a smoke run
**Context.** `docs/AUDIT.md` concern 5: $20 available against a committed $15–25 GPU line leaves
nothing for the deployed demo, and CLAUDE.md §7 Phase 7 requires a publicly reachable URL.
**Decision.** Spend is reserved in priority order, not phase order: **~$15 for three months of VPS
first**, then LLM extraction ($2–3), then recommendation generation ($5–8), then optional
pre-labelling. GPU rental is **not a committed budget line** — it is a separate decision taken at
week 5 on the evidence then available (dataset exists, baseline recorded, free tier assessed).
When taken, the **first run is a deliberate smoke run**: smallest model, ~200 examples, minutes of
wall clock, ~$1–2, purely to prove the pipeline end to end. Its metric is discarded. The real run is
a second, separate approval.
**Rationale.** A fine-tuned model behind a dead URL demonstrates nothing to a recruiter. And the
common way a GPU budget evaporates is a multi-hour run that fails on a dataset-loading bug in the
first five minutes — the smoke run buys that insurance for ~$1.
**Rejected.** Keeping GPU as a committed line (the arithmetic does not close); skipping the smoke run
(the failure mode it prevents is the expensive one); ruling out fine-tuning now (premature — the
evidence for the decision does not exist yet).
**Date.** 2026-09-12

## ADR-0012 — The demand model is graded against a naive baseline on real prices, never against the planted elasticity
**Context.** `docs/AUDIT.md` concern 4. `services/mock_store` generates 180 days of price and sales
history from a planted elasticity constant. A model trained on that and scored against that constant
recovers a number that was placed there by hand. That is circular, and an interviewer finds it.
**Decision.** Once Phase 1 has real collected price history, that becomes the backbone the demand
model consumes; the mock store's 180 days are **bootstrap only**, so the code can be written and
tested before enough real history exists. Grading is MAE/MAPE against a naive 7-day-average baseline,
evaluated on periods where the price actually moved in the collected data. "Recovered the planted
elasticity" is never reported as a result — at most it is a unit test asserting the training loop
works. The README states plainly which parts are real (prices, promotions, competitor moves) and
which are simulated (sales volumes), in the same table as the numbers.
**Rejected.** Reporting elasticity recovery as a headline result (fabricated); calling the whole
phase synthetic (understates the real price history, and is a weaker and less accurate claim);
dropping the demand model (it is one of the three capabilities the project must prove).
**Date.** 2026-09-12

## ADR-0013 - Every `.ps1` in this repo is ASCII-only, enforced by a test
**Context.** `scripts/schedule_daily.ps1` failed to run with `Unexpected token 'install'`,
`The token '&&' is not a valid statement separator`, and `Missing closing '}'` - all pointing at
correct lines, tens of lines from the real cause. Windows PowerShell 5.1 reads a `.ps1` with no
byte-order mark as **ANSI (cp1252), not UTF-8**, so five em dashes inside `Write-Host` strings
decoded wrongly, corrupted their string literals and desynchronised the parser.
**Decision.** No `.ps1` in this repo contains a byte above 0x7F - not in code, not in strings, not
in comments. `tests/test_powershell_ascii.py` scans every `.ps1` and fails with the file, line,
byte offset and character, plus the ASCII replacement to use. It includes a self-test asserting
the scan actually trips on an em dash, so the guard cannot pass vacuously.
**Rejected.** Saving every `.ps1` as UTF-8 with a BOM (a BOM is invisible in a diff, and one
editor or one tool writing the file without it silently reintroduces the bug); documenting the
rule in CLAUDE.md only (section 9 logic - a rule in a markdown file is a suggestion, a failing
test is a rule, the same reasoning as the LLM-SDK import ban in ADR-0006); switching the shim to
PowerShell 7 (not installed, and the Phase 7 VPS runs neither).
**Cost of the rule.** Markdown and Python keep their typography; only `.ps1` is constrained. That
is a small price for a failure mode whose error message points at the wrong line.
**Date.** 2026-09-12

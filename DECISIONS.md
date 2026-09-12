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

## ADR-0014 — Two databases, explicit split, enforced mechanically

**Context.** Collection moved to Neon (managed Postgres, Frankfurt, pgvector enabled): a Windows
Task Scheduler job cannot guarantee 7 consecutive days when the laptop is not open at 06:10, so
collection moves to a GitHub Actions cron. `DATABASE_URL` now points at Neon; `POSTGRES_*` still
describe the local docker container. Left implicit, this is exactly the kind of ambiguity where a
`pytest` run — or an accidental `make migrate` from an untrusted branch — writes into the same
database that holds real, unrecoverable collection history.
**Decision.** `DATABASE_URL` is authoritative for collected data (Neon, unpooled endpoint,
`postgresql+psycopg://`, because the pooled endpoint refuses prepared statements and Alembic needs
them). `TEST_DATABASE_URL` is authoritative for tests and offline development (local docker
Postgres). `tests/conftest.py::pytest_configure` overwrites the `DATABASE_URL` a test process
actually sees with `TEST_DATABASE_URL` — or unsets it entirely for a fully-offline run — before any
test module is collected, and then asserts the result does not name a Neon host, raising
`NeonGuardError` if it ever does. This is mechanical, not a convention someone has to remember:
even a `.env` with `TEST_DATABASE_URL` mistakenly set to Neon fails loudly instead of connecting.
`tests/test_database_split.py` is the self-test proving the guard actually trips — same reasoning
as ADR-0013's PowerShell ASCII guard.
**Rationale.** A rule written only in `.env.example` comments is a suggestion; the failure mode it
guards against (a test run quietly touching production collection data) is exactly the one that
cannot be caught by review, because nothing about a normal `pytest` invocation looks wrong.
**Rejected.** Documenting the split in CLAUDE.md/`.env.example` only (relies on memory, and the
Neon URL sits in `.env` regardless); a single `DATABASE_URL` with a runtime `APP_ENV` check (one
more thing to get right per environment, and no test fails if it's wrong); a second Neon branch/
database for tests (still a paid managed service in the loop for something that must cost nothing,
CLAUDE.md §5).
**Date.** 2026-09-12

## ADR-0015 — Neon cold-start: a 15s connect timeout, one retry, applied at both call sites

**Context.** Neon (free plan) suspends compute after 5 minutes idle. The first connection of the
day — the daily scrape's first query, or a scheduled Alembic run — pays a wake-up: the proxy holds
the socket rather than refusing it, but that can take several seconds, and a default psycopg
connect has no timeout tolerant of that without also risking a hung process on a genuine outage.
**Decision.** `NEON_CONNECT_TIMEOUT_SECONDS = 15` on every engine (`connect_args={"connect_timeout":
15}`), plus `connect_with_wakeup_retry()` in `src/pricepilot/db.py`: one retry, 2s later, on the
first `OperationalError`. Applied at both places a *new* connection is opened against the
collected-data database — `check_database()` and Alembic's `env.py` — not inside `session_scope`,
where the pool and `pool_pre_ping` already own connection reuse. Verified 2026-09-12: `alembic
upgrade head` ran clean against Neon on the day's first connection, and a second, separate
connection confirmed `products`, `scrape_runs`, `raw_listings`, `llm_calls`, `alembic_version` all
exist, `vector` extension 0.8.6 is active, and `<=>` answers.
**Rationale.** One retry is enough: the 15s timeout already absorbs a normal wake-up, so a second
consecutive failure is a real problem (bad credentials, Neon actually down, a network issue) and
should surface immediately rather than be retried away and disguised as a timeout.
**Rejected.** No timeout at all (a genuine outage hangs a scheduled run instead of failing loudly);
retrying more than once or with backoff (delays surfacing a real failure for no benefit — a cold
start either resolves within the one retry or the problem is not a cold start); polling Neon's API
to pre-warm compute before connecting (another moving part, another credential, for a problem one
retry already solves).
**Date.** 2026-09-12

## ADR-0016 — `raw_listings` ingest is idempotent within a day, amending ADR-0005

**Context.** Collection moves to a GitHub Actions cron (STEP 1–4) alongside `workflow_dispatch`
for manual runs. ADR-0005 made `raw_listings` append-only with one row per (listing, *run*): fine
when only a scheduled task ever wrote to it, but a manual `workflow_dispatch` run and the day's
cron run now both can, and both do, write the same day's observation. One row per run would let
the same calendar day produce two rows, silently double-counting a day of history in every
downstream count — listings collected, days of history, overlap — exactly the kind of thing
`make status` is supposed to catch, not cause.
**Decision.** Migration 0002 adds `external_id` (`source_product_id`, or the listing URL when a
shop exposes no id — the same fallback the petmax adapter already uses to dedupe within one page)
and `collected_date` (the run's start date) to `raw_listings`, with a unique constraint on
`(source, external_id, collected_date)`. `pricepilot.scrapers.runner.run_source` ingests via
`INSERT ... ON CONFLICT (source, external_id, collected_date) DO UPDATE`, so a second write on the
same day updates the existing row — new price, new `run_id`, new `scraped_at` — instead of
inserting a duplicate. Append-only is preserved **across** days; idempotency is scoped **within**
one day, which is the actual requirement. Verified against a real Postgres (local docker): a
manual run at price 10.00 followed by a same-day scheduled run at price 12.50 leaves exactly one
row, at 12.50, not two.
**Rejected.** Keeping strict one-row-per-run and deduplicating downstream at query time (pushes
the same bug into every consumer — `make status`, `overlap.py`, Phase 4 — instead of fixing it
once at the boundary that owns it); a `scrape_runs`-level lock preventing more than one run per day
(defeats the purpose of `workflow_dispatch` for a manual re-run after fixing a bug mid-day).
**Date.** 2026-09-12

## ADR-0017 — petmax category coverage expanded from 6 to 13, chosen from the real sitemap

**Context.** STEP 5. The original six categories (food and treats, dogs and cats) hold the
cross-shop overlap the Phase 1 gate needs, but cannot reach ≥3,000 in-scope listings from petmax
alone, and petmax is still the only adapter that exists (ADR-0010 — the other two are next
session's work). Guessing plausible-sounding category slugs risks scraping URLs that don't exist
or double-counting an already-covered category under a different name.
**Decision.** Fetched `sitemap_categories.xml` once (134 real category URLs) and picked the
smallest in-scope addition per CLAUDE.md §7's product-scope list: litter
(`asternut-litiera-nisip-silicat`), grooming/hygiene (`igiena-si-ingrijire-{caini,pisici}`),
accessories (`accesorii-{caini,pisici}`) and toys (`jucarii-{caini,pisici}`) — 7 new categories,
13 total. Volume was estimated with **one request per category**, reading the last page number
directly off the pagination widget's own link (page 0 of a Gomag category page already shows it,
e.g. `?p=37` → 38 pages) rather than crawling every page just to count — recon that respects the
same rate limit as production scraping. Estimate: ~208 page requests, ~4,990 listings, ~15–20
minutes wall-clock — comfortably under the ~45-minute guest-of-a-small-shop budget. Full
breakdown in `docs/SOURCES.md`.
**Rationale.** Broad umbrella categories (`accesorii-*`) were chosen over petmax's many narrower
ones (`hamuri-lese-si-zgarzi`, `castroane-boluri-apa-mancare-*`, `custi-transport-*`, …) because
those look like they cross-list the same products under the umbrella category — scraping both
would spend request budget re-observing listings already collected instead of growing distinct
volume. Regulated products mis-filed into any new category are still caught by
`REGULATED_TITLE_TOKENS`, independent of which category found them.
**Rejected.** Scraping all 134 categories (far more requests and wall-clock than the volume gain
justifies, and includes the pharmacy tree CLAUDE.md §7 excludes); guessing category slugs instead
of reading the sitemap (risks 404s or accidental duplicates); estimating volume by crawling every
page of every candidate category (10–40× the requests, for a number the pagination widget already
gives away in one).
**Date.** 2026-09-12

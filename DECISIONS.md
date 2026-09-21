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

## ADR-0018 — Collection moves from Windows Task Scheduler to a GitHub Actions cron

**Context.** The Phase 1 gate needs ≥7 **consecutive** days of history. The Windows Task
Scheduler job (ADR from the prior session) only runs while the laptop is open; `-StartWhenAvailable`
catches up a run missed to sleep, but a day the machine never wakes at all is a day of history
lost, and a gate that needs 7 *consecutive* days cannot tolerate that.
**Decision.** `.github/workflows/scrape-petmax.yml`: `schedule` cron at `10 3 * * *` (03:10 UTC =
06:10 Europe/Bucharest during EEST) plus `workflow_dispatch` for manual runs, secrets read only
from GitHub Secrets (`DATABASE_URL`, `SCRAPER_USER_AGENT`). The Windows scheduled task
(`PricePilot-scrape-petmax_ro`) is unregistered; `scripts/schedule_daily.ps1` and the
`make.ps1 schedule` target are removed rather than left as dead code that could mislead a future
session into thinking collection still runs locally.
**GitHub Actions runners are not blocked by petmax.ro.** Verified 2026-09-12 (STEP 1 gate): a
`workflow_dispatch`-only recon job fetched `hrana-uscata-caini` from the runner and got HTTP 200,
619,235 bytes, `data-Gomag` and `Lei_final_price` both present — byte-identical to the same fetch
run locally. No Cloudflare block on GitHub's Azure IP ranges was observed.
**Known trade-offs, accepted rather than engineered around:**
- **DST.** GitHub Actions cron has no IANA time zone support; 03:10 UTC drifts to 04:10 local
  after Romania's autumn changeover (last Sunday of October) until the following spring. Two
  cron entries gated by date would fix this but add complexity for roughly an hour of drift,
  twice a year, on a schedule chosen for "after overnight price changes settle" rather than a
  precise minute.
- **Scheduling delay.** GitHub delays `schedule`-triggered runs under load, sometimes by 10-30
  minutes. `scrape_runs.started_at` and `raw_listings.collected_date` both record the actual
  wall-clock start (`pricepilot.scrapers.runner`), never the cron's intended time, so a delayed
  run is still attributed to the correct calendar day rather than silently misdated.
**Rejected.** A self-hosted runner on the same laptop (reintroduces the exact "must be open"
problem this migration exists to solve); a paid always-on VPS now (Phase 7 money, not Phase 1 -
CLAUDE.md §5 spend schedule); leaving the Windows task registered as a backup (two sources of
truth for "is collection running" is worse than one, and an operator checking `make status` has
no way to know which one actually produced today's row).
**Date.** 2026-09-12

## ADR-0019 — Collected data moves to Neon, a managed Postgres, at $0

**Context.** ADR-0018 moves collection to GitHub Actions, which has no persistent local disk
between runs — a scheduled job on GitHub-hosted runners needs a database reachable from outside
Bogdan's laptop, not the docker-compose Postgres Phase 0 built (ADR-0002's local-only container).
**Decision.** Neon, free plan, Frankfurt region (closest to Romania of Neon's EU options, lowest
latency for the daily run), pgvector enabled from the start (Phase 3 will need it, and ADR-0004
already enables the extension in migration 0001 for exactly this reason). Connection uses the
**unpooled** endpoint with `postgresql+psycopg://`, not the pooled one — Neon's pooled endpoint
(PgBouncer in transaction mode) does not support prepared statements, and Alembic's DDL relies on
them. `DATABASE_URL` in GitHub Secrets and in local `.env`; never in the repo (CLAUDE.md §0.5).
See ADR-0014 for the resulting split from the local docker Postgres, and ADR-0015 for the
cold-start handling this plan choice requires (Neon's free tier suspends compute after 5 minutes
idle).
**Rationale.** Free tier costs nothing (CLAUDE.md §5: Phase 1 must be $0), needs no server to
patch or secure (unlike a Hetzner box provisioned early, which would also front-load Phase 7
money), and pgvector is a first-class extension rather than something to compile in later.
**Rejected.** Self-hosting Postgres on a VPS now (front-loads the Phase 7 hosting spend — CLAUDE.md
§5's priority-ordered spend schedule reserves that money for the deployed demo, not Phase 1
storage); Supabase (a heavier managed platform — auth, storage, realtime — for a need that is
purely "a Postgres GitHub Actions can reach"); SQLite over a persisted GitHub Actions artifact (no
concurrent-write story for a future second workflow, and artifacts are not built for this).
**Date.** 2026-09-12

## ADR-0020 — `robots.txt` is fetched through our own honest client, not `RobotFileParser.read()`

**Context.** Building the pentruanimale.ro adapter, a bounded live `--dry-run` (the same kind of
check that verified petmax before it went on the schedule) raised `RobotsDisallowed` for a category
page that a plain `curl` with our real `SCRAPER_USER_AGENT` fetched cleanly (HTTP 200) — including
for `robots.txt` itself. Investigated rather than routed around, per this session's standing rule
that a block is answered, not engineered past. Root cause: `PoliteClient._robots_for` called
`RobotFileParser.read()`, which fetches with a bare `urllib.request.urlopen()` — no custom headers,
so it sends Python's generic default User-Agent, not the honest one every other request on the
client uses. Confirmed directly: `urllib.request.urlopen("https://www.pentruanimale.ro/robots.txt")`
with no UA returns HTTP 403; the same URL fetched with our configured `SCRAPER_USER_AGENT` returns
200, byte-identical every time this session. `RobotFileParser` treats a 401/403 on its own fetch as
"disallow everything" (its documented behaviour) — so our compliance check was reading a block that
was never actually aimed at our crawler, only at an anonymous one it never otherwise uses.
**Decision.** `_robots_for` now fetches `robots.txt` through `self._client` — the same `httpx`
client, same honest `User-Agent` header, as every other request — and reproduces
`RobotFileParser.read()`'s own status-code handling (401/403 → disallow all; other 4xx → allow all;
5xx → fall through to the default of allowing, matching what stdlib does for that case too) by
hand, since `.parse()` still does the rule parsing itself. `PoliteClient.__init__` gained an
optional `transport` parameter purely as a test seam (`httpx.MockTransport`), default `None`
meaning "real network, unchanged". `tests/test_scraper_base.py` is the offline regression suite —
every branch (real rules honoured, 401, 403, 404, an unreachable robots.txt, and the User-Agent the
request itself carries) exercised via a mock transport, no network at all.
**This was not a shop blocking us; it was our own tooling misrepresenting itself.** Nothing about
this fix rotates, alters, or works around any User-Agent a shop has actually seen — pentruanimale.ro
has only ever seen the one honest, configured identity, and has allowed it on every request,
`robots.txt` included, throughout this session. The bug made our own compliance check briefly
disagree with reality; this closes that gap rather than papering over it.
**Rationale.** This bug is generic to `PoliteClient`, so it silently affected petmax.ro too — it
simply never surfaced there, because petmax.ro's server does not 403 anonymous/default-UA traffic
the way pentruanimale.ro's does. A second source with a stricter WAF is exactly the kind of thing
that was always going to catch this, and did.
**Rejected.** Retrying the blocked request under a different identity (indistinguishable from
exactly the "rotate the UA to get past a block" this session's rules forbid, and would not even
have been necessary — the real client already worked); ignoring the discrepancy and hardcoding an
allow for this one shop (papers over a bug that will resurface against the next stricter shop);
leaving `RobotFileParser.read()` in place and pre-emptively catching its exception into "allow"
(silently defeats robots.txt compliance for any shop that legitimately blocks robots.txt access).
**Date.** 2026-09-12

## ADR-0021 — The overlap proxy key is a floor estimate; it was tuned for precision, not recall

**Context.** The first real cross-shop measurement (petmax_ro + pentruanimale_ro) found 13 shared
products against the 400 gate. All 13 were hand-verified as genuine matches — precision was not
the problem. But CLAUDE.md §7 is explicit that the proxy key is "wrong in both directions" *by
design*, "a floor estimate", and that "it will join a few products that are not the same" is
**acceptable**. A key returning 13 pairs at ~100% precision is optimised for the wrong target: it
is a ceiling on false positives, not a floor on true overlap, and 13 cannot serve the one decision
CLAUDE.md §7 built this proxy for.

Two specific, measured causes, both bounded by "normalisation only" (no model, no fuzzy matching,
no learned threshold):

1. **Weight-token spacing.** `line_tokens()` stripped a bare unit token (`"kg"`, `"g"`) via
   `_NOISE`, but not a *combined* digit+unit token (`"85g"`, `"400g"`, `"0,85kg"`) — the decimal
   separator already splits a spaced-out number from its unit at the regex level, but an unspaced
   one glues the fractional digits to the unit into one surviving token. The identical product
   keyed differently purely from which shop's spacing convention it inherited. Measured: this one
   asymmetry alone hid 79 of 92 genuine matches in a diagnostic re-run.
2. **ml/l unsupported.** `net_weight_grams()` recognised only `kg`/`g`/`gr`/`grame` — a liquid
   product (shampoo, a supplement sold by volume) had no weight at all and was silently unkeyable,
   regardless of any spacing issue.

**Decision.**
- `_WEIGHT_UNIT_TOKEN` strips any `\d+(kg|g|gr|grame|mg|ml|l)` token from both `line_tokens()` and
  `normalized_brand()`'s no-brand-field fallback (factored into a shared `_is_line_token()` so the
  two functions cannot drift).
- `net_weight_grams()` gained `ml`/`l` (1 ml ≈ 1 g, 1 l = 1000 g — a water-density proxy, not an
  exact conversion; CLAUDE.md §7 asks for one canonical grams value, not more precision than the
  key needs).
- Curly apostrophes (U+2018/U+2019) fold to the ASCII `'` in `strip_diacritics`, so "Hill's"
  tokenizes identically regardless of which apostrophe glyph a shop uses — CLAUDE.md §7 names this
  trap explicitly.
- **Bonus-weight guard, encoded into the key, not just the weight parser.** `net_weight_grams()`
  still returns the base pack weight only (unchanged) — but the earlier documented judgement call
  that this was sufficient ("keeps product 233 and 2542 in the same bucket, which is correct for a
  floor estimate") is reversed: real measurement showed the trap is real and worth guarding
  against, not accepting. `bonus_weight_grams()` extracts the bonus amount (0 for a plain pack) and
  `OverlapKey` gained `bonus_g` as a first-class field (part of equality/hash), so `"15 kg"` and
  `"15 + 3 Kg Gratis"` never collide (`bonus_g` 0 vs 3000), while two shops' bonus-weight listings
  of the *same* product — in either word order or spacing — still do, because the comparison is on
  the normalized gram amount, not the raw text.

**Rationale.** CLAUDE.md §7 already states the target explicitly; this ADR is not introducing a
new goal, it is correcting the code to match one that was already written down. A trustworthy
floor needs recall a third source can plausibly grow toward 400; a 100%-precision key that misses
7 in 8 real matches gives that decision nothing to work with.
**Rejected.** A learned/fuzzy similarity threshold (explicitly out of bounds — normalisation only,
per this session's instructions, and a floor estimate should not depend on a tuned cutoff no one
can audit by reading it); adding the bonus grams into `net_weight_grams()` itself instead of a
separate key field (would make `net_weight_grams()` ambiguous for Phase 2, which needs the base
pack weight specifically, not a promotion-inflated one); relaxing `overlap_key()`'s "line tokens
must be non-empty" requirement to recover the rare brand-name-is-the-only-content case found while
investigating the keyable-rate asymmetry (a genuine, narrow edge case — see STATE.md — but relaxing
it is a change to what counts as *sufficient* identity to key on, not a normalisation, and was left
alone per this session's scope).
**Date.** 2026-09-12

## ADR-0022 — pentruanimale.ro's search pagination has a hard ~600-product-per-category ceiling

**Context.** STEP 1's investigation into 224 fetched pages vs. a 321-page recon estimate found two
separate causes, not one. The first (a transient `__STATE__` parse failure mistaken for "category
exhausted", fixed the same session) recovered some pages on re-run (224 → 269) but did not close
the gap. Direct comparison of `?page=50` vs. `?page=51` on `hrana-uscata-caini` showed why: page 50
returns a normal, populated `$ROOT_QUERY.productSearch(...)` key; **page 51 returns HTTP 200 with
no `productSearch` key in `__STATE__` at all** — only unrelated facet-widget data. The same
boundary (page 50 → 51) was hit independently on all three categories whose recon page count
exceeds 50 (`hrana-uscata-caini` 81, `recompense---snacks-caini` 63, `hrana-umeda-pisici` 70); the
other three, all under 50 pages, completed with zero errors. `recordsFiltered` itself was
re-verified accurate (zero drift across all six categories, re-checked a session later) — the
error was in assuming every page `ceil(recordsFiltered/12)` implies is actually retrievable.
**Decision.** Documented as a platform limit, not an adapter defect: this store's search
pagination stops returning product results past page 50 (600 products) per category, regardless
of the claimed total. `docs/SOURCES.md`'s category volume table is corrected accordingly (321 → 257
pages, ~6,593 → ~5,327 estimated listings). The three affected categories now permanently lose
everything past their first 600 products until a different retrieval path exists.
**Rationale.** `_should_continue_category`'s consecutive-parse-error cap (the STEP 1 code fix)
already makes the adapter fail this specific wall gracefully — a few wasted attempts, a clear
logged error, move to the next category — rather than either looping for `max_pages_per_category`
(120) pages against a wall that will never open, or (the original bug) silently truncating
everything *before* the wall on an unrelated transient hiccup. No further adapter change was made
to work around the ceiling itself.
**Rejected.** Enumerating `sitemap/product-N.xml` to reach the remaining ~639+ products per capped
category (a real option — petmax's own `docs/SOURCES.md` names its product sitemap as exactly this
kind of fallback — but a genuinely new retrieval mechanism, out of this session's explicitly
bounded scope: STEP 1 was diagnose-and-fix-the-adapter-bug, not build a second retrieval path);
treating the wall as unexplained and re-running repeatedly hoping it clears (it is a fixed
platform behaviour, not a transient condition — confirmed identically on three categories).
**Date.** 2026-09-12

## ADR-0023 — Cross-shop overlap is measured by a hand-verified random sample, not by the proxy key

**Context.** CLAUDE.md §7 sets the Phase 1 gate at ">=400 products appearing on two or more shops,
by the proxy key above, reported by `make status`". The proxy key was specified as a cheap floor
estimate, explicitly allowed to be "wrong in both directions". A random sample of 50 keyable
petmax food listings (seed 20260913) was drawn and every claimed match opened by hand against the
live shops (`docs/learned/q3-verification.md`, `docs/AUDIT.md`): 26/50 confirmed genuine, 1
rejected (#13, a petmax slug collision), 1 false negative found on spot-checking the "no match"
rows. Against the 94 the proxy key reports for the same listing pool, this implies the key's
recall is roughly 94 / 1,211 ≈ 8% — it under-reports true overlap by more than an order of
magnitude. A floor that low cannot support the one decision the gate exists to make ("add a source
before leaving Phase 1"): it would say the market is thin when the sample says the opposite.

**Decision.** The 400 threshold is UNCHANGED. The measurement method changes: the gate is
evaluated from the hand-verified random sample, reported as a point estimate with a 95% Wilson
confidence interval over the keyable food population, not from the proxy key's raw count. The
proxy key stays in `make status` as a daily indicator, relabelled explicitly as a known-low floor
with its measured recall printed next to it, so no future session mistakes it for the overlap.

**Evidence** (recomputed independently this session, not copied on trust — see
`docs/AUDIT.md`'s 2026-09-13 verification note for the sample itself):

- n = 50, x = 26 confirmed matches, p̂ = 0.52
- Wilson 95% CI on p̂ (z = 1.9600): **[0.3851, 0.6520]**
- Applied to N = 2,329 keyable petmax food listings: point estimate **1,211**, 95% CI **[897,
  1,519]**
- The lower bound of the interval (897) is more than twice the 400 threshold.

**Limitations, stated plainly.** n=50 is small — the CI is wide (±13 points either side of p̂).
The sample covers petmax food categories against pentruanimale.ro only, not animax.ro or any
other source. Verification judged brand, line, flavour, pack size and form as the criteria for
"same product", and treats a bonus pack (e.g. 12+2 kg) as a different purchasable unit from its
plain equivalent (12 kg) — a stricter standard than some matching definitions would use, which
means this estimate is not inflated by that choice.

**Rejected.** Lowering the 400 threshold to match what the broken key reports (would hide a
measurement bug behind a weaker goal, and the gate would no longer measure what CLAUDE.md §7
says it measures). Tuning `overlap_key()` until it reaches 400 (CLAUDE.md §7 forbids building a
matcher to compute this gate, and a key tuned to hit a target number stops being an independent
measurement — it becomes the thing being measured). Adding sources blindly on the strength of the
old 94 figure, which is now known to be wrong by more than an order of magnitude rather than a
genuine market signal.

**Date.** 2026-09-13

## ADR-0024 — animax.ro adapter: Shopify (not Magento), read via `products.json`

**Context.** CLAUDE.md §7's plan-stage note guessed animax.ro was Magento. Live recon
(`docs/SOURCES.md`) found `robots.txt` opens with `# Shopify storefront.` and the sitemap has
Shopify's standard shape — the plan's guess was wrong, caught before any code was written against
the wrong platform's assumptions. Every Shopify storefront also exposes
`/collections/<handle>/products.json`, a standard public part of the storefront theme (not a
private/reverse-engineered API), returning structured per-variant data (`vendor`, `sku`, `price`,
`compare_at_price`, `grams`, `available`, a stable numeric `id`) at roughly 1/58th the bandwidth of
the equivalent HTML collection page (~150 KB vs ~8.7 MB for the same 250 products, because the
HTML duplicates full facet/quick-add JSON inline per card).

**Decision.** The adapter reads `products.json`, not scraped HTML — the same "prefer the
structured source over parsing markup" instinct that led pentruanimale's adapter to read VTEX's
`__STATE__` JSON blob rather than its rendered HTML. `external_id` is the Shopify **variant** id
(`variants[].id`) — a platform-internal integer, never derived from title, handle, or URL slug,
per this morning's identity-stability finding (ADR from the 2026-09-13 diagnostic session) and
petmax's `-6847` slug-collision counter-example. `raw_payload` carries `sku`, `grams`, and
`product_type` — `grams` specifically for future reference, not as ground truth: recon found a
real animax listing (`grams: 500` on a product titled "... 2 kg") where the shop's own structured
weight field disagrees with its own title text by 4×. The overlap key stays title-only for exactly
this reason and was not changed.

**Evidence.** 10 categories, 2,551 products, exact-counted by walking `products.json` to its final
page (`docs/SOURCES.md`). Checked empirically, not assumed: zero of 750+ sampled products carry
more than one variant — every pack size is its own product, matching petmax's convention rather
than pentruanimale's grouping — so no variant-expansion logic was needed, though the adapter still
iterates `variants[]` generically rather than hardcoding "exactly one".

**Rejected.** Scraping the rendered HTML collection page (works, per CLAUDE.md §5's "prices in
the raw response" test, but ~58× the bandwidth for identical data, and requires class-based markup
parsing the JSON endpoint makes unnecessary). Treating `grams` as the net-weight source of truth
for future Phase 2 work (the 500g-vs-2kg disagreement found in recon rules this out; title-text
parsing remains authoritative, consistent with the existing key).

**Date.** 2026-09-13

## ADR-0025 — Regulated-product detection: line-code tokens only; quarantine, never delete

**Context.** The 2026-09-13/14 diagnostic session found `is_regulated()` (12 hardcoded
lowercase-substring tokens, unfolded) missing real veterinary-diet products cross-listed inside
the general food categories on all three sources: it never folds diacritics (`"dietă
veterinară"` does not match `"dieta veterinara"`), never matches the plural (`"diete
veterinare"` matches nothing), and consults no source-side classification at all. Tested against
all 18,703 stored titles at the time, token by token:

| candidate token | matches | verdict |
|---|---|---|
| `"diete veterinare"` (plural) | 0 today | kept — real gap, just not yet exercised in this data |
| `" vd "` | 70, all genuine (Calibra VD, Brit Grain Free VD, ADVANCE VD) | kept |
| `" vhn "` | 23, all genuine (Royal Canin VHN) | kept — found *during* this session, not in the original diagnostic |
| `"dietetic"`/`"dietetica"` | 8, all already covered by `" vd "` | **dropped** — zero net catch, and Romanian retail uses "dietetic" loosely for ordinary weight-control food (a real false-positive risk with no offsetting benefit shown here) |
| `"hidrolizat"`/`"hydrolyzed"` | 0 today | kept — defensive, same reasoning as the plural |

The diagnostic session's own Tier-B samples (urinar/urinary, renal, mobility, hypoallergenic,
digestive care, obezitate, recovery, satiety, hepatic, gastrointestinal, sensitivity, diabetic —
95–362 rows per source) read overwhelmingly as ordinary retail condition-support food sold
without a prescription (Royal Canin Urinary Care, Hill's Healthy Mobility, Julius-K9
Hypoallergenic), not restricted veterinary diets. The real manufacturer distinction is the
*line*, not the *symptom*: Royal Canin splits retail "Care Nutrition" from veterinary-channel
"VHN"; Brit splits retail "Brit Care" from veterinary "Brit VD"; Hill's splits retail lines from
"PD" (Prescription Diet — found this session, not yet acted on, see Open issues in STATE.md).

Two further signals exist beyond title text. animax's Shopify `product_type` field already
classifies 108 rows as "Diete veterinare pentru caini/pisici" — a title check alone would miss
25 of them (e.g. "Hill's PD Metabolic", no token catches "PD") and the shop's own classification
misses 2 that title tokens catch (e.g. "ADVANCE VD Gastroenteric", filed as plain "Hrana uscata
pentru caini"). pentruanimale's VTEX `__STATE__` carries `categories`/`categoryId` on every
Product node (confirmed live) but the adapter never captured it — so pentruanimale's true leak
size cannot be measured from data already collected; its 0-Tier-A-hits result is "not measured",
not "clean" (see STATE.md).

**Decision.**
1. `is_regulated()`/`REGULATED_TITLE_TOKENS` (petmax.py, shared): fold diacritics via the
   existing `normalize_title()` before matching; add `"diete veterinare"`, `" vd "`, `" vhn "`,
   `"hidrolizat"`, `"hydrolyzed"`. A new `regulated_match()` returns *which* token fired (not
   just a bool), so a caller can record the reason without re-deriving it.
2. animax (A4): `product_type` is checked as a second, independent signal in `_parse_product`,
   before insertion — a product is skipped if *either* the title or `product_type` flags it.
3. pentruanimale (A4): `categories`/`categoryId` are captured into `raw_payload` from now on.
   Forward-only — **not backfilled, cannot be backfilled**. STATE.md states plainly that
   pentruanimale's regulated-product exposure is unmeasured, not clean.
4. petmax (A4): no change. Its leak is entirely cross-listed items inside allowed food
   categories (confirmed in the diagnostic session) — the category the listing was scraped from
   tells us nothing a title check doesn't already know.
5. **118 already-collected rows are quarantined, not deleted** (STEP 2, this session): a new
   nullable `raw_listings.excluded_reason` column (migration 0004) records which signal fired;
   `NULL` means in scope. `scripts/quarantine_regulated.py` applied the tightened rule + the
   animax `product_type` check to every row with `excluded_reason IS NULL` — idempotent, and
   reversible by clearing the column on any row later found to be a false positive. `make
   status`, the listing-count gate, and `overlap.py`'s population all now read `excluded_reason
   IS NULL`, and `make status` prints total and in-scope side by side rather than applying the
   difference silently.

This lands **now**, in Phase 1, not deferred to Phase 2's `raw_listings -> norm_listings` work —
the in-scope listing count is a Phase 1 gate claim already ticked in STATE.md; holding a ticked
gate on a number known to include regulated products would be worse than the gap it corrects.
Phase 2 will reuse this same rule at the `norm_listings` boundary; it does not originate it.

**Evidence.** Per-source quarantine counts (`scripts/quarantine_regulated.py`, applied
2026-09-14): petmax_ro 8 rows (4 distinct products × 2 collected days), pentruanimale_ro 0,
animax_ro 110 (of which 83 agree on both signals, 25 caught by `product_type` only, 2 caught by
title only). Grand total: 18,703 stored → **18,585 in-scope**, still far above the 3,000
threshold. ADR-0023's sampled population, recomputed with quarantined rows removed: 2,329 →
**2,334** keyable, in-scope petmax food listings (only 4 of the 118 fell inside that specific
population). p̂ = 0.52 unchanged (the sample itself was not re-drawn); point estimate 1,211 →
**1,214**, 95% CI [897, 1,519] → **[899, 1,522]**. The gate holds with the same wide margin as
before — the correction moved the estimate by about 0.3%.

**Rejected.**
- **Adding symptom/condition-word tokens** (urinar/urinary, renal, mobility, hypoallergenic,
  digestive care, obezitate, recovery, satiety, hepatic, gastrointestinal, sensitivity,
  diabetic). This session's own Tier-B data is the argument: these tokens would flag hundreds of
  ordinary, purchasable retail products per source that are not restricted in any way — trading
  a small, real false-negative problem for a much larger false-positive one that would remove
  genuinely in-scope competitor products from the catalogue. If a specific named product turns
  out to be genuinely regulated, that is a case-by-case judgment a human makes by checking the
  brand's actual retail-vs-veterinary line split — not a keyword a script can reliably apply.
- **Deleting the 118 rows.** They carry two real, already-collected days of price history that
  CLAUDE.md §7 Phase 4 says cannot be recovered once missed. Given how much the tokens themselves
  changed between this session's first pass and its per-token-verified final pass (adding `"
  vhn "` alone added 23 rows that a narrower, earlier version of "Tier A" did not catch), treating
  today's rule as permanently final and destroying data on that basis would be premature. The
  quarantine column costs one migration and a few query filters; deletion costs the ability to
  ever revisit the decision.
- **Deferring the correction to Phase 2's `norm_listings` boundary.** Considered and rejected in
  this same session: the in-scope listing count is a Phase 1 gate claim, ticked in STATE.md
  today. A phase that has not started cannot be where a currently-ticked gate's number gets
  corrected. Phase 2 will still apply this same rule at the `raw_listings -> norm_listings`
  boundary for its own purposes — it inherits the rule, it does not own the decision to apply it
  now.

**Date.** 2026-09-14

## ADR-0026 — Phase 2 normalized layer: `norm_listings` schema, content_hash as a global title-only cache key, weight/volume as a checked invariant, dosage bands stay text, deterministic extraction first

**Context.** CLAUDE.md §6 names the pipeline stage (`raw_listings -> norm_listings`) but not the
table's shape. Phase 2 needs somewhere to put brand, product line, net weight/volume, pack count,
breed-size code, life stage, flavour, food form and dosage band, extracted from titles — with two
constraints CLAUDE.md's cost discipline and this session both insist on: extraction must run once
per unique title, never per scrape run (§5.1 — the single largest cost-risk named in the whole
document), and a null attribute must be distinguishable as "the title doesn't say" from "the
extractor broke" — conflating the two would make the Phase 2 gate (≥85% attribute accuracy)
unmeasurable, since a broken extractor and an honest "not stated" would look identical.

**Decision — table shape.** One table, `norm_listings` (migration 0005): `content_hash` (the
cache key, unique), `sample_source`/`sample_title` (one representative raw title/source, since
a hash isn't reversible), the ten extracted attributes (`brand`, `product_line`, `net_weight_g`,
`net_volume_ml`, `pack_count`, `bonus_weight_g`, `breed_size_code`, `life_stage`, `flavour`,
`food_form`, `dosage_band` — all nullable), and three extraction-metadata columns
(`extraction_status`, `extraction_errors` JSON, `extractor_version`). No foreign key to
`raw_listings`: `content_hash` is not unique there (many rows legitimately share one hash), so the
join is by hash value at query time, not by a constrained relationship. `raw_listings` stays
untouched — this table only ever reads `WHERE excluded_reason IS NULL`, never writes back.

**Decision — `content_hash` is reused, verified first, and is deliberately global across
sources.** Before reusing it as the cache key, `Listing.content_hash` (scrapers/base.py) was read,
not assumed: `sha256(normalize_title(self.title))` — title only. No price, no `compare_at_price`,
no stock state, no source. Confirmed by reading `runner.py:192`, which persists exactly that value
into `raw_listings.content_hash` with nothing else mixed in. It is therefore safe to reuse: it does
not change when a price moves, so it will not grow a new `norm_listings` row per price change or
force re-extraction on an unchanged title — the CLAUDE.md §9 failure mode this had to be checked
against before use, not after.

Because the hash carries no source component, reusing it as-is makes the key **global across
sources by construction**, not scoped per `(source, content_hash)` — a deliberate choice, not an
accident inherited from the reuse. Considered and rejected: scoping per-source, which would
re-extract every time two shops happen to write a byte-identical normalized title. That happens
rarely given how differently these shops write titles (CLAUDE.md §7's own examples), but when it
does happen it means the same real product with the same real attributes — extraction depends only
on the text, not on which shop produced it — so paying to re-derive the same answer twice would be
waste with no accuracy benefit, not caution.

**Decision — net_weight_g and net_volume_ml are mutually exclusive, enforced twice.** A listing's
quantity is mass-based (kibble, litter) or volume-based (shampoo, liquid supplements), never both.
Enforced at two levels: a DB `CheckConstraint` (`ck_norm_listings_weight_xor_volume`, plain boolean
SQL — `NOT (net_weight_g IS NOT NULL AND net_volume_ml IS NOT NULL)` — deliberately not Postgres's
`num_nonnulls()`, so the identical constraint is testable against SQLite in-memory with no live
database) and a SQLAlchemy `@validates` hook on the ORM model that raises `ValueError` at
assignment time, independent of the DB round-trip. Both null is allowed and means "quantity not
stated in the title" — a legitimate, expected value, not a violation. Tested offline
(`tests/test_norm_listings.py`): the ORM guard, the DB constraint via a Core-level insert that
bypasses the ORM guard entirely, and that exactly-one-or-neither is accepted.

**Decision — "not stated" vs "extraction failed" stays distinguishable.** A null attribute with no
matching key in `extraction_errors` means the extractor ran and the title genuinely doesn't state
that attribute. A null attribute **with** a matching key in `extraction_errors` (a JSON map of
`{field_name: error message}`) means the extractor raised on that field and the null is a gap. The
column is written only for the second case — never for an ordinary absent value — because writing
it for both would erase the exact distinction the column exists to preserve.

**Decision — `dosage_band` stays text, not split into min/max.** The Phase 2 gate needs the value
correct and distinguishable from "not stated", not range-queryable. A split into
`dosage_min_kg`/`dosage_max_kg` is mechanically derivable later from the stored text without
re-extraction, so deferring it costs nothing and avoids inventing a numeric convention (open vs.
closed bounds, unit handling) the gate does not yet need. Convention 4 (STEP 2, below) is the
higher-stakes rule for this field: a dosage band is the *animal's* weight and must never populate
`net_weight_g`.

**Decision — deterministic extraction first, LLM fallback stays unimplemented.** CLAUDE.md §7 is
explicit: regex and lookup tables first, an LLM only for what they cannot reach, cached by content
hash. STEP 3 of this session builds weight/volume parsing, brand canonicalization, an EN/RO
flavour table, and the rest as pure functions with offline fixture tests — no network call, no
API key read. The LLM transport stays unimplemented (ADR-0006 unchanged): there is nothing in this
phase's scope that has been shown to need it yet, and CLAUDE.md §5 treats an LLM call as something
that requires justification and a budget line before it exists, not a default reached for when a
regex would do.

**The five STEP 2 conventions** (four decided when this ADR was first written, a fifth added the
same day, before labelling started — see below. Written here verbatim so the gate-sample labeller
and the extractor cannot diverge on definitions; also carried in
`docs/learned/phase2-gate-sample-README.md`, a sibling of the frozen CSV, not a comment block
inside it — see the amendment at the end of this ADR for why):

1. Multipack `"12x85 g"`: `net_weight_g = 85` (the single unit), `pack_count = 12`. Total mass is
   derived, never the stored net weight — a 12-pouch box and a single pouch are different
   purchasable units, and `pack_count` is what distinguishes them.
2. Bonus pack `"12+2 kg"`: base = 12000, bonus = 2000, recorded separately in `net_weight_g` and
   `bonus_weight_g`. Reuses `OverlapKey.bonus_g`'s existing semantics exactly (ADR-0021) — not a
   second, conflicting convention.
3. `"1 x 85 g"`: `pack_count = 1`, `net_weight_g = 85`.
4. Dosage bands (`"10-25 kg"`) are the **animal's** weight, never the product's. They must never
   populate `net_weight_g` — the highest-risk confusion in this field, and the reason
   `net_weight_g`/`dosage_band` are two separate columns rather than one field a heuristic has to
   disambiguate after the fact.
5. **`brand` is the manufacturer, lowercased, in its simplest form**: `"brit"` (not
   `"Brit Premium"`), `"hill's"` (not `"HILL'S Science Plan"`), `"royal canin"`, `"calibra"`. The
   sub-line ("Premium by Nature", "Science Plan", "Life", "Care") belongs in `product_line`,
   never in `brand`. Added same-day, before any labelling happened, once review caught that brand
   form was otherwise undefined in this schema — the column existed, but nothing said whether
   "Brit Premium" or "brit" was the correct value, which would have failed the 85% gate on a
   definition disagreement between the labeller and the extractor rather than on either one being
   wrong. STEP 3's brand canonicalization targets exactly this shape.

**Rejected.**
- **Scoping `content_hash` per `(source, content_hash)`.** Would multiply extraction work exactly
  in the case where two shops coincidentally agree, which is the one case where re-extraction is
  guaranteed to produce the same answer — see above.
- **A single sentinel value (e.g. `-1` or `""`) for "extraction failed" instead of a separate
  `extraction_errors` column.** A sentinel inside a typed numeric/text column is exactly the kind
  of silent conflation CLAUDE.md's schema requirement this session was written to prevent — it
  would be indistinguishable from a real value without an out-of-band convention every reader has
  to remember. A separate JSON column makes the failure explicit and inspectable instead.
- **Splitting `dosage_band` into numeric min/max now.** Not needed for the gate; derivable later
  from the stored text without re-extraction; see above.
- **Postgres's `num_nonnulls()` for the weight/volume constraint.** Works, but ties the constraint
  (and any test of it) to a live Postgres instance. Plain boolean SQL does exactly the same job and
  is portable to SQLite in-memory, so the enforcement is offline-testable, not just
  applied-and-trusted.

**Date.** 2026-09-13

**Amendment, same day, before labelling started.** The frozen sample originally carried the
conventions as a "#" comment block at the top of the CSV itself. That block's first line contains
a comma, so Excel, Google Sheets and pandas all read it as the header row and scrambled every
column — the file was invalid CSV in practice, not just untidy. Fixed by moving the conventions
into a sibling file, `docs/learned/phase2-gate-sample-README.md`; the CSV now starts directly with
its real header row. The 100 rows, their order and their ids are unchanged — verified by diffing
the old file's data rows against the new CSV before committing, not re-drawn. This is also when
convention 5 (brand form, above) was added, for the reason given there.

## ADR-0027 — product_line extraction design; breed_size/life_stage gap report stays diagnostic-only; flavour/food_form tables extended from a checked sample

**Context.** Three parallel gaps from STEP 3/4's coverage report needed work while the Phase 2
gate sample is being labelled externally (docs/learned/phase2-gate-sample.csv — frozen,
unlabelled, and never read or used as input for any of this): `product_line` extraction did not
exist (0% coverage, by design); `breed_size_code`/`life_stage` had raw coverage numbers but no
breakdown of what their nulls actually meant; `flavour`/`food_form` had ~1,300-1,700 titles each
flagged as "likely a real food item, this field's word was missed". All work below draws its
examples from `raw_listings`/`norm_listings` (the full in-scope population), never the frozen CSV.

**Decision — product_line.** Built as a closed-vocabulary removal: the title minus (a) the shop's
own raw `source_brand` field text (never a canonicalized or guessed form — see `brand.py`'s own
note that convention 5's sub-line belongs in `product_line`, not `brand`), (b) a small,
data-built regex matching only contiguous sequences of recognized Romanian food/treat
descriptive words (form: uscata/umeda; packaging: plic/conserva/tavita/punguta/galetusa/bax/tub/
bol; qualifiers: monoproteica/fara cereale/continut redus cereale; animal: caini/pisici and
variants; a closed set of pack-descriptor words: multipack/pachet economic/pachet mixt), and (c)
the exact spans `quantity.quantity_spans()` used to produce its result (a new function added to
`quantity.py` this session, reusing the same compiled patterns and precedence order as
`extract_quantity` so the two can never disagree about what counts as "the quantity"). Everything
else is preserved verbatim, in its original language and casing.

Life-stage words (junior/senior/adult(i/e)/sterilizat(e/i)) are consumable **only** as the word
directly following an animal word inside a matched clause, never as a free-standing strip —
checked and enforced before trusting the pattern: `"Royal Canin Mini Adult 8 kg"` has no
`"hrana"/"recompense"` clause at all, and `"Adult"` there is the product's own real line name
(Royal Canin genuinely sells "Mini Adult"), not shop boilerplate. A global life-stage strip would
have silently deleted it. `tests/test_normalize_product_line.py::test_royal_canin_line_name_survives_intact`
is the regression guard.

Two real gaps were found and fixed while previewing 33 real before/after pairs (the required 30,
plus a few extra) before running this over the full table: (1) the reversed pack form
(`"85g x 4buc"`, 622 titles) left a dangling `"x"` glue character — bridged by extending
`quantity_spans()` to merge the gap between two adjacent found spans when it contains nothing but
whitespace or the multiplication sign; (2) `"multipack"`/`"bax"`/`"pachet economic"`/`"pachet
mixt"` (199+115 titles, checked in real context before adding — every occurrence sits directly
adjacent to a pack quantity, never inside a brand's sub-line name) needed their own removal
pattern, since some occur with no preceding hrana/recompense clause at all. A third refinement —
`"junior & adult"`-style compound stage chains (130 titles) — extended the trailing-stage slot to
accept `"& (junior|senior|adult(i/e)|adult)"` repeats, with the bare, otherwise-forbidden `"adult"`
form allowed **only** as the second+ link of a chain already anchored by a real stage word, never
as an entry point on its own — preserving the exact safety property the Royal Canin case above
depends on.

**`product_line` is NOT wired into `normalize.extract()` or run over `norm_listings` this
session** — CLAUDE.md's explicit instruction: 30 real pairs are shown for review first, full-table
coverage is measured only after that review. `extract()`'s `product_line` field stays hardcoded
`None` until that happens.

**Decision — breed_size_code/life_stage stay diagnostic-only.** The ask was to report the split
between "correct null" (the title genuinely doesn't state it) and "real gap" (stated in a form the
matcher misses), not to fix it. `scripts/normalize_coverage.py` gained two new shape functions
(`_breed_size_shape`, `_life_stage_shape`), each pattern checked against the real null population
before being trusted as a "real gap" bucket. Result: for both fields, the overwhelming majority of
nulls are genuinely correct —

- `breed_size_code` (7,690 nulls): 7,416 (96.4%) correct null, 155 (2.0%) RO "talie
  mica/mare/medie" stated but unmatched, 119 (1.5%) EN "Small/Medium/Large/Giant/Toy Breed" stated
  but unmatched.
- `life_stage` (7,571 nulls): 7,387 (97.6%) correct null, 175 (2.3%) "kitten" stated but
  unmatched, 9 (0.1%) an RO diminutive (catelus/pisicuta/pisoi) stated but unmatched.

Neither field's extractor was changed. If wired in later, the ceiling this data supports is
roughly 29.4% (`breed_size_code`) and 29.7% (`life_stage`) — a real but modest gain, not the
difference between a broken and a working extractor. The low raw coverage numbers mostly reflect
that most pet-food/treat listings genuinely don't state a breed size or life stage as a separate
descriptor, not that the matcher is failing on stated ones.

**Decision — flavour/food_form table extensions.** A seeded (20260917) random sample of 60 real
titles was drawn from the combined "likely real food, one field missing" pool (3,090 candidates:
1,366 flavour-missing + 1,724 food_form-missing) and read in full before any table change. Every
candidate word was then checked against the full in-scope population — count and real context
printed — before being added, same discipline as ADR-0025's per-token check:

*Flavour* (`flavour.py`), ten new EN/RO pairs: Bison/Bizon (14), Mackerel/Macrou (36),
Ham/Sunca/Jambon (77+5), Poultry/Pasare (210, kept **distinct** from Chicken/Pui — a different
level of specificity, and merging them would lose real information), Deer/Caprioara/Venison
(61+24), Reindeer/Ren (17, kept **distinct** from Deer and from the existing Game/Vanat bucket — a
different species; collapsing distinct species into one canonical value would hurt Phase 3
matching precision, not help it), Goose/Gasca (23), Sardine (28), Cod (142, identical spelling in
both languages).

*Food form* (`attributes.py`), six new words folded into the existing "specific" tier (checked
before the generic uscata/umeda fallback, same priority as conserva/plic): Jerky -> dry (108
total, 106 net-new), Pate -> wet (704 total, 51 net-new), Ragout -> wet (11 total, 8 net-new),
Cremoasa/Cremos -> wet (30 total, 30 net-new), Tub -> wet (76 total, 30 net-new), Sos -> wet (1,212
total, 74 net-new — mostly redundant with already-detected wet signal, as expected, but the net-new
74 are real).

**Rejected.**
- **"Cutie" (box, 128 total / 110 net-new) as a food_form signal.** Checked in real context first:
  samples showed it packaging both dry treats (dental sticks, supplements) and wet toppers with
  no reliable way to tell which from the word alone. Mapping it to any of dry/wet/tin/pouch would
  have been a guess dressed as a finding, exactly what this discipline exists to prevent.
- **Merging Reindeer into Deer or Game**, and **Poultry into Chicken.** Both would read as smaller,
  cleaner tables. Both would also destroy a real distinction Phase 3's matching needs — a
  reindeer product and a deer product are not the same product, and neither is a generic-poultry
  product the same as a chicken-specific one.
- **Fixing `breed_size_code`/`life_stage` in the same pass as reporting their gap.** Scoped
  strictly to what was asked (report the split); the found patterns (talie mica/mare/medie,
  Small/Large/Medium/Giant/Toy Breed, kitten, RO diminutives) are recorded here and in
  `normalize_coverage.py` precisely so a future session can wire them in without re-deriving the
  evidence.

**Evidence.** Coverage recomputed after STEP C (v3, `norm_listings` cleared and fully
re-extracted): flavour 59.6% -> 61.3% (+187 rows), food_form 56.1% -> 57.7% (+166 rows). Full
per-source breakdown and every remaining failure-shape bucket in STATE.md and this session's tool
output. STEP A's product_line coverage is deliberately not measured yet, pending the 30-pair
review.

**Date.** 2026-09-13 [continued below, 2026-09-14]

---

### Addendum, 2026-09-14 — product_line wired in (two fixes first); conventions 6 and 7; first gate measurement

**Context.** The architect-session review of `product_line`'s 30 preview pairs found two real bugs
before approving it to run over the full table. Both are fixed here, product_line is now wired
into `extract()`, and two more conventions surfaced while labelling `docs/learned/
phase2-gate-sample-labeled.csv` externally.

**Fix 1a — brand removal now strips only the manufacturer, never the shop's whole raw brand
field.** The original implementation stripped `source_brand` verbatim. For petmax's `"Brit
Premium"` that cut `"Premium"` out along with the brand, leaving `"by Nature Junior XL"` where the
real product line is `"Premium by Nature Junior XL"` — and worse, made the same product
non-comparable across shops: pentruanimale states the bare `"BRIT"` for the identical product, so
its product_line kept the whole `"Premium By Nature Adult Large Breed"`, sharing barely a token
with petmax's fragment. This is the exact Brit brand-field fragmentation the 2026-09-13 diagnostic
documented, re-entering through `product_line` instead of `brand`.

Fixed at the source: `brand.brand_span_text()` (new) returns only the manufacturer-only substring
of the raw brand field — the retained prefix once `_strip_marketing_suffix` removes a marketing
suffix (`"Brit Premium"` -> `"brit"`, leaving `"Premium"` as real sub-line text), or the whole
normalized string for an alias-table entry with no separate sub-line inside it (`"Affinity
Advance"` -> `"advance"`, unaffected by this fix). `product_line._brand_span` now searches for
that text instead of the raw field. Verified as the acceptance test asked: petmax
`"Brit Premium"` and pentruanimale `"BRIT"` now both produce a product_line starting with
`"Premium by Nature..."`; Calibra's Life/Premium/Expert petmax forms and pentruanimale's bare
`"CALIBRA"` all keep their real sub-line words; petmax's `"Hill's Pet Nutrition"` and
pentruanimale's `"HILL'S Science Plan"` both strip to the bare manufacturer, keeping their
(different, real) sub-lines. `tests/test_normalize_product_line.py` carries all of these as
regression tests.

**Fix 1b — a general dangling-token guard, not a per-case patch.** Found via a real accessory
title: `"Bol pentru hrana animale, inox, diametru 2 l, 25 cm, Negru Agility"` — excising the
quantity span `"2 l"` left `"diametru"` (its own qualifier) stranded in its own comma segment,
naming nothing. `product_line.py` gained a closed-vocabulary post-step
(`_strip_dangling_tokens`, run to a fixed point after every other removal) that drops a
comma-delimited segment reduced to nothing but one connective/qualifier word (`cu`, `si`, `de`,
`din`, `diametru`, `and`, `with`), and separately strips the same words from the whole string's
own leading/trailing edge. A companion checker, `product_line_guard_violations` (exported, not
test-private), encodes the same five invariants CLAUDE.md's instruction named — never fires on a
word that sits inside a longer real phrase, only on a segment/edge that reduces to exactly one
dangling word.

**Evidence.** Swept the guard over the full in-scope population (18,585 titles, this session's own
query): **zero** `product_line_guard_violations` after cleanup. Comparing pre-guard vs post-guard
output found **260 real titles** where the guard changed something — not a hypothetical edge case.
Two shapes, both represented in `scripts/preview_product_line.py`'s STEP 1b acceptance-test set:
an orphaned mid-string qualifier once its quantity is excised (6 "Bol ... diametru ..." accessory
titles, one of which had no attached quantity at all — the raw title's own text was already
dangling, not just a guard-induced case), and a leading `"cu {word}"`/`"de {phrase}"` connective
left dangling once the clause immediately before it is removed (254 titles, mostly Skipper/Pure
Nurture/Dog&Dog "cu {flavour}"-leading titles).

**Convention 6 — `"N x W"` vs `"N bucati / W"`.** Look alike, mean opposite things: `"12x85 g"` is
N separately packaged units of W each (`net_weight_g = 85`, `pack_count = 12`); `"6 bucati / 90
g"` is N pieces inside ONE package whose total net weight is W (`net_weight_g = 90`, `pack_count =
6`). Verified on the live petmax page for listing_id 1597: `"Greutate neta: 6 bucati / 90g"` — 90 g
is the bag, not the piece. **No code change was needed** — `quantity.py`'s existing precedence
order (`_PACK_TIGHT` for the first form, `_PLAIN` + `_PIECE_COUNT` for the second) already
produces the correct fields for both; this convention just names and pins the behaviour down with
explicit tests (`test_convention_6_*` in `tests/test_normalize_quantity.py`) and in
`docs/learned/phase2-gate-sample-README.md`.

**Convention 7 — `breed_size_code` names the ANIMAL, never the product's own dimension.** A
harness, leash, collar, or transport crate routinely carries a size letter/word from the exact
same vocabulary ("L", "Medium", "XS-XL") as a genuine breed-size classification — but it's the
*product's* own size. Fixed with two guards in `attributes.py`: an accessory-context vocabulary
(`zgarda`/`lesa`/`cusca`/`transport`, each checked against the full population before trusting —
113/187/51/54 distinct real titles respectively, zero collisions with any "hrana"/"recompense"
title) that suppresses `breed_size_code` entirely when present; and a separate anchored check for
`"ham"` (harness) requiring it as the title's *first* word, not matched anywhere — a bare `\bham\b`
collides with the English loanword "ham" (the meat) two real flavour-description titles use
("... with ham and chicken", "Pate With Ham"), while all 130 distinct real harness titles open
with "Ham" as the product-category word. One known, accepted miss from this trade-off: `"Curea Y,
ham Julius K9 - M"` states "ham" mid-title with no other accessory word present, so its own "M" is
not excluded — "curea" (strap) appears in only 2 titles total in this data, too thin to trust as
its own vocabulary entry by this codebase's own standard. A dedicated positive control (`"Bete
dentare Medium pentru caini talie medie"` -> `"Medium"`) confirms a genuine breed-size word with no
accessory context still resolves. Verified over the full population: zero accessory-context titles
still produce a non-null `breed_size_code` after the fix.

**Wiring.** `product_line` is now composed in `normalize.extract()` (previously hardcoded `None`).
`EXTRACTOR_VERSION` bumped `2026-09-13-v3` -> `2026-09-14-v4`. `norm_listings` was cleared (10,503
rows, fully derived/re-derivable from `raw_listings` — no data loss) and fully re-extracted:
10,503 rows re-inserted, zero extraction errors. **`product_line` coverage: 10,496/10,503 =
99.9%.**

**Gate measurement (STEP 3, `scripts/measure_gate.py`).** Scores exactly the ten fields an
external, code-blind model labelled in `docs/learned/phase2-gate-sample-labeled.csv` (committed
this session, unmodified, same 100 ids/order/titles as the frozen `phase2-gate-sample.csv`):
brand, net_weight_g, net_volume_ml, pack_count, bonus_weight_g, breed_size_code, life_stage,
flavour, food_form, dosage_band. `product_line` was labelled separately, by the architect session,
against a convention STEP 1 superseded — it carries **no accuracy figure**, per CLAUDE.md's
explicit instruction, and nothing was tuned against it.

**The first version of this measurement (96.6%) was inflated, and the correction is the more
important number here than the number itself.** Scoring against all 1,000 cells (100 rows x 10
fields) mostly scores "both sides correctly produced nothing" — most listings genuinely have no
`dosage_band`, no `pack_count`, no `bonus_weight_g`, so those trivial true-negative agreements
dominate the count and drown out the cells that actually test something. `dosage_band` alone
contributes 1 labelled cell and 99 such free points; `bonus_weight_g` 2; `net_volume_ml` 3. The
corrected script scores three different denominators, none hidden behind the others:

| Denominator | Result | Status |
|---|---|---|
| All cells (10 fields x 100 rows) | 966/1000 = 96.6% | transparency only, never the gate number |
| Labelled cells only, brand included | 346/368 = 94.0% | honest denominator, still mixes in an un-gradeable field |
| Labelled cells only, brand EXCLUDED | 261/273 = 95.6% | **superseded as "the gate number" by addendum #2 below** — this denominator cannot see a false positive; kept as the recall figure |

**Superseded — see addendum #2 below.** This table's own "95.6% is the gate number" claim was
itself corrected the same day: a labelled-cells-only denominator cannot penalise a false positive
(the extractor inventing a value where the label is empty), and two real titles in this sample
show that isn't academic. Addendum #2 adds a fourth, symmetric denominator that can — **93.2%
(261/280) is the actual gate figure**; 95.6% stays useful as the recall figure, not the headline.

Weight parsing (`net_weight_g`), measured separately per CLAUDE.md §7, on its 82 non-empty
labels: **82/82 = 100.0%**. Every per-field line in the script's output prints its own
`labelled_n` alongside the score, so a field with 1 labelled cell (`dosage_band`) can never be
mistaken for one actually measured 100 times.

**Reconciling this against the 90.8% (334/368) figure requested when this fix list was
approved.** That figure was a quick mental estimate (368 labelled cells minus all 34 mismatches =
334), not a re-run of the script — and it double-subtracts. 12 of the 34 total mismatches are
`extractor_has_extra` cases (the label was empty; the extractor produced a value anyway — a false
positive). A cell with an empty label was never part of the 368-cell "labelled" denominator to
begin with, so those 12 mismatches cannot be subtracted from it a second time. The rigorously
computed figure, run with the command above and shown in full below, is **261/273 = 95.6%**
(brand excluded) — higher than 90.8%, not lower. Both figures clear the ≥85% gate regardless, so
the substantive conclusion (gate met) is unchanged; only the specific number is corrected here,
with the reasoning shown rather than either number asserted silently.

**`brand` is excluded from every headline figure, not merely because its score is the weakest.**
12 of `brand`'s 15 mismatches come from a labelling-scope artifact, not an extractor bug:
`scripts/draw_gate_sample.py` gives the labeller only `listing_id`/`source`/`title` — never the
shop's own structured brand field. `canonicalize_brand()` deliberately prefers that field over
parsing the title. For a real generic cat toy (`raw_payload.brand = "Opti"`, nothing resembling
that in the title), for `TRIXIE`-branded accessories with a purely descriptive title, for
`Record`-manufactured `"Premiao"`-branded treats, for `Ipts`-supplied `"Beeztees"`-branded items,
for `Inaba`-manufactured `"Ciao"`/`"Churu"`-branded food, and for a `PURINA`-brand-fielded
`"Pro Plan..."` title — the label, working from title text alone, wrote what a human reading only
the title would reasonably write, and the extractor wrote what the shop's own structured field
says. Both are defensible answers to *different* questions ("what does the title say" vs "what
does the shop's own catalogue say"); the gate sample's own labelling scope cannot distinguish
them, so this sample cannot grade `brand` either way — it is **neither an extractor bug nor a bad
label**. `brand`'s own correctness is already checked a different, better way: STEP 1's cross-shop
comparability test (same product, different shops, same canonical brand — Brit/Calibra/Hill's,
above in this ADR). This is a real, named methodology gap in the gate sample itself (worth fixing
in a future sample: expose `raw_payload.brand` to the labeller, or score brand against
title-only extraction as a separate, explicitly scoped measurement).

Three further brand mismatches are smaller, genuine disagreements, not bugs (excluded from the
headline along with the rest of `brand`, not separately subtracted): one canonicalization-
granularity call already made deliberately in ADR-0026 (`"Pro Plan"` -> `"purina"`, sub-brand to
parent manufacturer — arguable either way, not wrong); two hyphen-vs-space spelling variants on
Julius K-9 (`"julius k9"` vs the alias table's `"julius-k9"`) that this session's whitespace-only
normalization doesn't absorb (a hyphen-insensitive comparison would have, but that's a scoring
choice made after seeing the mismatch, so it stays scored as-is here, per the "change nothing to
improve it" instruction).

**This measurement is frozen — it is the measurement of record, taken before any gate-derived
fix, and it must not be re-run and re-reported after STEP 3's fixes below.** Every fix in this
addendum's fix list was *derived from* a mismatch in this same 100-row sample. Re-scoring those
same 100 rows after fixing what they revealed is tuning on the test set: the extractor would now
be partly optimized for exactly the cases being used to grade it, and any number that produced
would not be comparable to the number that passed the gate — it would be a different, easier
question ("did we fix what we just saw" rather than "does the extractor generalize"). The fixes
below are verified against population-wide coverage instead (before/after counts on the full
`raw_listings` table), never against this sample a second time. If a future session wants a
post-fix accuracy number, it needs a *new*, independently drawn (and ideally independently
labelled) sample — not this one, scored again.

**Full command output** (per-field breakdown, all three denominators, every one of the 34
mismatches) is reproducible with `uv run python scripts/measure_gate.py` and is not repeated
verbatim here; the table above is its summary.

**Cache proof (STEP 4).** `scripts/normalize.py` run twice over the full population, no code
change between runs:

```
# first run (after norm_listings was cleared for the re-extraction above):
in-scope rows: 18,585 | distinct content_hash: 10,503
already in norm_listings (cached, skipped): 0 | new to extract: 10,503
APPLIED: 10503 rows inserted.

# second run, immediately after, same population:
in-scope rows: 18,585 | distinct content_hash: 10,503
already in norm_listings (cached, skipped): 10,503 | new to extract: 0
APPLIED: 0 rows inserted.
```

The second pass did zero extraction work for every one of the 10,503 unchanged content hashes —
the cache holds, with real command output as evidence, not a claim.

**STEP 5 — failure shapes and a priority-ordered fix list (proposed, not implemented; approval
pending).** Every one of the 34 mismatches, grouped and counted, each population-wide count a
fresh query run this session (never assumed from the 100-row sample alone):

| # | Shape | Field | Sample count | Population count | Kind |
|---|---|---|---|---|---|
| 1 | Structured brand field differs from title-only label | brand | 12 | n/a — scope gap, see above | **label/methodology, not a bug** |
| 2 | `"punguta"`/`"punguță"` (diminutive pouch) not in the food_form vocabulary | food_form | 3 | 418 titles carry it; 386 still null | **extractor bug — highest real-world impact** |
| 3 | `"M-PETS"` (and likely other hyphenated brand codes) false-positives a bare `"M"` as breed_size_code | breed_size_code | 2 | 81 titles carry `"M-PETS"`; 73 currently mis-tagged `"M"` | **extractor bug** |
| 4 | Label appears to have missed an obviously-present flavour word, or under-reports a compound flavour the extractor correctly found in full | flavour | 4 | n/a — label errors, not extractor | **label disagreement** |
| 5 | Plural generic food-form words (`"uscate"`, `"umede"`) not matched (`_GENERIC_FORM` only covers singular `uscat[aă]?`/`umed[aă]?`) | food_form | 1 | 8 + 17 = 25 titles | extractor bug, low volume |
| 6 | `"semi-umeda"` (semi-moist) wrongly matched as plain `"umeda"` -> `"wet"` | food_form | 1 | 8 titles | extractor bug, low volume, but a real category error (semi-moist isn't wet) |
| 7 | Known, already-documented EN `"Small"`/`"Large"`/etc. breed-size gap (ADR-0027 STEP B) | breed_size_code | 2 | 119 (previously measured) | **known gap, deliberately deferred, not new** |
| 8 | Known, already-documented `"kitten"` life-stage gap (ADR-0027 STEP B) | life_stage | 1 | 175 (previously measured) | **known gap, deliberately deferred, not new** |
| 9 | Word-form breed-size (`"Mini"`) false-positives a product-line name (`"Sheba Mini"`) | breed_size_code | 1 | 7 (Sheba Mini specifically; the general word-form risk is broader and unmeasured) | extractor bug, same class as the already-guarded Royal Canin case but for `_WORD_SIZE` |
| 10 | `"vanat"` (generic "game") vs `"venison"` (specific "deer") — the label may be more semantically correct than the extractor's own canonical mapping | flavour | 1 | unmeasured | **genuine definitional ambiguity — argued, not silently accepted** |
| 11 | Julius K-9 hyphen/space spelling variant | brand | 2 | unmeasured | minor, scoring-normalization edge, not a real semantic bug |
| 12 | Canonicalization granularity (`"Pro Plan"` -> `"purina"`) | brand | 1 | n/a — deliberate ADR-0026 choice | definitional, not a bug |
| 13 | `"jerky"` -> `"dry"` (STEP C's deliberate choice) vs. label leaving it null | food_form | 1 | unmeasured | definitional disagreement, not clearly wrong either way |
| 14 | `"crevete"`/`"shrimp"` missing from the flavour vocabulary | flavour | 1 | 52 titles | extractor bug, moderate volume |
| 15 | Multiple life-stage words in one title (`"junior"` and `"Puppy"` both present); `.search()` returns the leftmost, not necessarily the more specific one | life_stage | 1 | unmeasured | genuine precedence-order question |

**Proposed priority order**, evidence-based (population impact first, real bugs before
definitional debates, known-and-already-deferred gaps last):

1. **#2 — add `"punguta"`/`"punguță"` to `_SPECIFIC_FORM`.** Single-word regex addition, 386
   titles currently null, zero collision risk expected (same discipline as every other word in
   that table — would be checked in context before trusting, per this codebase's standing rule).
2. **#3 — guard `_SINGLE_LETTER_SIZE` against a hyphenated brand code** (`"M-PETS"`, and any
   other `<letter>-<word>` brand pattern found on a real check). 73 titles currently mis-tagged.
   Same shape as the existing apostrophe guard (`_PRECEDED_BY_APOSTROPHE`) — a hyphen immediately
   after the letter, followed by more letters, is a code, not a size.
3. **#6 — exclude `"semi-"` from `_GENERIC_FORM`'s `"umeda"` match.** Small volume (8) but a clean
   category error every time it fires.
4. **#5 — extend `_GENERIC_FORM` to the plural forms** (`uscate`/`umede`). Small volume (25) but
   trivial to add alongside #6 in the same regex.
5. **#14 — add `"crevete"`/`"shrimp"` to the flavour vocabulary.** 52 titles, same checked-before-
   adding discipline as every other STEP C word.
6. **#9 — investigate `_WORD_SIZE`'s false-positive rate beyond "Sheba Mini" specifically**
   (unmeasured population-wide) before deciding whether a guard is worth the complexity, or
   whether 7 known cases is small enough to leave as a documented gap like #7/#8.
7. **#1, #4, #10, #11, #12, #13, #15 — no extractor change proposed.** #1 is a gate-sample scope
   gap (a future sample should expose the structured brand field, or score brand separately);
   #4 looks like labeller error, not something to chase in code; #10, #12, #13, #15 are genuine
   definitional questions worth a deliberate decision, not a quiet extractor tweak; #11 is a
   scoring-normalization choice, not an extractor issue. #7/#8 stay exactly what STEP B already
   called them: known, measured, deliberately deferred.

**Status at the time this fix list was proposed: not implemented,** every item above a proposal
awaiting approval. **Superseded below** — items 1-4 of the priority order were approved and
implemented the same day; see the next addendum.

**Date.** 2026-09-14

---

### Addendum #2, 2026-09-14 (same day, continued) — the gate figure corrected; the four approved fixes implemented; gate frozen

**The gate figure was corrected before anything was implemented, per instruction, so a fix could
not be tuned against an inflated number. Scored against `norm_listings` under `EXTRACTOR_VERSION
2026-09-14-v4` — before any of the four fixes below existed.** `2026-09-14-v5` (the current code,
fixes applied) has no accuracy figure of its own, by design; see the "frozen" note further down.

The 96.6% first reported above is the "all cells" figure — mostly "both sides correctly produced
nothing" (a plain title correctly has no `dosage_band`, no `bonus_weight_g` — `dosage_band` alone
contributes 1 real test and 99 such free points). A second pass then scored only labelled cells
(label non-empty), landing on 95.6% — closer, but that denominator **cannot penalise a false
positive**: a cell where the extractor invented a value against an empty label has no label to
compare against, so it is simply excluded from both numerator and denominator, and the extractor
pays no price for having been wrong. Two real titles in this exact sample show why that is not
academic: `"Hrana semi-umeda pentru caini Devora Dog GF Semi-moist Mini Caprioara si curcan
5kg"` (listing_id 28159, label empty, extractor said `"wet"`) and `"Recompense pentru caini Lily's
Kitchen Festive Dog Turkey Jerky 70g"` (listing_id 28860, label empty, extractor said `"dry"`) —
both real category errors, both structurally invisible to a labelled-cells-only score, and the
first is exactly what fix #3 below corrected. A denominator that cannot see the error class a fix
was written for is not measuring what the gate is supposed to measure.

So a **fourth, symmetric denominator** was added: every cell where *either* side claims a value
(label non-empty OR extractor non-empty) counts in the denominator, with the same numerator as
before (a false-positive cell was never "correct"). Derived arithmetically from the already-
recorded v4 counters — not a re-run:

```
total mismatches                                  34
labelled-cell errors (368 - 346)                  22
=> false positives (34 - 22)                      12
brand labelled-cell errors (95 - 85)              10
=> brand false positives (15 - 10)                 5
=> headline-field false positives (12 - 5)         7

Headline fields, symmetric:  261 / (273 + 7) = 261/280 = 93.2%
All ten fields, symmetric:   346 / (368 + 12) = 346/380 = 91.1%
```

The gate number is now reported as four explicit denominators, relabelled for what each one
actually answers:

| Denominator | Result | What it answers |
|---|---|---|
| All cells (10 fields x 100 rows) | 966/1000 = 96.6% | transparency only, never a gate figure |
| Recall on stated values, brand included | 346/368 = 94.0% | can the extractor reproduce a stated value? cannot see false positives |
| Recall on stated values, brand excluded | 261/273 = 95.6% | same, brand excluded |
| Symmetric, brand included | 346/380 = 91.1% | recall + false positives penalised |
| **Symmetric, brand EXCLUDED — THE GATE FIGURE** | **261/280 = 93.2%** | **the gate number: CLAUDE.md §7 says "attribute accuracy", and an extractor that invents values on empty cells is not accurate** |

Weight parsing (`net_weight_g`), on its 82 non-empty labels: **82/82 = 100.0%** (no false
positives on this field, so recall and symmetric agree). `scripts/measure_gate.py` prints every
field's own `labelled_n` and `symmetric_n` alongside its score, so a field with 1 labelled cell
can never again be mistaken for one measured 100 times.

**The gate is met on both figures — 95.6% recall and 93.2% symmetric — so the substantive
conclusion (gate met) is unchanged. Only the framing is corrected: 93.2% is the gate figure,
95.6% is kept alongside it as the recall figure**, because it answers a real, different, useful
question (of the values the extractor did produce, how many matched) even though it cannot stand
alone as an accuracy claim.

**Reconciling against the 90.8% (334/368) mental estimate that accompanied the approval of this
fix list.** 368 - 34 (all mismatches) = 334 double-subtracts: 12 of the 34 mismatches are
`extractor_has_extra` cases (label empty, extractor produced a value — a false positive), and a
cell with an empty label was never part of the 368-cell "labelled" denominator to begin with, so
it cannot be subtracted from it a second time. Both correctly computed figures (95.6% recall,
93.2% symmetric) are higher than the 90.8% estimate, not lower — the substantive conclusion (gate
met) does not change under any of the three numbers; only the specific figures are corrected here,
with the arithmetic shown rather than any of them asserted silently.

**A labelling-provenance limitation, stated plainly, not worked around.** CLAUDE.md §7 asks for
"100 manually verified listings". What exists is 100 listings labelled by an external, code-blind
model — not a human — and, checked this session, **zero of the 100 rows have the `ambiguous`
column flagged**. `docs/learned/phase2-gate-sample-README.md` commits to "a hand-check of every
flagged row (plus a random 10 of the rest)"; with nothing flagged, that QA step never ran. This
session's own STEP 5 table already classified 4 `flavour` mismatches as probable label errors, and
one of them is concrete: listing_id 28159's label states only `"Turkey"` while the title reads
`"Caprioara si curcan"` (deer and turkey — both present, per this codebase's own multi-flavour
convention). The ground truth behind both the 95.6%/93.2% figures is therefore known-imperfect and
was never independently adjudicated. This is recorded as a **stated limitation of the gate, not a
defect that invalidates it** — the margin over the ≥85% threshold is wide under every one of the
four denominators computed above. A future, compliant sample needs three things this one lacks:
human adjudication of every `ambiguous`-flagged row (plus a random check of the rest, as the
README already promised), exposure of `raw_payload.brand` to the labeller (see the `brand`-
exclusion reasoning above), and `product_line` labelled against the current (STEP 1) convention
rather than the superseded one STEP A's labels used.

**`brand` stays excluded from every headline figure** (89.5% on its own 95 labelled cells, for the
record) — not because its score is weakest, but because 12 of its 15 mismatches are a
labelling-scope artifact (the gate sample gives the labeller only `title` text, never the shop's
own structured brand field `canonicalize_brand()` deliberately prefers): two different inputs to
the same question, which this sample cannot grade either way. It is neither an extractor bug nor a
bad label. `brand`'s correctness is validated a different, better way: the cross-shop
comparability check in this ADR's first addendum (Brit/Calibra/Hill's, same product, same
canonical brand across shops).

**Both figures (93.2% symmetric, the gate figure; 95.6% recall) are now frozen as the measurement
of record, taken BEFORE any of the four fixes below.** Neither is re-measured after the fixes, and
no post-fix accuracy figure is reported anywhere in this repo. Every one of the four fixes below
was *derived from* a mismatch inside this same 100-row sample; re-scoring those same 100 rows
after fixing exactly what they revealed would be tuning on the test set — the extractor would now
be partly optimized for the cases used to grade it, and any number that produced would answer a
different, easier question ("did we fix what we just saw") than the one the frozen figures answer
("does the extractor generalize"). If a future session wants a post-fix accuracy number, it needs
a new, independently drawn sample — never this one, scored twice.
`scripts/measure_gate.py` now also computes the symmetric denominator for any *future* sample, but
was not re-run against today's database — the code was added and statically checked
(ruff/mypy/compile), never executed for this session's own figures.

**The four fixes — implemented, measured by population coverage (never by re-scoring the sample),
same checked-before-trusting discipline as ADR-0025.** `EXTRACTOR_VERSION` bumped
`2026-09-14-v4` -> `2026-09-14-v5`; `norm_listings` cleared and fully re-extracted (10,532 rows —
grown from 10,503 by ordinary scheduled collection between sessions, not a data issue; 0
extraction errors).

1. **`"punguta"` (diminutive pouch) added to `food_form`'s specific tier.** Checked first: 418
   distinct titles carried it at the time of the STEP 5 fix-list check, **every one** in a
   `"recompense"` (treat) context — zero collisions. Reconciled this session against a fresh
   count: **420** distinct titles carry it now — the 2-title difference is ordinary scheduled
   collection between the two measurements (the in-scope population grew from ~10,503 to 10,532
   distinct titles over the same window), confirmed by direct count, not assumed. Of those 420,
   **388 were null before the fix and now correctly resolve to `"pouch"`** — the fix's own
   contribution, verified by re-running the pre-fix `_SPECIFIC_FORM`/`_GENERIC_FORM` regex
   (without `"punguta"`) against the same 420 titles. The other **32 already had a non-null
   `food_form`** before this fix, via an unrelated word co-occurring in the same title (`"plic"`,
   or a generic `"uscata"`/`"umeda"` elsewhere in the title) — the earlier framing in this
   addendum ("all 420 now resolve to `"pouch"` (100%)") was accurate about the *end state* but
   overstated the fix's own contribution; corrected here to the true before/after: 388 fixed, 32
   already correct for unrelated reasons, 420 total after.
2. **A hyphenated-code guard added to `breed_size_code`'s single-letter matcher** — a bare size
   letter immediately followed by a hyphen and more letters is a code, never a size. Checked
   first, broader than the proposed "M-PETS" case alone: every non-`_COMPOUND_SIZE`
   `<letter>-<word>` shape in the full population was one of three real false positives —
   `"m-pets"` (81 titles, the brand M-Pets), `"m-pes"` (1 title, a typo/OCR variant of the same
   brand), `"l-carnitina"` (1 title, L-Carnitine — a supplement ingredient, not a size at all).
   After: 83 titles checked, 80 now correctly null; the remaining 3 (`"Os CHEWBO M-PETS...20x5x4
   cm - L"` and its M/S siblings) correctly still resolve — a real, separate trailing size token
   for the chew bone itself, the same positive-control shape as the dental-stick case already in
   the test suite, not a residual bug.
3. **Two small `food_form` fixes**, both checked against the full population before trusting:
   - Plural `"uscate"` (dry) added — 8 distinct titles, all genuine dried treats (`"Urechi
     Uscate"`, `"chipsuri uscate"`, `"fâșii uscate"`), no collisions. After: 8/8 now `"dry"`.
   - Plural `"umede"` (wet) checked and **deliberately NOT added** — 17 distinct titles carry it,
     and **every single one** is `"Servetele umede"` (wet WIPES, a hygiene accessory), never wet
     food. Adding it would have manufactured 17 false positives — exactly the class of bug this
     checked-before-adding discipline exists to catch, and the clearest evidence in this session
     that the discipline works.
   - `"semi-umeda"` (semi-moist) was matching the generic `"umeda"` alternative as a substring,
     mis-tagging semi-moist food as `"wet"` — a real category error (semi-moist fits none of the
     four dry/wet/tin/pouch values). Guarded with a negative lookbehind for `"semi-"`/`"semi "`.
     Checked first: 8 distinct titles carry `"semi-umeda"`, every one a real semi-moist product;
     none is a plain wet product the guard would wrongly null out instead. After: 8/8 now
     correctly null.
4. **`"creveti"`/`"crevete"`/`"shrimp"` added to the flavour vocabulary.** Checked first: 52
   distinct titles carry `"creveti"` (`"creveți"` folds to it), every one a real cat-food/treat
   shrimp flavour (`"Ton și Creveți"`, `"cu ton si creveti"`) — zero collisions. `"crevete"`
   (singular RO) and `"shrimp"` (EN) have zero hits today, kept anyway per this table's own
   commitment to cover both EN and RO halves of every pair. After: 52/52 now include `"shrimp"`
   (e.g. the exact gate mismatch, listing_id 11166, now scores `"tuna+shrimp"`, matching the
   label exactly).

**Population coverage, before -> after** (whole-table percentages moved slightly by the 29 newly
collected titles between measurements, in addition to these fixes — the per-target-title
before/after counts above are the clean signal): `food_form` 57.7% -> 61.4%; `breed_size_code`
23.8% -> 23.1% (a **real, expected decrease** — the M-PETS/L-carnitina fix removed false positives
that used to count as "coverage"; less coverage from fewer wrong answers is the correct direction
here); `flavour` 61.3% -> 61.4%.

**Tests added for all four fixes and the guard's regression boundaries** (a legitimate
`_COMPOUND_SIZE` code like `"L-XL"` must still resolve; a plain `"umeda"` elsewhere in a different
title must still resolve after the `"semi-"` guard) — `tests/test_normalize_attributes.py`,
`tests/test_normalize_flavour.py`. 381 tests pass; ruff, ruff format, and mypy strict all clean.

**Date.** 2026-09-14

## ADR-0028 — Phase 3 prerequisites: embedding-independent recall@20 measured below target (69.9%/26.9%), root cause found; three retrieval signals; annotation conventions and tool built; queue drawn

**Context.** Phase 3 opened per explicit instruction: build only the prerequisites for
annotation this session — not the baseline, not fine-tuning. The user's annotation time is the
scarcest resource in this project, so every step here exists to make sure the ~1,000 pairs Bogdan
eventually labels are the pairs the real retriever actually produces, not an idealized set.

**STEP 1 — a retrieval evaluation set independent of embeddings
(`scripts/build_retrieval_eval_set.py`).** Two sources, neither touching an embedding:

- (a) The 26 browser-verified genuine matches in `docs/learned/q3-verification.md` (27 rows
  drawn; ADR-0023 records row #13 as rejected — a petmax slug collision). Matched back to
  `raw_listings` by URL **and** the exact weight `q3-verification.md` recorded, not URL alone —
  found the hard way: `pentruanimale.ro` groups every size variant under one shared product URL
  (CLAUDE.md's own documented structural note), so a naive "latest row at this url" lookup
  silently resolved a Hill's 6kg pair to its own 1.5kg sibling variant instead. Fixed
  (`_resolve_variant`), never by recency.
- (b) 120 of the proxy key's 241 current cross-shop collisions (`overlap.py`, ADR-0023 —
  independent of embeddings by construction), manually plausibility-checked by reading each
  title pair. 4 rejected: 3 are life-stage variants the proxy key can't distinguish (Junior vs
  Adult, plain Adult vs Adult 7+/senior — the exact false-collision class ADR-0023's own 25-pair
  hand-check already flagged), 1 genuinely uncertain.

**142 known-positive pairs total** (26 + 116), comfortably over the ~100 floor — reported, not
silently assumed sufficient.

**STEP 2 — candidate retrieval (`scripts/build_embeddings.py`, `scripts/measure_recall_at_20.py`).**
`sentence-transformers` added (`paraphrase-multilingual-MiniLM-L12-v2`, local, free, zero API
spend, no `SPEND:` line). Migration 0006 adds `norm_listings.embedding` (384-dim, pgvector
IVFFlat cosine index). All 10,532 rows embedded from `f"{brand} {product_line or sample_title}"`.

**Result: recall@20 = 95/136 = 69.9%, 95% CI [61.7%, 76.9%] — below CLAUDE.md §7's >=90% target.
Not tuned — per instruction, the number is reported and the misses analysed by shape, then this
session stopped for review before touching the embedding text or the model.** The pooled figure
hides the real signal: `proxy_key_collision` (the "easy" subset, textually similar by
construction) scores 80.0%; `q3_browser_verified` (the true random, unbiased draw) scores only
**26.9%, 95% CI [13.7%, 46.1%]** — the honest measure of how hard this retrieval problem actually
is, since the proxy-key subset is biased toward pairs a crude token key already found similar.

**Root cause found for ~49% of misses (20/41), confirmed with direct evidence, not inferred.**
`product_line` (Phase 2's own field) already has weight stripped out of it by design — so
embedding `f"{brand} {product_line}"` makes same-brand-same-line-different-weight siblings
embed **identically** (a checked case: Hill's SP Canine Adult Small and Mini Light Chicken at 6kg
vs 1.5kg — cosine distance **0.0**, brand and product_line byte-identical on both rows). The true
cross-shop match for that Hill's listing never appears in its top-20 because 19 of the 20 nearest
neighbours are the SAME petmax listing's own weight/life-stage sibling variants (Puppy/Senior/
Mature/Adult × several weights) — the exact "same-line-different-weight" hard negative CLAUDE.md
names, now shown to degrade RETRIEVAL itself, not just downstream matching. The remaining ~51% of
misses show weaker cross-shop discrimination even without weight-crowding — a general-purpose
multilingual model not separating brand identity from generic flavour-word overlap strongly
enough (e.g. a `"MATISSE, Pui și Curcan"` query's top-20 is dominated by other brands' `"Pui"`
products, not its own cross-shop `"Matisse"` twin).

**STEP 3 — three retrieval signals, same checked-before-trusting discipline as ADR-0025/ADR-0027.**
Migration 0007 adds `norm_listings.category`/`brand_blocking_key`/`brand_is_distributor_code`,
backfilled by `scripts/backfill_phase3_signals.py` (kept separate from `scripts/normalize.py`
deliberately — needs `url`/`raw_payload`, which the title-only deterministic `extract()` pipeline
never reads).

- **`category`** (`normalize/category.py`) — petmax's URL path segment IS its own category (12
  segments, checked); animax's `raw_payload["product_type"]` is its own structured field (29
  values, checked); pentruanimale has neither, and its entire 4,023-title collected catalogue was
  checked against every non-food keyword this session — zero hits, so defaulting it to `"food"`
  is evidence-backed, not assumed. Population: food 8,601 / accessory 1,550 / litter 202 / toy
  177 / unknown 2.
- **`brand_blocking_key`** (`normalize/brand.py`) — hyphen/space/punctuation-insensitive,
  grounded in 5 real collisions found among today's own canonical brand values (`"club 4
  paws"`/`"club4paws"`, `"cat's best"`/`` "cat`s best" ``, `"my love"`/`"mylove"`,
  `"lolopets"`/`"lolo pets"`, `` "dr. clauder's"``/`` "dr. clauder`s" ``).
- **`brand_is_distributor_code`** — an automated statistical approach (per-brand title-overlap
  rate) was tried and **rejected as unreliable**: checked against the full population, real
  manufacturers (`"essential foods"`, `"chicoppe"`, `"dr seidel"`, `"dolina"`/Dolina Noteci, whose
  own "Piper" house brand shows in titles instead of its name) score identically to confirmed
  distributor codes — the statistic cannot tell "a real brand a generic-category title doesn't
  repeat" from "no brand identity at all". Shipped instead: a small, hand-verified list built by
  actually reading titles — `"opti"` (confirmed: every sampled title is a generic colour-varying
  cat-tree description, no brand word anywhere) and `"ipts"` (weaker evidence, kept with the
  caveat recorded). `"record"` was checked and found to be a real, identifiable Italian
  accessories manufacturer (most titles carry `"Record"`/`"BiscoRe"` visibly) — corrected from an
  earlier, hastier read of the same string during the 2026-09-14 gate-fix session that had called
  it a distributor code without checking title context.

**STEP 4 — `docs/learned/phase3-annotation-conventions.md`, written before the tool, not derived
from labelling** (Phase 2's own lesson: conventions invented mid-labelling produce a dataset that
disagrees with itself). Operational question: "are these the same purchasable unit, such that a
price-comparison engine should compare their prices?" Ten numbered rules (weight/multipack/bonus/
flavour/breed-size/life-stage → N; brand-string provenance → M; no-weight-stated and >15s
uncertain → S; reformulation → M, flagged) plus five named cases the rules don't yet fully cover
(pack-count-vs-total-weight ambiguity, variety packs, accessory bundles, dosage-band-as-breed-size,
a shop's own unresolved variant grouping) — each defaulted to `S` rather than given an invented
firm rule, the same discipline that grew Phase 2's conventions from 5 to 7 from real labelling
gaps rather than up-front guessing.

**STEP 5 — `tools/annotate.html`, single local HTML page, keyboard-driven** (M/N/S/U/F).
Extracted-attribute side-by-side table with differing cells highlighted; a token-level
(LCS-based) title diff; the STEP 4 rubric always visible in a sidebar; autosave to `localStorage`
on every decision (fully resumable — a deterministic seeded shuffle, Mulberry32, reproduces the
identical display order across sittings); visible counter/timer/median-decision-time and
per-tier progress; NEVER displays a model prediction or score anywhere — there is no such field
in the queue schema. Structurally supports the "silently re-present ~50 labelled pairs to measure
self-agreement" requirement (state is keyed by `occurrence_id`, distinct from the underlying
`pair_id`, so a repeated pair's second showing is recorded independently) — this queue's own
trivial-tier spot-check (37 pairs, below) is exactly that mechanism, exercised for real. Verified
by extracting the inline script and syntax-checking it (`node --check`), and by running the
token-diff and seeded-shuffle functions directly against the real queue JSON (Node, not a
browser — the Chrome extension was unavailable this session) — determinism and diff output both
confirmed correct. Not opened in a live browser; no annotation decision was made.

**STEP 6 — the queue (`scripts/build_annotation_queue.py`), drawn from two sources, not one —
found necessary this session, not assumed.** A first version drew every candidate purely from
pgvector top-20 retrieval and got 120 hard-tier pairs out of 6,241 (1.9%) — nowhere near the
>=40% floor. Cause: the same one STEP 2 diagnosed — top-20 neighbours are dominated by a
listing's OWN shop's siblings, so genuine cross-shop hard cases are structurally crowded out of
retrieval almost every time. Fixed with a second, targeted source: a direct SQL query for
cross-shop pairs sharing `brand_blocking_key` and identical `product_line` text where capacity or
flavour differs (444 such pairs exist, checked) — the same "deliberate hard-case inclusion"
discipline Phase 2's own gate sample used (hard-case forms drawn first, by a targeted query, not
invented for this script).

**A second real bug caught while building the queue, not left in the shipped classifier.** An
early tier classifier's `same_capacity` check required "at least one side states a value" before
trusting equal `net_volume_ml` — which silently marked EVERY weight-only product (the
overwhelming majority: `net_weight_g` stated, `net_volume_ml` correctly `NULL` on both sides,
ADR-0026's mass-XOR-volume invariant) as "different capacity", corrupting the trivial/hard split
for nearly the whole catalog and hiding every genuine trivial pair. Found by tracing one specific
misclassified pair (two identical Applaws 70g cross-shop listings, wrongly tagged `hard`) rather
than trusting the aggregate tier counts. Fixed to plain equality (`None == None` is a legitimate
match).

**Final queue: 1,000 pairs — hard 444 (44.4%), easy 519 (51.9%), trivial spot-check 37 (3.7%).**
37 trivial-tier pairs were found in the combined pool (auto-labelled `M`); all 37 were re-inserted
into the human queue as a spot-check (below the 50-pair target because only 37 exist — reported
exactly, not padded). Fraction of the underlying draw removed from human labelling by
auto-labelling: 3.7%. Estimated wall-clock at 200 pairs/hour: **5.0 hours**.

**Rejected.** Shipping the statistical brand-trust classifier despite its false-positive evidence
(would present an unreliable signal as trustworthy — worse than shipping nothing, same reasoning
ADR-0023 used to reject tuning `overlap_key()` to hit a target number). Tuning the embedding text
or model to push recall@20 above 90% this session (explicit instruction: report, analyse by
shape, stop for review — not "quietly improve until it looks good", ADR-0023's own precedent).
Inventing firm rules for the annotation-conventions gaps STEP 4 found (defaulted to `S` instead,
to be resolved from real labelling data the way Phase 2's conventions 6-7 were). Opening
`tools/annotate.html` in a live browser and making a real M/N/S decision (explicit instruction:
do not start the annotation run).

**Date.** 2026-09-15

---

## ADR-0028 addendum — architect audit response: corrected denominator, retrieval fix, extended
eval set, queue rebuilt with a designed class balance and a permanent guard

**Context.** An architect audit of the ADR-0028 session above found two problems: the recall
denominator's own docstring made a false claim ("this never happens in practice" — it happened 6
times), and the annotation queue was unusable (894/1000 pairs decided by capacity difference alone,
zero genuinely-positive sourcing, 100% cross-shop). Four tasks, addressed in order below. No
annotation run was started at any point, per instruction.

### TASK 1 — recall denominator correction and the multi-source content_hash finding

**The denominator was already 136 in the numbers reported (95/136 = 69.9%), but the docstring's
claim that the 6 skips "never happens in practice" was false, and the 142 -> 136 change was never
stated as a change.** Both corrected: `measure_recall_at_20.py`'s docstring now says plainly that
it happens 6 times and why, and this entry states the change explicitly. The six skipped pairs, all
cross-shop, all byte-identical normalized titles:

| eval_source | sources | title (identical both sides after normalization) |
|---|---|---|
| proxy_key_collision | animax_ro <-> petmax_ro | Hrana semi-umeda pentru caini Devora cu miel si orez 5 kg |
| proxy_key_collision | animax_ro <-> petmax_ro | Hrana uscata pentru caini Brit Premium by Nature Sport 3 Kg |
| proxy_key_collision | animax_ro <-> petmax_ro | Hrana uscata pentru caini Brit Premium By Nature Junior L 15 Kg |
| proxy_key_collision | animax_ro <-> petmax_ro | Hrana semi-umeda pentru caini Petkult adult talie mica curcan caprioara si orez 1.5 kg |
| proxy_key_collision | animax_ro <-> petmax_ro | Hrana uscata pentru caini Devora Grain Free Mini Adult cu iepure 4 kg |
| proxy_key_collision | pentruanimale_ro <-> petmax_ro | ROYAL CANIN Medium Sterilised Adult, hrană uscată câini sterilizați, 12kg |

**Why this is a finding, not noise.** Since `norm_listings` is keyed on `content_hash` globally
(ADR-0026), two cross-shop listings whose titles normalize byte-identically collapse into ONE row —
there is no second row for either the retriever or the annotation queue to ever present. Queried
the full population: **15 distinct `content_hash` values in `norm_listings` are backed by
`raw_listings` rows from two or more different sources** (13 animax_ro<->petmax_ro, 2
pentruanimale_ro<->petmax_ro; all are food listings, all have identical price-relevant structured
attributes on both sides, checked by sampling). This is almost certainly the single easiest and
most certain class of true cross-shop match in the whole dataset — near-zero ambiguity — and it is
currently **structurally invisible** to `measure_recall_at_20.py`, `build_embeddings.py`, and
`build_annotation_queue.py` alike, all of which operate on distinct `norm_listings` rows.

**Proposed (not implemented — this is a data-model question, not a queue-composition one).** The
cleanest fix is a new, cheap query: `raw_listings` grouped by `content_hash` having
`count(distinct source) >= 2`, surfaced directly to `make status` as its own line ("N products
already confirmed identical cross-shop by title alone") and optionally auto-labelled `M` the same
way STEP 6's trivial tier already is, rather than asking a human to re-confirm something the
database has already proven twice over. Not built this session — flagged for the next Phase 3
session to decide, since it touches how `norm_listings`' identity model is read elsewhere.

### TASK 2 — retrieval fix, measured in two steps

**(a) Embedding text now carries the discriminating fields `product_line` strips out.**
`build_embeddings.py`'s `embedding_text()` appends `net_weight_g`/`net_volume_ml`, `pack_count`
(only when a real multipack — `None`/1 read as equal, matching the annotation conventions' rule 1),
`life_stage`, `breed_size_code` to `f"{brand} {product_line or sample_title}"`. Re-embedded all
10,532 rows (`build_embeddings.py --force`, new flag added for exactly this — a full-recompute
that isn't a new-row backfill).

**(b) Candidate generation now blocks on `brand_blocking_key` before ranking.**
`measure_recall_at_20.py` gained `top_k_hashes_blocked()`: candidates restricted to the query row's
own `brand_blocking_key`, ranked by cosine distance inside the block; falls back to the unblocked
global search when the row has no usable key (`NULL`, or flagged `brand_is_distributor_code` —
blocking on a code that doesn't identify the real manufacturer would silently exclude the true
match, not just narrow the search).

**Results, both eval subsets separately, Wilson 95% CI, q3_browser_verified as the headline
(never the pooled figure — it is biased toward the proxy key's own textually-similar-by-
construction pairs):**

| stage | pooled (biased) | proxy_key_collision | **q3_browser_verified (headline)** |
|---|---|---|---|
| before (ADR-0028 original) | 95/136 = 69.9% | 88/110 = 80.0% | 7/26 = 26.9%, CI [13.7%, 46.1%] |
| (a) alone | 92/136 = 67.6% | 81/110 = 73.6% | 11/26 = 42.3%, CI [25.5%, 61.1%] |
| (a)+(b) | 123/136 = 90.4% | 108/110 = 98.2% | 15/26 = 57.7%, CI [38.9%, 74.5%] |
| (a)+(b), extended eval set (TASK 3) | 128/141 = 90.8% | 108/110 = 98.2% | **20/31 = 64.5%, CI [46.9%, 78.9%]** |

**(a) alone made the pooled figure worse and the headline figure better** — expected, not a bug:
the embedding text change breaks the false ties among same-line-different-weight siblings (the
root cause), which helps exactly the hard, unbiased q3 cases and can reshuffle easy proxy-key pairs
away from their previous (falsely tied) top rank. **(a)+(b) together clear the pooled figure over
the 90% gate target, but the headline figure — the honest one — is still 64.5%, below 90%,** with a
CI wide enough (driven by n=31) that it cannot yet distinguish "meaningfully below target" from
"close, noisy". Not tuned further this session, per the same discipline as the original ADR-0028
entry — reported and stopped for review.

### TASK 3 — extended eval set

Full detail, method, and the complete verified table: `docs/learned/q3-verification-extension-
2026-09-15.md`. Same method as the original Q3 (`q3-verification.md`): random draw over the same
population (petmax food-category keyable listings, now 2,353 at draw time), a new seed (`20260915`)
excluding the 50 titles already checked, verified by hand via the `claude-in-chrome` browser tool
against `pentruanimale.ro`'s real VTEX search.

**40 of a planned 150 draws were completed: 5 confirmed matches (12.5%)**, appended to
`phase3-retrieval-eval-set.csv`, growing the headline subset from n=26 to **n=31**. This is short
of the "at least 100" target, reported plainly rather than padded: at a 12.5% hit rate (well below
Q3's original 54% — genuine sample variation or a weaker query-construction choice this session
made, not resolved), reaching 100 confirmed matches from this population would need on the order of
800 draws, each costing 2-6 browser tool calls (a follow-up product-page visit is needed for any
plausible candidate whose weight isn't visible in the search-result card) — not achievable in one
session's budget. **Never drew candidates from the retriever being measured** — the population is
petmax's own raw listings, independent of embeddings throughout, so the resulting number stays
usable for TASK 2's measurement even though it fell short of size.

### TASK 4 — annotation queue rebuilt with a designed class balance and a permanent guard

**`scripts/build_annotation_queue.py` rewritten, not amended** — the audit's arithmetic (894/1000
capacity-differing, all 444 "hard" pairs negatives by construction, ~36 genuinely uncertain) meant
the SQL that sourced the queue was the problem, not a tuning parameter within it. The new version
draws from nine named, quota'd sources instead of one query a tier classifier sorted after the
fact:

- **Positives** (`proxy_key_collision` — the Phase 1 overlap proxy key, ADR-0023's ~96% precision,
  recomputed over the current population; `blocked_retrieval_positive` — TASK 2b's blocked
  candidate retrieval, capacity-tuple-filtered after a checked, not assumed, finding: unfiltered,
  same-brand different-weight siblings still dominated a block's own nearest neighbours and alone
  pushed the guard's capacity_differs figure to ~49%).
- **`capacity_differs`**, capped rather than uncapped — same targeted query as the first version,
  now split cross-shop / within-shop and bounded to ~30% of the queue instead of taking everything
  available.
- **Four required negative/hard sub-classes**, each its own query with its own quota:
  `same_capacity_diff_flavour`, `same_capacity_diff_lifestage`, `same_capacity_diff_breedsize`,
  `diff_brand_similar_title`. **A real finding while building these**: requiring exact
  `product_line` text equality alongside an exact quantity-tuple match returned ZERO rows against
  the real population for all three same-capacity-diff-X classes — `product_line` strips exactly
  the qualifier these classes key on, so identical `product_line` plus a differing flavour is
  nearly a contradiction in the data as extracted today. Relaxed to same `brand_blocking_key` only
  (checked to confirm real volume: tens of thousands of candidates each) — recorded in the query's
  own comment, not silently loosened.
- **`reformulation_approx`** — searched `sample_title` for reformulation/generation marker phrases
  (`"noua formula"`, `"reformulat"`, `"new formula"`, etc.). **Result: zero matches in the entire
  collected catalogue** — none of these markers appear in any title. A genuine, checked finding
  (not a query bug — verified with a direct `LIKE` count per marker), reported as such rather than
  invented a synthetic substitute; this sub-class's quota (4%) was redistributed to
  `proxy_key_collision`, which had ample surplus (374 available in the population).
- **`capacity_differs_within_shop`**, its own quota (was 0% of the first version — 100% cross-shop
  — against the 2026-09-13 diagnostic's ~1,919 within-shop hard negatives that existed the whole
  time).

**The guard, implemented as specified.** For the whole assembled queue, computes the raw fraction
where `capacity_differs` (unconditional — the same computation that produces "894 of 1,000" for the
first version), `flavour_differs` (both sides stated), and `brand_differs` (canonical `brand`
field) each hold. **Refuses to write the file if any exceeds 40%**, printing which feature and by
how much. **Validated against both queues**: re-run against the first (committed) version's JSON,
the guard reproduces the audit's own figure exactly — capacity_differs 894/1000 = **89.4%**,
comfortably over the limit, confirming it would have refused that queue. Against the rebuilt
version: capacity_differs 29.4%, flavour_differs 13.5%, brand_differs 5.5% — **all under the
limit**, queue written.

**Final composition, 997 of the 1,000-pair target (reformulation_approx's 0-count is the only
shortfall not fully absorbed by redistribution):**

| category | count | % of queue |
|---|---:|---:|
| proxy_key_collision | 286 | 28.7% |
| blocked_retrieval_positive | 123 | 12.3% |
| **expected positives, combined** | **409** | **41.0%** (target: >=25%) |
| capacity_differs_cross_shop | 209 | 21.0% |
| capacity_differs_within_shop | 76 | 7.6% |
| **capacity_differs, combined** | **285** | **28.6%** (cap: ~30%) |
| same_capacity_diff_flavour | 85 | 8.5% |
| same_capacity_diff_lifestage | 66 | 6.6% |
| same_capacity_diff_breedsize | 47 | 4.7% |
| diff_brand_similar_title | 55 | 5.5% (short of its 66-pair quota — only 55 exist under the capacity-tuple-matched query) |
| reformulation_approx | 0 | 0.0% (population has none — see above) |
| trivial_spot_check (auto-labelled M elsewhere, re-shown for self-agreement) | 50 | 5.0% |

Estimated wall-clock at 200 pairs/hour: **5.0 hours** (up from the first version's 5.0 hours —
materially the same total size and rate, but now a queue that can actually teach the fine-tune
something beyond weight comparison).

**Rejected.** Padding `reformulation_approx` with a loosened query once the marker search returned
zero, which would have manufactured a sub-class the data does not actually contain. Requiring exact
`product_line` equality for the three same-capacity-diff-X classes once it returned zero rows,
rather than relaxing to `brand_blocking_key` and checking the real volume first. Continuing TASK 3's
browser verification past 40 items to chase the letter of "at least 100" once the achievable rate
made that arithmetic clear, rather than stopping and reporting the shortfall plainly. Starting the
annotation run once the guard passed (explicit instruction: stop and report, Bogdan reviews before
labelling).

**Date.** 2026-09-15 (same-day addendum, architect audit response).

---

## ADR-0028 addendum #2 — second architect audit: 12.5% retracted as a search-method artifact,
predicted-label forecast replaces "expected positives", eval-set contamination found and
corrected, pilot-stop built

**Context.** A second architect audit, of the addendum above, verified the guard works correctly
(reproduced 89.4% against the old queue exactly) but found three problems and asked for a fourth
capability. Four tasks, addressed in order, no annotation run started at any point.

### TASK A — the 12.5% figure retracted; the Phase 1 gate is not at risk

The audit's arithmetic is correct and was checked, not taken on trust: ADR-0023's gate rests on
p̂=0.52 (n=50) applied to N=2,329, point estimate 1,211, CI [897, 1,519]; at p=0.125 the same
arithmetic gives point estimate 292, CI [127, 609] — 400 falls inside, which would make the gate
undetermined rather than met, IF 12.5% were a valid re-measurement of the same quantity.

**Re-checked 10 of the 35 "not found" rows using a short query (brand root, or brand + core line
words — not this session's original `brand + product_line`).** Result: **0 of 10 became a newly
CONFIRMED match** — every one still resolves to `N` under the annotation conventions (a real
capacity or form difference). But the evidence for WHY the original queries found nothing is
decisive:

- **Item 39 (Hill's SP Canine Perfect Digestion, 3kg)** — the original full query returned ZERO
  results on pentruanimale's own search. A shorter query found the almost-exactly-named product on
  the first try (`HILL'S SP Perfect Digestion Small&Mini Adult, ...`). It still resolves `N`
  (6kg sold, not 3kg) — but the "not found" verdict itself was a search failure, not a fact about
  the product.
- **Item 17 (Advance Sensitive, "& orez"/rice token)** — the original query included a token
  ("orez") the real product's name does not carry at all; a query without it found the product
  immediately (resolves `N` on weight: 3kg vs. 7kg, but again the original absence was a query
  artifact).
- **7 of 10** turned out to have their brand+line genuinely present once queried more simply — the
  original full query found NONE of these seven; the short query found all seven (each still
  resolving `N` on a real, single differing dimension).
- **3 of 10** (Taste of the Wild, Chicopee, Josera) remained genuinely not found even bare-brand —
  real absence for those three specifically, not a query problem.

**Conclusion: the 12.5% figure is RETRACTED as an estimate of true market overlap.** It measured
this session's search-query recall, not the population — demonstrated concretely twice (items 17
and 39), not inferred. **The Phase 1 gate is NOT at risk**: it was never validly contradicted,
because the number that appeared to threaten it was never a comparable measurement in the first
place (a different, more careful method — Q3's own brand-then-scan verification — produced the
original 52%). Full detail: `docs/learned/q3-verification-extension-2026-09-15.md`'s addendum.

### TASK B — a predicted-label forecast replaces the source-tier "expected positives" claim

`scripts/build_annotation_queue.py` gained `predict_label()`: applies the conventions-v2 ladder
(rule 1 quantity, rule 2 life-stage — puppy/junior grouped per instruction, rule 3 breed-size,
rule 4 flavour, then `S` for a one-sided field or an ambiguous brand-only difference, `M` as the
fall-through) to every pair in the assembled queue. Conservative throughout: an N-rule fires only
when BOTH sides state the field. **Never used to auto-label anything beyond the pre-existing
trivial-tier pass** — this is a workload forecast, not a label source.

`blocked_retrieval_positive` renamed to `blocked_retrieval_candidate` throughout (a tier name must
not assert a label retrieval, at 64.5%/CI-wide recall and unmeasured precision, cannot guarantee).

**Result: M-plausible 31-32% of the queue** (fluctuates slightly run to run — `blocked_retrieval
_candidate`'s anchor draw uses `ORDER BY random()`, not seeded, a known minor reproducibility gap,
not fixed this session), comfortably over the 25% floor — **no rebalance needed.** N-by-rule ~55%
(quantity differs 28%, flavour differs 12%, life-stage differs 10-11%, breed-size differs 4%),
S-likely ~13%.

### TASK C — the eval-set extension is contaminated; the headline is corrected

All 5 of the 2026-09-15 extension's new pairs were hits: 15/26 (57.7%) became 20/31 (64.5%) — a
0.577^5 ≈ 6.4% event under the prior rate. **Mechanism, found in this session's own work**: the
extension's search queries were `brand + product_line`; TASK 2(a) (the addendum above) made the
embedding text `brand + product_line + quantity + ...` — the same core signal. A pair the
extension's query finds easily is, by construction, the kind of pair the embedding-based retriever
also finds easily. The extension is therefore not independent of what it measures — the identical
pooled-vs-unbiased bias already diagnosed for the proxy-key subset, re-entering through the query
one task later.

**Correction, in both the extension document and `measure_recall_at_20.py` itself** (not just
prose — the script now buckets `q3_browser_verified` by its `verification` date and prints both,
labelled): **57.7% (15/26, 2026-09-13) is the headline.** 64.5% (20/31) is printed separately,
tagged `EXTENDED ... CONTAMINATED`, never as "the" number. Rule for future extensions, per
instruction: the query must not share text with the embedding input — Q3's original "brand root +
weight, then scan by eye" qualifies; `brand + product_line`, however phrased, does not.

### TASK D — a configurable pilot stop, and a real ordering bug found while building it

**`tools/annotate.html` gained a pilot stop** (`PILOT_SIZE`, default 100, `?pilot=N` override):
the tool now stops cleanly once the first `PILOT_SIZE` positions of the display order are all
decided, showing observed M/N/S counts, a tally of S-reasons (a new lightweight, optional
non-blocking capture — five quick-key codes, never free text, so it doesn't cost the 200/hr
budget), and the pilot slice's median decision time, before a "Continue to full queue" action is
required to proceed.

**A real bug found while verifying the "first 100 must be representative" requirement, not
assumed.** `buildOrder()` shuffled WITHIN each tier but then concatenated tiers in plain
alphabetical order — verified directly against the real queue (`tools/annotate.html`'s own
`seededShuffle`/`buildOrder` functions extracted and run in Node, same discipline as STEP 5's
original verification): the first 100 positions were **100% `blocked_retrieval_candidate`** (that
tier's name sorts first), nothing else, for the ENTIRE pilot. Fixed by giving every item a
fractional rank within its own shuffled tier — `(position + 0.5) / tier_size` — and sorting the
whole queue globally by that rank, which spreads every tier's items evenly across the full
sequence. **Re-verified against the real queue after the fix**: every tier's share of the first
100 positions is within ±0.5 percentage points of its share of the full 997-pair queue (e.g.
`proxy_key_collision` 29.0% of the pilot vs. 28.7% of the full queue; `capacity_differs_cross_shop`
21.0% vs. 21.0%) — genuinely representative, not assumed to be from the seed alone.

**Rejected.** Free-text S-reason capture (would cost real time against the 200/hr target; five
quick-key codes plus an "other" bucket keep the same information at near-zero cost). Silently
continuing past the pilot boundary without a report (the whole point of a pilot is to check the
TASK B forecast against real labels before committing further hours). Assuming the shuffle seed
alone made the first 100 representative without checking — checked, and it was not, until fixed.

**Date.** 2026-09-15 (same-day addendum #2, second architect audit response).

---

## ADR-0028 addendum #3 — TASK A reopened: full SKU-list enumeration overturns 6 of 7 re-checked
rows; corrected rate 27.5%, form (a) conclusion

**Context.** A third audit challenged addendum #2's retraction of 12.5% directly: the 10-row
recheck it performed found brand+product line for 7 rows using a shortened query and called all 7
`N` on weight, but never enumerated each product's *complete* variant list — only whatever the page
or search result showed by default. This is the exact failure mode `_resolve_variant` (STEP 5,
ADR-0028) was built to catch the first time: pentruanimale groups size variants under one product
URL, and a naive lookup had already once resolved a Hill's 6kg pair to its own 1.5kg sibling.

**Method.** The Chrome browser extension was not connected this session (unlike the original Q3 and
its first extension, both done via `claude-in-chrome`). Each of the 7 rows' products was instead
looked up via pentruanimale's own public VTEX Catalog System API
(`GET /api/catalog_system/pub/products/search?ft=<query>` — the same unauthenticated JSON endpoint
the storefront's own search box calls), which returns every SKU (`items[].nameComplete`) with live
price/stock — strictly more complete than reading rendered HTML, and not subject to "only the
default variant renders."

**Result: 6 of 7 rows have the petmax weight somewhere in their full SKU list.** Brit Care
Hypoallergenic L-XL (petmax 3kg — full list 1/3/12/12+2kg), Advance Sensitive Mini XS-S (petmax
7kg — full list 3/7kg), Calibra Cat Life Hering (petmax 1.5kg — full list 1.5/6kg), Primordial
Holistic Ton&Miel (petmax 12kg — full list 2/12kg), Calibra Dog Life Senior Small Breed Miel
(petmax 1.5kg — full list 1.5/6kg), Hill's SP Perfect Digestion Small&Mini (petmax 3kg — full list
1.5/3/6kg, the 3kg SKU currently out of stock but real and listed). Only Hill's SP Feline
Sterilised Salmon (dry, petmax 1.5kg) checks out as genuinely absent — every Hill's SP Feline
Sterilised product on the site was enumerated; the dry line exists only in Pui/chicken, and Salmon
exists only as an 85g wet pouch. Full table: `docs/learned/q3-verification-extension-2026-09-15.md`
addendum #2.

**Recount.** 5 (original extension, Table 1) + 6 (newly confirmed) = **11/40 = 27.5%**, up from
12.5%. Wilson 95% CI [16.1%, 42.8%]. Same simplified population arithmetic as addendum #2 used
(N=2,334 keyable petmax listings): point estimate 642, CI [376, 1,000] (vs. 12.5%'s point 292, CI
[127, 609]).

**Conclusion, form (a) per instruction — explained, not unmoved, not inconclusive.** The rate more
than doubled under a demonstrated (not hypothesized) mechanism: incomplete variant enumeration,
the same bug class this project has already fixed once in code. **ADR-0023's Phase 1 overlap gate
remains genuinely unaffected** — it was never re-measured by this line of investigation; it stands
on its own hand-verified estimate (p̂=0.52, n=50, point 1,214, CI [899, 1,522]), untouched.

**Stated plainly, not smoothed over.** The corrected CI's lower bound (376) sits just under 400 —
this n=40 sample, even corrected, does not on its own statistically slam the door at 95%
confidence. Two reasons this is reported as resolved rather than as a new live risk: (1) this
sample was never the gate's own measurement — ADR-0023's independent p̂=0.52 sample is; (2) only 10
of the 35 "not found" rows in this sub-sample, and none of the original Q3 draw's 23 "no match"
rows, have been re-checked against a full SKU list — 27.5% is a floor under the same discipline
already applied to 12.5% itself, not a ceiling. If a future session wants a tighter number, the
next step is mechanical: re-run the remaining "not found" rows through the same VTEX Catalog API
check, not a fresh draw.

**Rejected.** Re-asserting "not at risk" without the page evidence behind it a second time — this
time it is backed by 6 concretely enumerated SKU lists, not an unretried assumption. Treating the
CI's near-miss of 400 as disqualifying when the population this sample draws from was never the
gate's metric of record to begin with.

**Date.** 2026-09-15 (third same-day session, architect audit response; Chrome extension
unavailable — verified via pentruanimale's public VTEX Catalog API instead of the browser tool).

---

## ADR-0028 addendum #4 — response to the 100-pair AI reference labelling pass (findings 4-8)

**Context.** `docs/learned/phase3-pilot100-ai-reference-pass.json` (an Opus architect session,
not a human — a measurement of the queue, never training data) labelled the pilot's first 100
pairs: M 36 / N 62 / S 2, vs. the rules-engine forecast's M 33 / N 53 / S 14, agreement 80/100.
Five gaps in the disagreement, addressed in order. Full detail, every number, the full breed-size
equivalence-class evidence, and the exact forecast movement:
`docs/learned/phase3-reference-pass-response-2026-09-15.md`; summary also in `STATE.md`.

**Species (finding 4).** `normalize/species.py` — same structured-signal-then-title-keyword
pattern as `category.py`. Checked, not assumed: the `"canin"` stem collides with the "Royal
Canin" brand on CAT products (282 titles initially mis-flagged); fixed with `"canine"` (Hill's
own dog-line word) instead. Litter resolves to `"cat"` unconditionally — this catalogue carries
no dog litter, checked directly. Backfilled via migration 0008 into `norm_listings.species`.
In-scope split: dog 4,888 / cat 3,791 / unknown 124 (1.4%, two named honest gaps). New
`predict_label()` rule 0b (species differs, both known -> N).

**Breed-size canonicalisation (finding 5).** Full 18-value census printed first. Equivalence
built from TWO independent real-population sources — pentruanimale's own titles pairing a word
form with a compact code in the same string, and a cross-shop same-product join (75 pairs) — not
assumed from "Medium"="M"/"Mini"="XS-S" alone. Modelled as a rank interval (XS=1..XL=5,
`breed_size_rank`/`breed_size_class`/`breed_size_overlaps` in `attributes.py`) rather than a flat
bucket, because compact codes like "M-XL" genuinely span more than one rank and a flat bucket
would have to arbitrarily pick a side (concretely demonstrated: bare "Maxi" maps to L-XL, but the
compound phrase "Medium & Maxi" maps to M-XL — same word, different real meaning, only
distinguishable because the compound CODE, already stored, is self-describing and never needed
re-deriving from word context). Two codes are "the same size" on any rank overlap, not string
equality. `predict_label()` rule 3 updated.

**"XS-XL" nulled (finding 6).** Checked, not assumed: 100% of 985 in-scope occurrences are
pentruanimale_ro, 0 from the other two sources — the largest `breed_size_code` value in the whole
population, consistent with a boilerplate "fits any size" default rather than a real claim.
`extract_breed_size` now returns `None` for a literal "XS-XL" match. 985 rows changed on
re-extraction (`scripts/reextract_breedsize_lifestage.py`, new this session).

**Age qualifiers reach `life_stage` (finding 7).** Checked against all 97 in-scope titles
carrying a bare `\d+\+` token, not assumed from the two named pilot cases: a real
false-positive class exists (bonus-weight phrases like "10+2kg GRATUIT") and is excluded by
requiring the `+` not be immediately followed by another digit — the same shape
`quantity.py`'s own bonus-weight pattern already uses, applied as a guard rather than reused
as a dependency. 38 of 97 candidate titles gained a qualifier (`"adult"` -> `"adult+7"`); a bare
qualifier with no life-stage word to attach to is left `None`, a named open gap, not guessed.

**Rule 0 leak, root cause and fix (finding 8).** Pilot 86's `category` was correct
(`"accessory"`) the whole time — checked directly, not assumed to be a mapping bug. The real
defect: none of the 9 source SQL queries in `build_annotation_queue.py` filtered on `category`
at all; `predict_label()`'s rule 0 caught the leak downstream and scored it `S`, which is exactly
why it only ever showed up as a forecast label rather than a visible bug. Fixed at the source:
`main()` now applies one `in_scope_only()` filter (category in food/litter, both sides) to every
pool right after listings are fetched, rather than duplicating a predicate into 9 queries.
Verified against the rebuilt queue: 0 of 1,157 distinct listings carry a non-food category.

**Forecast re-run, not tuned toward the observed distribution (explicit instruction).** M 30.2%
(was ~31-32%), N 57.8% (was ~55%, gap to observed 62% narrowed from ~7pp to ~4.2pp — mostly the
new species rule and the breed-size overlap fix), S 12.0% (was ~13%, gap to observed 2% barely
moved). **Finding 6's own hypothesis about S is only partially confirmed**: XS-XL nulling removed
exactly the one-sidedness it was manufacturing, but the S bucket's `one_sided_attribute` reason
(81 of 120 S pairs) is still dominated by one-sided flavour/life-stage cases unrelated to breed
size, plus 39 `ambiguous_brand_rule5` pairs the ladder deliberately never auto-resolves either
way. Reported as a structural property of the ladder's conservatism — no rule was loosened to
chase the observed 2%, which would be tuning the extractor to labels an AI produced.

**Record-keeping (Block 3).** The planned human blind-subset pass was **not run** — the pilot
numbers above are AI-labelled only, and CLAUDE.md §7's "the user annotates 800-1,000 pairs
manually... it is not generated, it is labelled" is **still unmet**. No AI-labelled pair may enter
the train/val/test split. Two carry-overs closed: the M/N/S forecast is now written into
`phase3-annotation-queue.json` itself (`predicted_label_forecast` key), and
`blocked_retrieval_candidate`'s previously-unseeded `ORDER BY random()` anchor draw is now seeded
via `setseed()` derived from `RNG_SEED` — the queue is fully reproducible from its seed.

**Rejected.** Loosening any N-rule or the one-sided-attribute fallback to shrink the S gap toward
2% — the observed distribution is a sanity check from 100 AI-produced labels, not ground truth,
and fitting the extractor to it would be tuning on a test set a model produced. Treating finding
6 as having "explained" the S gap once the population showed it only moved 13% -> 12% — reported
as a partial, not full, explanation, with the actual residual cause (one-sided flavour/life-stage,
ambiguous brand) named directly instead.

**Date.** 2026-09-15 (fourth same-day session, response to the 100-pair AI reference pass).

---

## ADR-0028 addendum #5 — follow-up review of addenda #3/#4: TASK A conclusion widened to a band,
queue-comparison invalidity found and corrected, cross-species quota proposed, species promoted
to conventions Rule 1

**Context.** A follow-up review of addenda #3 and #4 raised four substantive points and one
housekeeping pair. Handled in order; full numbers in `STATE.md` and
`docs/learned/q3-verification-extension-2026-09-15.md`/`phase3-reference-pass-response-2026-09-15.md`
(both edited in place — as working documents of record, not append-only the way this file is).

**1. TASK A conclusion restated at its real strength.** Addendum #3's "27.5%, form (a)" was
correct but under-claimed: only 10 of the 35 "not found" rows have ever been rechecked, and 6 of
those 10 (60%) flipped to confirmed. Extrapolating that 60% recovery rate to the 25 still-
unrechecked rows (25×0.60≈15, +5 original +6 confirmed = 26/40 = 65%) is arithmetic, not a new
measurement, and is explicitly flagged as optimistic — the 10 were not a random draw from the 35.
**Restated: the true rate lies in [27.5%, ~65%], and Q3's own 54% sits comfortably inside that
band**, which is the actual resolution to the original contradiction. What would close it
completely: rechecking the remaining 25 rows the same way (mechanical now — the VTEX Catalog API
check took seconds per product for the 7 rows addendum #3 verified), not done this session.

**2. The queue-comparison in addendum #4 was invalid, found and corrected.** The rebuilt queue
is a different draw from the queue the 100-pair pilot was drawn from — the session's own fixes
(species didn't exist before; XS-XL nulling and the extended `life_stage` change which rows the
source SQL's equal-attribute joins match; `in_scope_only()` removes rows outright) change which
pairs get sourced even with the same seeds. Measured directly: **only 44 of the pilot's 100
pair_ids survive in the rebuilt queue.** Addendum #4's whole-queue-vs-100-pilot comparison (and
its "N gap narrowed to ~4.2pp" claim) compared two different populations and is retracted.
**Corrected: before/after/observed recomputed on the n=44 intersection only** — N moved toward
observed (gap 15.9pp -> 6.8pp), M moved slightly away (2.3pp -> 6.8pp, possibly n=44 noise), S did
not move (7 pairs both times, vs. observed 1) — confirming finding 6 explains only part of the S
gap. Full table in `STATE.md`.

**3. Cross-species pairs: still in the queue, not removed, a quota proposed.** 49/997 (4.9%)
remain. Kept deliberately — a cat-vs-dog pair is a real, cheap easy-negative class, not removed
the way finding 8 removed out-of-scope categories. Proposed quota ~2% (≈20 pairs), lower than the
other required hard-negative sub-classes (4.7%-6.6% each) because species is cheaper/more certain
to decide than any of them. Current 4.9% sits above that proposed cap — reported for a future
queue rebuild, not acted on this session.

**4. Species promoted to conventions Rule 1.** `phase3-annotation-conventions.md` revision 3:
species inserted as the new Rule 1 (ahead of quantity, the cheapest and most decisive check),
revision 2's rules 1-8 renumbered to 2-9, text otherwise unchanged. `predict_label()`'s rule tags
renamed to match (`rule1_species_differs`, `rule2_quantity_differs`, ... `ambiguous_brand_rule6`)
— a pure rename, no logic change. **Found while re-running the queue for this**: the M/N/S totals
shift by 1-3 pairs run-to-run regardless of any code change, traced to Python's default
per-process string-hash randomisation affecting `set`/`dict` iteration order upstream of the
seeded shuffle — a minor, real reproducibility gap, not fixed this session, noted for a future one
(likely fix: `PYTHONHASHSEED` pinned for this script's invocation).

**5. Housekeeping.**
- **Commit policy.** The prior "uncommitted, per standing policy" line in this session's report
  was wrong — CLAUDE.md §4 states plainly, under BUILD: "Small commits, one logical change each.
  Do not ask permission." No rule in this file says otherwise. Corrected: this session's work is
  committed in logical commits (see git log), and this is the expected behaviour going forward,
  not an exception.
- **Database driver.** `pyproject.toml` and `uv.lock` are unchanged (`git diff` on both: empty).
  `pg8000` (a pure-Python driver, installed to work around a sandboxed environment's Windows
  Application Control policy blocking `psycopg`'s binary wheel — unrelated to the project itself)
  was used only in scratch scripts outside the repository and is referenced nowhere in any
  tracked file (`git grep pg8000`: no matches in `scripts/`, `src/`, `alembic/`, `tests/`). The
  project's runtime driver remains `psycopg[binary]`, unchanged.

**Rejected.** Treating "27.5%, form (a)" as the final word once a clear, arithmetic path to a
tighter band existed. Reporting the whole-queue-vs-pilot forecast comparison as valid once the
pair-survival check showed it wasn't, rather than retracting it the same way this project retracts
any other invalidated number. Removing cross-species pairs from the queue when only a quota
proposal was asked for.

**Date.** 2026-09-15 (fifth same-day session, follow-up review of addenda #3 and #4).

---

## ADR-0028 addendum #6 — candidate retrieval: eval set grown to n=50, hybrid retrieval, TASK A
closed completely

**Context.** Candidate retrieval recall@20 is the only measured Phase 3 gate currently missed
(57.7%, n=26, vs. the >=90% target). Full detail, every number, all failure-shape examples:
`docs/learned/phase3-retrieval-improvement-2026-09-16.md`.

**BLOCK 1(a) — TASK A closed.** The remaining 25 of the extension's 35 "not found" rows were
rechecked via pentruanimale's VTEX Catalog API (full SKU list, brand-root query). **12 of 25 are
genuine confirmed matches** missed by the original full-descriptive query. **Corrected 40-row
rate: 23/40 = 57.5%, CI [42.2%, 71.5%] — reconciles with Q3's original 54%** (previously 12.5%,
then 27.5% as a floor with a [27.5%, ~65%] band; now closed, every one of the 35 rows checked
against a full SKU list). 4 of the 12 confirmed matches (plus 1 from the prior session's 6) are
real-world confirmed but not usable for the retrieval eval set — the exact matching pentruanimale
SKU was never collected by our own scraper (out of stock at every scrape, or missed by the VTEX
variant expansion) — a confirmed market match and a retrieval-testable pair are different claims.

**BLOCK 1(b) — eval set grown to n=50.** New random draw (seed `20260916`, 300 items, population
excludes all previously-checked titles), verified by brand-root query (never brand+product_line,
per the contamination finding TASK C already established) via the same API. Automated weight+brand
matching alone produces real false positives (checked, not assumed — a coincidental same-
brand/weight match with zero title-token overlap); tightened with flavour-canonical agreement or
token-overlap scoring, and **every surviving candidate still read by eye** before counting —
caught a Pro-Plan-vs-Cat-Chow retail-tier mismatch, a Calibra dog-vs-cat species mismatch, and a
Julius-K9 formula (Hypoallergenic vs. Vital Essentials) mismatch the automated score alone would
have accepted. Of 300 drawn, 226 successfully queried (74 hit an unrecoverable fetch failure this
session, reported not padded past), yielding **11 usable confirmed pairs** after review. Eval set
headline subset: 26 (original) + 13 (this session's TASK A recheck, both sessions) + 11 (new
draw) = **50**. Per-item cost: ≈27 draws per usable pair at this rate; reaching 100 would need
~1,600 more draws, not attempted — reported honestly as impractical this session, per instruction.

**New pre-Block-2 baseline, before any retrieval change: 66.0% (33/50), CI [52.2%, 77.6%]**
(dense, blocked by `brand_blocking_key` — same config as before, just measured on the larger set;
higher than 57.7% because the new pairs skew easier on average, a composition effect, not a
retrieval change).

**BLOCK 2(c) — failure shapes re-grouped from scratch** (the old ADR-0028 grouping is stale: embedding
text, blocking, XS-XL, breed-size and life_stage all changed since). New top shapes on the 17
current misses: EN/RO flavour-word crossing (Salmon/Somon, Lamb/Miel, Turkey/Curcan — 29%),
retailer-specific line-naming divergence (Optiderma vs. Sensitive Skin, no shared vocabulary at
all — 24%), one-sided extra descriptive text (24%), near-identical-text crowding (18%), packaging
variant (6%).

**BLOCK 2(d) — hybrid retrieval, built.** `scripts/measure_recall_hybrid.py`: a Postgres
full-text lexical channel over the SAME text the embedding uses (isolates ranking method, not a
text change), fused via Reciprocal Rank Fusion (k=60). Lexical alone is much weaker than dense
alone (12.0% vs 38.0% unblocked) — cannot bridge EN/RO flavour pairs at all — but fusing still
lifts blocked recall **66.0% -> 72.0% (+6pp)**. Adding the canonical `flavour` field to the
lexical text (targeting the #1 failure shape directly) was tried and measured: no material change
(still 72.0%) — reported as a checked dead end, not silently dropped.

**BLOCK 2(e) — K-sweep, the key diagnostic.** Unblocked recall is nearly flat past K=20 (38% ->
42% by K=100) — most unblocked misses are absent from the ranking entirely. **Blocked recall
climbs to 94% by K=100** — most blocked misses are present, just ranked 21-100. Conclusion:
blocking (candidate generation) already does nearly all the real work; **the open problem is
within-block re-ranking, not a wider net or a stronger embedding model.**

**BLOCK 2(f) — a stronger embedding model: infeasible this session, not a judgement call.**
`import sentence_transformers` fails outright in this session's sandboxed environment —
`ImportError: DLL load failed while importing _argkmin: An Application Control policy has blocked
this file` (a scikit-learn compiled extension, transitive dependency), the same class of Windows
sandbox restriction that blocked `psycopg`'s binary wheel previously. No pure-Python workaround
exists for a transformer forward pass the way `pg8000` substituted for `psycopg`. Every
measurement this session read pre-computed embeddings via `pgvector`'s `<=>` operator in raw SQL —
none were recomputed. (e)'s own finding also argues this would not have been the highest-leverage
fix even if available — ranking, not embedding quality, is the dominant remaining gap.

**Final figure against the gate: 72.0% (36/50), CI [58.3%, 82.5%] — below >=90%, reported as
final, not tuned further, not reframed.** What would close it: a small within-block re-ranker
(cross-encoder or similar) over the top-100 blocked candidates — CLAUDE.md's own Phase 3
architecture already calls for a small, CPU-servable matching model at this exact position, which
could double as this re-ranker rather than needing a separate one.

**Rejected.** Treating the automated weight+brand scorer's output as confirmed without an eye
review pass, once it demonstrably produced real false positives. Continuing the BLOCK 1(b) draw
past a clearly impractical per-item cost to chase n>=100. Attempting (f) by disabling or bypassing
the sandbox restriction rather than reporting it as a real environment limitation.

**Date.** 2026-09-16 (candidate retrieval focus session).

---

## ADR-0028 addendum #7 — canonical fields in the embedding text; eval-set brand-anchoring bias
recorded; K=20-vs-K=100 re-ranking PROPOSED for Bogdan; Phase 1 gate confirmed twice

**STATUS OF THIS ENTRY: mixed.** Items 1, 2 and 4 below are DONE, measured, and committed. **Item
3 is PROPOSED ONLY — not applied, not decided.** It is recorded here, in the same log as every
other decision, specifically so it is visible and awaits Bogdan's approval rather than living only
in a session transcript nobody reads twice.

### Item 1 — the cheapest untried fix: canonical fields, done and measured

Per-field audit of `build_embeddings.py::embedding_text()` (full table in that file's own
docstring and in `docs/learned/phase3-retrieval-improvement-2026-09-16.md`): `brand`,
`product_line`, quantity, `pack_count`, `life_stage` were already canonical values, not raw title
tokens. Two real gaps: `breed_size_code` was the RAW token (so "Medium" and "M" still differed in
the embedding even though last session's `breed_size_class()` already unifies them), and
`flavour` was **absent from the text entirely**, even though `extract_flavour()` already
canonicalises Salmon/Somon, Lamb/Miel, Turkey/Curcan etc. to one EN value on both sides. Both
fixed.

Re-embedded all 10,532 rows despite `sentence-transformers` still being blocked in this sandbox
(confirmed again this session) — worked around it one level lower, via `transformers`'
`AutoModel`/`AutoTokenizer` directly (the documented standard recipe: mean-pooling + L2-normalize,
exactly what `SentenceTransformer.encode()` does internally), stubbing `sklearn` in `sys.modules`
before import since `transformers` also transitively imports it for an unrelated, unused feature.
Runs the real model with its real weights; confined to a scratch script, same discipline as the
`pg8000` workaround — `build_embeddings.py` itself is untouched and still imports
`sentence_transformers` normally for any environment where that works. 134s for the full catalog.

**Recall@20, headline (n=50), before -> after:** dense blocked 66.0% (33/50) -> **74.0% (37/50)**;
RRF-fused blocked 72.0% (36/50) -> **88.0% (44/50), CI [76.2%, 94.4%]**. A +22pp combined
improvement from a text change plus the existing hybrid fusion, no new model.

**Did the EN/RO flavour-crossing shape shrink, as predicted? Checked, not assumed — mostly no,
and that is reported as a finding.** All 4 pairs still readable as EN/RO crossing after the fix
were queried directly: `flavour` extracts correctly and MATCHES on both sides for every one
(salmon=salmon, lamb=lamb, turkey=turkey, chicken=chicken). The shape's raw count barely moved (5
of 17 misses -> 4 of 13). **The mechanism this fix targeted IS fixed at the data level** — these
pairs no longer fail on flavour misalignment, because there no longer is any — but they still miss
because of separate, substantial `product_line` phrasing divergence inside large, crowded brand
families (Brit Premium by Nature, Brit Care) that the embedding still doesn't collapse even with
brand+flavour+weight+breed-size all aligned. One of the five original EN/RO misses (Calibra Cat
Pouch Trout & Salmon) WAS resolved. The fix works; it is not sufficient alone for titles that also
diverge this much elsewhere.

### Item 2 — eval set structural limitation, recorded

Every one of the 50 headline pairs was found by a brand-root query; blocked retrieval blocks on
`brand_blocking_key`. Checked directly: **0 of the 50 pairs' 100 listings have
`brand_is_distributor_code = true` or a null `brand_blocking_key`.** The fallback path inside
blocked retrieval (the one that matters for the distributor-code class ADR-0028 already named —
`"Ipts"`, `"opti"`) has never been exercised by any recall measurement in this project. Every
blocked/fused figure reported (66.0% through 88.0%) is **recall on brand-aligned pairs
specifically**; recall on brand-misaligned pairs is unmeasured. Not a defect introduced this
session — Q3's own original method was brand-anchored too, so all 50 pairs inherit it from the
eval set's very first row. Full detail, including what an unbiased draw would require (a
verification method that ignores brand strings entirely — slower, no anchor to search by, a
separate session's work): `docs/learned/phase3-retrieval-improvement-2026-09-16.md`.

### Item 3 — PROPOSED: widen candidate generation to K=100 and let the matching model re-rank

**Not applied. Recall@20 stands as measured: 88.0% (44/50), CI [76.2%, 94.4%] — MISSED against
CLAUDE.md §7's >=90% target.** That figure is not being reframed by what follows.

**The argument.** The K-sweep (this session and last) is consistent: blocked recall climbs from
74.0% at K=20 to 96.0% at K=100. For the pairs recall@20 currently misses, **the true match is
usually IN the candidate pool already — just ranked 21st to 100th, not absent.** Re-ranking a
wider pool is a different problem than retrieving a wider pool, and CLAUDE.md's own Phase 3 plan
already assigns exactly that job to a component: **the fine-tuned matching model itself**, which
was always going to read a candidate list and decide M/N/S — it does not need to be a NEW
component, only fed 100 candidates instead of 20.

**Option A — accept the K=20 gate as the candidate-generation gate, unchanged.** Recall@20 stays
the measured, missed gate. Whatever the matching model can't see at position 21+ is invisible to
it, permanently, for that pair. Zero additional serving cost. Simple, and already what the repo
currently does.

**Option B — generate K=100 candidates, let the matching model score and re-rank all 100 per
query.** Recovers the ~22pp gap the K-sweep shows is sitting at ranks 21-100. Cost, stated
precisely as a multiplier since the section-7 serving benchmark itself has not been run yet (Phase
3 has not reached fine-tuning):

- **5x more matching-model scorings per query** (100 vs. 20 candidates).
- **Over the current 10,532-row population**, a full one-time candidate-generation sweep (one
  query per row) would need **10,532 × 100 = 1,053,200 scorings at K=100**, vs. **10,532 × 20 =
  210,640 at K=20** — +842,560 scorings, a real number for THIS population, not an estimate; it
  will grow as the catalogue grows (Phase 1's scrapers add rows daily).
- **This is the one-time/batch sweep cost, not the live per-listing cost.** Matching one NEW
  listing against the catalogue (the everyday production case, `docs/learned/` Phase 6's
  eventual `update_price` flow) costs 100 vs. 20 scorings regardless of catalogue size — cheap
  either way. The 5x multiplier matters for whichever process re-scores the WHOLE candidate pool
  at once (rebuilding `blocked_retrieval_candidate` for the annotation queue, or a full nightly
  re-match), not for interactive use.
- **Directly multiplies whatever CLAUDE.md §7's "cost per 1,000 comparisons" serving benchmark
  measures**, once it exists: if the quantized model costs $X (or Yms p95) per 1,000 comparisons
  at K=20, a full-population K=100 sweep costs 5X (or 5Y) for the same population, all else equal.
  **This is exactly the number that benchmark is supposed to produce — the K decision should be
  made WITH that number in hand, not before it, which is the concrete reason this stays PROPOSED
  rather than decided now.**

**Recommendation, not a decision**: Option B, once the serving benchmark exists to price it
properly — the K-sweep's own evidence (74% -> 96% between K=20 and K=100) is strong enough that
paying a bounded, quantifiable re-ranking cost looks likely to close most of the remaining recall
gap. **Awaiting Bogdan's decision.** STATE.md's gate line stays MISSED either way until he
chooses.

### Item 4 — Phase 1 overlap gate: confirmed twice, and a second blocked-library flag

The corrected TASK A rate (23/40 = 57.5%, CI [42.2%, 71.5%]) and ADR-0023's own hand-verified
estimate (p̂=0.52, n=50) are **two independent verification passes — different sessions, different
query methods (Q3's manual brand-then-scan vs. this project's VTEX Catalog API full-SKU checks) —
agreeing.** Applied to the current N=2,334 keyable population: **point estimate 1,342, CI [985,
1,669]** (vs. ADR-0023's own point 1,214, CI [899, 1,522]) — both comfortably clear the 400
threshold and substantially overlap each other. STATE.md's overlap bullet updated to cite both
measurements, not ADR-0023 alone — this is now the best-evidenced gate in the repo.

**Second blocked-library flag, for the record before it's needed**: `sentence-transformers`
joins `psycopg` as a library this sandboxed environment's Application Control policy blocks
outright. Phase 3's fine-tuning step (item 6, LoRA/QLoRA) needs `torch` + `transformers` (both
import cleanly here, confirmed this session) **+ `peft`**, not yet checked, and training itself —
unlike a forward pass for embeddings — cannot be worked around with a `sys.modules` stub the way
this session's re-embedding was, since training needs the real, full dependency chain (optimizers,
schedulers, mixed precision) most of which routes through the same blocked compiled extensions at
some point. **The fine-tuning step is planned for a hosted GPU notebook, not this local
environment, and this is flagged now rather than discovered on the day**, per instruction.

**Rejected.** Treating item 1's partial (not full) shrinkage of the EN/RO shape as if the fix had
failed, when the data-level mechanism demonstrably succeeded for all 4 remaining cases and one of
five previously-failing pairs was resolved. Deciding item 3 unilaterally because the K-sweep
evidence is strong — it is a real architectural/cost trade-off with a number CLAUDE.md's own
process will produce soon, and the instruction was explicit: propose, do not apply.

**Date.** 2026-09-17 (fourth candidate-retrieval session).

## ADR-0028 addendum #8 — retrieval closed: embeddings reproduced from committed code, gate figure
reframed as a measurement-power finding, not "missed"

**Context.** Two problems with addendum #7's 88.0% figure, both closed this session (fifth
candidate-retrieval session, same day): (1) the vectors it was measured on were produced by an
uncommitted scratch script, so `build_embeddings.py` — the reviewed, committed code — did not
demonstrably produce them; (2) addendum #7 reported the figure as "MISSED against the >=90%
target," which is a stronger claim than a 95% CI of [76.2%, 94.4%] (target inside the interval)
actually supports.

**Decision 1 — embeddings are now genuinely reproducible from `build_embeddings.py`.** Checked
one level deeper than the prior session's `transformers`-direct workaround: a generalised
`sys.meta_path` stub (intercepts any `sklearn`/`sklearn.*` import with an empty module, not just
two hand-picked attribute names) lets the REAL `sentence_transformers` package import and run in
this sandboxed environment — not a manual reimplementation of pooling, the genuine library.
Verified on 20 real rows before trusting it: genuine `SentenceTransformer.encode()` vs. the vector
already stored in `norm_listings.embedding` for the same text — cosine similarity 1.000000 on
every row, max abs diff ~1e-7 (pgvector's float32 round-trip, not a real gap). The scratch script's
manual mean-pool + L2-normalize was correct all along. Ported the working stub into
`build_embeddings.py` itself as `_load_sentence_transformer_class()` — tries the normal import
first, installs the stub only on `ImportError`, so behaviour is unchanged on a machine where
`sklearn` imports cleanly (Bogdan's own machine, the deployment VPS). Then actually re-ran it,
`--force`, regenerating all 10,532 embeddings via the now-working committed script (genuine model,
real weights, ~81s) — not merely argued that it would work. Re-measured recall@20 against the
freshly-rebuilt vectors: **44/50 = 88.0%, CI [76.2%, 94.4%] — identical to addendum #7's figure.**
Full detail: `docs/learned/phase3-embedding-equivalence-2026-09-17.md`.

**Decision 2 — the gate figure is reported as a measurement-power finding, not "missed."**
At n=50 and p̂=0.88, the 95% CI is [76.2%, 94.4%], and CLAUDE.md §7's >=90% target sits INSIDE that
interval. 88% and 90% are not statistically distinguishable at this sample size. Addendum #7's
"MISSED against the >=90% target" language overstated what the measurement supports — a point
estimate below target is real, but calling it "missed" implies a distinguishable shortfall the CI
does not show. Corrected framing, now the framing of record: **the point estimate is below target;
the difference is inside the measurement's own noise; closing the question would need roughly
1,000 verified positive pairs** (a ±2pp Wilson half-width at p≈0.9) **which, at this project's own
observed rate of ~27 draws per usable verified pair (`phase3-retrieval-improvement-2026-09-16.md`
BLOCK 1b), is on the order of 27,000 draws — out of reach for this project.** This is not a
reframing to a more favourable number; 88% is still 88%, and item 3's K=20/K=100 decision (below)
stays exactly as unresolved as before. It is a correction to how much certainty a sample of 50 can
support saying about a 2-point gap.

**Decision 3 — the K=20/K=100 serving-benchmark decision (addendum #7 item 3) stays PROPOSED,
explicitly not decidable now.** Nothing about decisions 1-2 changes this: what prices Option B
(widen to K=100, let the matching model re-rank) is CLAUDE.md §7's section-7 serving benchmark,
which has not been built yet (Phase 3 has not reached fine-tuning). Recorded again here so a
future session does not mistake "retrieval is closed for this round" for "the K=20/K=100 question
is closed" — it isn't; it is blocked on a measurement that doesn't exist yet, not on more retrieval
tuning.

**Retrieval work stops here, per instruction.** No further tuning is planned against this figure;
Phase 3 proceeds to freezing the annotation queue and building the assisted-annotation flow on the
retrieval as it now stands.

**Rejected.** Continuing to grow the eval set to try to resolve the 88%-vs-90% question now
(explicitly out of scope this session — the growth rate is documented as impractical, ~27 draws
per usable pair, and instruction was to stop tuning); leaving `build_embeddings.py` unfixed on the
grounds that the scratch script was "close enough" (an argument, not a verification — the fix cost
one conditional import and confirmed nothing had silently drifted); deciding the K=20/K=100
question now on the strength of the K-sweep alone (the same reasoning addendum #7 already rejected
once — the serving benchmark is what actually prices it).

**Date.** 2026-09-17 (fifth candidate-retrieval session).

## ADR-0028 addendum #9 — the annotation queue is rebuilt once more, then FROZEN

**Context.** Retrieval is now closed (addendum #8) — every signal Phase 3 built this week
(canonical embedding fields, species, breed-size rank, XS-XL nulling, age qualifiers,
`in_scope_only()`) now feeds the queue builder, and the queue itself has been rebuilt three times
this week already as those signals landed, each time comparing against a shrinking intersection
with the prior draw. Per instruction: rebuild it once more, on everything now in place, then stop
rebuilding it.

**Decision.** `scripts/build_annotation_queue.py` re-run, unmodified, against the current
database state (fresh embeddings from addendum #8, `in_scope_only()`, species, canonical
breed-size). Output: **997 pairs, 959 distinct `pair_id`s** (some pairs recur across categories
before dedup collapses to distinct ids — matches the previous queue's own 959-distinct-of-997
shape).

**Guard, three figures (limit 40%, none exceeded):**

| feature | share of queue |
|---|---:|
| `capacity_differs` | 29.4% |
| `flavour_differs` (both stated) | 11.4% |
| `brand_differs` | 5.7% |

**M/N/S forecast (rules-engine, `predicted_label_forecast` — persisted inside the JSON artifact
itself, not only console output):** M-plausible 306 (30.7%), N-by-rule 554 (55.6%) — quantity
differs 285 (28.6%), lifestage differs 105 (10.5%), flavour differs 88 (8.8%), species differs 47
(4.7%), breedsize differs 29 (2.9%) — S-likely 137 (13.7%).

**Survival, measured directly, not assumed:**
- **469 of the previous queue's 959 pairs (48.9%) survive into this rebuild** — the source SQL
  queries changed enough (fresh embeddings, `in_scope_only()`, canonical breed-size/species) that
  roughly half the queue is a genuinely different draw, consistent with how much churn the last two
  same-day rebuilds already showed.
- **47 of `phase3-pilot100-ai-reference-pass.json`'s 99 distinct pair_ids (47.5%) survive.** The
  100-pair AI reference pass (addendum #4/finding-8 discussion) is therefore comparable to this
  queue only on that 47-pair intersection, same caveat as the last comparison (n=44 there) —
  smaller than the full 100, directional only.

**This queue file is now FROZEN.** No further rebuild without a stated reason recorded in
STATE.md first — the same discipline already applied to the Phase 2 gate figure (ADR-0027: frozen
before any fix, never re-scored afterward). The annotation run (STATE.md, "Blocked on Bogdan") can
now proceed against this exact file.

**Rejected.** Rebuilding a fourth time to chase a higher old-queue/pilot-100 survival rate (there
is no target number for survival — it is a diagnostic, not a gate); waiting for a fifth signal
before freezing (retrieval and normalization are both closed for this round; the marginal value of
one more signal does not justify another 5 hours of relabelled-queue churn against Bogdan's still
entirely unstarted annotation clock).

**Date.** 2026-09-17 (fifth candidate-retrieval session, queue-freeze step).

## ADR-0028 addendum #10 — STEP 7: product-level TEST/TRAIN_VAL split, assisted annotation flow
(rules-engine suggestions, never an LLM), annotation run still NOT started

**Context.** CLAUDE.md §7 requires product-level train/val/test splits (item 4: "otherwise the
same product appears in train and test and every metric is inflated... the most common way these
projects become worthless") and, separately, an assisted-labelling flow to make Bogdan's ~1,000
manual decisions (the scarcest resource in this project, ~5 hours at 200/hour) closer to ~2 hours
without contaminating the ground truth with an LLM's judgement.

**Decision 1 — the split is a NEW, additive script, not a rebuild.**
`scripts/split_annotation_queue.py` reads the FROZEN `phase3-annotation-queue.json` (addendum #9)
read-only and writes two new files:
- `docs/learned/phase3-annotation-split.json` — per-`occurrence_id`: `split` ("test" |
  "train_val"), `tier`, and — **TRAIN_VAL entries only** — `engine_prediction` ({label, rule}
  from the same `predict_label()` ladder `build_annotation_queue.py` already uses, ported
  verbatim so the two can never disagree). **TEST entries carry no `engine_prediction` key at
  all** — not `null`, absent — the file itself cannot leak one.
- `docs/learned/phase3-test-split-reference-predictions.json` — TEST pairs' predictions, for
  later OFFLINE evaluation only. `tools/annotate.html` has no `fetch()` call to this file anywhere
  in it; named with a `WARNING` field telling a human not to open it while labelling.

**Decision 2 — product-level split via connected components, not a pair-level random split.**
There is no ground-truth "real product id" in this dataset — that absence is the entire reason
matching is hard. The strongest defensible proxy: treat the frozen queue's own pairs as edges over
`content_hash` nodes, take connected components (union-find), and assign each WHOLE component to
one split. A listing is then structurally unable to appear in both splits — verified directly,
not assumed (`0 overlap` between 262 TEST listings and 891 TRAIN_VAL listings, printed by the
script and checked by set intersection).

**Decision 3 — one giant component (281 of 997 pairs, 28.2%) is excluded from TEST eligibility.**
Assigning it whole to a ~300-pair TEST split would make ~94% of the headline test set describe one
product family. Policy, stated as a general rule rather than hand-picked for this one case: a
component may not supply more than 30% of the TEST target (target 300 → cap 90 pairs); anything
larger routes to TRAIN_VAL, where it is one family among ~700 pairs rather than the entire signal.
A seeded shuffle + best-fit walk over the remaining 381 components then assembles **TEST at
exactly 300 pairs, from 36 components**; the rest — **697 pairs, from 346 components (including
the excluded 281-pair giant) — form TRAIN_VAL.** Both splits span every tier (TEST: proxy_key
35.0%, capacity_differs_cross_shop 25.0%, blocked_retrieval 10.3%, plus five smaller hard-negative
tiers 4–7% each — not dominated by any single source).

**Decision 4 — the assisted flow lives in `tools/annotate.html`, gated on `split`, keyed
distinctly from M/N/S.** For a `split === "test"` pair, the tool renders exactly as before —
no suggestion pill, no confirm button — enforced three ways at once, not just one: (a) the merge
step in `init()` sets `item.engine_prediction = null` for any pair whose split isn't
`"train_val"`, regardless of what the split file says; (b) the split file itself never contains a
prediction for a TEST `occurrence_id` to merge in the first place; (c) the render/confirm code
paths both re-check `item.split === "train_val"` explicitly before showing or acting on anything,
so a hypothetical future bug in (a) or (b) alone still cannot surface a prediction on a TEST pair.
For a `split === "train_val"` pair with a prediction, a "Suggested: <label>" pill and a **`C`
(Confirm)** button appear — a key deliberately distinct from `M`/`N`/`S`, so pressing `M`/`N`/`S`
is always recorded as the annotator's own independent judgement (`source: "override"`), even in
the case where it happens to match the suggestion, and only pressing `C` (`source: "confirm"`,
label forced to the suggestion) counts as a confirmation. Recorded per pair: final label, engine
prediction, `source` (`"blind"` for TEST, `"override"`/`"confirm"` for TRAIN_VAL), `corrected`
(`true` only when `source === "override"` AND the chosen label differs from the suggestion),
decision time (`ms`), and `tier` — all already-existing fields (`answer`, `ms`, `tier`) plus four
new ones, no schema break.

**Decision 5 — the end-of-run report** (`assistedFlowReport()`, shown on the done-screen)
computes, over TRAIN_VAL decisions only: counts of confirmed / corrected / "overrode but agreed",
overall correction rate, correction rate **per tier**, and median decision time for confirmed vs.
corrected pairs — exactly what was asked for, nothing extra grafted on. TEST decisions are counted
separately and explicitly excluded from the correction-rate arithmetic (they never had a
suggestion to correct).

**Verification, done without opening a browser (Chrome extension unavailable this session, same
constraint as STEP 5's original build) — same discipline as before, not skipped.**
`node --check` on the extracted `<script>` (syntax clean). Then a DOM-free simulation: a stub
`document`/`localStorage`/`fetch` and four synthetic pairs (one TEST/blind, one TRAIN_VAL
confirmed, one TRAIN_VAL corrected, one TRAIN_VAL "overrode but agreed") driven through the real
`decide()`/`confirmSuggestion()`/`assistedFlowReport()` functions extracted from the file itself
(not reimplemented for the test). Output matched the expected classification and arithmetic
exactly: 1 blind, 1 confirmed, 1 corrected, 1 override-agreed, correction rate 33.3% (1/3), correct
per-tier breakdown, correct medians (3.0s confirmed vs. 8.0s corrected in the synthetic data).

**Also fixed while verifying**: `_quantity_tuple`/`predict_label` in the new split script
initially returned `S` for every pair (rule 0 fired on every row) — `left.get("category")` was
always `None` because `build_annotation_queue.py`'s own `listing_dict()` never persists `category`
per-pair into the frozen queue JSON (a real, pre-existing gap in that file, found while porting
the ladder, not assumed). Fixed by skipping rule 0 in the split script with a comment explaining
why it's safe to skip: every pair in the frozen queue already passed `in_scope_only()` before
being written, so rule 0 cannot fire on this data regardless. Sanity-checked the fix against the
frozen queue's own recorded forecast: TEST (117 M / 146 N / 37 S) + TRAIN_VAL (189 M / 408 N / 100
S) = 306 M / 554 N / 137 S — **exactly** the frozen queue's own `predicted_label_forecast`
(addendum #9), confirming the ported ladder agrees with the original on every one of the 997 pairs.

**Reported, per instruction — split sizes, blind/assisted boundary, enforcement — no annotation
run started:**
- **TEST: 300 pairs, 262 distinct listings, blind — no suggestion shown, ever.**
- **TRAIN_VAL: 697 pairs, 891 distinct listings, assisted — suggestion shown, `C` to confirm,
  `M`/`N`/`S` to override.**
- Enforcement is structural (three independent layers, decision 4 above), not a single "don't
  render this" check that a future edit could quietly break.

**Rejected.** An LLM pre-label for the assisted suggestion (explicitly forbidden by instruction —
would make the fine-tune a distillation of a larger model, not supervised learning on ground
truth, and would make the reported F1 a measure of imitation, not matching skill). A pair-level
random split (the exact CLAUDE.md §7 item 4 failure mode — leaks listing identity across the
train/test boundary). Letting the 281-pair component into TEST uncapped (would make the headline
test metric mostly a measurement of one product family). Treating "pressed M/N/S and it happened
to match the suggestion" as a confirmation (would undercount how often the annotator is actually
exercising independent judgement, the opposite of what the correction-rate report needs to show).

**Date.** 2026-09-17 (fifth candidate-retrieval session, STEP 7).

## ADR-0028 addendum #11 — three defects found and fixed before annotation starts: occurrence_id
collisions, an unstratified TEST split, and no label export

**Context.** A short verification session (same-week, before any labelling began) reviewed
addendum #10's split/assisted-flow build and found two real defects, plus a missing capability
CLAUDE.md §5's "never report a number without the command behind it" discipline extends to: with
no export, every recorded decision would live only in one browser's `localStorage`, unrecoverable
if that browser profile is ever cleared. All three fixed here, denominators corrected to 997 rows
(addendum #10's "959 keys" framing implicitly treated the file as if it had 959 rows; it has 997,
959 is the DISTINCT `pair_id` count, and the two numbers being conflated is exactly what caused
defect 1 below).

**Defect 1 — occurrence_id collisions, verified before fixing.** The frozen queue has 997 rows but
only 959 distinct `occurrence_id` values. `build_annotation_queue.py` hardcodes
`occurrence_id = f"{pair_id}_0"`; 38 `pair_id`s appear TWICE in the frozen file, always as one
`proxy_key_collision` row and one `trivial_spot_check` row (the trivial-tier pass scans
already-selected pairs for byte-identical attributes and can re-select one a category query
already placed elsewhere — a real gap in the frozen queue builder, not touched, since the queue
is frozen). Both rows collide on `occurrence_id`. Two real consequences, not hypothetical: (a) a
split file keyed by `occurrence_id` can only ever have 959 keys, 38 short of the 997 it needs;
(b) `tools/annotate.html`'s `state` dict is ALSO keyed by `occurrence_id`, so the moment the first
occurrence of a collided pair is decided, `findNextUndone()` treats the second as already done and
never shows it — the self-agreement check these 38 double-drawn pairs exist to provide would
silently never have run.

**Fix.** `occurrence_id = f"{pair_id}_{k}"`, `k` = 0-based ordinal of that `pair_id` in FROZEN-FILE
ROW ORDER — computed identically in three independent places, deliberately not shared code across
languages: `scripts/split_annotation_queue.py::derive_occurrence_ids()` (Python),
`tools/annotate.html::deriveOccurrenceIds()` (JS, mutates `queue` items before merging the split
file), and `tests/test_annotation_split.py::_derive_occurrence_ids()` (Python, re-derived from the
rule's own description rather than imported, so a bug shared between the first two would still be
caught). All three verified to agree: 997 distinct derived ids, 0 missing assignments.

**A silent default was also removed, not just the collision.** The first build of
`tools/annotate.html` defaulted a queue item with no split-file assignment to `"test"` — a "safe"
default that is exactly the kind of silent fallback that hid the collision in the first place.
Replaced with a visible, blocking error: if any queue item has no assignment, the tool refuses to
start and names the missing occurrence_ids, rather than guessing.

**A second, related fix — repeat spacing.** Even with unique ids, showing a collided pair's two
occurrences close together in the DISPLAY order would let short-term memory answer the second one,
defeating its purpose as a self-agreement check. `enforceRepeatSpacing(order, queue, 100)` is a
deterministic post-pass on `buildOrder()`'s output: for each of the 38 repeated `pair_id`s, if its
second occurrence is currently shown fewer than 100 positions after its first, it is moved later
(never earlier) to close the gap. Verified by running the REAL `buildOrder()` in Node against the
real frozen queue and its real `shuffle_seed`: **all 38 gaps are >=100 (min 100, median 314, max
849)**, and the resulting order is still a valid permutation of all 997 rows.

**Defect 2 — the first split was filled by raw component size, with no tier balance, and CLAUDE.md
§7 needs per-category results.** Measured before fixing: `capacity_differs_within_shop` landed at
3/300 (1.0%) in TEST vs. 73/697 (10.5%) in TRAIN_VAL — an 9.5pp gap — and
`same_capacity_diff_flavour` at 12/300 (4.0%) vs. 73/697 (10.5%), a 6.5pp gap. A per-category F1
computed on 3 TEST examples for one tier is not a usable number.

**Fix.** Replaced the best-fit-decreasing walk with a seeded local-search optimizer minimising
`sum_t (test_t - target_t)^2` across the 9 active tiers, `target_t = 300 * (rows of tier t in all
997) / 997` — a HARD constraint that `sum(test_t) == 300` exactly, and the existing 90-row
component cap unchanged (the 281-row component still routes to TRAIN_VAL — checked again this
session: it holds 123 of `capacity_differs_cross_shop`'s 209 rows, 58.9% of that whole tier, the
single tightest structural constraint of any tier, since only 86 of its rows are even ELIGIBLE for
TEST once the giant component is excluded, against a target of 62.9). Balances ONLY on `tier` —
`engine_prediction` is never a balancing input, exactly as instructed; it is reported afterward as
a diagnostic (TEST: M 103/N 164/S 33; TRAIN_VAL: M 203/N 390/S 104 — this run's numbers, not fixed
across reruns since the optimizer's exact component choice is one of several equally-optimal sets;
see the reproducibility note below).

**Result — every tier's gap collapsed to <=0.3pp** (from as much as 9.5pp): blocked_retrieval
0.0pp, capacity_differs_cross_shop 0.1pp, capacity_differs_within_shop 0.1pp,
diff_brand_similar_title 0.3pp, proxy_key_collision 0.0pp, same_capacity_diff_breedsize 0.1pp,
same_capacity_diff_flavour 0.2pp, same_capacity_diff_lifestage 0.1pp, trivial_spot_check 0.0pp —
every tier comfortably inside the 4.5pp acceptance limit, every TEST count (14-86) above the
14-row minimum. **5-seed objective range: [0.556, 0.611]** (`SPLIT_SEED` through `SPLIT_SEED+4`) —
tight, confirming the committed seed's result (0.556) is not a lucky outlier; the committed split
always uses `SPLIT_SEED` specifically, never whichever of the 5 scored best (that would be tuning
the split to a result, not measuring one). Acceptance gate — checked and enforced, script exits
non-zero on failure — PASSED on every criterion: all tier gaps <=4.5pp, all TEST counts >=14, 0
`content_hash` overlap, exactly 997 assignment keys, no `engine_prediction` on any TEST entry.

**A reproducibility gap was found and fixed while building this**: the optimizer's hill-climbing
loop called `rng.choice(list(selected))` where `selected` is a Python `set` — `set` iteration order
depends on per-process string-hash randomization, so the exact set of components chosen (though
not the resulting tier-count vector or objective) differed between two runs with the IDENTICAL
seed. Fixed by sorting before choosing (`rng.choice(sorted(selected))`) — verified by running the
script twice in a row and diffing the output file byte-for-byte: identical. This is the same class
of gap STATE.md already flagged once for `build_annotation_queue.py`'s own Python-hash-order
sensitivity; fixed here rather than left as a second instance of a known issue.

**Defect 3 (a missing capability, not a bug) — no way to get labels out of the browser.**
`tools/annotate.html` persisted every decision to `localStorage` only, with no export — a cleared
browser profile would silently destroy hours of labelling with no recovery path.

**Fix.** `E` (Export) downloads `phase3-labels-YYYYMMDD-HHMM.json`: the full `state` object plus
`queue_sha256`/`split_sha256` (computed in-browser via `crypto.subtle.digest`, over the fetched
files' raw text, at load time) and a decision count/timestamp. `I` (Import) reads a file, and
`applyImportPayload()` REFUSES — leaving current `state` untouched — unless both hashes match the
currently-loaded queue and split files exactly. Verified with the same DOM-free Node harness style
as addendum #10 (stub `document`/`localStorage`/`fetch`/`crypto`, the real extracted functions):
export -> clear -> import round-trips `state` byte-for-byte identical; a payload with a deliberately
wrong `queue_sha256` is refused, with `state` left untouched.

**Verification summary, all done without opening a browser (same constraint as addenda #9/#10).**
`node --check` on the extracted `<script>` (syntax clean). A Node harness loading the REAL frozen
queue and REAL split file confirmed: 997 distinct derived occurrence_ids; all 38 repeat groups
correctly `_0`/`_1`; `buildOrder()` + `enforceRepeatSpacing()` both produce valid 997-item
permutations; all 38 repeat gaps >=100 (min 100, median 314, max 849); 0 queue items missing a
split assignment against the current files; export/import round-trip exact; mismatched-hash import
refused. `uv run mypy` (45 files, clean), `uv run ruff check .` / `ruff format --check .` (clean),
`uv run pytest` (all tests green, 12 new in `tests/test_annotation_split.py`).

**The frozen queue file itself was never touched.** SHA-256
`696e983392628b868c4becd92db400735a52498a4994b5b7c8651b160a087011`, verified identical before this
session's first edit and after its last — `scripts/split_annotation_queue.py` now also checks this
hash itself, every run, and refuses to proceed if it ever disagrees.

**Rejected.**
- **Pair-level rebalancing** (relaxing the connected-component constraint to hit tier targets more
  easily) — would reopen exactly the CLAUDE.md §7 item 4 leak the product-level split exists to
  close, to make an optimizer's job marginally easier. Not considered once the component-based
  approach was shown to reach <=0.3pp gaps anyway.
- **Editing the frozen queue** to remove or renumber the 38 collided rows — the queue is frozen by
  its own rule (addendum #9); the fix belongs in how `occurrence_id` is DERIVED downstream, not in
  rewriting data that rule already protects.
- **Balancing the TEST selection on `engine_prediction`** (M/N/S forecast) instead of only `tier` —
  explicitly forbidden by instruction, and would make the TEST set's label distribution partially
  an artifact of the same deterministic rules ladder the fine-tune is later compared against,
  contaminating the comparison it's supposed to be neutral for.
- **Treating a same-size-only swap as sufficient** for the local search — tried first, converged
  to a visibly worse objective on early testing; the general remove-one/add-one-plus-singleton-
  rebalance move was added because pure same-size swaps could get stuck whenever no unselected
  component of exactly the needed size existed.

## ADR-0028 addendum #12 — display order reworked (TEST first, TRAIN_VAL second) and the
evaluation rules written down before any label exists

**Context.** Written 2026-09-18, the day before Bogdan starts labelling, in response to a specific
anchoring risk the prior interleaved order (addendum #10/#11, 2026-09-17) created: mixing blind
TEST pairs with assisted TRAIN_VAL pairs meant that by the time the annotator reached a given TEST
pair, they had plausibly already seen hundreds of TRAIN_VAL suggestions and absorbed the rules
engine's habits — anchoring that leaks straight into the blind labels the headline metric is
computed from.

**TASK 1 — display order: all TEST items first, then all TRAIN_VAL items, sequential only.**
`tools/annotate.html`'s `buildOrder()` now runs the existing per-tier shuffle + fractional-rank
interleave (`interleaveBlock()`, unchanged logic, just factored out) SEPARATELY over the TEST
subset and the TRAIN_VAL subset, then concatenates TEST-block + TRAIN_VAL-block — never
interleaved across the two. The `>=100`-position repeat-spacing post-pass
(`enforceRepeatSpacing()`) now also runs once per block, with `findRepeatGroups()` taking an
`allowedIdxSet` so a group is only ever detected within the block both its occurrences actually
belong to (guaranteed by construction: `split_annotation_queue.py` assigns a whole connected
component to one split, so both occurrences of any of the 38 repeated pair_ids always land in the
same block — verified directly, not assumed: 13 of the 38 repeats sit in TEST, 25 in TRAIN_VAL,
confirmed against `docs/learned/phase3-repeat-first-occurrence.json`'s own `split` field, zero
pairs split across the boundary). Running the spacing pass per block, rather than on the
concatenated 997-row sequence, is what keeps a repeat's spacing adjustment from ever being pushed
across the TEST/TRAIN_VAL boundary — the block's own length is the clamp, not the full queue's.

No way to jump between phases exists or was added — advancing through `order` is the only
navigation, same as before.

**A full-width, non-blocking banner** fires once, exactly when `cursor` first lands on
`order[testBlockSize]` (the first TRAIN_VAL item): "Blind TEST phase complete (N shown / M distinct
pairs). Assisted phase starts — suggestions now visible." Both numbers are computed live from the
loaded files, not hardcoded. **The progress header** now also shows the active phase name and how
many undone items remain IN THAT PHASE specifically (`currentPhaseInfo()`), not just the
whole-queue done/total count that was already there.

**Accepted cost, as instructed — fatigue now concentrates on TRAIN_VAL rather than being spread
evenly across the whole run.** The right trade: TEST is where the reported metric comes from, and
under this order it is labelled first, while attention is freshest.

**A second, smaller accepted cost, found while verifying, not anticipated going in — CORRECTED,
see "Post-report correction" below.** This session's own report described the following as an
accepted cost. It was not: nothing enforced the `>=100` invariant this same paragraph (and
STATE.md) claimed elsewhere, and no test locked it. The original text is kept for the record,
not deleted:

> Confining `enforceRepeatSpacing()` to a 300-row and a 697-row block (instead of the full 997-row
> sequence addendum #11 measured) means a repeat whose first occurrence lands close to its own
> block's end can only be pushed as far as that end, not the full 100 positions. Verified against
> the real files: of the 38 repeated pairs, 4 land short of the 100-position target — TEST: 3 pairs
> at gaps 48, 77, 99 (of 13 TEST repeats; min 48, median 126, max 249); TRAIN_VAL: 1 pair at gap 66
> (of 25 TRAIN_VAL repeats; min 66, median 209, max 543). All four are still clearly separated,
> just under the nominal threshold — a direct, explainable consequence of shrinking the available
> room, not a new defect, and not worth a more invasive placement algorithm for four pairs at these
> margins.

That framing was wrong on the substance, not just the tone: a `>=100` invariant with 4 known
violations is a broken invariant, not an accepted cost, regardless of how small the shortfall.
See "Post-report correction" below for the fix, the corrected numbers, and why the verification
that produced this paragraph missed it.

**Verification (Node, against the real committed files, no browser — same constraint as addenda
#9-#11).** A DOM-free harness (`vm` module, stubbed `document`/`fetch`/`location`/`crypto`) executes
the REAL extracted `<script>` body against the real frozen queue and real split file:
- Positions 0-299 of the resulting order are all `split === "test"`; positions 300-996 are all
  `split === "train_val"` — both checked directly over every position, not sampled.
- Per-block tier composition in display order is **identical** to that block's own full tier
  composition (interleaving reorders, it does not resample) — confirmed for both blocks, all 9
  tiers. The first 100 items of each block track the block's own full-block percentages within
  ~1pp per tier (e.g. TEST first-100 `proxy_key_collision` 29.0% vs. full-TEST-block 28.7%).
- Repeat gaps, both blocks: reported above.
- Determinism: `buildOrder()` run twice against the identical seed produces byte-identical output
  (`JSON.stringify` equal), including `testBlockSize`.

**TASK 2 — evaluation rules, written down before any label exists.** Five rules, enforced two ways:
stated here and mirrored machine-readably into `docs/learned/phase3-annotation-split.json`'s new
`evaluation_rules` block (written by `scripts/split_annotation_queue.py`, re-run this session —
confirmed byte-identical `assignments`, `evaluation_rules` the only new top-level key), and checked
structurally by new tests in `tests/test_annotation_split.py`.

1. **The headline TEST set is 287 DISTINCT pair_ids, not 300 rows.** Every reported metric (P/R/F1,
   per-tier breakdown, baseline vs. fine-tune) is computed over those 287. `split["test_distinct_
   pair_ids"]` already carried this number since addendum #11; `evaluation_rules
   .headline_test_metric_denominator` now says so in words next to it.
2. **For a repeated pair, the evaluation label is the FIRST decision in DISPLAY order** — not file
   order, not occurrence_id order. `docs/learned/phase3-repeat-first-occurrence.json` (new,
   committed, built by `scripts/compute_repeat_first_occurrence.js`) names which of each of the 38
   pairs' two occurrence_ids that is. **Built by executing the real `tools/annotate.html` ordering
   logic, not by re-implementing the Mulberry32/interleave/spacing algorithm a second time** — a
   hand-ported duplicate of a stateful RNG algorithm is exactly the kind of thing that silently
   drifts from the original, which is what produced the occurrence_id collision bug addendum #11
   fixed. The second occurrence is used only for self-agreement, never as a second test point.
3. **A repeated pair is attributed to tier `proxy_key_collision` for per-category reporting.**
   `trivial_spot_check` is NOT reported as its own TEST category: of its 15 TEST rows, 13 are the
   second occurrence of a pair already counted under `proxy_key_collision` — verified directly
   against the lookup file, not assumed — leaving only **2** distinct pair_ids genuinely unique to
   `trivial_spot_check` in TEST (`0d008008050b_3156616197c4`, `5e1296b9a5e1_a479d20bd164`). n=2 is
   noise pretending to be a category; reported as a footnote with its raw count instead. (Check:
   8 headline categories' TEST distinct-pair-id counts sum to 285, plus these 2 standalone
   `trivial_spot_check` pairs = 287 — reconciles exactly with rule 1's denominator.)
4. **Stated limitation for the README: the rules-engine forecast differs between splits.** TEST 103
   M / 164 N / 33 S of 300 rows; TRAIN_VAL 203 M / 390 N / 104 S of 697 rows — both verified
   directly from `phase3-test-split-reference-predictions.json` and the split file's own
   `engine_prediction`s, not re-derived by hand. The split was balanced on `tier` only, deliberately
   never on predicted label (addendum #11, "Rejected" — balancing on `engine_prediction` would
   contaminate the fine-tune-vs-baseline comparison). This forecast gap is a consequence of that
   choice, reported, not corrected.
5. **Per-tier TEST counts run 14-86 pairs.** Any per-tier figure must be reported with its
   denominator and a Wilson 95% CI, never a bare percentage — the same discipline already applied
   to recall@20's 88% [76.2%, 94.4%] (STATE.md).

**New tests, `tests/test_annotation_split.py`:** exactly 287 distinct TEST pair_ids (recomputed from
`assignments`, not read from the summary field); every one of the 38 repeated pairs has both
occurrences in the same split; the repeat-first-occurrence lookup covers exactly 38 pairs, and both
`first_occurrence_id`/`second_occurrence_id` of every entry are real derived occurrence_ids present
in the frozen queue; the frozen-queue SHA-256 constant still matches (already existed, re-asserted
here as part of the same run).

**Rejected.**
- **Interleaving TEST and TRAIN_VAL but hiding suggestions with a per-pair random draw** (e.g. only
  show suggestions on 70% of TRAIN_VAL pairs, still interleaved) — doesn't solve the anchoring
  problem the reordering exists for: the annotator would still see hundreds of suggestions, shown or
  not, before reaching a given TEST pair, whatever the interleave ratio.
- **A blocking "continue" screen at the TEST/TRAIN_VAL boundary**, mirroring the pilot-stop screen —
  rejected as unnecessary friction; the instruction asked for a banner, not a gate, and there is
  nothing to decide at that boundary the way there is at the pilot stop (whether to keep going at
  all).
- **Re-running the full local-search split optimizer** to try to reduce the 4 short repeat gaps —
  the split itself (which components land in TEST vs. TRAIN_VAL) is unrelated to repeat spacing
  (a display-order concern); changing it over 4 pairs' gaps would revisit an already-frozen,
  already-verified assignment for a cosmetic gain of a few tens of positions.

**Post-review fixes (same session, `reviewer` sub-agent on Opus, before commit).** One
BLOCKING finding: `make annotate` / `make.ps1 annotate` used `python -m http.server`'s default
bind (`0.0.0.0`), which would have exposed `.env` (API keys, DB password, the scraper contact
address CLAUDE.md §5 says must never leave that file) to the whole LAN for the duration of any
labelling sitting on shared Wi-Fi. Fixed: both now pass `--bind 127.0.0.1`, verified with a real
request (`netstat` shows the listener on `127.0.0.1` only, not `0.0.0.0`) — see the session report
for the command output. Two real validation gaps in `scripts/ingest_labels.py`, closed: its
docstring claimed every provenance field was cross-checked "not just present, but equal to what
the queue/split actually say," but `engine_prediction` and `corrected` were only presence-checked
— a hand-crafted export could claim `source="confirm"` for a label the rules engine never
suggested, or attach a populated `engine_prediction` to a TEST row (structurally impossible for
the real tool). Both now cross-checked against the canonical queue/split data, with two new tests;
fixing this also caught a real inconsistency in this session's own test fixtures (a "corrected"
flag left `False` on a decision that should have computed `True`), evidence the new check works.
One fabricated number, found and corrected: `docs/phase3-training-environment.md` (written by the
`researcher` sub-agent) stated "697/891" for TRAIN_VAL rows/listings; 891 appears nowhere in the
repo — corrected to the real, verified figure, 802 distinct listings. Two documentation gaps,
closed: the runbook's `ingest_labels.py docs/learned/labels/*.json` command only glob-expands in
Git Bash, not PowerShell (added the `Get-ChildItem ... .FullName` form); and a stale `python -m
http.server` / port 8000 reference survived in `tools/annotate.html`'s own load-failure message
(updated to `make annotate` / port 8010). Two judgement calls, not changed: the ADR heading
wrapping across two lines (matches every prior addendum in this file — addenda #10/#11 do the
same; fixing only #12 would be the inconsistent choice) and `scripts/compute_repeat_first_
occurrence.js`'s driver re-implementing `init()`'s orchestration, not just its algorithm (flagged
in that file's own docstring as a residual risk for a future `init()` change to remember, not
fixed — no test infrastructure change was in scope this session). One item surfaced, not acted on:
an untracked `Claude outputs/pricepilot-blind30.xlsx` predates this session, is not gitignored,
and — checked directly, not assumed — has every label cell empty (`I2:I31` blank in
`sheet2.xml`), so it carries no fabricated data; it is a second labelling surface with none of
`ingest_labels.py`'s provenance discipline, reported to Bogdan rather than modified unprompted.

**Date.** 2026-09-18 (seventh session, pre-annotation verification pass — one day after addendum
#11's session; both are pre-annotation work, no labelling has started).

---

**Post-report correction (2026-09-20, found by the architect, before annotation started).** The
architect re-ran this session's own `buildOrder()`/`enforceRepeatSpacing()` in Node against the
committed files and reproduced the exact numbers this ADR's "accepted cost" paragraph reported —
38 repeats, min gap 48, median 147, 4 violations (TEST gaps 99 at 169→268, 77 at 221→298, 48 at
251→299; TRAIN_VAL gap 66 at 930→996, i.e. block-local 630→696) — and pointed out that a `>=100`
invariant with 4 violations is a defect, not an accepted cost, and that STATE.md's "min 100, median
314, max 849" was stated as current fact when it in fact described the addendum #11 **single-block**
order that this addendum's TEST/TRAIN_VAL split had already replaced.

**Root cause.** `enforceRepeatSpacing()` can only ever push a repeat's SECOND occurrence forward,
clamped to `Math.min(newFirstPos + minGap, seq.length)`. If the FIRST occurrence already sits
within `minGap` positions of the block's own end, no amount of pushing the second occurrence can
reach the full gap — exactly the four cases above, all with a first occurrence past position ~200
in the 300-row TEST block.

**Fix.** A new function, `ensureRepeatFirstOccurrencesFit()` (`tools/annotate.html`), runs before
`enforceRepeatSpacing()` on each block. For any repeat whose first occurrence sits later than the
last position from which a full `minGap` gap still fits (`blockLength - 1 - minGap`), it swaps that
first occurrence with a **same-tier, non-repeated ("singleton") item** at or before that cutoff,
chosen via the seeded Mulberry32 RNG (factored out of `seededShuffle()` into its own `mulberry32()`
so both callers share one PRNG) from *all* eligible candidates, not the first one scanned — so the
result stays deterministic without a positional bias toward the block's start. Restricting the
swap partner to a same-tier singleton is what preserves `interleaveBlock()`'s tier interleaving:
the tier present at every position touched by the swap is unchanged, only which item of that tier
sits there differs, so a prefix's tier proportions are provably unaffected, not just checked and
hoped to hold. The pass throws immediately if a repeat has no eligible singleton to swap with,
rather than silently leaving a short gap — the failure mode this correction exists to close. A
second, independent check (`assertRepeatSpacing()`) runs after `enforceRepeatSpacing()` as a
belt-and-braces guard against a future regression in either function.
`scripts/compute_repeat_first_occurrence.js`'s driver was updated to call the same three functions
in the same order (its own docstring already flagged this orchestration-duplication as a residual
risk in the original addendum #12 session — this is that risk materializing on the very next
`init()` change, exactly as flagged).

**Corrected numbers (real files, Node, no browser — same harness style as every prior addendum in
this ADR).**
- **TEST block (n=300):** 13 repeats, min gap **100**, median 126, max 251, **0 violations**.
- **TRAIN_VAL block (n=697):** 25 repeats, min gap **100**, median 224, max 543, **0 violations**.
- Overall (38 repeats): min 100, median 146.5, max 543 — this replaces both addendum #11's
  "min 100, median 314, max 849" (which described the single-block, pre-addendum-#12 order and no
  longer applies to the current TEST/TRAIN_VAL split) and this addendum's own now-corrected
  "min 48, median 147" paragraph above.
- First 300 positions all `split === "test"`, positions 300-996 all `split === "train_val"` —
  unchanged, still true after the fix.
- `buildOrder()` + the new pre-pass run twice against the identical seed produce byte-identical
  output.
- Tier proportions, first 100 of each block vs. that block's own full composition: unchanged from
  addendum #12's original measurement (within ~1pp per tier, both blocks, all 9 tiers) — expected,
  since the swap is same-tier by construction and therefore cannot move tier mass across the
  prefix boundary.
- `docs/learned/phase3-repeat-first-occurrence.json` regenerated from the corrected order; each of
  the 38 entries now also carries its `gap`, and the file header carries `gap_stats.test` /
  `gap_stats.train_val` (min/median/max/count), matching the numbers above exactly.
- `tests/test_annotation_split.py`: 4 new tests lock the invariant against the regenerated lookup
  file (all 38 gaps `>=100`; `first_position < second_position`; both occurrences of a pair share a
  split; the header's per-split gap_stats match a recomputation from the entries) — pytest 22/22
  passed, `ruff check`/`ruff format --check` clean.

**Why the original verification missed this.** The prompt that produced addendum #12's
verification asked for per-block gap **statistics** (count, min, median, max) — the same shape this
correction's own "Corrected numbers" section above reproduces — but not for a **violation count**
against the stated `>=100` threshold. Min-48/median-126 was reported as a fact about the
distribution; nobody then checked that fact against the invariant the surrounding prose claimed
was still being enforced. The gap between "here is the distribution" and "here is whether the
distribution satisfies the rule" is exactly where the false "accepted cost" framing slipped through
uncaught. `tests/test_annotation_split.py` closes this permanently by asserting the threshold
directly, not just recording the distribution next to it.

**Commits.** One for the fix (`tools/annotate.html`, `scripts/compute_repeat_first_occurrence.js`,
regenerated `docs/learned/phase3-repeat-first-occurrence.json`,
`tests/test_annotation_split.py`); one for this documentation correction (this file and
`STATE.md`).

## ADR-0028 addendum #13 — mechanical rule-consistency pass over the closed 300-row blind TEST
set: a real conventions gap found (food form), a relabel queue built, review mode added, no
relabelling done this session

**Context.** 2026-09-21, after the blind TEST phase closed (300/300 labels, commits
`c25b5e7`/`f961b65`). The architect ran a mechanical rule-consistency pass over
`docs/learned/phase3-labels.json` against the conventions ladder and found `food_form` (dry vs
wet/tin/pouch) was never actually a ladder rule — revision 3's text tells the annotator to ignore
"hrană uscată"/"hrană umedă" entirely, which conflates two different things: the descriptive
*wording* (ignore, correctly) and the *food form itself* (never addressed). Every number below was
reproduced independently before acting, per the session's own instruction, not taken on faith from
the prompt.

**TASK 1 — conventions revision 4: Rule 3b.** New rule inserted between rule 3 (formula qualifier)
and rule 4 (breed size) in `docs/learned/phase3-annotation-conventions.md`: both sides state a food
form, one `dry` and the other `wet`/`tin`/`pouch` → `N`; `wet`/`tin`/`pouch` among themselves are
the same food form at different extractor granularity, never a difference on their own; one side
silent → ignore, decide on the rest — the same one-sided-absence discipline rule 4's dosage bands
and rule 7's quantity already use. Worked example from the real 300 TEST labels: `Hrana umeda
Petkult Adult cu miel 400 g` (wet) vs `Hrana uscata pentru pisici Petkult Cat Adult Indoor Miel
400g` (dry) — same brand/flavour/weight, labelled `M` under revision 3's text, `N` under revision
4. Measured directly: 37 of 300 TEST pairs have `food_form` stated on both sides and differing; 7
are dry-vs-wet (matches the prompt's count exactly), of which 6 were already `N` for an unrelated
reason (usually quantity) and 1 — the Petkult pair above — was not; the remaining 30 are
wet-family-only differences, correctly unaffected by the new rule.

**TASK 2 — the rules engine learns the same rule, at the same ladder position, in both copies.**
Added to `predict_label()` in `scripts/build_annotation_queue.py` and
`scripts/split_annotation_queue.py`, between the life-stage check (rule 3) and the breed-size check
(rule 4) in both. Verified byte-identical behaviour, not just byte-identical source, by running
both functions over all 997 real frozen-queue pairs (constructing a `Listing` from each pair's
dict for the dataclass-based copy) and diffing every `(label, rule)` pair: **0 mismatches across
997 pairs**, before and after the change. Re-ran `scripts/split_annotation_queue.py` (the frozen
queue itself, SHA-256 `696e98...`, was never touched — verified identical before and after) and
diffed the regenerated split file's `assignments` against the previously-committed one:
**split/tier/pair_id unchanged for all 997 keys, 0 changes to any TRAIN_VAL `engine_prediction`**
(same forecast: M 203/N 390/S 104, both before and after). The only change anywhere is in the
TEST reference file (never shown to the annotator, held out for post-hoc evaluation only): the
hidden TEST forecast moved from M:103/N:164/S:33 to **M:102/N:165/S:33** — the one Petkult pair
above flipping from `default_M` to `rule3b_foodform_dry_vs_wet`, plus two already-`N` pairs whose
*attributed* rule changed from `rule5_flavour_differs` to the earlier-firing `rule3b_...` without
changing their label. Acceptance gate re-checked and still passes (997 keys, 0 listing overlap, no
`engine_prediction` on any TEST entry, all tier gaps `<=4.5pp`). `docs/learned/
phase3-repeat-first-occurrence.json` was regenerated (`scripts/compute_repeat_first_occurrence.js`)
purely because the split file's SHA-256 changed (the *content* — order, spacing, gap stats — is
byte-identical: TEST 13 repeats min100/median126/max251, TRAIN_VAL 25 repeats
min100/median224/max543, exactly as addendum #12's post-report correction recorded).
`tests/test_annotation_split.py`'s two hardcoded-forecast assertions updated to 102/165 to match.

**TASK 3 — `scripts/check_label_rule_consistency.py`, a new mechanical-only checker.** Reads the
frozen queue + `phase3-labels.json`, flags a decided pair only when it contradicts one of five
purely mechanical checks (a-d mirror ladder rules 2/1/3b and the `trivial_spot_check` tier
invariant; class (e) is a data-quality check — title vs. stored `species` field — explicitly never
attributed as an annotator error, since the one real instance found is a case where the annotator
read the title correctly and the stored field was wrong). Run against the real 300 TEST labels:
**(a) 3, (b) 4, (c) 1, (d) 0, (e) 1** — every count matches the prompt's stated expectation exactly.
9 total flags across 7 distinct occurrence_ids (one pair, the Petkult one, carries both class (b)
and class (e) — its `species` field disagreement is *why* rule 1 misfired on it, the same
underlying defect surfacing twice). Flags are grouped by occurrence_id (not by flag) in the output
file, `docs/learned/phase3-relabel-queue.json`, so `tools/annotate.html`'s review mode walks each
flagged pair once, carrying every class/rule that fired for it. Exit code non-zero whenever any
class is non-empty (it was, here: exit 1). Nine pytest cases in
`tests/test_check_label_rule_consistency.py`, one synthetic fixture per class plus a negative case
(a label set consistent with every mechanical rule flags nothing) — all against a `tmp_path`
synthetic dataset, `FROZEN_QUEUE_SHA256` monkeypatched, never the real files.

**TASK 4 — review mode in `tools/annotate.html`.** Entered by `?review=<path>`, walks only the
occurrence_ids the named file lists (in the file's own key order), shows the existing label and
the flagging rule(s), and lets the annotator re-decide with `M`/`N`/`S`. Three independent guards
ensure no suggestion is ever shown in review mode, mirroring the existing TEST-blindness pattern:
(1) `engine_prediction` forced `null` on every item, review-mode-wide, the instant review mode
initializes — not just on the items being walked; (2) the render guard (`showSuggestion`) carries
an explicit `&& !REVIEW_MODE` alongside the existing null check; (3) `confirmSuggestion()` refuses
unconditionally, first, when `REVIEW_MODE` is set. A re-decision sets `revised_from` (the answer
immediately before this call — from live `state` if present, else the relabel file's own recorded
label, so a fresh browser/machine with no prior localStorage still gets a correct value),
`revised_at`, and `revision_rule` (every class/rule that flagged the pair, comma-joined); `source`
still follows the existing TEST/TRAIN_VAL rule (`item.split === "test" ? "blind" : "override"`),
unchanged by review mode. `undo()` in review mode never deletes a record — every reviewed item
already had a real label before review mode started, so the ordinary delete-and-step-back undo
would silently erase pre-existing history, which the task explicitly forbids; review-mode undo
just steps the cursor back so re-deciding records another proper revision instead of a gap.
Verified with a DOM-free Node harness (`vm` module, stubbed `document`/`fetch`/`location`/
`crypto`, same technique addenda #10-#12 used) run against the REAL frozen queue, split file, and
the newly-generated `phase3-relabel-queue.json`: order matches the flagged set exactly (7 items);
every item's `engine_prediction` is null; the suggestion pill/confirm button never render across
all 7 items; `confirmSuggestion()` is a verified no-op; a real `decide()` call sets all three
revision fields correctly and preserves the TEST/TRAIN_VAL source rule; `undo()` neither deletes
nor changes the state key count. The ordinary (non-review) flow was re-verified unaffected by the
same technique: `order.length` 997, `testBlockSize` 300, first pair renders without throwing.
`node --check` on the extracted `<script>` body: syntax clean.

`scripts/ingest_labels.py` updated to match: `revised_from`/`revised_at`/`revision_rule` pass
through into `phase3-labels.json` when present (omitted otherwise, same shape as before for a
fresh decision); `merge_exports()` gained a chronological-ordering check
(`_is_legitimate_revision()`) that treats an answer change as an audited revision — not a
conflict — exactly when the later decision's `revised_from` names the earlier decision's own
answer, regardless of which export file was passed first on the command line; every other
disagreement still refuses exactly as before (a new test, `test_unrelated_answer_mismatch_still_
refused_as_conflict`, locks this). The QA report gained a "Review-mode revisions" section: total
count, broken down by `revision_rule`, plus an old→new detail line per revision. Three new tests
cover: a revision merging cleanly across two exports with no `--resolve=latest` needed; a TEST
pair's revision keeping `source: "blind"`; and the unrelated-conflict negative case above.
12/12 `test_ingest_labels.py` tests pass (9 pre-existing + 3 new).

**TASK 5 — species field vs. title mismatch, measured over the full population, not fixed.**
`psycopg` is reachable in this environment (checked directly — Application Control did not block
it this session), so `scripts/measure_species_field_mismatch.py` measured the real
`norm_listings` table, not the frozen queue's 1,994-row fallback the task anticipated for a
blocked environment. **53 of 10,532 rows (0.50%): 46 `animax_ro`, 7 `petmax_ro`, 0
`pentruanimale_ro`** — the zero is structural (that source has no structured species signal at
all, so its stored field IS the title-keyword test and can never disagree with it), every real
mismatch is a case where a structured per-source signal (`animax_ro`'s `product_type`,
`petmax_ro`'s URL segment) disagreed with the title's own wording. One of the 53 is the same
occurrence_id class (e) flagged in the 300-row TEST set, a cross-check that the queue-level and
population-level measurements agree. Not fixed this session (Phase 2 is closed; this is a finding,
not a reopening) — full detail in `docs/learned/phase3-species-field-mismatch-20260921.md`,
recorded as an open issue in `STATE.md`.

**The relabel policy, decided before any model number exists.** Only mechanical, ladder-derived
contradictions enter `phase3-relabel-queue.json` — never a "looks wrong" judgement call, and never
a class (e) data-quality hit treated as a reason to doubt the annotator. Nothing in
`phase3-relabel-queue.json` is auto-applied; every entry is a candidate for the annotator to
re-decide through review mode, and until that happens the 300 TEST labels on disk are unchanged —
**no relabelling was done this session**, per explicit instruction.

**Verification run this session, in order:** frozen queue SHA-256 printed and matched at start and
end (`696e983392628b868c4becd92db400735a52498a4994b5b7c8651b160a087011`, unchanged); every count in
the prompt reproduced independently before acting; `predict_label()` parity checked directly (0/997
mismatches, and now permanently locked by `tests/test_predict_label_parity.py`, added after the
`reviewer` pass below found the original ad-hoc check wasn't committed anywhere); split-file
assignment diff (0 changes outside the stated forecast fields).

**The `reviewer` sub-agent was run on the full diff before committing and found 9 real issues**,
most severe first (verbatim in the PR/commit history if this repo ever grows one; summarized here
since none exists yet):

1. **Blocking — `ingest_labels.py`'s `corrected` cross-check would refuse a legitimate TRAIN_VAL
   review revision** whenever the CANONICAL split-file prediction disagreed with the revised
   answer, because it recomputed `expected_corrected` from `canon.engine_prediction_label`
   instead of trusting that a review-mode decision (`engine_prediction` always null, GUARD 1)
   never claims a suggestion to be corrected against. The existing test happened to revise TO the
   canonical answer, which cannot trigger the bug. **Fixed**: `expected_corrected = False`
   whenever `"revised_at" in decision`. New regression test,
   `test_review_revision_where_revised_answer_disagrees_with_canonical_prediction`, revises to an
   answer the canonical prediction does NOT match.
2. **`tools/annotate.html`'s `initReviewMode()` never checked the relabel file's own
   `queue_sha256`/`split_sha256`** against the page's loaded files, unlike every other file
   boundary in this page (`applyImportPayload()`, `init()`'s missing-assignment check). **Fixed**:
   a visible ERROR card on mismatch, same idiom; an unknown occurrence_id now also surfaces in the
   visible resume-note, not just `console.warn`. Verified with the DOM-free harness (mismatched
   hash -> visible ERROR card, `order` stays empty).
3. **`_is_legitimate_revision()`'s strict `newer.revised_from == older.answer` equality breaks the
   tool's own two-revision workflow** (`undo()` explicitly supports re-deciding a second time): a
   chain M -> N -> S merged from an original-M export and a final-S export (whose `revised_from`
   is "N", the never-separately-exported intermediate) would be refused as a conflict. **Fixed**:
   trust ANY non-null `revised_from` on the chronologically later decision, full stop -- it can
   only ever have been set by review mode. New regression test,
   `test_chained_review_revision_merges_without_an_intermediate_export`.
4. **Review-mode revisions were polluting the assisted-flow (TRAIN_VAL correction-rate) metrics**
   in both `tools/annotate.html`'s `assistedFlowReport()` and `ingest_labels.py`'s QA report --
   every revision carries `source:"override"`/`corrected:false` (no suggestion was ever shown), so
   it landed in "overrode but agreed w/ suggestion" and inflated the denominator. **Fixed**: both
   now exclude `revised_at`-bearing decisions from that section (counted instead in the "Review-mode
   revisions" section already added for TASK 4).
5. **`currentPhaseInfo()`'s review branch always reported 0 remaining**, counting "has no `state`
   entry at all" (every review item already has one, by construction -- the exact trap
   `reviewFirstUnrevisedIndex()`'s own comment names and avoids). **Fixed**: same
   `!s || !s.revised_at` definition as `reviewFirstUnrevisedIndex()`. Verified with the harness.
6. **The conventions-doc/DECISIONS.md food-form breakdown (37/7/6/30) had no script behind it**
   (CLAUDE.md §0.4/§9), unlike the species (53/10,532) and throughput (3.2s/10.8s) figures next to
   it. **Fixed**: added `food_form_diagnostic()` to `check_label_rule_consistency.py`'s own output
   and the relabel-queue JSON -- reproduces 37/7/6/30/1 exactly, matching what was already written.
7. This "Verification run" paragraph itself originally claimed the reviewer pass had already
   happened and been recorded "in the corresponding commit(s)" before either was true -- the same
   §9 defect class as an unverified claim of working code. Rewritten after the fact, which is what
   this paragraph now is.
8. **No test locked the two `predict_label()` copies' parity** -- only an ad-hoc session check,
   not committed anywhere, despite `split_annotation_queue.py`'s own docstring claiming "so the two
   can never disagree". **Fixed**: `tests/test_predict_label_parity.py`, added above.
9. **Class (e) (data-quality, never an annotator error) still appeared in the human relabel
   queue with the same "flagged by rule" wording as an actionable class**, inviting a "fix" the
   script's own docstring says is unwarranted. **Fixed**: `check_label_rule_consistency.py` now
   marks an occurrence `data_quality_only: true` when EVERY class flagging it is (e), and
   `renderReviewBanner()` uses softer wording for that case (moot for today's 7 flags -- the one
   class-(e) hit also carries class (b) -- but real for any future class-(e)-only hit).

All nine addressed before committing. Re-verified after fixes: `pytest` full suite (483 passed,
0 failed — `test_check_label_rule_consistency.py` 9/9, `test_ingest_labels.py` 14/14 (2 new
regression tests for findings 1/3), `test_predict_label_parity.py` 1/1 new, `test_annotation_split.py`
updated and passing); `ruff check .` / `ruff format --check .` clean; `uv run mypy` clean (48
files); `node --check` on the extracted script; the DOM-free Node harness re-run against the real
files for both review mode (now 16 assertions, including the two new ones for findings 2 and 5)
and the ordinary (non-review) flow — all pass.

**Commits.** One per task (conventions revision 4; the rules-engine/split re-run, including the new
`test_predict_label_parity.py`; the consistency checker + tests + food-form diagnostic; the
review-mode tool changes + `ingest_labels.py` + tests), each folding in the reviewer-found fixes
that landed in that task's own files (all fixes above are inside files TASK 2-4 already touched,
so there is no file left over for a separate "fixes" commit), plus this entry and the `STATE.md`
"Current state" update.


## ADR-0028 addendum #14 — split-file hash was the wrong ingest invariant; header stale on last review decision

*2026-09-21.* Two defects in code written earlier the same day, found while the annotator was mid-run
(300 TEST labels exported, 7 review-mode revisions applied, TRAIN_VAL not started).

**Defect 1 — `scripts/ingest_labels.py` refused any export recorded against a different split FILE.**
The regenerated split for conventions revision 4 changed the file's bytes (`a9a4c758...` vs
`83c6b0e3...`), so both earlier exports were refused even though no pair had moved. The invariant
that actually protects the dataset is: the frozen queue is unchanged (byte equality, unchanged and
still strict) AND every occurrence_id keeps the same `split` and `tier`. A file hash is only a
proxy for that, and it cost a real workflow.
**Replaced by:** if the export's `split_sha256` differs from the current file's, find the historical
split file with that hash via `git log --all -- <split path>` + `git show`, and compare `assignments`
on `split` and `tier` per occurrence_id. Identical -> ingest, printing both hashes, the count of
`engine_prediction` differences by old->new label, and any other top-level key that differs. Any
moved occurrence_id, or a historical file that cannot be found -> refuse, naming the moved ids.
Both hashes (`split_sha256_recorded`, `split_sha256_current`) are recorded per source file in
`phase3-labels.json`. There is no skip flag. **Rejected:** a `--force`/`--ignore-split-hash` flag
(would re-open exactly the hole the check exists for); trusting the recorded hash's mere presence.
**Finding worth recording:** the brief described the regeneration as changing only
`engine_prediction` values. Measured, all 997 assignments are identical on every field (0
engine_prediction differences, 0 split/tier moves); the only differing key is the top-level
`evaluation_rules` text. The check accepts it either way; the note now reports both.

**Defect 2 — review header `6/7 done ... 1 left` under a `7/7 re-decided` completion screen.**
Suspected cause (a same-label re-decision not counted) was **wrong**: `decide()` stamps `revised_at`
on every review decision regardless of label, and a same-label re-decision mid-sequence counted
correctly. Actual cause: `renderPair()`'s completion branch (`cursor >= order.length`) returned
through `showDone()` before the only `updateTopbar()` call, so deciding the LAST pair never
refreshed the header (the ordinary flow had the same off-by-one at 996/997). Fixed by calling
`updateTopbar()` in that branch. Regression: `tests/js/annotate_review_topbar.test.mjs` drives the
real page script in a vm with a fake DOM; a same-label re-decision is placed both mid-sequence and
last; fails 2/2 without the fix, passes with it.

**Not changed, flagged:** `tools/annotate.html`'s review mode and its own import path still compare
`split_sha256` by file hash (they cannot run `git`); they refuse, loudly, on a regenerated split.

**Reviewer findings folded in (all fixed before commit):** history lookup now tolerates CRLF
worktree bytes vs LF blobs and skips commits where `git show` fails (path deleted) instead of
aborting; malformed/old-schema historical splits refuse cleanly instead of a traceback; a real
throwaway-git-repo test covers the lookup (previously only mocked); the note warns that a
TRAIN_VAL export can still be refused later by the confirm/corrected cross-check; the Node test is
wired into `make test` / `make.ps1 test`. Known limit: a shallow clone (CI default) has no history,
so a hash difference refuses there -- fail-closed, by design.


## ADR-0028 addendum #15 — annotation complete (997/997); final consistency pass; freeze mechanism (2026-09-21)

**Context.** CLAUDE.md §7 item 3 is met: 997 labels, M 359 / N 628 / S 10; blind TEST 300 rows (287
distinct pairs), assisted TRAIN_VAL 697. Self-agreement TEST 13/13 = 100%, TRAIN_VAL 22/25 = 88% (pre-reconciliation, measured at ingest).
Median decision time 3.0s blind / 1.5s assisted / 1.8s overall (recomputed from the labels file;
3.2s was the pre-review blind figure), against §7's untested 18s. `C` was pressed 0 times.

**Assisted-phase caveat.** TRAIN_VAL was decided faster (1.5s vs 3.0s) and less self-consistently
(88% vs 100%) than TEST, so TRAIN_VAL labels are more engine-shaped than TEST ones. This is why the
headline number is computed on the blind TEST set alone. Correction rate of the suggestion in
TRAIN_VAL, 104/697 = 14.9%, per tier: blocked_retrieval_candidate 28/86 (32.6%),
capacity_differs_cross_shop 2/146 (1.4%), capacity_differs_within_shop 0/53 (0.0%),
**diff_brand_similar_title 38/39 (97.4%)**, proxy_key_collision 25/200 (12.5%),
same_capacity_diff_breedsize 4/33 (12.1%), same_capacity_diff_flavour 0/59 (0.0%),
same_capacity_diff_lifestage 1/46 (2.2%), trivial_spot_check 6/35 (17.1%). On
diff_brand_similar_title the annotator overrode the engine almost everywhere.

**Final mechanical pass over all 997** (`scripts/check_label_rule_consistency.py`): (a) 2, (b) 0,
(c) 0, (d) 4, (e) 3, new (f) 6 = 15 flags / 12 occurrences -> `phase3-relabel-queue.json`.
- (a): Royal Canin Maxi Adult 4 kg vs 3 kg and Bulldog Adult 12 kg vs 3 kg, both labelled M (rule 2
  says N; both decided in ~1s) — likely slips, annotator to re-decide.
- (d): 3 N + 1 S. classify_tier() is NOT defective in its labelling logic but its "trivial" is
  weaker than "byte-identical": it compares brand, line, capacity, pack, bonus only, so
  life_stage/food_form differ (None vs value) on all four; no field conflicts. Three of the four
  are also the three (f) pairs, whose other occurrence was M. The 4th (33394df3427d_3ab75d311be0)
  is a single N on fields with no conflict. All four go back to the annotator; the tier description
  ("byte-identical") in earlier notes was overstated.
- (f): a self-agreement disagreement is reported with `self_agreement: true`,
  `data_quality_only: false`; the annotator must pick one label per pair.
- (e) entries now carry `revert_hint: true`: a stored-data defect never justifies changing a label.

**Schesir correction.** `3f574dad8b6e_b52acad20816_0` was revised M -> N under
rule1_species_differs. Wrong: rule 1 reads the TITLE, not the `species` field; both titles state
"pisici"; the left `species='dog'` is the known normalize/species.py defect. It is re-queued (not
hand-edited) with the reason recorded in the checker (`ARCHITECT_NOTES`) and shown as a prominent
block in the tool's review screen, because the rule id was visible last time and the note was not.
Observation for the annotator, not a finding: the left title says "grau", the right "fără cereale".

**Freeze mechanism.** `scripts/freeze_labels.py --freeze` records the SHA-256 of
`phase3-labels.json` in `tests/test_labels_frozen.py` and STATE.md; it refuses unless 997
decisions and no class a/b/c/d/f finding remain. The test skips loudly while `UNFROZEN`, fails on
any change afterwards. **After the freeze no label may change without a stated reason recorded in
STATE.md first.** Not frozen yet: the annotator's review pass comes first.

**Alternatives rejected.** Editing labels by script (violates "labelled, not generated"); fixing
the checker to hide the (d) pairs (they are real inconsistencies); auto-freezing at ingest.

**Reviewer findings folded in.** (1) The Schesir note is shown on a blind TEST occurrence, so that
one row's re-decision is NOT blind; stated as an exception in README rather than dropping the
instructed note. (2) Freeze hash normalises CRLF->LF (CI is Linux). (3) `--freeze` now checks the
frozen-queue hash. (4) An occurrence whose label the annotator deliberately keeps can be listed with
a reason in `docs/learned/phase3-freeze-acknowledgements.json`; the checker never overrides the
annotator. (5) The 22/25 self-agreement is labelled pre-reconciliation; the (f) note reveals the
other label, so no fresh self-agreement is computable after review. Known, not changed:
`FROZEN_QUEUE_SHA256` is CRLF-dependent in the checker (not run in CI); `make status` does not yet
show freeze state.

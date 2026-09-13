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

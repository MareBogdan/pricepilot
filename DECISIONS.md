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

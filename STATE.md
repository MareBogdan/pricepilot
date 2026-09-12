# STATE

Phase: 1 — Collection (petmax.ro + pentruanimale.ro on a daily GitHub Actions cron)
Updated: 2026-09-12

## Gate progress

Phase 0 — Foundation: **CLOSED**, verified end to end in Docker on 2026-09-12.

[x] `docker compose up -d` brings up Postgres 16 + pgvector, api, mock-store — all three healthy
[x] `make migrate` applied migration 0001; `\dt` shows products, scrape_runs, raw_listings, llm_calls
[x] pgvector extension live in the container: `vector 0.8.6`, `<=>` operator answers
[x] `/health` responds `{"status":"ok","database":true}` from inside the compose network
[x] mock-store serves 30 products / 180 days and accepted a live `PATCH /products/1/price`
[x] `make test` passes — 86 passed
[x] `make lint` passes — ruff check + format clean, mypy strict clean on 20 source files
[x] zero dollars spent

Phase 1 — Collection: in progress. Gate per CLAUDE.md §7 as amended 2026-09-12.

[x] `docs/SOURCES.md` filled in for petmax.ro and pentruanimale.ro from real fetches
[x] fixtures saved for both sources, offline tests passing
[x] both adapters implemented behind the `Scraper` protocol, tested offline
[x] every run logs to `scrape_runs`; volume-alert logic verified (petmax)
[x] ingest is idempotent on (source, external_id, collected_date) — **re-verified today**: petmax
    ran twice (17:16 and 18:25 UTC), 4,060 rows both times, zero duplicate
    (source, external_id, collected_date) groups across the whole table (query shown, ADR-0016)
[x] collection running on a GitHub Actions cron for both sources — `.github/workflows/scrape-petmax.yml`
[x] ≥3,000 in-scope listings — **7,611 total** (4,060 petmax_ro + 3,551 pentruanimale_ro), verified
    from `scrape_runs` and `raw_listings` on a separate connection
[ ] ≥3,000 in-scope listings from **≥3 sources** — 2 sources only; volume is not the blocker, source
    count is
[ ] ≥7 consecutive days of history — **1 / 7** (2026-09-12 only so far)
[ ] **≥400 products on two or more shops — MEASURED, NOT MET: 13.** Hand-verified: all 13 are
    genuine same-purchasable-unit matches (~100% precision on the claimed matches, one packaging-
    format caveat). The gap to 400 is not a false-positive problem. A diagnostic (not applied)
    found the true overlap is materially higher — a weight-token-spacing bug in the proxy key
    hides real matches, ~92 by one narrow fix — but that same fix reintroduces the bonus-weight
    trap CLAUDE.md §7 names (merges plain packs with "+X kg gratuit"/"gratis" packs). Full detail
    in `docs/SOURCES.md`'s "Confirmed cross-shop overlap" section. **A third adapter alone will
    not close this gap — the proxy key needs fixing first.**
[ ] adapter for animax.ro — not started (deliberately out of this session's scope)
[ ] all adapters tested offline against fixtures — petmax + pentruanimale done, animax to go

## Last done

- **Built and shipped the pentruanimale.ro adapter** (VTEX storefront — a different platform from
  petmax's Gomag). Prices and every grouped-variant SKU come from a server-rendered `__STATE__`
  Apollo-cache JSON blob on the category page itself; no product-page fetch needed for variant
  expansion, unlike the original guess in `docs/SOURCES.md`. 19 offline tests against a real,
  trimmed fixture (multi-variant expansion, single-variant passthrough, a real bonus-weight trap).
- **Found and fixed a real bug in `PoliteClient`**: `robots.txt` was being fetched via
  `RobotFileParser.read()`'s bare `urllib.request.urlopen()`, which sends Python's generic default
  User-Agent, not the honest one configured everywhere else. pentruanimale.ro 403s that anonymous
  UA specifically, which `RobotFileParser` reads as "disallow everything" — a false block; our
  real, identified client got 200 on every request, robots.txt included, throughout. This silently
  affected petmax.ro too; it just never surfaced there. Fixed and regression-tested offline via
  `httpx.MockTransport` (ADR-0020).
- **Added pentruanimale.ro to the daily GitHub Actions workflow** as its own job (own concurrency
  group, same cron/dispatch/secrets), then ran the real thing: 3,551 listings ingested, 224 pages,
  1227s, verified from `scrape_runs` on a fresh connection.
- **Re-verified idempotency operationally, not just in a test**: petmax ran twice today (a manual
  dispatch last session, another this session) — 4,060 rows both times, zero duplicates anywhere
  in the table, confirmed by a direct query.
- **Measured cross-shop overlap for the first time**, with two real sources: 13 shared products,
  hand-verified for precision, plus a diagnostic (not implemented) showing the true number is
  likely much higher, blocked on a specific, named bug in the proxy key rather than genuinely thin
  overlap. See `docs/SOURCES.md`.

## Open issues

- **Overlap proxy key needs work before it's trustworthy at scale.** Two known, specific problems,
  both documented in `docs/SOURCES.md`: (1) `line_tokens()` doesn't strip a `\d+(kg|g)` token when
  a shop omits the space before the unit, silently splitting identical products across a spacing
  difference; (2) any fix to (1) has to simultaneously guard the bonus-weight trap (`"+ X kg
  gratuit/gratis"`), or it merges genuinely different purchasable units. Neither is fixed yet —
  flagged, not tuned, per this session's explicit instruction.
- **13 is a real number, and it changes what the third adapter is for.** Adding animax.ro will grow
  volume and source count, but will not by itself close a 400-target gap of this size while the
  proxy key still under-counts real overlap by roughly 7×. Fix the key before or alongside the next
  adapter, not after.
- **7 consecutive days is 1 so far**, and the scheduled (non-manual) cron has not fired yet as of
  this session — every run to date has been `workflow_dispatch`. Watch for the first real
  `schedule`-triggered run and whether `make status` shows a gap.
- **`scrape_runs` does not persist error message text**, only a count. Confirmed on the
  pentruanimale.ro run (3 errors, cause unknown — could be HTTP-level or parse-level, no way to
  tell after the fact). Same class of gap as `skipped_out_of_scope` not being persisted for petmax.
  Worth fixing before relying on this run's history for diagnosis.
- **pentruanimale.ro fetched 224 pages vs. ~321 estimated at recon** for full coverage of its 6
  categories — a real, unexplained gap (recon was accurate for petmax; this is the first sign it
  might not transfer directly to a second source). Not investigated further this session.
- **LLM transport not implemented.** `src/pricepilot/llm/client.py` ships the budget cap, cache
  key and call log; `complete()` raises. ADR-0006.
- **`make` not installed.** `.\make.ps1 <target>` is the Windows path. ADR-0003.
- **Bonus-weight titles are a known trap**, now empirically confirmed to actually occur in real
  scraped data on both shops (not just theorized) — see the overlap diagnostic above and
  `tests/fixtures/pentruanimale_ro/README.md`. Needs to reach the Phase 3 annotation set.

## Blocked on Bogdan

Nothing that blocks progress. One real decision for Bogdan when he's ready: the overlap proxy key
needs a fix (weight-token spacing + bonus-weight guard) before a third adapter can be expected to
close the 400 gate — worth deciding whether that fix happens before or alongside animax.ro.

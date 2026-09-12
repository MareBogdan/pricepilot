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
[x] every run logs to `scrape_runs`; volume-alert logic verified; error text now persisted
    (`error_detail`, ADR from this session) after hitting the "count only, no detail" gap twice
[x] ingest is idempotent on (source, external_id, collected_date) — **re-verified twice**: petmax
    ran twice today, pentruanimale ran twice today, zero duplicate
    (source, external_id, collected_date) groups anywhere in the table (query shown, ADR-0016)
[x] collection running on a GitHub Actions cron for both sources — `.github/workflows/scrape-petmax.yml`
[x] ≥3,000 in-scope listings — **8,076 total** (4,064 petmax_ro + 4,012 pentruanimale_ro), verified
    from `scrape_runs` and `raw_listings` on a separate connection
[ ] ≥3,000 in-scope listings from **≥3 sources** — 2 sources only; volume is not the blocker, source
    count is
[ ] ≥7 consecutive days of history — **1 / 7** (2026-09-12 only so far; the scheduled, non-manual
    cron has not fired yet — every run to date has been `workflow_dispatch`)
[ ] **≥400 products on two or more shops — MEASURED, NOT MET: 94** (re-measured after fixing the
    proxy key — see below). Hand-checked a random 25 of the 94: 22/25 (88%) clean, 3/25 (12%)
    contain a false pairing mixed with a genuine one (life-stage/senior variant, packaging format)
    — within CLAUDE.md §7's accepted floor-estimate error and above the 90% stop-and-report bar
    this session set, so not tuned further. **83 of the 94 (88%) are Royal Canin** — the gap to
    400 is now partly structural (concentrated in one brand, food/treats categories only), not
    purely a key-recall problem. Arithmetic projection in `docs/SOURCES.md`: a well-chosen third
    source plausibly lands overlap around ~150–250, not 400, because of heavy re-use of the same
    Royal Canin SKUs across every source pair. **A third adapter helps but is not alone plausibly
    sufficient on this arithmetic** — worth deciding alongside broader category scope or a further
    key look, not assumed to close the gap by itself.
[ ] adapter for animax.ro — not started (deliberately out of this session's scope)
[ ] all adapters tested offline against fixtures — petmax + pentruanimale done, animax to go

## Last done (this session, in order)

1. **Built and shipped the pentruanimale.ro adapter** (VTEX — different platform from petmax's
   Gomag). Prices and every grouped-variant SKU come from a server-rendered `__STATE__` Apollo
   cache on the category page; no product-page fetch needed for variant expansion. 24 offline
   tests against a real, trimmed fixture.
2. **Fixed a `PoliteClient` bug**: `robots.txt` was fetched via `RobotFileParser.read()`'s bare
   `urllib.request.urlopen()`, sending Python's generic default User-Agent instead of the honest
   configured one. pentruanimale.ro 403s that anonymous UA specifically, read by `RobotFileParser`
   as "disallow everything" — a false block; our real, identified client got 200 everywhere,
   robots.txt included. Silently affected petmax.ro too. Fixed, regression-tested offline via
   `httpx.MockTransport` (ADR-0020).
3. **Corrected a wrong date** (STATE.md/DECISIONS.md/docs said 2026-09-13; verified against the
   system clock — it was still 2026-09-12).
4. **`scrape_runs.error_detail`** — persists actual error strings now, not just a count. Hit this
   gap twice (petmax's `skipped_out_of_scope` reasons, pentruanimale's first-run errors) before
   fixing it.
5. **Found and fixed the real pagination bug**: a transient `__STATE__` parse failure was treated
   identically to "category exhausted", silently truncating every page behind it. Fixed with
   `_should_continue_category` (a consecutive-parse-error cap, not an infinite retry).
6. **Found a second, separate cause, and it's a platform limit, not a bug**: this store's search
   pagination stops returning results past page 50 (600 products) per category regardless of the
   claimed total — confirmed by diffing `?page=50` vs `?page=51`'s raw `__STATE__`. Corrected
   `docs/SOURCES.md`'s recon estimate accordingly (321→257 realistic pages).
7. **Classified why petmax's keyable rate (61%→71.7% after the fixes below) lags pentruanimale's**:
   sampled 40 + queried the full 4,060 by category. 98%+ of unkeyable petmax listings concentrate
   in the non-food categories (accessories, hygiene, litter) added purely for listing volume —
   genuinely no weight in the title, not a parsing failure. Nothing fixed here; nothing needed
   fixing.
8. **Fixed the overlap key itself** (ADR-0021): weight-token spacing bug (the single biggest
   recall problem — "85g" vs "85 g" keyed differently), ml/l support, curly-apostrophe folding,
   and a bonus-weight guard (`OverlapKey.bonus_g`) so a plain pack and its bonus-weight promo never
   collide while two shops' bonus forms of the same product still do. Normalisation only — no
   model, no fuzzy matching.
9. **Re-measured overlap for real**: 13 → **94** shared products. Hand-checked a random 25 (not
   all 94): 88% clean, 12% with a caveat, consistent with the plan's accepted error margin.
   Bonus-weight guard verified working on real cross-shop data (kept a bonus pack from merging
   into a larger plain/senior-variant bucket, while still matching the two shops' bonus listings
   of the same product to each other).

## Open issues

- **The 400 gate now looks partly structural, not just thin data.** 88% of current overlap is one
  brand (Royal Canin). Whether a third adapter closes the gap depends heavily on whether it also
  carries that brand's range near-completely — worth confirming before assuming animax.ro alone
  solves this. See the arithmetic in `docs/SOURCES.md`.
- **7 consecutive days is 1 so far**, and no scheduled (non-manual) cron run has fired yet.
- **pentruanimale.ro's ~600-product-per-category ceiling is permanent** with the current
  `?page=N` retrieval path. Reaching the remainder would need a different mechanism (e.g. the
  `sitemap/product-N.xml` files) — not attempted, flagged for whoever next touches this adapter.
- **3/25 hand-checked overlap keys contain a false pairing**: life-stage/senior variants ("Adult"
  vs "Adult 8+", "Adult" vs "Junior") and a packaging-format nuance (can vs pouch) that the current
  key doesn't distinguish. Within the plan's accepted error margin; not tuned further this session
  per explicit instruction.
- **LLM transport not implemented.** ADR-0006.
- **`make` not installed.** `.\make.ps1 <target>` is the Windows path. ADR-0003.
- **Bonus-weight titles are a confirmed real trap**, not just theorized — seen in real scraped data
  on both shops this session. Needs to reach the Phase 3 annotation set.

## Blocked on Bogdan

Nothing that blocks progress right now. One real decision when ready: whether to build animax.ro
next as originally planned, or first decide whether/how to broaden category scope (the 400 gate's
gap now looks partly structural — concentrated in one brand and in food/treats categories only —
so a third adapter alone may not be sufficient on the arithmetic in `docs/SOURCES.md`).

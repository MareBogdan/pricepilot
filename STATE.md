# STATE

Phase: 1 — Collection (petmax.ro + pentruanimale.ro + animax.ro, all three on a daily GitHub
Actions cron). Gate met except the 7-consecutive-days requirement, which just needs time to pass.
Updated: 2026-09-13

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

Phase 1 — Collection: in progress. Gate per CLAUDE.md §7. Checked against git history
(2026-09-13): the ≥400-overlap bullet did not exist before 2026-09-12 (`git show 591b7a3 --
CLAUDE.md`) — that commit added it, along with the proxy-key methodology and the build-order
note. The ≥3,000/≥3-sources/≥7-days wording predates that commit unchanged (only its formatting,
from one sentence into a bulleted list, changed that day). The overlap bullet's *measurement
method* was amended again on 2026-09-13, this time in CLAUDE.md text itself (this session), to
point to ADR-0023 rather than the proxy key alone. So "as amended 2026-09-12" was accurate only
for the overlap bullet's addition, not for the whole gate, and is now stale for that same bullet's
measurement method — hence dropped in favour of dating each actual change.

[x] `docs/SOURCES.md` filled in for petmax.ro, pentruanimale.ro and animax.ro from real fetches
[x] fixtures saved for all three sources, offline tests passing
[x] all three adapters implemented behind the `Scraper` protocol, tested offline
[x] every run logs to `scrape_runs`; volume-alert logic verified; error text now persisted
    (`error_detail`, ADR from this session) after hitting the "count only, no detail" gap twice
[x] ingest is idempotent on (source, external_id, collected_date) — **re-verified twice**: petmax
    ran twice today, pentruanimale ran twice today, zero duplicate
    (source, external_id, collected_date) groups anywhere in the table (query shown, ADR-0016)
[x] collection running on a GitHub Actions cron for all three sources —
    `.github/workflows/scrape-petmax.yml` (name kept; the workflow now runs three independent jobs)
[x] ≥3,000 in-scope listings — **18,700 total** (8,127 petmax_ro + 8,023 pentruanimale_ro +
    2,550 animax_ro), verified from `scrape_runs` and `raw_listings` on a separate connection.
    (2,550 is the correct, distinct-product count; `docs/SOURCES.md`'s category table sums to
    2,551 because one product is a genuine member of two of the ten categories and gets counted
    twice by a per-category sum — see that doc for the verified diff. Not a bug, not data loss.)
[x] ≥3,000 in-scope listings from **≥3 sources** — **3 sources, animax.ro added and verified
    2026-09-13** (ADR-0024): real dispatched run, 2,550 items ingested, 0 errors, verified on a
    fresh Neon connection. petmax (Gomag) and pentruanimale (VTEX) are both non-Shopify, satisfying
    CLAUDE.md §7's "at least one non-Shopify" regardless of animax's own platform.
[ ] ≥7 consecutive days of history — **2 / 7** (2026-09-12 → 2026-09-13, no gap; the scheduled
    cron fired for the first time on 2026-09-13, 5 hours late against its 03:10 UTC trigger)
[x] **≥400 products on two or more shops — MET by hand-verified sample estimate: point 1,211,
    95% CI [897, 1,519]** (ADR-0023). The proxy key itself now reports 241 with all three sources
    live (up from 94 with two) and is a known floor at ~8% measured recall — kept in `make status`
    as a daily indicator, not as the gate metric. The sample itself (n=50, seed 20260913) covered
    petmax food listings vs pentruanimale.ro only; see `docs/AUDIT.md`'s 2026-09-13 verification
    note and ADR-0023 for the full computation and its limitations.
[x] adapter for animax.ro — **built, tested, deployed 2026-09-13** (ADR-0024)
[x] all adapters tested offline against fixtures — petmax, pentruanimale and animax all done

## Last done (2026-09-13 session, in order)

1. **Closed the overlap gate by measurement method, not by lowering the bar** (ADR-0023): the
   proxy key's recall measured at ~8% (a hand-verified n=50 sample implies point estimate 1,211,
   95% CI [897, 1,519], against the key's own 94) — too low to support the decision the gate
   exists to make. Threshold stays 400; the gate is now decided from the sample. `make status`
   and `make overlap` both relabelled so the proxy count reads as a known-low floor, never as the
   gate itself.
2. **Built, tested, and deployed the animax.ro adapter** (ADR-0024). Recon corrected the plan's
   platform guess (Shopify, not Magento) before any code was written against the wrong
   assumptions. Reads the standard `products.json` endpoint, not scraped HTML — structured data,
   ~58x lighter bandwidth than the rendered page. `external_id` is the Shopify variant id, never
   product id/handle/url — this morning's identity-stability diagnostic's lesson applied
   immediately. 26 offline tests against a real, trimmed fixture; live `--limit 5 --dry-run`
   clean; real dispatched run ingested 2,550 items with 0 errors, verified on a fresh Neon
   connection. Wired into the daily workflow as a third independent job.
3. **Re-measured the proxy overlap with all three sources live**: 94 → 241 (sources=3). Reported
   as a floor with its recall caveat, not as the gate — the gate stays decided by ADR-0023's
   sample.
4. **Found real animax data quirks worth keeping**: the shop's own structured `grams` field
   disagrees with its own title text on at least one listing (500g vs a title stating "2 kg");
   decimal point vs comma within the same shop on the same product line (not just cross-shop);
   age-band/breed-size codes ("8+", "L+XL") that contain "+" but are not CLAUDE.md §7's
   bonus-weight pattern. All captured in `docs/SOURCES.md` and the adapter's test fixture.

## Last done (2026-09-12 session, in order)

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

- **`is_regulated()` is not catching real veterinary-diet products on animax.ro — 108 listings,
  not fixed this session.** Found while reconciling the 2,551-vs-2,550 count (`docs/SOURCES.md`):
  108 ingested animax listings carry `product_type` "Diete veterinare pentru caini/pisici"
  (veterinary diets — explicitly out of scope per CLAUDE.md §7). Title-substring matching misses
  them (e.g. "Brit Grain Free **VD** Recovery 400g" — "VD" reads as a product-line code, not a
  flagged phrase). These are legitimately cross-listed into the general food categories by animax
  itself, not a category-selection mistake. Needs a decision: extend `is_regulated()`'s vocabulary
  (title tokens like "VD", "recovery", or check `raw_payload.product_type` instead of/alongside
  title), or leave it — either way this is a scope/logic change, deliberately not made this
  session (out of the 3-step brief that found it).
- **Deferred to Phase 2 (Normalization)**, causes already diagnosed in `docs/AUDIT.md`: brand-field
  canonicalization (petmax splits Brit into Brit/Brit Premium/Brit Care/Brit Fresh and Calibra into
  5 strings; pentruanimale writes "HILL'S Science Plan" where petmax writes "Hill's"), an
  English-Romanian flavour-word table (Chicken/Pui, Lamb/Miel, Beef/Vita, Salmon/Somon,
  Turkey/Curcan, Duck/Rata, Rabbit/Iepure, Tuna/Ton), and partial token overlap instead of exact
  set equality. These are normalization work, not a proxy-key patch — `overlap_key()` stays as-is.
- **petmax's `url` field is not a trustworthy identity signal.** Slug collisions produce a numeric
  suffix (e.g. `-6847`) and the URL can describe a different product than the row's title (see
  2026-09-13 verification note in `docs/AUDIT.md`). Checked this session: nothing downstream keys
  on `url` — `overlap.py` never references it, and the one place it could matter,
  `runner.py:182`'s `source_product_id or listing.url` fallback, has never actually fired (0 of
  8,075 rows lack `source_product_id`). Stays a documented constraint for future code, not a bug
  fixed today.
- **The 2026-09-13 scheduled run started at 08:13 UTC against a 03:10 UTC cron** — a ~5 hour
  delay, far past the 10-30 minutes ADR-0018 anticipates. One data point so far; watch it.
- **The proxy key moved 94 → 241 once animax.ro joined** (sources=3, 2026-09-13), still a known
  floor at ~8% measured recall, not the gate — the gate stays closed by the hand-verified sample
  (ADR-0023). Whether animax's contribution is concentrated the same way petmax/pentruanimale's
  overlap was (88% Royal Canin, per the diagnostic session) has not been re-checked; worth a look
  before trusting 241 as evenly distributed across brands.
- **animax's structured `grams` field cannot be trusted as ground truth** — a real listing titled
  "... 2 kg" carries `grams: 500` in the shop's own data (docs/SOURCES.md, ADR-0024). Captured into
  `raw_payload` for reference only; nothing reads it as authoritative. Reinforces why the overlap
  key parses weight from title text and was not changed to use it.
- **7 consecutive days is 2 so far** (2026-09-12 → 2026-09-13, no gap) — the scheduled cron has now
  fired once, 5 hours late (see above).
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

Nothing that blocks progress right now. Every Phase 1 gate box is met except 7 consecutive days
of history, which is wall-clock — it closes on its own once the daily cron has run 5 more times,
nothing to decide. Phase 2 (Normalization) is the natural next phase to open when ready; its
starting scope is already recorded in Open issues above (brand-field canonicalization, the
EN/RO flavour table, partial token overlap).

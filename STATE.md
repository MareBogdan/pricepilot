# STATE

Phase: 1 — Collection (still open — gate met except 7-consecutive-days, 3/7 as of 2026-09-14, pure
wall-clock, nothing to decide) **and Phase 2 — Normalization, CLOSED 2026-09-14.**

Phase 2, 2026-09-14 session, in order: fixed two real bugs the architect review found in
`product_line` (1a brand-span, 1b dangling-token guard — DECISIONS.md ADR-0027), added
conventions 6 and 7, wired `product_line` into `extract()`, committed and scored the
externally-labelled gate sample. **The first accuracy figure (96.6%) was inflated — mostly
both-sides-null agreement — and was corrected before anything was tuned against it: the gate
figure is labelled-cells-only, brand excluded, frozen as measured BEFORE any fix: 261/273 =
95.6%, weight parsing 82/82 = 100%.** `brand` is excluded from the gate figure on principle, not
because its score is weakest — 12 of its 15 mismatches are the gate sample seeing only `title`
text while the extractor correctly prefers the shop's structured brand field, two different
inputs the sample cannot grade either way; brand's own correctness is validated separately by
STEP 1's cross-shop comparability check. Cache proof run with command output (0 new extractions
on a second pass). Four gate-derived fixes then approved and implemented — `"punguta"` food_form
gap (420 titles), a hyphenated-brand-code guard on `breed_size_code` (M-PETS/L-carnitina, 83
titles checked, 80 fixed), two small `food_form` fixes (plural "uscate" added, plural "umede"
checked and deliberately rejected — 17/17 would have been false positives on wet wipes, not wet
food; "semi-umeda" no longer false-positives as wet), and the `"creveti"`/shrimp flavour gap (52
titles) — each measured by population coverage, never by re-scoring the gate sample (that would
be tuning on the test set; the 95.6% stays the frozen, un-re-measured figure of record). No Phase
1 box ticked this session.
Updated: 2026-09-14

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
[x] ≥3,000 in-scope listings — **18,703 total / 18,585 in-scope** (both numbers, always shown
    together per ADR-0025 — 118 rows quarantined as regulated products, never deleted: 8
    petmax_ro, 0 pentruanimale_ro, 110 animax_ro). By source, total/in-scope: petmax_ro
    8,128/8,120, pentruanimale_ro 8,025/8,025, animax_ro 2,550/2,440. Verified from
    `raw_listings` on a separate connection and from `make status`'s own output.
    (`docs/SOURCES.md`'s category-volume table sums to 2,551 for animax because one product is a
    genuine member of two of the ten categories and gets counted twice by a per-category sum —
    not a bug, see that doc for the verified diff; unrelated to the quarantine above.)
[x] ≥3,000 in-scope listings from **≥3 sources** — **3 sources, animax.ro added and verified
    2026-09-13** (ADR-0024): real dispatched run, 2,550 items ingested (2,440 in-scope after
    ADR-0025), 0 errors, verified on a fresh Neon connection. petmax (Gomag) and pentruanimale
    (VTEX) are both non-Shopify, satisfying CLAUDE.md §7's "at least one non-Shopify" regardless
    of animax's own platform.
[ ] ≥7 consecutive days of history — **2 / 7** (2026-09-12 → 2026-09-13, no gap; the scheduled
    cron fired for the first time on 2026-09-13, 5 hours late against its 03:10 UTC trigger)
[x] **≥400 products on two or more shops — MET by hand-verified sample estimate: point 1,214,
    95% CI [899, 1,522]** (ADR-0023, population corrected by ADR-0025). The proxy key itself now
    reports 241 with all three sources live (up from 94 with two) and is a known floor at ~8%
    measured recall — kept in `make status` as a daily indicator, not as the gate metric. The
    sample itself (n=50, seed 20260913, p̂=0.52 unchanged) covered petmax food listings vs
    pentruanimale.ro only, projected onto 2,334 keyable in-scope listings. That number moved from
    ADR-0023's original 2,329 via two separate effects, not one — stated separately per the
    2026-09-13 correction below because the combined "2,329 → 2,334" wording read as the
    population growing after quarantine, when quarantine only ever removes:
      1. **Catalogue churn, 2,329 → 2,338** (+9): each daily petmax run replaces the "latest
         observation" row for a product, so the keyable-food population measured today is not
         the same snapshot ADR-0023 measured on 2026-09-13 — new listings, re-priced listings and
         weight-parsing outcomes shift the count independently of any filtering rule.
      2. **Quarantine, 2,338 → 2,334** (-4): of the 118 rows ADR-0025 quarantined, only 4 fall
         inside this specific population (petmax, food categories, keyable) — the rest are
         non-food-category petmax rows or animax/pentruanimale rows this population never included.
    Recomputed and verified 2026-09-13, against the system clock (`petmax food-category, keyable, latest-observation, ALL
    rows: 2338 / in-scope: 2334 / quarantined: 4`). Gate holds with the same wide margin — neither
    effect moves the estimate by more than about 0.4%. See `docs/AUDIT.md`'s 2026-09-13
    verification note and ADR-0023/ADR-0025 for the full computation and its limitations.
[x] adapter for animax.ro — **built, tested, deployed 2026-09-13** (ADR-0024)
[x] all adapters tested offline against fixtures — petmax, pentruanimale and animax all done

## Phase 2 — Normalization: **CLOSED 2026-09-14**

Opened 2026-09-13, ran in parallel with Phase 1 — was never blocked on Phase 1's remaining
7-consecutive-days box, and does not tick that box closed either (Phase 1 stays open below).

Gate per CLAUDE.md §7: "≥85% attribute accuracy on 100 manually verified listings, with weight
parsing measured separately", plus the cache demonstrably preventing repeat extraction.

**The gate figure, exactly as recorded (not the first number this session produced — see below
for why).** Scored on `docs/learned/phase2-gate-sample-labeled.csv` (100 rows, labelled
externally, code-blind), against `norm_listings` under `EXTRACTOR_VERSION 2026-09-14-v5`
(post-fix code, pre-fix *measurement* — the number below was taken before any of the four fixes,
see "frozen" note further down):

- **Gate figure: labelled cells only, `brand` excluded — 261/273 = 95.6%.**
- Weight parsing (`net_weight_g`), separately, on its 82 non-empty labels: **82/82 = 100.0%.**
- Reported for transparency, not the gate figure: all-cells 966/1000 = 96.6% (inflated — mostly
  both-sides-null agreement); labelled-cells-with-brand 346/368 = 94.0%.
- Cache proof: `scripts/normalize.py` run twice, second pass 0 new extractions out of 10,503
  content hashes (command output in DECISIONS.md ADR-0027 addendum).

**Why `brand` is excluded from the gate figure — not because its score is weakest.** 12 of
`brand`'s 15 mismatches (89.5% on its own 95 labelled cells) are a labelling-scope artifact: the
gate sample shows the labeller only `title` text, never the shop's own structured brand field
`canonicalize_brand()` deliberately prefers. Two different inputs to the same question — this
sample cannot grade `brand` either way, and it is neither an extractor bug nor a bad label.
`brand`'s own correctness is validated separately, by STEP 1's cross-shop comparability check
(Brit/Calibra/Hill's — same product, different shops, same canonical brand).

**Why 95.6%, not the 96.6% first reported or the 90.8% used to approve the fix list.** 96.6% was
scored against all 1,000 cells, and most fields are null on most rows — `dosage_band` alone
contributes 1 real test and 99 free "both sides correctly said nothing" points. 90.8% (334/368)
was a quick mental estimate (368 labelled cells minus all 34 mismatches) that double-subtracts:
12 of the 34 mismatches are false positives on an empty label, never part of the 368-cell
denominator to begin with. The rigorously computed figure is higher than the estimate, not lower.
Full reasoning and the reconciliation arithmetic: DECISIONS.md ADR-0027, addendum #2.

**This figure is frozen — measured before any gate-derived fix, and never re-measured after.**
Every one of the four fixes below was derived from a mismatch inside this same 100-row sample;
re-scoring those same rows after fixing what they revealed would be tuning on the test set. A
future post-fix accuracy number needs a new, independently drawn sample.

[x] `norm_listings` schema designed, reviewed, approved, migrated (0005), verified live on Neon
    (ADR-0026)
[x] gate sample frozen — 100 rows, seed 20260913, seven conventions (6 and 7 added 2026-09-14)
[x] gate sample **labelled and committed** — `docs/learned/phase2-gate-sample-labeled.csv`, by an
    external, code-blind model, same 100 ids/order/titles as the frozen file
[x] deterministic extractor — `src/pricepilot/normalize/` (`quantity.py` -> `brand.py` ->
    `flavour.py` -> `attributes.py` -> `product_line.py`). Regex and lookup tables only, no LLM,
    no network. `norm_listings` fully re-extracted under `EXTRACTOR_VERSION 2026-09-14-v5`:
    10,532 rows (population grew by 29 via ordinary scheduled collection between sessions), 0
    extractor exceptions.
[x] coverage report — `scripts/normalize_coverage.py`, current numbers: brand 100.0%,
    product_line 99.9%, net_weight_g 81.0%, breed_size_code 23.1%, life_stage 27.9%, flavour
    61.4%, food_form 61.4%, dosage_band 0.1%.
[x] `product_line` — built, two real bugs fixed after architect review (1a brand-span, 1b
    dangling-token guard), wired into `extract()`.
[x] `breed_size_code`/`life_stage` failure-shape breakdown (diagnostic): the EN "Small/Large/..."
    breed-size gap and "kitten" life-stage gap are documented, deliberately not fixed this
    session — resurfaced honestly in this session's gate mismatches, not silently ignored.
[x] `flavour`/`food_form` table extensions (multiple sessions, most recently `"creveti"`/shrimp).
[x] **85% accuracy gate — MET: 95.6% (261/273, labelled cells, brand excluded), weight parsing
    100.0% (82/82).**
[x] cache proof — MET, command output in DECISIONS.md ADR-0027 addendum.
[x] **four gate-derived fixes approved and implemented** (`"punguta"` food_form, M-PETS/
    L-carnitina breed_size false positives, two small food_form fixes, `"creveti"`/shrimp
    flavour), each measured by population coverage before/after — never by re-scoring the gate
    sample. Details and every number: DECISIONS.md ADR-0027 addendum #2.

## What Phase 3 will need from Phase 2's output that doesn't exist yet

Grounded in what this session actually saw in the data, not the plan's description:

- **A category signal** (food vs. accessory vs. litter vs. toy) — `norm_listings` has none. Two
  real false-positive classes surfaced this session precisely because nothing upstream separates
  categories: a food product line named `"Sheba Mini"` vs. an accessory's own `"Mini"` dimension;
  `"umede"` (wet WIPES, an accessory) vs. wet food. Phase 3's candidate retrieval will hit the
  same ambiguity at a larger scale without a cheap category filter.
- **`product_line`'s own accuracy measurement.** It's the field Phase 3 will lean on hardest for
  matching, and it has never been gated — the only external labels for it (STEP A, prior session)
  were drawn against a convention STEP 1 superseded. It needs a fresh, convention-matched labelled
  sample before Phase 3 trusts it at the level `brand`/quantity now are.
- **A brand-trustworthiness signal.** Some shops' structured brand fields are genuine manufacturer
  names; others are internal supplier/distributor codes (`"Ipts"`, `"Record"`, `"Opti"`) that
  don't match across shops at all for the same product. Candidate blocking on `brand` can't treat
  every value as equally reliable without knowing which is which.
- **Hyphen/spacing-normalized brand keys.** `canonicalize_brand()` still leaves `"julius-k9"` and
  a human's `"julius k9"` as different strings. Fine as a feature for a learned matcher; a real
  gap if Phase 3 uses exact-match brand as a blocking key rather than just a signal.
- **The still-open EN breed-size vocabulary gap** (`"Small"`/`"Medium"`/`"Large"`/`"Giant"`/`"Toy
  Breed"`, `"kitten"`) is exactly the size-variant hard-negative class CLAUDE.md names as the
  dominant Phase 3 error risk — leaving it unmatched removes a real signal precisely where
  matching needs it most.

## Last done (2026-09-14 Phase 2 session, in order)

1. **STEP 1a — `brand.brand_span_text()`: strip only the manufacturer from `product_line`, not
   the shop's whole raw brand field.** Fixes a real bug the architect review found: stripping
   `"Brit Premium"` whole cut `"Premium"` out along with the brand, and made the same product
   non-comparable across shops (petmax vs pentruanimale's bare `"BRIT"`). Verified on the
   Brit/Calibra/Hill's cross-shop pairs the 2026-09-13 diagnostic documented.
2. **STEP 1b — general dangling-token guard for `product_line`** (`_strip_dangling_tokens`,
   `product_line_guard_violations`), found via a real accessory title (`"...diametru 2 l..."` ->
   `"diametru"` stranded once its quantity is excised). Zero violations swept over the full
   18,585-title population; 260 real titles changed by the guard.
3. **`product_line` wired into `extract()`**, `EXTRACTOR_VERSION` bumped to `2026-09-14-v4`,
   `norm_listings` cleared and fully re-extracted (10,503 rows, 0 errors). Coverage 99.9%.
4. **Convention 6** (`"N x W"` vs `"N bucati / W"`) — no code change needed, just tests and README.
   **Convention 7** — `breed_size_code` accessory-context guard (`attributes.py`), verified zero
   accessory titles still leak a breed_size_code over the full population.
5. **Gate sample labelled and committed**, scored (`scripts/measure_gate.py`). First figure
   (96.6%, all-cells) was inflated; corrected to the gate figure — **95.6% (261/273, labelled
   cells, brand excluded), 100% weight parsing (82/82)** — before any fix, and frozen at that
   number. Cache proof run with command output. STEP 5 fix list proposed (15 named failure
   shapes, priority-ordered, population counts for each real bug).
6. **Four gate-derived fixes approved and implemented, measured by population coverage (never by
   re-scoring the gate sample):** `"punguta"` food_form gap (420 titles, all now `"pouch"`); a
   hyphenated-brand-code guard on `breed_size_code` (M-PETS/M-Pes/L-carnitina, 83 titles checked,
   80 now correctly null, 3 correctly still resolve — a real, separate size token on a dental chew
   bone, not a bug); two small `food_form` fixes (plural `"uscate"` added — 8/8 now `"dry"`;
   plural `"umede"` checked and **rejected** — all 17 hits are wet WIPES, not wet food, and adding
   it would have manufactured 17 false positives; `"semi-umeda"` no longer false-positives as
   `"wet"` — 8/8 now correctly null); `"creveti"`/`"crevete"`/`"shrimp"` flavour gap (52 titles,
   all now include `"shrimp"`). `EXTRACTOR_VERSION` bumped to `2026-09-14-v5`, `norm_listings`
   cleared and fully re-extracted (10,532 rows, 0 errors). 381 tests pass; ruff, format, mypy
   clean. **Phase 2 gate: MET and CLOSED.**

## Last done (2026-09-13 Phase 2 session, in order)

1. **STEP 0a — Hill's "PD" (Prescription Diet) token, checked and added.** Same per-token
   discipline ADR-0025 used for " vd "/" vhn ": " pd " checked against all 18,703 stored titles —
   8 matches, all genuine (Hill's PD Afectiuni hepatice L/D, Metabolic, Digestive Care I/D, Low
   Fat I/D, Urinary Care C/D, Gastrointestinal Biome, Stress C/D, Boli Renale K/D), zero false
   positives. Added to `REGULATED_TITLE_TOKENS`. Re-ran `scripts/quarantine_regulated.py`: 0
   newly matched — all 8 were already quarantined via animax's `product_type` signal, so this is
   defense-in-depth for petmax/pentruanimale (neither exposes a structured signal), not a
   population change.
2. **STEP 0b — the mixed "2,329 → 2,334" population number, separated into its two causes.** See
   the corrected Gate progress text above: catalogue churn (+9, 2,329 → 2,338, a day of collection
   passing between ADR-0023's original measurement and this session) and quarantine (-4, 2,338 →
   2,334, only 4 of the 118 quarantined rows fall inside that specific population). Recomputed and
   verified directly against the DB, not asserted.
3. **STEP 1 — `norm_listings` schema, proposed, corrected on review, migrated, verified**
   (ADR-0026). Before reusing `raw_listings.content_hash` as the cache key, actually read
   `Listing.content_hash` (scrapers/base.py) rather than assuming: confirmed
   `sha256(normalize_title(title))` — title only, no price/stock/source — so it's safe to reuse,
   and confirmed it carries no source component, making the key deliberately global across
   sources (documented as a decision, not left as an accident). Added `net_volume_ml` as
   `net_weight_g`'s sibling, enforced mutually-exclusive by a DB `CheckConstraint` written in
   plain boolean SQL (not Postgres's `num_nonnulls()`) specifically so it's testable against
   SQLite in-memory with no live database, plus a second, independent ORM-level `@validates`
   guard. `dosage_band` stays text (approved as proposed). `brand` indexed for Phase 3. Migration
   0005 applied to Neon and verified live via `sqlalchemy.inspect` (columns, both unique-index
   forms, the check constraint, the PK — all match). 10 new offline tests
   (`tests/test_norm_listings.py`), including a real constraint-violation insert against SQLite
   that bypasses the ORM guard entirely. `test_migration_covers_every_model_table` (test_schema.py)
   generalized to scan every migration file, not just 0001 — it had assumed every table lived in
   the first migration, true until this session's first genuinely new table.
4. **STEP 2 — gate sample drawn and frozen, `docs/learned/phase2-gate-sample.csv`**
   (`scripts/draw_gate_sample.py`, committed and reusable). 100 rows, seed 20260913, in-scope only
   (`excluded_reason IS NULL`), deduplicated to one row per `content_hash` (10,503 distinct
   titles in the in-scope population) so each row is a genuinely distinct extraction case, not a
   title repeated across collection days. Stratified roughly proportional to each source's share
   of that population (25/36/39 vs. a 23/38/39 population split). Ten CLAUDE.md-named hard-case
   forms deliberately over-sampled first (2 each, one source — special-char brands — had only 1
   genuine candidate under an early, buggy detector regex; caught and fixed before freezing, see
   below), then the remainder filled by the proportional random draw. Every attribute column
   written empty; the four STEP 2 conventions are written verbatim at the top of the file. Not
   filled in by this session, not filled in by the extractor — labelling happens in parallel with
   STEP 3.
5. **Caught and fixed a bug in the sample's own hard-case detector before freezing it.** The
   first draft's diacritic-folding helper didn't touch apostrophes, so its "Hill's" detector
   (`hill s|hills`) matched neither "Hill's" nor "hill's" — it found exactly one candidate, and
   that candidate was "Manitoba Hills" (an unrelated line name containing the substring
   "Hills"), a false positive. Caught by checking the actual candidate count (1) before trusting
   it, not by assuming the regex worked. Fixed by reusing `overlap.strip_diacritics` (which
   already folds both apostrophe styles) instead of a bespoke fold — candidate count went from 1
   (wrong) to 387 (genuine), and the frozen sample now carries two real Hill's rows. No genuine
   Smolke candidates exist in the current three-source data — CLAUDE.md's Smolke example names
   zoomalia.ro, a source not yet built — so that half of the "special-character brands" case is
   absent from this sample by data reality, not by a detector miss.
6. **Fixed the frozen CSV's own comment-block preamble — it was invalid CSV.** Line 1 of the
   "#" block contained a comma, so Excel/Sheets/pandas would have read it as the header and
   scrambled every column. Moved the conventions into a sibling file,
   `docs/learned/phase2-gate-sample-README.md`; the CSV now starts directly at its real header
   row. Verified the 100 data rows are byte-identical to before (diffed old vs. new, not
   re-drawn) — same rows, same order, same ids, still empty. Also added a fifth convention,
   caught on review: `brand` form was undefined (manufacturer only, lowercased, simplest form —
   e.g. "brit" not "Brit Premium"), which would otherwise have failed the gate on a definition
   disagreement rather than a real extraction error. Recorded in ADR-0026 as a same-day
   amendment, not a silent rewrite of what the ADR originally said.
7. **STEP 3 — deterministic extractor built, `src/pricepilot/normalize/`.** Order per CLAUDE.md
   §7: `quantity.py` (weight/volume/pack/bonus/dosage) first, then `brand.py` (built from real
   per-source brand strings — 132/153/185 distinct on animax/pentruanimale/petmax, printed and
   read before any alias was written, not guessed), then `flavour.py` (EN/RO pairs — CLAUDE.md's
   eight plus fish/liver/game, extended from real titles), then `attributes.py` (breed-size, life
   stage, food form). 55 new offline tests (`tests/test_normalize_*.py`). `scripts/normalize.py`
   populated `norm_listings` for all 10,503 distinct in-scope titles, 0 extractor exceptions; a
   second dry run confirmed the content_hash cache works (0 new to extract, matching CLAUDE.md
   §5.1's "runs once per unique title" rule, extended here to deterministic extraction too even
   though it costs nothing).
8. **Two real bugs found and fixed before trusting the output — same "verify before trusting a
   regex" discipline as ADR-0025's token checks, applied to STEP 3's own code, not just the
   quarantine rule.**
   - **Breed-size single-letter matcher had two false-positive classes.** Checked the pattern
     against all 18,585 in-scope titles before trusting it (same discipline the " pd " token
     check used): (a) `"Nisip Silicat ... 7,6 L"` — a **volume unit**, not a size code, matched
     because a bare `\bL\b` doesn't know a preceding digit means "litres"; (b) `"HILL'S ..."`,
     `"SAM'S FIELD ..."`, `"WOLF'S MOUNTAIN ..."` each produced a **phantom standalone "S"**
     purely from the apostrophe creating a word boundary — every Hill's-branded title would
     otherwise have silently gained a fabricated size code. Both guarded in
     `attributes.py::extract_breed_size` before any coverage number was measured.
   - **Dosage-band regex collided with the "Julius K-9" brand name** (385 titles). "Julius K-9-
     3kg" parsed as dosage band "9-3 kg", swallowing the product's real 3kg weight — found via
     STEP 4's own coverage report (a "quantity regex missed it" example), not by inspection.
     Fixed with a lookbehind requiring the band's first digit not be glued to a letter-hyphen
     code (`quantity.py::_DOSAGE_BAND`). `norm_listings` was cleared and fully re-extracted
     (`EXTRACTOR_VERSION` v1 -> v2) before the coverage numbers below were measured, so they
     reflect the fixed extractor, not the buggy first pass.
9. **STEP 4 — coverage report, `scripts/normalize_coverage.py`.** Coverage, not accuracy (the
   gate sample is still unlabelled, nothing to score against). Quantity found (net_weight_g OR
   net_volume_ml): **86.1% overall** — pentruanimale 98.5%, animax 88.6%, petmax 72.2% (petmax's
   gap matches the already-diagnosed 2026-09-12 finding: its non-food categories genuinely carry
   no weight in the title, not a parsing failure). `brand` 100.0% (only 3 nulls, all a genuinely
   empty shop-side field). `flavour` 59.6%, `food_form` 56.1% — of their nulls, ~2,882 have
   *both* null together (very likely non-food listings: toys, litter, accessories) and the
   remainder (~1,300-1,700 each) are titles the extractor's word lists plausibly should have
   caught but didn't, the honest remaining gap. `breed_size_code` 26.8%, `life_stage` 27.9% — no
   further failure-shape breakdown built for these two this session (raw examples only).
   `product_line` 0.0% (not built this session, by design — see Open issues).
   `pack_count`/`bonus_weight_g`/`dosage_band` are all correctly low (8.5%/0.4%/0.1%): most
   listings genuinely have no multipack, bonus, or dosage band, and the report deliberately
   excludes these three (plus `product_line`) from "worst fields" analysis so a low, expected
   number isn't presented as if it were a discovered failure.
10. **STEP A/B/C — parallel work while the gate sample is labelled externally (ADR-0027).**
    Every example drawn from `raw_listings`/`norm_listings`, never `docs/learned/
    phase2-gate-sample.csv`.
    - **STEP A, `product_line.py` built.** Title minus raw `source_brand` text, minus a closed-
      vocabulary RO food/treat descriptive-clause regex (form/packaging/qualifier/animal/
      trailing-stage words, all read from real leading n-grams and mid-title descriptor windows
      before being added), minus `quantity.quantity_spans()` (new function, reuses
      `extract_quantity`'s own patterns so the two can never disagree). Life-stage words are
      consumable ONLY inside a matched clause, never free-standing — verified against
      `"Royal Canin Mini Adult 8 kg"`, where "Adult" is the product's own real line name, not
      boilerplate. Previewing 30+ real pairs surfaced and fixed two real bugs before the full-
      table run: a dangling "x" glue character from the reversed "85g x 4buc" pack form (622
      titles), and "multipack"/"bax"/"pachet economic"/"pachet mixt" (199+115 titles) needing
      their own removal pattern. **Not yet wired into `extract()` or run over `norm_listings`** —
      waiting on review of the pairs (see below), per explicit instruction.
    - **STEP B, `breed_size_code`/`life_stage` failure shapes — report only, not fixed.**
      `breed_size_code` (7,690 nulls): 96.4% correct null, 2.0% RO "talie mica/mare/medie"
      stated-but-missed, 1.5% EN "Small/Medium/Large/Giant/Toy Breed" stated-but-missed.
      `life_stage` (7,571 nulls): 97.6% correct null, 2.3% "kitten" stated-but-missed, 0.1% an RO
      diminutive stated-but-missed. Both fields' low raw coverage mostly reflects real absence in
      the title, not a broken matcher.
    - **STEP C, flavour/food_form tables extended from a checked sample.** 60 real titles sampled
      (seed 20260917) from the 3,090-title "likely real food, one field missing" pool. Ten new
      flavour pairs (bison, mackerel, ham, poultry — kept distinct from chicken, deer, reindeer —
      kept distinct from deer/game, goose, sardine, cod) and six new food_form words (jerky->dry;
      pate/ragout/cremoasa/tub/sos->wet), every one checked against the full population before
      adding. "Cutie" (box) checked and dropped — packaged both dry and wet items in real
      samples, no reliable single mapping. `norm_listings` cleared and re-extracted
      (`EXTRACTOR_VERSION` v2 -> v3): flavour 59.6% -> 61.3% (+187 rows), food_form
      56.1% -> 57.7% (+166 rows).
    - 351 tests total (65 new this round), ruff/format/mypy clean throughout.

1. **Confirmed the petmax toy-category anomaly is dedup working correctly, not a bug** (STEP 0).
   Live-fetched `jucarii-caini`'s real product ids and checked them against `raw_listings`: all
   sampled ids were present, but filed under `accesorii-caini` — petmax cross-lists these
   products under both categories, and the run-wide `seen` set (scoped across the whole run,
   `accesorii-caini` iterated before `jucarii-caini` in `DEFAULT_CATEGORIES`) correctly captures
   each product once, under whichever category it's encountered first. No listings missing.
2. **Tightened `is_regulated()` and closed the veterinary-diet leak found 2026-09-13** (ADR-0025).
   Diacritic folding (reusing `normalize_title()`) plus five new tokens — `"diete veterinare"`
   (plural), `" vd "`, `" vhn "`, `"hidrolizat"`, `"hydrolyzed"` — each verified individually
   against all 18,703 stored titles before being added (table in ADR-0025). `"dietetic"` was
   tested and dropped: zero net catch beyond `" vd "`, real false-positive risk against ordinary
   Romanian retail weight-control marketing. Explicitly did **not** add symptom/condition words
   (urinar, renal, mobility, hypoallergenic, digestive care, obezitate, recovery, satiety,
   hepatic, gastrointestinal, sensitivity, diabetic) — verified these overwhelmingly catch
   ordinary retail condition-support food, not prescription diets.
3. **Added animax's `product_type` as a second, independent regulated signal** (checked before
   insertion, in `_parse_product`) and **started capturing pentruanimale's VTEX
   `categories`/`categoryId`** into `raw_payload` going forward (forward-only — cannot be
   backfilled; pentruanimale's historical regulated-product exposure stays genuinely unmeasured,
   see Open issues).
4. **Quarantined 118 already-collected rows, deleted none** (STEP 2, ADR-0025). New nullable
   `raw_listings.excluded_reason` column (migration 0004) names the signal that fired; NULL means
   in scope. `scripts/quarantine_regulated.py` applied the tightened rule — petmax 8 rows (4
   products × 2 days), pentruanimale 0, animax 110 (83 both signals agree, 25 caught only by
   `product_type`, 2 caught only by title) — verified idempotent (a second dry run found 0 new
   matches). `overlap.py` and `make status` now read `excluded_reason IS NULL`; `make status`
   prints total and in-scope side by side everywhere rather than applying the difference
   silently.
5. **Recomputed everything the quarantine touches, gate holds with the same wide margin**:
   grand total 18,703 stored / 18,585 in-scope (still ≫ 3,000); ADR-0023's sampled population
   2,329 → 2,334 (only 4 of the 118 fell inside that specific population); point estimate 1,211 →
   1,214; 95% CI [897, 1,519] → [899, 1,522]. The correction moved the estimate by about 0.3%.

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

- **CLOSED 2026-09-13: Hill's "PD" token, checked and added** — 0 newly quarantined (all 8
  matches were already caught by animax's `product_type` signal); defense-in-depth for the other
  two sources going forward. See "Last done" above.
- **CLOSED 2026-09-14: Phase 2 gate sample labelled and scored, gate MET and CLOSED.** Labelled
  externally (by a model with no visibility into this repo's code, so never tuned against),
  committed as `docs/learned/phase2-gate-sample-labeled.csv`, scored by
  `scripts/measure_gate.py`: **gate figure 95.6% (261/273, labelled cells, brand excluded), 100%
  weight parsing (82/82)** — the 96.6% first computed was the inflated all-cells figure, corrected
  before anything was tuned against it (DECISIONS.md ADR-0027 addendum #2 has the full
  reconciliation). This figure is frozen, taken before the four gate-derived fixes below, and not
  re-measured after them. Full breakdown and the 34 mismatches' failure-shape analysis in
  DECISIONS.md ADR-0027.
- **CLOSED 2026-09-14: `product_line` extraction wired into `normalize.extract()` and run over
  the full table.** `src/pricepilot/normalize/product_line.py` — the manufacturer-only portion of
  the brand field (not the whole raw field, since STEP 1a) + RO food/treat descriptive clause +
  quantity/pack/bonus/dosage tokens removed, a general dangling-token guard applied, everything
  else preserved verbatim. Coverage 99.9% (10,525/10,532).
- **CLOSED 2026-09-14: four gate-derived fixes implemented** (`"punguta"` food_form, M-PETS/
  L-carnitina breed_size false positives, two small food_form fixes, `"creveti"`/shrimp flavour),
  each verified by population coverage before/after, never by re-scoring the gate sample.
  `EXTRACTOR_VERSION` -> `2026-09-14-v5`. Full detail: DECISIONS.md ADR-0027 addendum #2.
- **CLOSED: `flavour`/`food_form` gap investigated (STEP C, ADR-0027).** Sampled 60 real titles
  (seed 20260917) from the combined "likely real food, one field missing" pool, checked every
  candidate word against the full population before adding. flavour 59.6% -> 61.3%, food_form
  56.1% -> 57.7%. "Cutie" (box) was checked and deliberately NOT added — real samples packaged
  both dry and wet items, no reliable single mapping. Full list of additions in ADR-0027.
- **Brand extraction has no title-only fallback.** `canonicalize_brand()` returns `None` when the
  shop's own structured brand field is empty — only 3 of 10,503 rows today (all petmax), so low
  priority, but the function's `title` parameter is already reserved for this if it ever becomes
  worth building.
- **CLOSED: `breed_size_code`/`life_stage` failure-shape breakdown built (STEP B, ADR-0027) —
  diagnostic only, not fixed.** For both fields, ~96-98% of nulls are genuinely correct (title
  states nothing); the small real-gap remainder (talie mica/mare/medie, Small/Large/Medium/
  Giant/Toy Breed, kitten, RO diminutives) is documented in `scripts/normalize_coverage.py` and
  ADR-0027 but deliberately not wired into `attributes.py` this session — scoped strictly to what
  was asked (report the split, not fix it).
- **CLOSED 2026-09-14: `is_regulated()` veterinary-diet leak** (ADR-0025). Tightened the shared
  token check (diacritic folding, line-code tokens), added animax's `product_type` as a second
  signal, and quarantined the 118 already-collected rows the tightened rule catches. See "Last
  done" above and ADR-0025 for the full rule, evidence, and rejected alternatives.
- **pentruanimale.ro's regulated-product exposure is "not measured", not "clean".** Its 0-hits
  result from the 2026-09-13/14 title-text diagnostic is real but incomplete: the source also
  carries VTEX `categories`/`categoryId` (confirmed live) that could in principle reveal a
  veterinary-diet branch, but that field was never captured before ADR-0025 started capturing it
  **going forward only** — it cannot be backfilled onto rows already collected. Do not read
  pentruanimale's 0-Tier-A-hits as evidence it has no leak; it means only that title text alone
  found nothing, which is the weaker of the two signals everywhere else it was checked.
- **Hill's "PD" (Prescription Diet) is a candidate line-code token, not added this session.**
  Found while reconciling animax's title-check against its `product_type`: "Hill's PD Metabolic",
  "Hill's PD Afectiuni hepatice L/D" and similar are caught by `product_type` but not by any
  title token (ADR-0025's token list is `" vd "`/`" vhn "` only, per the two brands checked).
  Worth the same per-token verification ADR-0025 did for "VD"/"VHN" before adding "PD" — not done
  this session, since "PD" is a much shorter, more collision-prone string than "VD"/"VHN" and
  needs its own check across all stored titles before being trusted.
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

Nothing right now. Phase 2's gate is met and closed (2026-09-14); STEP 5's fix list was approved
and the 5 items covering the four fix groups were implemented the same session (punguta, M-PETS,
two food_form fixes, crevete/shrimp — DECISIONS.md ADR-0027 addendum #2). The remaining 10 of 15
named shapes (#1, #4, #7-#13, #15) stay documented-but-unfixed by design — genuine definitional
questions, known-deferred gaps, or a gate-sample scope limit, none needing a decision to proceed
with Phase 3.

Every Phase 1 gate box is met except 7 consecutive days of history (3/7 as of 2026-09-14), which
is wall-clock — it closes on its own once the daily cron has run 4 more times, nothing to decide.

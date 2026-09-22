# STATE

Phase: 1 — Collection, **CLOSED 2026-09-22** (last box, ≥7 consecutive days, MET — see Gate
progress below), Phase 2 — Normalization, **CLOSED 2026-09-14**, and **Phase 3 — Matching, open
since 2026-09-15.**

**Current state, 2026-09-22 (after the annotator's review-pass ingest) — read this paragraph
first; everything below is history, not status.** **Phase 1 is CLOSED** (re-measured this session
against the real database: strict definition 9 consecutive days, 2026-09-13→2026-09-21; see Gate
progress below for the full query output). **Phase 2 is CLOSED.** **Phase 3 is open**, items 1-4 of
CLAUDE.md §7 done: (1) candidate retrieval closed at **recall@20 = 88.0% (44/50), Wilson 95% CI
[76.2%, 94.4%]** — a measurement-power finding, neither met nor missed; (2) annotation tool built;
(3) **annotation COMPLETE: 997/997 labels, M 354 / N 634 / S 9** (post-review; was M 359/N 628/S 10
pre-review — 6 labels moved: 5 M→N, 1 S→N), all by Bogdan; (4) product-level split: **blind TEST 300 rows / 287 distinct
pairs**, **assisted TRAIN_VAL 697 rows / 672 distinct pairs**. Self-agreement on the 38 repeated
pairs — **TEST 13/13 = 100%, TRAIN_VAL 22/25 = 88%** (pre-reconciliation, measured at ingest
2026-09-21; not recomputed post-review — the review pass reconciled the 3 disagreements by
construction, so a fresh figure would be circular, not a real second measurement; see DECISIONS.md
ADR-0028 addendum #17) — measures consistency on the `trivial_spot_check` pairs only
(near-identical titles), never the hard negatives; TRAIN_VAL's more informative reading is a **12%
self-disagreement rate on trivially easy pairs**.

**Labels are still UNFROZEN — the annotator's review pass ran this session (11 of 12 queued
occurrences genuinely re-decided, 6 changed label), but the checker still finds a real blocking
problem, so `scripts/freeze_labels.py --freeze` was correctly refused, not attempted.** Checker
re-run: **a 0, b 0, c 0, d 4, e 3, f 0 — 7 flags / 7 occurrences** (was 15 flags / 12 occurrences
pre-review; a and f fully resolved). **Class d (4) blocks the freeze** — four `trivial_spot_check`
"Royal Canin Kitten" pairs are labelled `N` with no rationale recorded, contradicting the tier's
own "trivially the same" assumption (DECISIONS.md ADR-0028 addendum #16 already characterised this
population as a measured anchoring effect on the engine's suggestion, not a labelling oversight —
that framing stands). Class e (3) never blocks (`freeze_labels.blocking_findings()` excludes it by
construction — a stored `normalize/species.py` data defect, never a labelling error).

**One occurrence needs the annotator's explicit attention before anything else — this is the real
next action, not "run the review pass again":** `3f574dad8b6e_b52acad20816_0`, the *only* queued
occurrence in the blind TEST split, was **not actually re-examined this session** despite being
queued — its stored `decided_at`/`revised_at` is still `2026-09-21T16:39:52.697Z`, with no
2026-09-22 timestamp anywhere, and its label (`N`) is simply the prior session's revision carried
forward — **the same revision ARCHITECT_NOTES already flagged as invalid** (rule 1 reads the
title, not the `species` field; both titles say "pisici"/cat). Whether blind TEST is genuinely
287/287 blind or has one non-blind exception is open until this is resolved (README corrected to
say so, not to assert either way). Full detail: DECISIONS.md ADR-0028 addendum #17.

**`docs/learned/phase3-eval-view.json` (`scripts/build_eval_view.py`) is the single source of
per-tier pair-count denominators for item 5** (the baseline, not started) — post-review: **TEST 287
distinct pairs (97 M / 187 N / 3 S, 284 scored) — byte-identical to pre-review, nothing in TEST
moved**; **TRAIN_VAL 672 distinct pairs (222 M / 444 N / 6 S, 666 scored)** — was 226/439/7/665;
only `proxy_key_collision` and `capacity_differs_cross_shop` tiers moved. `--assert-pre-review` now
correctly fails (it pins the pre-review numbers, and TRAIN_VAL has genuinely moved) — that failure
is expected, not a bug. Never read `phase3-annotation-split.json`'s own `per_tier_counts` block for
denominators — its `test_pair_ids`/`train_val_pair_ids` fields are mislabelled ROW counts (sum to
300/697, not 287/672), a known trap left in that frozen file, documented not fixed (ADR-0028
addendum #16). `docs/phase3-baseline-model-choice.md` updated to 666 trainable pairs (was 665, all
three occurrences) and the TRAIN_VAL S-count rule (6, was 7).

Throughput (recomputed from `phase3-labels.json` `ms`, post-review): median **3.0s blind (n=300),
1.5s assisted (n=697), 1.8s overall** — unchanged from pre-review, against §7's untested
18s/decision assumption. Correction rate of the engine's suggestion in TRAIN_VAL, post-review:
**96/697 = 13.8%** overall (was 104/697 = 14.9% pre-review — this recomputation folds in the
review pass's own label changes); per-tier breakdown pre-review in ADR-0028 addendum #15
(`diff_brand_similar_title` 38/39 = 97.4%). The new QA report's own "review-mode revisions" count
(**13**, cumulative across every export ever ingested) is a different metric from the 6
label-changing revisions this session — 7 revisions were merged in earlier sessions, 6 more this
one; full detail in `phase3-label-qa-20260922.md` and DECISIONS.md ADR-0028 addendum #17.
Queue frozen, SHA-256 (LF-normalised) `7da125e1856bc65514234d516e17d0a12363ee6ada9b324b3f00ca8bfa146d2a`
— raw-CRLF value `696e983392628b868c4becd92db400735a52498a4994b5b7c8651b160a087011`, still the
constant four other files pin (`scripts/ingest_labels.py`, `scripts/split_annotation_queue.py`,
`tests/test_annotation_split.py`, `tests/test_predict_label_parity.py` — DECISIONS.md ADR-0028
addendum #16 item 2; not the same file changing, two hash conventions of the same unchanged file).
**Caveat:** TRAIN_VAL decisions were faster and less self-consistent than blind ones, so TRAIN_VAL
labels are more engine-shaped than TEST; the headline number comes from the blind TEST set alone.

## Blocked on Bogdan

- **`3f574dad8b6e_b52acad20816_0` needs a real, confirmed re-decision.** It was queued for the
  2026-09-22 review pass but its stored data shows it was never actually touched. It carries a
  known-invalid M→N revision. Open the review tool at
  `tools/annotate.html?review=docs/learned/phase3-relabel-queue.json` and make sure this occurrence
  specifically gets a fresh, deliberate decision — not just that the review screen was opened.
- **The 4 class-d occurrences** (Royal Canin Kitten pairs, all `N`, all genuinely re-examined) are
  a real mechanical-rule violation blocking the freeze. Either they are correct and the `d` rule's
  "trivial_spot_check must be M" assumption needs a documented exception for this specific case, or
  they should be reconsidered. Either way this needs a decision, not another automated pass.
- After both are resolved: re-run `scripts/check_label_rule_consistency.py`, confirm it's clean,
  then `scripts/freeze_labels.py --freeze`.

**This session — final mechanical pass over all 997, nothing relabelled.**
`scripts/check_label_rule_consistency.py` over 997: (a) 2, (b) 0, (c) 0, (d) 4, (e) 3, (f) 6 —
15 flags, 12 distinct occurrences, written to `docs/learned/phase3-relabel-queue.json`. The class
(d) pairs are NOT byte-identical: `classify_tier` only compares brand/line/capacity/pack/bonus, so
`life_stage`/`food_form` differ (None vs value) on them; no field conflicts. 3 of the 4 are also
the 3 self-disagreeing pairs. **Measured fact, not softened as a tier-naming quirk (2026-09-22
correction):** across the full `trivial_spot_check`-class population, blind TEST is **15/15
correct** (0 failures) and assisted TRAIN_VAL is **31/35 correct, 4/35 failed**
(`docs/learned/phase3-eval-view.json`'s `trivial_spot_check`/repeat counts: TEST 2 standalone + 13
repeats = 15, TRAIN_VAL 10 standalone + 25 repeats = 35). All 4 TRAIN_VAL failures are this
session's class (d) flags. Zero failures where the engine showed no suggestion, all four where it
did — an **anchoring effect on the engine's suggestion**, not merely a tier-definition looseness.
The Schesir occurrence `3f574dad8b6e_b52acad20816_0` was revised
M -> N wrongly (rule 1 reads titles, not the `species` field) and is queued for re-decision with
the reason on screen. The dataset-freeze mechanism exists (`scripts/freeze_labels.py`,
`tests/test_labels_frozen.py`) but is NOT frozen. Full detail: DECISIONS.md ADR-0028 addendum #15.

Frozen labels SHA-256: `UNFROZEN`

**The next action is Bogdan's:** run review mode over the 12 queued occurrences
(`tools/annotate.html?review=docs/learned/phase3-relabel-queue.json`), ingest, re-run the checker,
then `uv run python scripts/freeze_labels.py --freeze`. After the freeze no label may change
without a reason recorded here first. Then Phase 3 item 5 (baseline) — model choice in
`docs/phase3-baseline-model-choice.md`. No AI-labelled pair may enter any split.

Phase 3, 2026-09-15 session, in order: built a retrieval evaluation set independent of embeddings
(142 known-positive pairs — 26 browser-verified + 116 plausibility-checked proxy-key collisions),
measured candidate-retrieval recall@20 against it — **69.9% pooled, but the unbiased random-draw
subset alone scores only 26.9%, both below CLAUDE.md's >=90% target** — found and documented the
root cause (Phase 2's own `product_line` strips weight, so same-line-different-weight siblings
embed identically and crowd the true cross-shop match out of retrieval), stopped without tuning
per explicit instruction. Built the three retrieval signals STATE.md's own "what Phase 3 needs"
list (below, now historical) named — `category`, `brand_blocking_key`, and a brand-trust flag
that started as an automated classifier, was found unreliable on real data, and shipped instead
as a small hand-verified list. Wrote the annotation conventions before the tool
(`docs/learned/phase3-annotation-conventions.md`), built the tool (`tools/annotate.html`), and
drew the 1,000-pair queue (444 hard / 519 easy / 37 trivial spot-check) — found and fixed two real
bugs along the way (a URL-based variant-resolution bug in the eval set, a capacity-equality bug
in the queue's own tier classifier), both caught by tracing a specific wrong case, not by
inspection. Full detail: DECISIONS.md ADR-0028. **Stopped for review before any labelling begins.**

Phase 2, 2026-09-14 session, in order: fixed two real bugs the architect review found in
`product_line` (1a brand-span, 1b dangling-token guard — DECISIONS.md ADR-0027), added
conventions 6 and 7, wired `product_line` into `extract()`, committed and scored the
externally-labelled gate sample. **The first accuracy figure (96.6%) was inflated — mostly
both-sides-null agreement — and was corrected twice before anything was tuned against it: first
to labelled-cells-only (95.6%, which cannot see a false positive), then to the symmetric figure
that can — the gate figure, frozen as measured BEFORE any fix: 261/280 = 93.2% (labelled cells
plus false positives, brand excluded), weight parsing 82/82 = 100%; 95.6% kept alongside it as
the recall figure, not the gate number.** `brand` is excluded from the gate figure on principle,
not because its score is weakest — 12 of its 15 mismatches are the gate sample seeing only
`title` text while the extractor correctly prefers the shop's structured brand field, two
different inputs the sample cannot grade either way; brand's own correctness is validated
separately by STEP 1's cross-shop comparability check. The sample's ground truth is also
known-imperfect (0 of 100 rows flagged `ambiguous` — the promised hand-check never ran) and
recorded as a stated limitation, not a defect, since the margin over 85% is wide regardless. Cache
proof run with command output (0 new extractions on a second pass). Four gate-derived fixes then
approved and implemented — `"punguta"` food_form gap (420 titles now, 388 actually fixed by this
change, 32 already correct via unrelated words), a hyphenated-brand-code guard on
`breed_size_code` (M-PETS/L-carnitina, 83 titles checked, 80 fixed), two small `food_form` fixes
(plural "uscate" added, plural "umede" checked and deliberately rejected — 17/17 would have been
false positives on wet wipes, not wet food; "semi-umeda" no longer false-positives as wet), and
the `"creveti"`/shrimp flavour gap (52 titles) — each measured by population coverage, never by
re-scoring the gate sample (that would be tuning on the test set; 93.2%/95.6% stay the frozen,
un-re-measured figures of record). No Phase 1 box ticked this session.
Updated: 2026-09-22

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

Phase 1 — Collection: **CLOSED 2026-09-22** (all gate boxes MET, see below). Gate per CLAUDE.md §7. Checked against git history
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
[x] **≥7 consecutive days of history — MET, re-measured 2026-09-22 against the real database**
    (pg8000 workaround, ADR-0028 addendum #5 — `psycopg` blocked by Application Control). Query:
    `select date(started_at) as day, source, status, count(*) from scrape_runs group by 1, 2, 3
    order by 1, 2` — full, unedited output:
    ```
    2026-09-12,pentruanimale_ro,ok,2
    2026-09-12,petmax_ro,ok,3
    2026-09-13,animax_ro,ok,1
    2026-09-13,pentruanimale_ro,ok,2
    2026-09-13,petmax_ro,ok,2
    2026-09-14,animax_ro,ok,1
    2026-09-14,pentruanimale_ro,ok,1
    2026-09-14,petmax_ro,ok,1
    2026-09-15,animax_ro,ok,1
    2026-09-15,pentruanimale_ro,ok,1
    2026-09-15,petmax_ro,ok,1
    2026-09-16,animax_ro,ok,1
    2026-09-16,pentruanimale_ro,ok,1
    2026-09-16,petmax_ro,ok,1
    2026-09-17,animax_ro,ok,1
    2026-09-17,pentruanimale_ro,ok,1
    2026-09-17,petmax_ro,ok,1
    2026-09-18,animax_ro,ok,1
    2026-09-18,pentruanimale_ro,ok,1
    2026-09-18,petmax_ro,ok,1
    2026-09-19,animax_ro,ok,1
    2026-09-19,pentruanimale_ro,ok,1
    2026-09-19,petmax_ro,ok,1
    2026-09-20,animax_ro,ok,1
    2026-09-20,pentruanimale_ro,ok,1
    2026-09-20,petmax_ro,ok,1
    2026-09-21,animax_ro,ok,1
    2026-09-21,pentruanimale_ro,ok,1
    2026-09-21,petmax_ro,ok,1
    ```
    **STRICT definition** (every in-scope source has ≥1 `status='ok'` run that day): qualifying
    days 09-13 through 09-21, longest consecutive run **9 days, 2026-09-13 → 2026-09-21** —
    clears the ≥7 target. 09-12 fails strict only because animax hadn't been added yet (ADR-0024,
    2026-09-13). **WEAK definition** (at least one source ok that day), reported separately, not
    used to tick this box: 10 days, 2026-09-12 → 2026-09-21 (includes 09-12 since
    petmax/pentruanimale alone ran that day). **Phase 1 gate is now fully met — Phase 1 CLOSED
    2026-09-22.**
[x] **≥400 products on two or more shops — MET, now confirmed by TWO independent verification
    passes, not one.** ADR-0023's own hand-verified sample: point **1,214**, 95% CI **[899,
    1,522]**. A second, independent pass (2026-09-15/16, TASK A — pentruanimale's VTEX Catalog
    API, full SKU-list checks, a different session and a different query method than Q3's manual
    brand-then-scan): corrected rate **23/40 = 57.5%, CI [42.2%, 71.5%]**, applied to the same
    2,334 keyable population — point **1,342**, CI **[985, 1,669]**. **The two estimates
    substantially overlap** (1,214 sits inside the second CI, 1,342 sits inside the first) —
    this is now the best-evidenced gate in the repo, two sessions and two methods agreeing, not
    one measurement standing alone. Full detail: DECISIONS.md ADR-0028 addendum #7 item 4.
    The proxy key itself now
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
externally, code-blind), against `norm_listings` **under `EXTRACTOR_VERSION 2026-09-14-v4`** —
run and recorded *before* the four gate-derived fixes existed. `EXTRACTOR_VERSION 2026-09-14-v5`
(the current code, with those four fixes applied) **has no accuracy figure of its own, by
design** — see "frozen" note further down for why it is never re-measured against this same
sample, and will not have one until a new, independently drawn sample exists.

- **Gate figure: symmetric (labelled cells + false positives), `brand` excluded — 261/280 =
  93.2%.** CLAUDE.md §7 says "attribute accuracy" — an extractor that invents a value on an empty
  cell is not accurate, so the denominator must be able to see that error, not just a miss.
- **Recall figure, kept alongside it, not as the gate number**: labelled cells only (cannot
  penalise a false positive — see DECISIONS.md ADR-0027 addendum #2 for the two real category
  errors this blind spot hid, listing_id 28159 and 28860), `brand` excluded — 261/273 = 95.6%.
- Weight parsing (`net_weight_g`), separately, on its 82 non-empty labels: **82/82 = 100.0%**
  (no false positives on this field, so recall and symmetric agree).
- Reported for transparency, not the gate figure: all-cells 966/1000 = 96.6% (inflated — mostly
  both-sides-null agreement); labelled-cells-with-brand 346/368 = 94.0%; symmetric-with-brand
  346/380 = 91.1%.
- The gate is met on both the 93.2% and 95.6% figures — the substantive conclusion is unchanged;
  only the framing (which one is "the" gate figure) is corrected.
- Cache proof: `scripts/normalize.py` run twice, second pass 0 new extractions out of 10,503
  content hashes (command output in DECISIONS.md ADR-0027 addendum).
- **Labelling-provenance limitation, stated plainly:** the 100 rows were labelled by a code-blind
  model, not a human, and 0 of 100 have the `ambiguous` column flagged (verified this session) —
  the sample README's promised hand-check of flagged rows never ran, since nothing was flagged.
  Recorded as a limitation of the gate, not a defect that invalidates it: the margin over 85% is
  wide under every denominator computed. Full reasoning: DECISIONS.md ADR-0027 addendum #2.

**Why `brand` is excluded from the gate figure — not because its score is weakest.** 12 of
`brand`'s 15 mismatches (89.5% on its own 95 labelled cells) are a labelling-scope artifact: the
gate sample shows the labeller only `title` text, never the shop's own structured brand field
`canonicalize_brand()` deliberately prefers. Two different inputs to the same question — this
sample cannot grade `brand` either way, and it is neither an extractor bug nor a bad label.
`brand`'s own correctness is validated separately, by STEP 1's cross-shop comparability check
(Brit/Calibra/Hill's — same product, different shops, same canonical brand).

**Why 93.2%/95.6%, not the 96.6% first reported or the 90.8% used to approve the fix list.** 96.6%
was scored against all 1,000 cells, and most fields are null on most rows — `dosage_band` alone
contributes 1 real test and 99 free "both sides correctly said nothing" points. 95.6% (labelled
cells only) is closer but structurally cannot see a false positive — a cell where the extractor
invented a value against an empty label is simply excluded from that denominator, no penalty
paid. Two real titles in this sample show the cost: listing_id 28159 ("semi-umeda", label empty,
extractor said "wet") and 28860 ("Turkey Jerky", label empty, extractor said "dry") — both real
category errors, both invisible to 95.6%, the first exactly what fix #3 corrected. The symmetric
figure (93.2%) adds every false-positive cell to the denominator, so it can penalise them; that is
now the gate figure, with 95.6% kept alongside as the recall figure. 90.8% (334/368) was a quick
mental estimate (368 labelled cells minus all 34 mismatches) that double-subtracts: 12 of the 34
mismatches are false positives on an empty label, never part of the 368-cell denominator to begin
with. Both rigorously computed figures are higher than the 90.8% estimate, not lower. Full
reasoning and the reconciliation arithmetic: DECISIONS.md ADR-0027, addendum #2.

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
[x] **85% accuracy gate — MET: 93.2% (261/280, symmetric — labelled cells + false positives,
    brand excluded) — the gate figure; 95.6% (261/273, labelled cells only, cannot see false
    positives) kept alongside it as the recall figure. Weight parsing 100.0% (82/82).**
[x] cache proof — MET, command output in DECISIONS.md ADR-0027 addendum.
[x] **four gate-derived fixes approved and implemented** (`"punguta"` food_form, M-PETS/
    L-carnitina breed_size false positives, two small food_form fixes, `"creveti"`/shrimp
    flavour), each measured by population coverage before/after — never by re-scoring the gate
    sample. Details and every number: DECISIONS.md ADR-0027 addendum #2.

## What Phase 3 will need from Phase 2's output that doesn't exist yet (historical — written 2026-09-14, before Phase 3 opened)

Grounded in what that session actually saw in the data, not the plan's description. Status as of
the 2026-09-15 Phase 3 session, item by item:

- **A category signal** (food vs. accessory vs. litter vs. toy) — **BUILT.**
  `normalize/category.py`, `norm_listings.category` (migration 0007). See the Phase 3 gate
  section below for the population breakdown.
- **`product_line`'s own accuracy measurement.** **STILL OPEN, not addressed this session** —
  Phase 3's own annotation queue (below) implicitly exercises `product_line` as part of the tier
  classifier and the attribute-comparison table the annotator sees, but no dedicated accuracy
  figure for the field itself was produced. Stays a real gap.
- **A brand-trustworthiness signal.** **BUILT, with a correction.** An automated statistical
  approach was tried and rejected as unreliable (real manufacturers like Chicopee and Dolina
  Noteci score identically to confirmed distributor codes on title-overlap rate). Shipped as a
  small hand-verified list instead: `"opti"` (confirmed) and `"ipts"` (weaker evidence, flagged as
  such). **`"Record"`, named here as an example of a distributor code, was checked this session
  and found to be a real manufacturer** — this line's own example was wrong; corrected in
  DECISIONS.md ADR-0028, not silently dropped.
- **Hyphen/spacing-normalized brand keys.** **BUILT.** `brand_blocking_key()`, grounded in 5 real
  collisions found among today's canonical brand values (not the Julius K-9 case this line
  named — that one turned out to already canonicalize identically via the existing alias, checked
  this session; the real collisions found were different brands entirely — `"club 4 paws"`,
  `"cat's best"`, `"my love"`, `"lolopets"`, `"dr. clauder's"`).
- **The still-open EN breed-size vocabulary gap** (`"Small"`/`"Medium"`/`"Large"`/`"Giant"`/`"Toy
  Breed"`, `"kitten"`) — **STILL OPEN, not addressed this session.** Stays exactly the risk this
  line described.

## Phase 3 — Matching: opened 2026-09-15, prerequisites only

CLAUDE.md §7 gate for this phase: candidate retrieval recall@20 >=90%, an annotation tool and
1,000-pair dataset, a baseline, a fine-tuned model, a serving benchmark. **This session built only
through the queue — no baseline, no fine-tuning, no annotation run.** Full detail and every
number: DECISIONS.md ADR-0028.

[x] STEP 1 — retrieval evaluation set independent of embeddings
    (`scripts/build_retrieval_eval_set.py`, `docs/learned/phase3-retrieval-eval-set.csv`). 142
    known-positive pairs: 26 browser-verified (`q3-verification.md`, ADR-0023) + 116 of 120
    plausibility-checked proxy-key collisions (4 rejected — 3 life-stage variants, 1 uncertain).
[x] STEP 2 — candidate retrieval built and measured
    (`scripts/build_embeddings.py`, `scripts/measure_recall_at_20.py`). `sentence-transformers`
    (local, free) + pgvector IVFFlat, migration 0006. **recall@20 = 95/136 = 69.9%, 95% CI
    [61.7%, 76.9%] — BELOW the >=90% target.** Per-source: proxy_key_collision 80.0%,
    q3_browser_verified (unbiased) only 26.9%, CI [13.7%, 46.1%]. Root cause found and documented
    (product_line strips weight -> same-line-different-weight siblings embed identically and
    crowd out the true cross-shop match) — **not tuned this session, per explicit instruction.**
[x] STEP 3 — three retrieval signals (`normalize/category.py`, `normalize/brand.py`,
    migration 0007, `scripts/backfill_phase3_signals.py`). category: food 8,601 / accessory
    1,550 / litter 202 / toy 177 / unknown 2. brand_blocking_key built. brand-trust: automated
    approach rejected as unreliable (checked, not assumed); small hand-verified list shipped
    instead (`"opti"` confirmed, `"ipts"` weaker evidence).
[x] STEP 4 — `docs/learned/phase3-annotation-conventions.md`, written before the tool. Ten
    numbered rules plus five named gaps the rules don't yet cover (defaulted to `S`, not guessed).
[x] STEP 5 — `tools/annotate.html`, single local HTML page, keyboard-driven (M/N/S/U/F).
    Attribute diff table, token-level title diff, always-visible rubric sidebar, localStorage
    autosave/resume, self-agreement spot-check support, never shows a model prediction. Verified
    by syntax-checking the extracted script and running its core functions (diff, seeded shuffle)
    against the real queue in Node — not opened in a live browser (extension unavailable this
    session), no annotation decision made.
[x] STEP 6 — the queue (`scripts/build_annotation_queue.py`,
    `docs/learned/phase3-annotation-queue.json`). **1,000 pairs: hard 444 (44.4%), easy 519
    (51.9%), trivial spot-check 37 (3.7%).** Two real bugs found and fixed while building this
    (a URL-based variant-resolution bug reused from STEP 1's own fix; a capacity-equality bug in
    the tier classifier that hid nearly every trivial pair) — both caught by tracing one specific
    wrong case, not by inspection. Estimated wall-clock at 200 pairs/hour: **5.0 hours.**
    **Superseded same day — see the addendum immediately below; STEP 6's own file and numbers
    stay here as the historical record of what was built and audited, not erased.**

**ADR-0028 addendum, same-day architect-audit response (2026-09-15) — corrects STEP 2's
denominator and rebuilds STEP 6's queue. Full detail: DECISIONS.md.**
**A second same-day audit found the 12.5% figure below and the "41.0% expected positives" figure
below were each wrong in a different way — corrected in the addendum #2 block further down. Left
here as the historical record of what this addendum first reported, not erased.**
- TASK 1: recall denominator corrected and explained (95/136, not 95/142 — 6 skipped pairs are
  cross-shop listings whose titles collapse to ONE `norm_listings` row, ADR-0026). Found **15**
  such multi-source content_hash rows in the full population — the easiest class of true
  cross-shop match in the dataset, currently invisible to retrieval and the queue alike. How to
  surface them: proposed, not implemented (a data-model question).
- TASK 2: embedding text now carries weight/pack/life_stage/breed_size (a); candidate generation
  blocks on `brand_blocking_key` before ranking (b). **recall@20, headline (q3_browser_verified):
  26.9% -> 42.3% (a alone) -> 57.7% (a+b) -> 64.5% on the extended eval set (n=31, CI [46.9%,
  78.9%]).** Pooled figure clears 90% (90.8%) but the headline stays below the >=90% gate target
  — reported, not tuned further.
[ ] STEP 1/2 eval set extension (TASK 3) — grew from n=26 to **n=31** browser-verified positives
    (target was >=100). 40 of a planned 150 new draws completed this session; 12.5% hit rate (vs.
    the original 54%) made the full 150 impractical in one session — stopped and reported plainly,
    not padded. Detail: `docs/learned/q3-verification-extension-2026-09-15.md`.
[x] STEP 6 rebuilt (TASK 4) — `scripts/build_annotation_queue.py` rewritten, not amended. **997
    pairs, quota-sourced: 41.0% expected positives (proxy-key collisions + capacity-matched
    blocked retrieval), capacity_differs capped at 28.6% (was 89.4%), four required negative
    sub-classes each with their own targeted query, within-shop hard negatives included (0% ->
    7.6%).** New permanent guard: refuses to write the queue if any single deterministic feature
    (capacity/flavour/brand equality) decides >40% of it — validated against the OLD queue (would
    have refused it: capacity_differs = 89.4%, reproducing the audit's own figure exactly) and the
    new one (passes: 29.4% / 13.5% / 5.5%). `reformulation_approx` found to be genuinely empty in
    the collected catalogue (zero title matches any reformulation marker, checked directly) —
    reported as a finding, not padded with a loosened query. Estimated wall-clock unchanged: 5.0
    hours.

**ADR-0028 addendum #2, second same-day architect audit (2026-09-15). Full detail: DECISIONS.md.**
- TASK A: the 12.5% "not found" rate above is **RETRACTED** as a market-overlap estimate — it was
  a search-method artifact (re-checking 10 "not found" rows with a shorter query found 0 new
  matches but two concrete cases of the original query missing a product that genuinely exists,
  once even under nearly its exact name). **ADR-0023's Phase 1 overlap gate is confirmed NOT at
  risk.**
  **Reopened and re-closed, third session, same day (2026-09-15) — full SKU-list enumeration
  overturns 6 of the 7 "brand+line found, weight mismatched" rows.** The 10-row recheck above
  never enumerated each product's *complete* variant list, only the default/shown one — the exact
  `_resolve_variant` failure mode this project already hit once. Re-checked all 7 rows where the
  short query found brand+line, this time via pentruanimale's own public VTEX Catalog API (full
  SKU list per product, not scraping infra — Chrome extension unavailable this session). **6 of 7
  have the petmax weight in their full SKU list and are genuine confirmed matches**, missed by both
  prior passes (Brit Care Hypoallergenic L-XL 3kg, Advance Sensitive Mini 7kg, Calibra Cat Life
  Herring 1.5kg, Primordial Holistic Ton&Miel 12kg, Calibra Dog Life Senior Small Breed Miel 1.5kg,
  Hill's SP Perfect Digestion Small&Mini 3kg). Only 1 of 7 (Hill's SP Feline Sterilised Salmon,
  dry) is a genuine non-match — dry Salmon doesn't exist on pentruanimale at any weight, only as a
  wet 85g pouch. **Recount: 11/40 = 27.5%** (up from 12.5%), Wilson CI [16.1%, 42.8%]. Applied to
  N=2,334 with the same simplified arithmetic as before: point 642, CI [376, 1,000] (vs. 12.5%'s
  point 292, CI [127, 609]).
  **Conclusion — form (a), at its real strength: 27.5% is a FLOOR, and the true rate is bounded,
  not pinned.** Only 10 of the 35 "not found" rows have ever been rechecked against a full SKU
  list, and 6 of those 10 flipped to confirmed — a 60% recovery rate on that rechecked subsample.
  **The true rate plausibly lies between 27.5% (the floor, everything actually measured) and
  ~65% (26/40 — if the 60% recovery rate held across the 25 still-unrechecked rows: 25×0.60≈15,
  +5 original +6 already confirmed = 26).** That extrapolation is optimistic, not a second
  measurement — the 10 rechecked rows were not a random draw from the 35, so projecting their
  rate onto the other 25 is an assumption, stated as one. **Q3's original 54% sits comfortably
  inside that [27.5%, 65%] band**, which is the actual resolution: the acute, specific
  contradiction (12.5%, whose CI included a point below the 400 threshold) is retracted for
  cause and replaced by a band that contains Q3's estimate rather than conflicting with it.
  **What would close this completely**: rechecking the remaining 25 "not found" rows the same
  way — mechanical and fast now (the VTEX Catalog API lookup used for the 7 confirmed rows took
  seconds per product, not the multi-call browser navigation the original checks used), not done
  this session because it wasn't asked for.
  **The Phase 1 gate is genuinely unaffected** — it was never re-measured by this exercise; it
  remains ADR-0023's own p̂=0.52 (n=50), point 1,214, CI [899, 1,522], untouched. Full detail:
  `docs/learned/q3-verification-extension-2026-09-15.md` addendum #2.
- TASK B: `build_annotation_queue.py`'s "41.0% expected positives" (a source-tier label, not a
  prediction) is replaced by a **predicted M/N/S distribution** from a deterministic rules engine
  applying the annotation conventions to every pair: **M-plausible ~31%** (over the 25% floor),
  N-by-rule ~55%, S-likely ~13%.
- TASK C: the eval-set extension (n=26->31) is **CONTAMINATED** — its query shared signal with
  TASK 2(a)'s new embedding text, so it preferentially found pairs the retriever can already find
  (all 5 new pairs were hits, ~6.4% probability under the prior rate). **Headline recall@20 is
  57.7% (15/26, n=26), not 64.5%** — the extended figure is now reported separately and labelled
  contaminated, in both the docs and `measure_recall_at_20.py`'s own output.
- TASK D: `tools/annotate.html` gained a configurable 100-pair pilot stop (observed M/N/S,
  S-reason tally, median decision time, before requiring "continue"). Caught a real bug while
  building it: the display order concatenated tiers alphabetically, so a pilot's first 100 pairs
  would have been 100% one tier — fixed (proportional interleaving) and re-verified against the
  real queue (every tier within ±0.5pp of its full-queue share in the first 100).

**2026-09-17 session (fifth candidate-retrieval session) — retrieval closed, queue rebuilt and
FROZEN, assisted annotation flow built. Full detail: DECISIONS.md ADR-0028 addenda #8-#9.**

1. **Retrieval closed.** Proved `build_embeddings.py` itself (not an uncommitted scratch script)
   now reproduces the vectors the 88% figure was measured on — genuine `SentenceTransformer`,
   imported here via a generalised sklearn-import stub, verified bit-identical to the stored
   vectors on 20 real rows (cosine 1.000000), then actually re-run (`--force`, all 10,532 rows)
   and re-measured: **44/50 = 88.0%, CI [76.2%, 94.4%] — unchanged.**
   `docs/learned/phase3-embedding-equivalence-2026-09-17.md`.
2. **Gate figure reframed as a measurement-power finding.** 88% and the >=90% target are not
   distinguishable at n=50 (target sits inside the CI) — not "gate met," not "gate missed."
   Resolving it needs ~1,000 verified positive pairs (~27,000 draws at this project's observed
   rate) — out of reach; not pursued further. ADR-0028 addendum #8 corrects addendum #7's "MISSED"
   language accordingly. The K=20/K=100 re-ranking decision (addendum #7 item 3) stays PROPOSED —
   still blocked on the section-7 serving benchmark, which doesn't exist yet.
3. **Queue rebuilt once more, then FROZEN** — no further rebuild without a stated reason recorded
   here first (same discipline as the Phase 2 gate figure). 997 pairs (959 distinct pair_ids).
   Guard: capacity_differs 29.4%, flavour_differs 11.4%, brand_differs 5.7% (all under the 40%
   limit). Forecast (persisted in the JSON): M-plausible 30.7%, N-by-rule 55.6%, S-likely 13.7%.
   **469 of the previous queue's 959 pairs (48.9%) survive** into this rebuild; **47 of
   `phase3-pilot100-ai-reference-pass.json`'s 99 distinct pairs (47.5%) survive** — any comparison
   to that reference pass is on this 47-pair intersection only. ADR-0028 addendum #9.
4. **Assisted annotation flow built — no annotation run started.** `scripts/split_annotation_queue.py`
   (new, additive — reads the frozen queue read-only, never rewrites it) computes a PRODUCT-LEVEL
   TEST/TRAIN_VAL split via connected components over the queue's own pairs (no ground-truth
   product id exists; two listings connected by any queue pair are, by construction, candidates
   for the same identity) — verified 0 content_hash overlap between splits. One 281-pair component
   (28.2% of the queue) was excluded from TEST eligibility (cap: no component may supply >30% of
   the TEST target) so the headline test set isn't ~94% one product family.
   **TEST: 300 pairs / 262 listings, BLIND — no engine suggestion, ever, enforced three
   independent ways** (merge-time nulling, the split file structurally omitting the field for
   TEST, and an explicit split-check in the render/confirm code). **TRAIN_VAL: 697 pairs / 891
   listings, ASSISTED** — the deterministic rules engine's prediction is shown as a suggestion,
   `C` (Confirm — a key deliberately distinct from `M`/`N`/`S`, so pressing M/N/S is always an
   independent judgement, never miscounted as a confirmation) accepts it, `M`/`N`/`S` overrides
   it. Per-pair record gained `source` (blind/override/confirm) and `corrected`. End-of-run report
   (`tools/annotate.html`'s done-screen) computes correction rate overall and per tier, plus
   median decision time confirmed vs. corrected. Verified via `node --check` (syntax) and a
   DOM-free simulation driving the real `decide()`/`confirmSuggestion()`/`assistedFlowReport()`
   functions on 4 synthetic pairs — output matched the expected classification exactly (no browser
   available this session). Full detail, including a real bug found and fixed while porting the
   rules ladder (frozen queue's `listing_dict()` never persists `category` per-pair — worked
   around, sanity-checked against the frozen queue's own forecast, exact match on all 997 pairs):
   DECISIONS.md ADR-0028 addendum #10.

[ ] Baseline (classical cross-encoder) — not started.
[x] 997 pairs annotated by Bogdan — M 354 / N 634 / S 9 (post-review, 2026-09-22; was M 359 / N 628
    / S 10 pre-review); TEST 300 blind, TRAIN_VAL 697 assisted.
    [x] review pass over the 12 flagged occurrences RAN 2026-09-22 — 11/12 genuinely re-decided, 6
        labels moved. [ ] NOT complete: `3f574dad8b6e_b52acad20816_0` was queued but never actually
        re-examined (no 2026-09-22 timestamp) and needs the annotator's explicit attention; 4
        class-d occurrences still block the freeze. Dataset freeze still pending — see "Blocked on
        Bogdan" at the top of this file and DECISIONS.md ADR-0028 addendum #17.
[ ] Fine-tuned matcher — not started.
[ ] Serving benchmark (CPU-quantized vs. cross-encoder vs. hosted API) — not started.

**ADR-0028 addendum #4 (2026-09-15, fourth same-day session) — response to a 100-pair AI
reference labelling pass (`docs/learned/phase3-pilot100-ai-reference-pass.json`, NOT human
labels — see the record-keeping note below). Observed M 36 / N 62 / S 2 vs. the forecast's M 33 /
N 53 / S 14, agreement 80/100. Full detail:
`docs/learned/phase3-reference-pass-response-2026-09-15.md`. No annotation run started.**

- **Finding 4 — species (dog/cat) signal, built.** `normalize/species.py`, backfilled into a new
  `norm_listings.species` column (migration 0008). Structured signal (petmax URL segment, animax
  `product_type`) + checked title-keyword fallback + a checked structural default (this
  catalogue's litter is exclusively cat litter). In-scope population: dog 4,888 (55.5%), cat
  3,791 (43.1%), unknown 124 (1.4%, two honest checked classes — species-word-less dog dental
  chews, and genuine dual-species products). New `predict_label()` rule: species differs (both
  known) -> N, ahead of quantity. **Cross-species pairs were NOT removed from the queue — kept
  deliberately as a small, cheap easy-negative class, same reasoning as `trivial_spot_check`'s
  50-pair (5.0%) self-agreement slice.** Current count: **49/997 (4.9%)**, against a proposed
  quota of **~2% (≈20 pairs)** — lower than the other required hard-negative sub-classes (4.7%-
  6.6% each) because species is cheaper/more certain to decide than any of them. 4.9% sits above
  the proposed 2% cap — reported for a future queue rebuild's quota tuning, not acted on.
- **Finding 5 — breed-size vocabulary canonicalised.** Full census printed first (18 distinct
  `breed_size_code` values). Equivalence built two independent ways (pentruanimale's own
  word+code co-occurring in one title; a cross-shop same-product join), not assumed from the
  task's own two examples. Modelled as a rank interval (`breed_size_rank`/`breed_size_class`/
  `breed_size_overlaps`, `attributes.py`), not a flat bucket — resolves "Medium"="M" (pilot 12)
  and "Mini"="XS-S" (pilot 55) by rank overlap, not string equality. `predict_label()` rule 3
  updated to use it.
- **Finding 6 — "XS-XL" nulled.** Checked, not assumed: 100% of 985 in-scope occurrences are
  pentruanimale_ro (0 from the other two sources), the single largest `breed_size_code` value in
  the population — a boilerplate "fits any size" default, not a real claim. `extract_breed_size`
  now returns `None` for it; 985 rows changed on re-extraction.
- **Finding 7 — age qualifiers ("(5+)"/"7+"/"8+") now reach `life_stage`.** Checked against all 97
  in-scope titles carrying a bare `\d+\+` token before trusting the pattern — a real
  false-positive class (bonus-weight phrases, "10+2kg GRATUIT") excluded by requiring the `+` NOT
  be followed by another digit. 38 rows gained a qualifier (`"adult"` -> `"adult+7"`) on
  re-extraction; a bare qualifier with no life-stage word to attach to stays `None`, an honest
  open gap.
- **Finding 8 — Rule 0 leak, root cause found and fixed at the source.** Pilot 86's `category`
  was correctly `"accessory"` all along — the bug was that none of the 9 source SQL queries in
  `build_annotation_queue.py` ever filtered on `category`; rule 0 caught it downstream (scored
  `S`), which is why it read as a forecast label, not a visible defect. Fixed: `main()` now
  applies `in_scope_only()` (category in food/litter, both sides) to every pool before the
  cross/within-shop split. **Verified against the rebuilt queue: 0 of 1,157 distinct listings
  carry a non-food category** (was previously unverified/leaking).
- **Re-run forecast vs. observed — corrected after a same-day review found the first comparison
  invalid.** The rebuilt queue is substantially a DIFFERENT DRAW from the queue the 100-pair pilot
  was drawn from (the fixes above change which rows the source SQL joins match) — measured
  directly: **only 44 of the pilot's 100 pair_ids still exist in the rebuilt queue.** Comparing
  the rebuilt queue's whole-queue forecast (n=997) against the pilot's observed distribution
  (n=100) was therefore comparing two different populations; that comparison, and its "gap
  narrowed to ~4.2pp" claim, is retracted. **Corrected comparison, on the n=44 intersection only,
  before vs. after this session's fixes, same 44 pairs both times:**

  | | BEFORE (n=44) | **AFTER (n=44)** | OBSERVED (n=44) |
  |---|---:|---:|---:|
  | M | 27 (61.4%) | **23 (52.3%)** | 26 (59.1%) |
  | N | 10 (22.7%) | **14 (31.8%)** | 17 (38.6%) |
  | S | 7 (15.9%) | **7 (15.9%)** | 1 (2.3%) |
  | agreement | 34/44 = 77.3% | **35/44 = 79.5%** | — |

  n=44 is small — directional, not precise. N moved toward observed (gap 15.9pp -> 6.8pp). **M
  moved slightly away** (gap 2.3pp -> 6.8pp, opposite the naive whole-queue read, possibly noise
  at this n). **S did not move at all** (7 pairs both times) **vs. observed 1** — finding 6's
  hypothesis is confirmed only partial: XS-XL nulling removed the one-sidedness IT was
  manufacturing, but `one_sided_attribute` (81 of the whole queue's 120 S pairs) is still
  dominated by other one-sided flavour/life-stage cases plus 39 `ambiguous_brand_rule6` pairs the
  ladder deliberately never auto-resolves — a structural property of the ladder's conservatism,
  not fixed by loosening a rule to chase observed 2% (forbidden by instruction). The whole-queue
  forecast (M 30.2-30.3% / N 57.8-58.0% / S 11.7-12.0%, n=997) remains a legitimate description of
  the current queue's own composition, just not comparable to the pilot's 100 pairs.
- **Species promoted to Rule 1 of the annotation conventions (revision 3).** A follow-up review
  asked for the species check to be named in `phase3-annotation-conventions.md`'s ladder, not
  only in code — added as the new Rule 1 (ahead of quantity), revision 2's rules 1-8 renumbered to
  2-9. `predict_label()`'s rule tags renamed to match (a pure rename, no logic change — the M/N/S
  totals shift by 1-3 pairs run-to-run regardless, from Python's default per-process string-hash
  randomisation affecting `set`/`dict` iteration order upstream of the seeded shuffle; a minor,
  unfixed reproducibility gap, not a behaviour change from this rename).
- **Record-keeping (Block 3, this session):** the planned human blind-subset pass was **NOT
  run** — the 100-pair pilot distribution above is AI-labelled only. Two things remain genuinely
  unmeasured: the annotator's real throughput (CLAUDE.md §7 assumes 200 pairs/hour; untested —
  the full run may take 5 hours or 12) and the human S rate. CLAUDE.md §7's requirement — "the
  user annotates 800-1,000 pairs manually... it is not generated, it is labelled" — is **still
  unmet**. **No AI-labelled pair may enter the train/val/test split.** The M/N/S forecast now
  lives inside `phase3-annotation-queue.json` itself (`predicted_label_forecast`), not only in
  console output, and `blocked_retrieval_candidate`'s anchor draw is now seeded (`setseed()`,
  derived from `RNG_SEED`) — the queue is reproducible byte-for-byte from its seed, which it was
  not before this session.

## Last done (2026-09-15 addendum session, in order)

1. Committed the previous session's uncommitted work as-is (STEP 4/5/6, ADR-0028) plus a
   mid-session sync of `phase3-annotation-conventions.md` to revision 2 (written externally by an
   architect session while this one was working — re-read from disk, not reconstructed).
2. TASK 1 — corrected the recall denominator's docstring, listed and explained the 6 skipped
   same-content_hash pairs, found and reported the 15-row multi-source content_hash population.
3. TASK 2 — embedding text now carries weight/pack/life_stage/breed_size; candidate retrieval
   blocks on `brand_blocking_key`. Headline recall@20 26.9% -> 64.5% (still below the 90% target).
4. TASK 3 — extended the browser-verified eval set from n=26 to n=31 (target >=100, not reached —
   reported plainly with the reason: 12.5% hit rate this session vs. 54% originally).
5. TASK 4 — rebuilt `build_annotation_queue.py` from named, quota'd sources; added the permanent
   single-feature-dominance guard; validated it against both the old queue (would refuse: 89.4%)
   and the new one (passes: 29.4%/13.5%/5.5%). New queue: 997 pairs, 41.0% expected positives.
6. (Addendum #2, same day) TASK A — retracted the 12.5% figure as a search-method artifact after
   re-checking 10 "not found" rows with a shorter query (0 new matches, but two concrete cases of
   the original query missing a genuinely-existing product). Confirmed the Phase 1 gate is safe.
7. TASK B — added a deterministic rules-engine forecast (predicted M/N/S) to the queue builder,
   replacing the source-tier "expected positives" claim; renamed `blocked_retrieval_positive` to
   `blocked_retrieval_candidate`. M-plausible ~31%, no rebalance needed.
8. TASK C — found and corrected the eval-set extension's contamination (shared query signal with
   the new embedding text); headline recall@20 corrected to 57.7% (n=26), extended figure (64.5%,
   n=31) kept but explicitly labelled contaminated, in both docs and the script's own output.
9. TASK D — built a configurable pilot stop for `tools/annotate.html`; found and fixed a real
   ordering bug (tiers concatenated alphabetically, not interleaved) caught while verifying the
   pilot slice would actually be representative — it was not, until fixed.

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
   (96.6%, all-cells) was inflated; corrected twice — to 95.6% (labelled cells only, cannot see a
   false positive), then to **93.2% (261/280, symmetric, brand excluded) — the gate figure**,
   100% weight parsing (82/82) — before any fix, and both frozen at those numbers. Cache proof run
   with command output. STEP 5 fix list proposed (15 named failure
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

- **Flagged 2026-09-21 (ADR-0028 addendum #13, TASK 5): `species` field disagrees with its own
  title on 53/10,532 `norm_listings` rows (0.50%)** — 46 `animax_ro`, 7 `petmax_ro`, 0
  `pentruanimale_ro` (structurally impossible there — see below). A `normalize/species.py`
  extraction defect, found by `scripts/check_label_rule_consistency.py`'s class (e) on the 300-row
  TEST label set (1 instance, `3f574dad8b6e...`) and then measured over the whole population by
  `scripts/measure_species_field_mismatch.py`. Every mismatch is a case where `animax_ro`'s
  `raw_payload["product_type"]` or `petmax_ro`'s URL path segment (the STRUCTURED per-source
  signal `classify_species()` trusts ahead of the title) disagreed with what the title itself
  says; `pentruanimale_ro` has no structured signal at all, so its stored field IS the title
  keyword test and can never disagree with it by construction. **Not fixed this session — Phase 2
  is closed, this is a recorded finding, not a reopening.** Full detail, methodology and examples:
  `docs/learned/phase3-species-field-mismatch-20260921.md`. Matters most for Phase 3's rule 1
  (species-differs): a wrong `species` field can silently suppress a real cross-species `N` the
  annotator would have caught reading the actual title, and worth reconsidering before Phase 3
  fine-tuning leans on the field again — but no evidence yet that it changed any of the 300 TEST
  labels themselves (the one overlapping instance was already correctly labelled `M` by the
  annotator, reading the real title, not the wrong field).
- **Flagged 2026-09-17: `sentence-transformers` is the second library this machine's Windows
  Application Control policy blocks outright (after `psycopg`, flagged earlier).** Worked around
  for a plain embedding forward pass this session (`transformers` directly + a `sklearn` stub —
  see DECISIONS.md ADR-0028 addendum #7 item 1). **That workaround does not extend to Phase 3 item
  6 (LoRA/QLoRA fine-tuning)** — training needs the real, full `torch` + `transformers` + `peft`
  dependency chain (optimizers, schedulers, mixed precision), most of which routes through the
  same blocked compiled extensions somewhere a `sys.modules` stub can't reach. `torch` and
  `transformers` import cleanly here (checked); `peft` not yet checked. **The fine-tuning step is
  planned for a hosted GPU notebook, not this local environment — flagged now, before the week-5
  fine-tuning decision, not discovered on the day.**
- **CLOSED 2026-09-13: Hill's "PD" token, checked and added** — 0 newly quarantined (all 8
  matches were already caught by animax's `product_type` signal); defense-in-depth for the other
  two sources going forward. See "Last done" above.
- **CLOSED 2026-09-14: Phase 2 gate sample labelled and scored, gate MET and CLOSED.** Labelled
  externally (by a model with no visibility into this repo's code, so never tuned against),
  committed as `docs/learned/phase2-gate-sample-labeled.csv`, scored by
  `scripts/measure_gate.py`: **gate figure 93.2% (261/280, symmetric — labelled cells + false
  positives, brand excluded), 95.6% kept alongside as the recall figure, 100% weight parsing
  (82/82)** — the 96.6% first computed was the inflated all-cells figure, and the 95.6%
  labelled-cells figure that replaced it structurally cannot see a false positive; both corrected
  before anything was tuned against them (DECISIONS.md ADR-0027 addendum #2 has the full
  reconciliation). These figures are frozen, taken before the four gate-derived fixes below, and not
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

Phase 3 prerequisites (STEP 1-6, ADR-0028) are built and committed. Two same-day architect audits
found and fixed real problems (ADR-0028 addendum, then addendum #2, both 2026-09-15) — full detail
in DECISIONS.md. **Still stopped for review before any labelling begins**, per explicit
instruction. Bogdan needs to review, in particular:

- **Retrieval is now considered done — no further tuning.** Headline recall@20 (2026-09-17
  session): **88% (44/50), Wilson 95% CI [76.2%, 94.4%].** **This is a measurement-power finding,
  not a pass or a fail: at n=50, 88% and the >=90% target are not statistically distinguishable —
  the target sits inside the interval.** Write it exactly this way, not as "gate met" and not as
  "gate missed" (that would claim a difference the sample cannot establish): the point estimate
  sits below target, and the gap between 88% and 90% is smaller than this measurement's own noise.
  **Closing that question would need roughly 1,000 verified positive pairs** (a ±2pp Wilson
  half-width at p≈0.9) — at this project's observed rate of ~27 draws per usable verified pair
  (`phase3-retrieval-improvement-2026-09-16.md`, BLOCK 1b), that is on the order of 27,000 draws,
  out of reach for this project. The number is not being chased further; the queue is frozen
  instead (below) and annotation proceeds on the retrieval this session produced.
  Grown/improved across three same-week sessions: 57.7% (15/26) -> 66.0%/72.0% dense/fused (n=50,
  eval set grown via pentruanimale's VTEX Catalog API, query independent of the embedding input)
  -> **74.0%/88.0% dense/fused** after a per-field audit of the embedding text found
  `breed_size_code` was still the RAW token (not the canonical `breed_size_class` built two
  sessions ago) and `flavour` — already EN/RO-canonicalised by Phase 2 — was missing from the
  embedding text entirely. Both fixed, all 10,532 rows re-embedded.
  **Provenance, corrected this session**: the vectors behind this figure were first produced by an
  uncommitted scratch script (worked around `sentence-transformers` being blocked in this sandbox
  via `transformers` directly + a `sklearn` stub), which meant `build_embeddings.py` itself did
  not demonstrably produce what was measured. Proved equivalence on 20 real rows first — genuine
  `SentenceTransformer.encode()` (imported here via a generalised version of the same stub, which
  turns out to let the REAL library run, not just a manual reimplementation) vs. the stored
  vectors: cosine 1.000000, max abs diff ~1e-7 (pgvector float32 round-trip noise) — identical.
  Then fixed `build_embeddings.py` itself to use that same stub as a fallback (tries the normal
  import first; only on this sandbox's ImportError does it install the stub — unchanged behaviour
  on Bogdan's own machine or the deployment VPS), re-ran it for real (`--force`, all 10,532 rows,
  genuine model, real weights), and re-measured: **44/50 = 88.0%, CI [76.2%, 94.4%] — identical.**
  Full detail: `docs/learned/phase3-embedding-equivalence-2026-09-17.md`.
  **The predicted shrink in EN/RO-flavour-crossing misses mostly did NOT happen (5/17 -> 4/13)**
  even though the underlying data-level fix demonstrably worked (flavour matches on both sides of
  all 4 remaining cases, checked directly) — those 4 pairs now miss for a different reason (general
  `product_line` phrasing divergence in large crowded brand families), reported as a finding, not
  smoothed into a round success number. K-sweep still shows blocked recall reaching 96% by K=100
  (up from 94%) — **a within-block re-ranking fix (the Phase 3 matching model itself) stays
  PROPOSED ONLY (DECISIONS.md ADR-0028 addendum #7 item 3) — not decidable now, since what prices
  it is the section-7 serving benchmark, which does not exist yet.** No decision needed from
  Bogdan to proceed with annotation; this is recorded for when the serving benchmark exists.
  **Structural limitation of the eval set, recorded (not previously written down): all 50 pairs
  were found by a brand-root query, and blocked retrieval blocks on brand.** Checked directly: 0
  of the 50 pairs' listings are flagged `brand_is_distributor_code` or have a null
  `brand_blocking_key` — every recall figure above (66% through 88%) is **recall on brand-aligned
  pairs only**; the fallback path blocked retrieval uses for brand-misaligned/distributor-code
  listings has never been exercised by any measurement in this project. Not a defect introduced
  this session — Q3's own original method was brand-anchored too, so every pair inherits it.
  Full detail on all of the above: `docs/learned/phase3-retrieval-improvement-2026-09-16.md`,
  DECISIONS.md ADR-0028 addendum #7.
  TASK A (the Q3-vs-12.5%-vs-27.5% question) is fully closed: all 35 "not found" rows from the
  extension have been rechecked against a full SKU list, giving a corrected 40-row rate of
  **57.5% (23/40), CI [42.2%, 71.5%] — reconciles cleanly with Q3's original 54%**, and now serves
  as the Phase 1 overlap gate's second independent confirmation (see the gate checklist above).
- **The annotation queue is now FROZEN (2026-09-17, ADR-0028 addendum #9) — no further rebuild
  without a stated reason recorded here first.** Final numbers: 997 pairs (959 distinct
  pair_ids), guard passed (capacity_differs 29.4%, flavour_differs 11.4%, brand_differs 5.7%, all
  under the 40% limit), forecast M-plausible 30.7% / N-by-rule 55.6% / S-likely 13.7% (persisted
  inside the queue JSON itself). 469 of the previous queue's 959 pairs (48.9%) and 47 of the
  100-pair AI reference pass's 99 distinct pairs (47.5%) survive into this final draw.
- **Product-level TEST/TRAIN_VAL split + assisted annotation flow built (2026-09-17, ADR-0028
  addendum #10) — no annotation run started.** TEST: 300 pairs / 262 listings, BLIND (no
  suggestion, ever, enforced three independent ways). TRAIN_VAL: 697 pairs / 891 listings,
  ASSISTED (rules-engine suggestion shown, `C` to confirm, `M`/`N`/`S` to override — pressing
  M/N/S is always an independent judgement, never counted as a confirmation). Split is by
  connected component over the queue's own pairs (no ground-truth product id exists), so no
  listing can appear in both splits — verified, 0 overlap. Full detail: DECISIONS.md ADR-0028
  addendum #10.
- `tools/annotate.html` now also supports a configurable 100-pair pilot stop (reports observed
  M/N/S, S-reasons, median decision time before requiring an explicit "continue"). Building it
  caught a real bug: the display order concatenated tiers alphabetically rather than interleaving
  them, so the first 100 pairs would have been 100% one tier — fixed and re-verified against the
  real queue (every tier now within ±0.5pp of its full-queue share in the first 100).

Nothing is asked of him beyond reviewing before labelling starts — no architecture question is
open. When he's ready: `python -m http.server` from the repo root, then
`http://localhost:8000/tools/annotate.html`.

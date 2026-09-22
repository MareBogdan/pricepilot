# Phase 3 — TEST evaluation denominators (authoritative, pre-baseline)

Produced 2026-09-21 by the architect session, recomputed directly from the committed files.
Nothing here is copied from STATE.md or DECISIONS.md; both were checked *against* this.

Inputs (SHA-256 of the raw bytes as committed on the Windows worktree):

| File | SHA-256 |
|---|---|
| `docs/learned/phase3-labels.json` | `9ba2775c8165245261c6abe22628d73e329baa0aaa8afb8be11664e95cb9b4e2` (LF-normalised: `6d514651ed5fa836a5c5de28af7b5d747096beb01ea2331354db01bc029f3fb3`) |
| `docs/learned/phase3-annotation-queue.json` | `696e983392628b868c4becd92db400735a52498a4994b5b7c8651b160a087011` (LF-normalised: `7da125e1856bc65514234d516e17d0a12363ee6ada9b324b3f00ca8bfa146d2a`) |
| `docs/learned/phase3-annotation-split.json` | `a9a4c7583215769c8053d148b65525b88d8ebf0ed9d345cd82d3fa9d68280c29` |
| `docs/learned/phase3-repeat-first-occurrence.json` | used for the repeat tie-break |

**This table is PRE-REVIEW** — the state of the labels *before* the annotator's review pass over
the 12 queued occurrences. Kept unchanged below as the audit-trail baseline; **see the POST-REVIEW
section near the end of this file for the current numbers.** The Schesir occurrence
(`3f574dad8b6e_b52acad20816_0`) was the only one eligible to move a TEST cell, and it did not — its
label is still `N`, unchanged, carried forward from a 2026-09-21 revision. **This is not the same
as "the review pass confirmed it": its stored record shows no 2026-09-22 timestamp at all, meaning
it was not actually re-examined this session. See POST-REVIEW for the full detail — this remains
outstanding, not resolved.**

## Rules applied (DECISIONS.md ADR-0028 addendum #12)

1. One row per **distinct `pair_id`**, not per decision row. TEST: 300 rows → **287 pairs**.
2. For a repeated pair the evaluation label is the **first decision in display order**
   (`phase3-repeat-first-occurrence.json`), never the file order.
3. A repeated pair is attributed to tier **`proxy_key_collision`**, not to the tier of its first
   occurrence. `trivial_spot_check` is therefore not a reportable TEST category — 2 pairs remain.
4. `S` labels are **dropped from scoring** and their count reported
   (`docs/phase3-baseline-model-choice.md`, fairness rule 4).
5. Every per-tier figure is reported with its denominator and a Wilson 95% CI.

## TEST — 287 distinct pairs

| Tier | pairs | M | N | S | scored (M+N) |
|---|---:|---:|---:|---:|---:|
| `proxy_key_collision` | 86 | 74 | 12 | 0 | 86 |
| `capacity_differs_cross_shop` | 63 | 1 | 62 | 0 | 63 |
| `blocked_retrieval_candidate` | 37 | 15 | 21 | 1 | 36 |
| `same_capacity_diff_flavour` | 26 | 0 | 26 | 0 | 26 |
| `capacity_differs_within_shop` | 23 | 0 | 22 | 1 | 22 |
| `same_capacity_diff_lifestage` | 20 | 1 | 18 | 1 | 19 |
| `diff_brand_similar_title` | 16 | 0 | 16 | 0 | 16 |
| `same_capacity_diff_breedsize` | 14 | 4 | 10 | 0 | 14 |
| `trivial_spot_check` (footnote only) | 2 | 2 | 0 | 0 | 2 |
| **TOTAL** | **287** | **97** | **187** | **3** | **284** |

The three `S` pairs: `458190b7d79e_8b7d069a7266` (capacity_differs_within_shop),
`d5fcb235eb23_97a5d666acd4` (blocked_retrieval_candidate),
`687e29e4280d_a746795258cd` (same_capacity_diff_lifestage).

### What is and is not computable per tier

- **Precision, recall and F1 are only meaningful on three tiers**: `proxy_key_collision` (74 pos),
  `blocked_retrieval_candidate` (15 pos), `same_capacity_diff_breedsize` (4 pos — wide CI).
- **Four tiers contain zero or one positive**: `same_capacity_diff_flavour` (0/26),
  `capacity_differs_within_shop` (0/22), `diff_brand_similar_title` (0/16),
  `capacity_differs_cross_shop` (1/63). Recall is undefined there. Report **false-positive rate**
  (FP / N) with a Wilson CI instead, and say so explicitly — do not print `recall = 0.000`.
- **The headline recall is dominated by one tier.** 74 of the 97 TEST positives (76.3%) sit in
  `proxy_key_collision`, and 13 of those 74 are the duplicated spot-check pairs (near-identical
  titles, all `M`). Overall recall must be reported alongside recall excluding those 13, otherwise
  it reads as harder than it is.
- **Overall precision is the number that carries the project's thesis**, because the hard negatives
  (size / flavour / life stage / breed size / different brand) are 187 of 284 scored pairs.

## TRAIN_VAL — 672 distinct pairs (697 rows)

| Tier | pairs | M | N | S | scored (M+N) |
|---|---:|---:|---:|---:|---:|
| `proxy_key_collision` | 200 | 166 | 31 | 3 | 197 |
| `capacity_differs_cross_shop` | 146 | 2 | 144 | 0 | 146 |
| `blocked_retrieval_candidate` | 86 | 39 | 43 | 4 | 82 |
| `same_capacity_diff_flavour` | 59 | 0 | 59 | 0 | 59 |
| `capacity_differs_within_shop` | 53 | 0 | 53 | 0 | 53 |
| `same_capacity_diff_lifestage` | 46 | 1 | 45 | 0 | 46 |
| `diff_brand_similar_title` | 39 | 4 | 35 | 0 | 39 |
| `same_capacity_diff_breedsize` | 33 | 5 | 28 | 0 | 33 |
| `trivial_spot_check` | 10 | 9 | 1 | 0 | 10 |
| **TOTAL** | **672** | **226** | **439** | **7** | **665** |

**Training must use 672 pairs, not 697 rows.** 25 pairs occur twice; training on rows
double-weights them and, pre-review, feeds three pairs two contradictory labels. Deduplicate with
the same first-occurrence-in-display-order rule, then drop `S`: **665 trainable pairs**.
`docs/phase3-baseline-model-choice.md` currently says "fine-tuned on the 697 TRAIN_VAL pairs" —
that wording is wrong on both counts.

## Split integrity — verified independently

- `pair_id` overlap TEST ↔ TRAIN_VAL: **0**.
- Distinct listing `content_hash` overlap TEST ↔ TRAIN_VAL: **0** (351 vs 802 listings).
  The "no listing appears on both sides" claim in README holds.

## Caveat that must travel with the self-agreement figures

All 38 repeated pairs are the `trivial_spot_check` pairs, re-drawn once under
`proxy_key_collision` (this is by construction — see `phase3-annotation-split.json`
`evaluation_rules.repeat_reporting_note`). Therefore **self-agreement was measured only on the
easiest pairs in the dataset**. "TEST 13/13 = 100%" is consistency on near-identical titles, not on
the hard negatives, and must never be quoted without that qualifier. The same construction means
TRAIN_VAL's 22/25 = 88% is a **12% self-disagreement rate on trivially easy pairs**, which is the
more informative reading of the two.

## Addendum (2026-09-22, DECISIONS.md ADR-0028 addendum #16)

`docs/learned/phase3-eval-view.json` (`scripts/build_eval_view.py`) now materialises the rules
above into a file, verified byte-for-byte against this table via `--assert-pre-review`. It is the
**only source of per-tier pair-count denominators from here on** — never
`phase3-annotation-split.json`'s own `per_tier_counts` block, whose `test_pair_ids`/
`train_val_pair_ids` fields are mislabelled (they hold ROW counts, e.g. `proxy_key_collision`
`test_pair_ids: 86` is the same number as `test_rows: 86`, and the whole block sums to 300/697 —
rows — not 287/672 — distinct pairs). That file is frozen and hashed in three other places, so the
trap is documented here rather than fixed in place.

## POST-REVIEW table (2026-09-22, after the annotator's review pass, DECISIONS.md ADR-0028 addendum #17)

12 occurrences were queued in `phase3-relabel-queue.json`. Re-ingested via
`scripts/ingest_labels.py` over all five export files in `docs/learned/labels/` (per the runbook).
**997 decisions in, 997 out** — a revision replaces, never adds; **zero occurrence_ids outside the
12 queued ones changed.**

**Only 11 of the 12 carry a fresh 2026-09-22 decision. The 12th — `3f574dad8b6e_b52acad20816_0`,
the sole queued TEST occurrence — does not, and this is flagged here as outstanding, not glossed
over.** Its stored record in the export
(`docs/learned/labels/phase3-labels-20260922-1136.json`) still reads `decided_at:
"2026-09-21T16:39:52.697Z"`, `revised_at: "2026-09-21T16:39:52.697Z"` — identical to before this
session, with no 2026-09-22 timestamp anywhere on it. It was queued for review and is included in
the export's full-state snapshot, but nothing in the stored data shows it was actually re-examined
this session; the label (`N`) is simply carried forward from the prior session's revision —
**the same revision `ARCHITECT_NOTES` already flagged as invalid** (rule 1 reads the title, not
the `species` field; both titles say "pisici"/cat). **This is not resolved. It needs the
annotator's attention, specifically, before this occurrence can be trusted as reviewed.** (A prior
report described this session's review pass as "12/12" — that count does not match what is
actually stored; 11/12 is what the data supports.)

Of the **11** occurrences with a genuine 2026-09-22 decision, **6 actually changed label** relative
to what was already merged (the other 5 were re-confirmed at their existing value). All 6 changes
are in **TRAIN_VAL** — the TEST table above is byte-identical, pre- to post-review (including
`3f574dad8b6e_b52acad20816_0` itself, whose value never moved).

| occurrence_id | pair_id | class(es) | before | after |
|---|---|---|---|---|
| `1c0d1a45d509_614c9a4d1f42_0` | `1c0d1a45d509_614c9a4d1f42` | a | M | **N** |
| `a960a4aea31a_cf3c9566947c_0` | `a960a4aea31a_cf3c9566947c` | a | M | **N** |
| `01b880c1f365_33394df3427d_0` | `01b880c1f365_33394df3427d` | d, f | S | **N** |
| `01b880c1f365_33394df3427d_1` | `01b880c1f365_33394df3427d` | f | M | **N** |
| `3f12b3225e74_a0b2cb253771_0` | `3f12b3225e74_a0b2cb253771` | f | M | **N** |
| `a19a1b41f49f_afc62890b6b5_1` | `a19a1b41f49f_afc62890b6b5` | f | M | **N** |

The other 5 of the 11 genuinely-reviewed occurrences were re-confirmed unchanged (all still `N`):
`2acc97947c1c_c8f4810554f2_0` (e), `84fe6219552b_e8343e4a08b2_0` (e),
`a19a1b41f49f_afc62890b6b5_0` (d, f), `3f12b3225e74_a0b2cb253771_1` (d, f) and
`33394df3427d_3ab75d311be0_0` (d). Plus the one occurrence above whose review status is
unconfirmed: `3f574dad8b6e_b52acad20816_0` (e), also `N`.

**Checker re-run:** class (a) 0, (b) 0, (c) 0, (d) **4**, (e) 3, (f) **0** — 7 flags / 7
occurrences. Classes a and f fully resolved. **Class (d) did NOT resolve**: all four
`trivial_spot_check`-tier pairs (the Royal Canin Kitten pairs, `01b880c1f365_33394df3427d`,
`a19a1b41f49f_afc62890b6b5`, `3f12b3225e74_a0b2cb253771`, `33394df3427d_3ab75d311be0`) are labelled
`N` — three of the four are repeats and are `N` on both occurrences; the fourth
(`33394df3427d_3ab75d311be0`) has only one occurrence, also `N`. All four carry fresh 2026-09-22
timestamps (genuinely re-examined, not just carried forward — contrast the Schesir occurrence
above). **No rationale is recorded for any of the four**: `s_reason` is only ever populated for `S`
answers, so its being `null` here is not itself evidence — check instead that no free-text note
exists anywhere in the export
(`docs/learned/labels/phase3-labels-20260922-1136.json`; the field doesn't survive into
`phase3-labels.json` at all) — this doc does not know, and does not claim to know, why the
annotator decided `N` on titles that read as the same product
("Royal Canin Kitten, 10 kg" vs "ROYAL CANIN Kitten, hrană uscată pisici junior, 10kg", and
similarly for the 400g/2kg pairs). **This is the same population DECISIONS.md ADR-0028 addendum
#16 already characterised as a measured anchoring effect on the engine's suggestion** (assisted
TRAIN_VAL 31/35 correct pre-review, these being 4 of the 35) — that framing is not retracted or
softened here; it is the framing that stands. It is a real mechanical-rule violation the checker
is right to keep flagging, and — unlike the 3f574dad8b6e_b52acad20816_0 case above — all four DO
carry fresh 2026-09-22 timestamps, so these four genuinely were re-examined this session and kept
at `N`.
**Class e (3, unchanged) never blocks the freeze** (`freeze_labels.blocking_findings()` excludes
it); **class d (4) does block it.** `scripts/freeze_labels.py --freeze` was **not run** this
session — the dataset stays UNFROZEN.

### TEST — unchanged from the pre-review table above (287 pairs, 97 M / 187 N / 3 S, 284 scored)

Every per-tier cell matches the pre-review table exactly — verified by comparing
`scripts/build_eval_view.py`'s per-tier TEST output directly against `EXPECTED_PRE_REVIEW["test"]`
in code, tier by tier, zero mismatches. **Note on `--assert-pre-review` itself:** running it now
correctly exits non-zero overall ("MISMATCH against the architect's table") because
`EXPECTED_PRE_REVIEW` still pins the PRE-review TRAIN_VAL numbers and TRAIN_VAL has genuinely
moved (see below) — that failure is expected and by design, not a bug; it is scoped to TRAIN_VAL
only, TEST alone produces zero mismatch lines. S pairs unchanged: `458190b7d79e_8b7d069a7266`,
`d5fcb235eb23_97a5d666acd4`, `687e29e4280d_a746795258cd`.

### TRAIN_VAL — 672 distinct pairs, POST-REVIEW

| Tier | pairs | M | N | S | scored (M+N) | Δ vs pre-review |
|---|---:|---:|---:|---:|---:|---|
| `proxy_key_collision` | 200 | 164 | 34 | 2 | 198 | M −2, N +3, S −1 |
| `capacity_differs_cross_shop` | 146 | 0 | 146 | 0 | 146 | M −2, N +2 |
| `blocked_retrieval_candidate` | 86 | 39 | 43 | 4 | 82 | unchanged |
| `same_capacity_diff_flavour` | 59 | 0 | 59 | 0 | 59 | unchanged |
| `capacity_differs_within_shop` | 53 | 0 | 53 | 0 | 53 | unchanged |
| `same_capacity_diff_lifestage` | 46 | 1 | 45 | 0 | 46 | unchanged |
| `diff_brand_similar_title` | 39 | 4 | 35 | 0 | 39 | unchanged |
| `same_capacity_diff_breedsize` | 33 | 5 | 28 | 0 | 33 | unchanged |
| `trivial_spot_check` | 10 | 9 | 1 | 0 | 10 | unchanged |
| **TOTAL** | **672** | **222** (was 226) | **444** (was 439) | **6** (was 7) | **666** (was 665) | M −4, N +5, S −1 |

Only `proxy_key_collision` and `capacity_differs_cross_shop` moved — the eval-view TIER of the
changed pair (post rule 3 repeat re-attribution), not necessarily the QUEUE tier of the changed
occurrence itself: `01b880c1f365_33394df3427d_0`'s own occurrence tier is `trivial_spot_check`,
and it is reported under `proxy_key_collision` only because rule 3 attributes every repeated pair
to that tier regardless of its first occurrence's tier. S pairs, post-review (6, was 7 —
`01b880c1f365_33394df3427d` moved S→N): `337b68ef4d83_0b356dfb4b69`, `381ad6bf4e5c_98bff2af651c`,
`48fd1f2f7142_db48d6e143a2`, `4b716da37ec2_fcebb06c2a34`, `889e719216a5_ea6d5f153b94`,
`bce9992b1579_d38a575da629`.

**665 trainable pairs (672 − 6 S) is now 666.** `docs/phase3-baseline-model-choice.md` has already
been updated in this same session (all "665" occurrences now read "666", the TRAIN_VAL S-count rule
updated 7→6) — this is a record of the change, not an open TODO for a future session. Phase 3 item
5 itself has still not started.

### Files regenerated this session

`docs/learned/labels/phase3-labels-20260922-1136.json` (the annotator's export, the input to
everything below), `docs/learned/phase3-labels.json` (997 decisions, 6 label changes),
`phase3-label-qa-20260922.md`
(new QA report), `phase3-relabel-queue.json` (now 7 flags), `phase3-eval-view.json` (this table's
source). `phase3-annotation-queue.json` and `phase3-annotation-split.json` are unchanged (not
touched, not re-run).

## Tier purity note (not a defect to fix, a caveat to state)

TEST pair `00f775f25237_6a81b0d8429b` sits in `capacity_differs_cross_shop` although the two sides
are `85g` and `1x85g` — the same quantity; the tier fired on `pack_count` `None` vs `1`. It is
correctly labelled `M` and is the single positive in that tier. Do not "fix" the queue: it is
frozen and its hash is recorded in three files.

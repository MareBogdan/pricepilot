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

**This table is pre-review.** It is the state of the labels *before* the annotator's review pass
over the 12 queued occurrences. Regenerate it after ingest; only the Schesir occurrence
(`3f574dad8b6e_b52acad20816_0`, currently `N`) can move a TEST cell.

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

## Tier purity note (not a defect to fix, a caveat to state)

TEST pair `00f775f25237_6a81b0d8429b` sits in `capacity_differs_cross_shop` although the two sides
are `85g` and `1x85g` — the same quantity; the tier fired on `pack_count` `None` vs `1`. It is
correctly labelled `M` and is the single positive in that tier. Do not "fix" the queue: it is
frozen and its hash is recorded in three files.

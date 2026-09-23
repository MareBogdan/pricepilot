# Phase 3 item 5 — cross-encoder baseline, TEST results

Model: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`, run on a hosted Kaggle notebook, CPU
(accelerator reset to None), seed 20260923. Two variants scored on the same 287-pair blind TEST
set (284 scored, 3 `S` dropped), each touched exactly once
(`docs/learned/results/test-touch-ledger.json`). Full run facts, selection-maximum caveat and
limitations: DECISIONS.md ADR-0028 addendum #20.

## Headline TEST numbers

| model | threshold | precision | recall (all 97 pos) | F1 | accuracy |
|---|---|---|---|---|---|
| zero-shot | 0.86 | 0.3434 (n=265, 95% CI [0.2888, 0.4024]) | 0.9381 (n=97, CI [0.8716, 0.9713]) | 0.5028 | 0.3662 (n=284, CI [0.3123, 0.4237]) |
| fine-tuned (ep6) | 0.89 | 0.8925 (n=93, CI [0.8133, 0.9405]) | 0.8557 (n=97, CI [0.7722, 0.9120]) | 0.8737 | 0.9155 (n=284, CI [0.8773, 0.9426]) |

F1 has no independent Wilson CI — it is a harmonic mean of two different proportions, not itself
a single binomial proportion Wilson's assumptions apply to.

## Recall, both ways

The 13 `proxy_key_collision` pairs that duplicate a `trivial_spot_check` pair inflate recall if
counted twice; both readings are reported side by side.

| model | recall, all 97 positives | recall, excl. 13 repeat positives (n=84) |
|---|---|---|
| zero-shot | 0.9381 (n=97, CI [0.8716, 0.9713]) | 0.9405 (n=84, CI [0.8681, 0.9743]) |
| fine-tuned (ep6) | 0.8557 (n=97, CI [0.7722, 0.9120]) | 0.8333 (n=84, CI [0.7395, 0.8980]) |

For zero-shot the two readings barely move — expected, since a model that calls almost everything
`M` recalls the repeats and non-repeats about equally. For the fine-tuned model the repeat-excluded
figure drops 2.2pp, meaning a disproportionate share of its correct recalls come from the easier,
duplicated `trivial_spot_check`-derived pairs.

## Zero-shot is not weakly discriminating — it is not discriminating at all

Measured by `scripts/measure_score_distribution.py` (not taken from the notebook), output
committed at `docs/learned/results/mmarco-mMiniLMv2-zeroshot-score-distribution.json`: on TEST,
the zero-shot model's score distribution is **median 1.0000 for both label classes** — M (n=97):
median 0.99998, min 0.298, max 0.99998; N (n=187): median 0.99998, min 0.190, max 0.99998. 88.7%
of M pairs and 91.4% of N pairs score ≥0.99. "F1 0.5028" reads as a moderate signal; it is actually
a model that outputs ~1.0 for nearly every pair regardless of label, and the reported precision/
recall/F1 are almost entirely an artefact of the TEST set's own class balance (97 M / 187 N)
landing at the validation-selected threshold (0.86), not of the model separating the classes.

## Per-tier (fine-tuned model, threshold 0.89)

Tiers with fewer than 5 positives report FP rate instead of recall (docs/phase3-baseline-model-choice.md
rule 6) — a zero- or near-zero-positive tier never reports a recall figure here.

| tier | n_pos | n_neg | metric |
|---|---|---|---|
| proxy_key_collision | 74 | 12 | P=0.947 R=0.973 F1=0.960 (tp=72 fp=4 fn=2) |
| capacity_differs_cross_shop | 1 | 62 | FP rate 0.0000 (n=62, CI [0.0000, 0.0583]) |
| blocked_retrieval_candidate | 15 | 21 | P=0.700 R=0.467 F1=0.560 (tp=7 fp=3 fn=8) |
| same_capacity_diff_flavour | 0 | 26 | FP rate 0.0000 (n=26, CI [0.0000, 0.1287]) |
| capacity_differs_within_shop | 0 | 22 | FP rate 0.0909 (n=22, CI [0.0253, 0.2781]) |
| same_capacity_diff_lifestage | 1 | 18 | FP rate 0.0000 (n=18, CI [0.0000, 0.1759]) |
| diff_brand_similar_title | 0 | 16 | FP rate 0.0000 (n=16, CI [0.0000, 0.1936]) |
| same_capacity_diff_breedsize | 4 | 10 | FP rate 0.1000 (n=10, CI [0.0179, 0.4042]) |
| trivial_spot_check | 2 | 0 | undefined (n=0) |

Raw per-tier tp/fp/fn/tn for every tier (not gated by rule 6's n_pos>=5 reportability floor, which
withholds a precision/recall RATE computed from too few positives, never the raw counts
themselves), from `scripts/measure_score_distribution.py --threshold 0.89`, committed at
`docs/learned/results/mmarco-mMiniLMv2-finetuned-ep6-score-distribution.json`:

| tier | tp | fp | fn | tn |
|---|---|---|---|---|
| proxy_key_collision | 72 | 4 | 2 | 8 |
| capacity_differs_cross_shop | 1 | 0 | 0 | 62 |
| blocked_retrieval_candidate | 7 | 3 | 8 | 18 |
| same_capacity_diff_flavour | 0 | 0 | 0 | 26 |
| capacity_differs_within_shop | 0 | 2 | 0 | 20 |
| same_capacity_diff_lifestage | 0 | 0 | 1 | 18 |
| diff_brand_similar_title | 0 | 0 | 0 | 16 |
| same_capacity_diff_breedsize | 1 | 1 | 3 | 9 |
| trivial_spot_check | 2 | 0 | 0 | 0 |

**Where the fine-tuned model actually fails:**
- **`blocked_retrieval_candidate` (15 pos, 21 neg): recall only 46.7% (7/15 recalled, 8 missed),
  precision 70.0% (7/10 predicted-M correct).** This is the model's worst reportable tier by
  precision/recall and the largest ABSOLUTE number of missed positives in the table (8) — these
  are pairs retrieval itself put in front of the model as candidates, and the fine-tuned model
  still misses more than half of the true matches among them. By recall RATE alone,
  `same_capacity_diff_breedsize` below is worse (1/4 = 25% vs. this tier's 46.7%), but that tier's
  n_pos=4 sits below rule 6's reportability floor, so its rate is not stated as a headline figure.
- **`proxy_key_collision` (74 pos, 12 neg): 4 of 12 negatives wrongly predicted `M` (FP rate
  33.3%)** — the highest false-positive rate of any tier in the table, reportable tier included;
  its own precision (0.947) and recall (0.973) stay high only because its 74 positives dwarf its
  12 negatives.
- **`same_capacity_diff_breedsize` (4 pos, 10 neg): tp=1, fn=3 on the positives** (rule 6 withholds
  a recall figure at n_pos=4 < 5) **and 1 of 10 negatives wrongly predicted `M`** — the model
  misses 3 of its 4 true matches in this tier. Breed-size variants are exactly the hard-case class
  CLAUDE.md's Phase 3 section calls out as the dominant error class to expect, and this tier is
  where that expectation shows up most clearly in the numbers.
- **`same_capacity_diff_lifestage` (1 pos, 18 neg): the single positive is missed** (tp=0, fn=1),
  with 0 false positives on the 18 negatives.
- **`capacity_differs_within_shop` (0 pos, 22 neg): 2 of 22 negatives wrongly predicted `M`** (FP
  rate 9.1%), on pairs whose defining difference is a capacity mismatch within one shop.
- The remaining tiers (`capacity_differs_cross_shop` — 1 positive, correctly recalled, 0 false
  positives on its 62 negatives; `same_capacity_diff_flavour`; `diff_brand_similar_title`) show 0
  false positives.

No causal explanation is offered beyond what these counts support — `blocked_retrieval_candidate`
being the model's worst reportable tier is a finding, not a diagnosed root cause.

# Phase 3 model comparison (TEST)

CLAUDE.md §7 item 7. One row per model on the same frozen TEST set (287 pairs, 284 scored, 3 S
dropped). Everything between the GENERATED markers is produced by `scripts/compare_models.py`
(`uv run python scripts/compare_models.py`), which reads each model's ledger threshold (chosen on
validation only) and reuses `score_predictions.score()`, so its numbers equal the committed
`*-metrics.json` files (asserted at run time). Every rate carries its denominator and Wilson 95% CI.
This script scores no new model and touches no ledger; the TEST-touch ledger still holds exactly
three entries.

<!-- BEGIN GENERATED (scripts/compare_models.py) -->
### Headline TEST metrics (284 scored pairs; each: value (k/n) [Wilson 95% CI])

| model | val-selected threshold | precision | recall | recall excl. 13 repeat positives | accuracy | F1 |
|---|---|---|---|---|---|---|
| Cross-encoder mMiniLMv2, zero-shot | 0.86 | 0.343 (91/265) [0.289, 0.402] | 0.938 (91/97) [0.872, 0.971] | 0.940 (79/84) [0.868, 0.974] | 0.366 (104/284) [0.312, 0.424] | 0.5028 |
| Cross-encoder mMiniLMv2, fine-tuned (epoch 6) | 0.89 | 0.892 (83/93) [0.813, 0.941] | 0.856 (83/97) [0.772, 0.912] | 0.833 (70/84) [0.739, 0.898] | 0.915 (260/284) [0.877, 0.943] | 0.8737 |
| LoRA Qwen2.5-0.5B-Instruct (epoch 8) | 0.86 | 0.894 (84/94) [0.815, 0.941] | 0.866 (84/97) [0.784, 0.920] | 0.845 (71/84) [0.753, 0.907] | 0.919 (261/284) [0.881, 0.945] | 0.8796 |

F1 carries no CI of its own (harmonic mean of two proportions; see the metrics files).

### Cost columns

| model | parameters trained | artefact size | training wall clock |
|---|---|---|---|
| Cross-encoder mMiniLMv2, zero-shot | 0 (no training) | n/a (no training artefact) | 0 (no training) |
| Cross-encoder mMiniLMv2, fine-tuned (epoch 6) | all weights, ~0.1B (model card rounds; exact UNVERIFIED) | not recorded | ~1 hour on Kaggle CPU (approximate; ADR-0028 #20; accelerator had reset) |
| LoRA Qwen2.5-0.5B-Instruct (epoch 8) | 8,798,208 LoRA params (derived from architecture: r=16 on q/k/v/o/gate/up/down across 24 layers; not read from the run log) | 35.24 MB LoRA adapter (run log); base weights not included | 15.0 min real run on Kaggle T4 GPU (+36.6 s smoke run, excluded) |

The two wall clocks are on DIFFERENT hardware (CPU vs GPU) and are not a like-for-like speed comparison.

### Do the two fine-tuned models' confidence intervals overlap?

| metric | cross-encoder | LoRA | CIs overlap? |
|---|---|---|---|
| precision | 0.892 (83/93) [0.813, 0.941] | 0.894 (84/94) [0.815, 0.941] | **YES** |
| recall | 0.856 (83/97) [0.772, 0.912] | 0.866 (84/97) [0.784, 0.920] | **YES** |
| recall_excl_repeats | 0.833 (70/84) [0.739, 0.898] | 0.845 (71/84) [0.753, 0.907] | **YES** |
| accuracy | 0.915 (260/284) [0.877, 0.943] | 0.919 (261/284) [0.881, 0.945] | **YES** |

### McNemar's exact test (paired, same TEST pairs; correct = prediction matches label)

| subset | n | both right | cross-encoder only right | LoRA only right | both wrong | p (exact, two-sided) |
|---|---|---|---|---|---|---|
| all scored pairs | 284 | 252 | 8 | 9 | 15 | 1.0000 |
| true M only (recall side) | 97 | 78 | 5 | 6 | 8 | 1.0000 |
| true N only (false-positive side) | 187 | 174 | 3 | 3 | 7 | 1.0000 |

### Per tier: correct/n [Wilson 95% CI], and discordant pairs

| tier | n | zero-shot | cross-encoder | LoRA | cross-encoder-only right | LoRA-only right | McNemar p (post-hoc, uncorrected) |
|---|---|---|---|---|---|---|---|
| proxy_key_collision | 86 (74 M) | 0.791 (68/86) [0.693, 0.863] | 0.930 (80/86) [0.856, 0.968] | 0.895 (77/86) [0.813, 0.944] | 5 | 2 | 0.453 |
| capacity_differs_cross_shop | 63 (1 M) | 0.190 (12/63) [0.112, 0.304] | 1.000 (63/63) [0.943, 1.000] | 0.984 (62/63) [0.915, 0.997] | 1 | 0 | 1.000 |
| blocked_retrieval_candidate | 36 (15 M) | 0.417 (15/36) [0.271, 0.578] | 0.694 (25/36) [0.531, 0.820] | 0.833 (30/36) [0.681, 0.921] | 1 | 6 | 0.125 |
| same_capacity_diff_flavour | 26 (0 M) | 0.000 (0/26) [0.000, 0.129] | 1.000 (26/26) [0.871, 1.000] | 1.000 (26/26) [0.871, 1.000] | 0 | 0 | 1.000 |
| capacity_differs_within_shop | 22 (0 M) | 0.000 (0/22) [0.000, 0.149] | 0.909 (20/22) [0.722, 0.975] | 0.909 (20/22) [0.722, 0.975] | 0 | 0 | 1.000 |
| same_capacity_diff_lifestage | 19 (1 M) | 0.105 (2/19) [0.029, 0.314] | 0.947 (18/19) [0.754, 0.991] | 0.947 (18/19) [0.754, 0.991] | 0 | 0 | 1.000 |
| diff_brand_similar_title | 16 (0 M) | 0.000 (0/16) [0.000, 0.194] | 1.000 (16/16) [0.806, 1.000] | 1.000 (16/16) [0.806, 1.000] | 0 | 0 | 1.000 |
| same_capacity_diff_breedsize | 14 (4 M) | 0.357 (5/14) [0.163, 0.612] | 0.714 (10/14) [0.454, 0.883] | 0.714 (10/14) [0.454, 0.883] | 1 | 1 | 1.000 |
| trivial_spot_check | 2 (2 M) | 1.000 (2/2) [0.342, 1.000] | 1.000 (2/2) [0.342, 1.000] | 1.000 (2/2) [0.342, 1.000] | 0 | 0 | 1.000 |

### Size-variant hard negatives (tiers capacity_differs_cross_shop, capacity_differs_within_shop; n=85, 1 positive -> F1 undefined)

| model | correct calls / n [Wilson 95% CI] |
|---|---|
| Cross-encoder mMiniLMv2, zero-shot | 0.141 (12/85) [0.083, 0.231] |
| Cross-encoder mMiniLMv2, fine-tuned (epoch 6) | 0.976 (83/85) [0.918, 0.994] |
| LoRA Qwen2.5-0.5B-Instruct (epoch 8) | 0.965 (82/85) [0.901, 0.988] |
<!-- END GENERATED -->

## Verdict

**The two fine-tuned models are statistically indistinguishable on this TEST set. No winner is
declared.**

- Point estimates: LoRA F1 **0.8796** vs cross-encoder **0.8737**, a gap of **0.0059**.
- **The confidence intervals overlap on every metric** (precision, recall, recall excluding the 13
  repeat positives, accuracy) -- table above. A point-estimate lead inside overlapping intervals is
  not evidence of a better model.
- **McNemar's exact test** (paired, same 284 pairs; computed by `scripts/compare_models.py`): the
  cross-encoder was right and the LoRA model wrong on **8** pairs, the LoRA model right and the
  cross-encoder wrong on **9**; **p = 1.0000**. Split by true label: positives 5 vs 6, negatives
  3 vs 3, both p = 1.0000. The whole 0.0059 F1 gap is one pair (261 vs 260 correct of 284).
- Per tier the models differ in direction, not significantly: the LoRA model is ahead on
  `blocked_retrieval_candidate` (30/36 vs 25/36; discordant 6 vs 1, p = 0.125) and behind on
  `proxy_key_collision` (77/86 vs 80/86; discordant 2 vs 5, p = 0.453). These are post-hoc,
  uncorrected p-values over nine tiers with small denominators: a hypothesis for the next
  experiment, not a finding.
- The validation picture was different and should not be quoted as the result: on 133 validation
  pairs the LoRA model's selected F1 was 0.8941 against the cross-encoder's 0.840 -- a 0.055 gap
  that is 4 true positives (34 -> 38 of 46) at the same single false positive, and both figures are
  selection maxima. On TEST that gap shrank to 0.0059.

### Against the pre-registered rule (docs/phase3-baseline-model-choice.md)

The rule was written before the result existed: if the LoRA 0.5B does not beat the cross-encoder's
TEST F1 of 0.8737, that is the finding; CLAUDE.md §7 adds that a **tie on F1 makes the serving
benchmark the result**. The LoRA model's point F1 is nominally above 0.8737, but by 0.0059 with
overlapping intervals and a McNemar p of 1.0. **Recorded verdict: a tie on F1.** No claim that
fine-tuning beat the classical baseline is supported by this data, and none is made. Per the tie
rule, the headline of Phase 3 is the item 8 serving benchmark (quantized CPU accuracy, p50/p95
latency, cost per 1,000 comparisons), with F1 as the parity claim. Neither follow-up is needed to
rescue a result: the 1.5B second attempt remains optional and separately ledgered; the
cross-encoder baseline was not re-run, retuned or weakened.

### Limits

- One annotator, one frozen split; TEST positives are 76% `proxy_key_collision`, and the three
  tiers with zero positives cannot say anything about recall.
- Four of the ten selected failure cases (2, 3, 6 and 7 in `phase3-failure-analysis.md`) are pairs
  labelled M whose extracted attributes differ in a way the project's rules read as NOT the same
  unit (cases 3, 6, 7: a life-stage difference, Rule 3; case 2: different breed lines, i.e. a
  different product rather than an enumerated rule). The cross-encoder also predicted N on all
  four. That is consistent with label noise in the TEST set (the labels are frozen and were not
  touched), which would depress both models' scores equally; case 8 (life stage missing on one
  side) is a grey zone. Not proven -- an observation.
- The cost columns compare different hardware (CPU vs GPU) and the cross-encoder's parameter count,
  artefact size and exact wall clock were not recorded precisely.

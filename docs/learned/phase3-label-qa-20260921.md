# Phase 3 label QA report

Generated: 2026-09-21T16:52:41.803936+00:00
Source files (3):
  - phase3-labels-20260921-1807.json: 100 decisions in file (claimed 100), exported_at=2026-09-21T15:07:15.806Z
  - phase3-labels-20260921-1827.json: 300 decisions in file (claimed 300), exported_at=2026-09-21T15:27:25.005Z
  - phase3-labels-20260921-1941.json: 300 decisions in file (claimed 300), exported_at=2026-09-21T16:41:34.134Z

## Coverage

Overall: 300/997 = 30.1% [27.3%, 33.0%]
  test: 300/300 = 100.0% [98.7%, 100.0%]
  train_val: 0/697 = 0.0% [0.0%, 0.5%]

Per tier:
  blocked_retrieval_candidate: 37/123 = 30.1% [22.7%, 38.7%]
  capacity_differs_cross_shop: 63/209 = 30.1% [24.3%, 36.7%]
  capacity_differs_within_shop: 23/76 = 30.3% [21.1%, 41.3%]
  diff_brand_similar_title: 16/55 = 29.1% [18.8%, 42.1%]
  proxy_key_collision: 86/286 = 30.1% [25.0%, 35.6%]
  same_capacity_diff_breedsize: 14/47 = 29.8% [18.7%, 44.0%]
  same_capacity_diff_flavour: 26/85 = 30.6% [21.8%, 41.0%]
  same_capacity_diff_lifestage: 20/66 = 30.3% [20.6%, 42.2%]
  trivial_spot_check: 15/50 = 30.0% [19.1%, 43.8%]

## Label distribution (M/N/S)

Rules-engine forecast is shown SIDE BY SIDE as a DIAGNOSTIC only -- it is never a correctness judgement of Bogdan's labels. It is computed over the SAME decided occurrence_ids as the observed counts (not the whole population), for a fair comparison.

### overall (n=300 decided)
  M: observed 110/300 = 36.7% [31.4%, 42.3%]   |   forecast 102/300
  N: observed 187/300 = 62.3% [56.7%, 67.6%]   |   forecast 165/300
  S: observed 3/300 = 1.0% [0.3%, 2.9%]   |   forecast 33/300

### test (n=300 decided)
  M: observed 110/300 = 36.7% [31.4%, 42.3%]   |   forecast 102/300
  N: observed 187/300 = 62.3% [56.7%, 67.6%]   |   forecast 165/300
  S: observed 3/300 = 1.0% [0.3%, 2.9%]   |   forecast 33/300

### train_val (n=0 decided)
  M: observed n=0   |   forecast 0/0
  N: observed n=0   |   forecast 0/0
  S: observed n=0   |   forecast 0/0

Per tier (observed only, n too small for forecast to be meaningful tier-by-tier):
  blocked_retrieval_candidate (n=37): M=15 N=21 S=1
  capacity_differs_cross_shop (n=63): M=1 N=62 S=0
  capacity_differs_within_shop (n=23): M=0 N=22 S=1
  diff_brand_similar_title (n=16): M=0 N=16 S=0
  proxy_key_collision (n=86): M=74 N=12 S=0
  same_capacity_diff_breedsize (n=14): M=4 N=10 S=0
  same_capacity_diff_flavour (n=26): M=0 N=26 S=0
  same_capacity_diff_lifestage (n=20): M=1 N=18 S=1
  trivial_spot_check (n=15): M=15 N=0 S=0

## Self-agreement (repeated pairs, both occurrences decided)

TRAIN_VAL repeats are both ASSISTED -- the annotator saw a suggestion both times, so agreement there is anchored by the rules engine and is a weaker signal than TEST self-agreement, where neither occurrence was ever shown a suggestion.

  test: 13/13 repeated pairs have both occurrences decided; of those, 13/13 = 100.0% [77.2%, 100.0%] agree
  train_val: 0/25 repeated pairs have both occurrences decided; of those, n=0 agree

## Assisted flow (TRAIN_VAL only)

TRAIN_VAL decisions: 0
  confirmed (pressed C): 0
  corrected (overrode, differs from suggestion): 0
  overrode but agreed with suggestion: 0
  correction rate (overall): n=0
  correction rate per tier:
  median decision time, confirmed: -
  median decision time, corrected: -

## Throughput

First real measurement of CLAUDE.md §7's untested '200 pairs/hour' claim (sub-18s median decision).

  overall (n=300): median 3.0s, p90 10.8s, 697 remaining -> implied 0.6h to finish (at this median pace)
  test (n=300): median 3.0s, p90 10.8s, 0 remaining -> implied 0.0h to finish (at this median pace)
  train_val (n=0): median -, p90 -, 697 remaining -> implied - to finish (at this median pace)
  Per-tier median decision time:
    blocked_retrieval_candidate: median 7.4s (n=37)
    capacity_differs_cross_shop: median 1.7s (n=63)
    capacity_differs_within_shop: median 2.0s (n=23)
    diff_brand_similar_title: median 4.9s (n=16)
    proxy_key_collision: median 3.2s (n=86)
    same_capacity_diff_breedsize: median 6.2s (n=14)
    same_capacity_diff_flavour: median 6.0s (n=26)
    same_capacity_diff_lifestage: median 3.7s (n=20)
    trivial_spot_check: median 1.6s (n=15)

## Flagged pairs

  (none flagged)

## Skip (S) decisions and their stated reasons

  - 458190b7d79e_8b7d069a7266_0 (pair_id=458190b7d79e_8b7d069a7266): unspecified
  - d5fcb235eb23_97a5d666acd4_0 (pair_id=d5fcb235eb23_97a5d666acd4): unspecified
  - 687e29e4280d_a746795258cd_0 (pair_id=687e29e4280d_a746795258cd): unspecified

## Review-mode revisions

Total revised: 7
By rule:
  rule1_species_differs: 2
  rule1_species_differs,rule3b_foodform_dry_vs_wet: 1
  rule1_species_differs,species_title_field_mismatch: 1
  rule2_quantity_differs: 3

Detail (old -> new):
  - 0e45d9b997f8_153c7e549d19_0 (pair_id=0e45d9b997f8_153c7e549d19): 'M' -> 'N' (rule: rule2_quantity_differs, revised_at=2026-09-21T16:39:38.511Z)
  - 3f3a8d1d2b69_96aa964f7dc7_0 (pair_id=3f3a8d1d2b69_96aa964f7dc7): 'M' -> 'N' (rule: rule2_quantity_differs, revised_at=2026-09-21T16:39:40.526Z)
  - 3f574dad8b6e_b52acad20816_0 (pair_id=3f574dad8b6e_b52acad20816): 'M' -> 'N' (rule: rule1_species_differs,species_title_field_mismatch, revised_at=2026-09-21T16:39:52.697Z)
  - c55327a4a4cb_ecc599237076_0 (pair_id=c55327a4a4cb_ecc599237076): 'M' -> 'N' (rule: rule2_quantity_differs, revised_at=2026-09-21T16:39:54.700Z)
  - af9c46b9524a_bcfe44adfdf1_0 (pair_id=af9c46b9524a_bcfe44adfdf1): 'M' -> 'N' (rule: rule1_species_differs, revised_at=2026-09-21T16:40:07.644Z)
  - da2907bb100e_fced2443703b_0 (pair_id=da2907bb100e_fced2443703b): 'M' -> 'N' (rule: rule1_species_differs, revised_at=2026-09-21T16:40:08.769Z)
  - 4ebc3a6e6210_31cc6248c1de_0 (pair_id=4ebc3a6e6210_31cc6248c1de): 'M' -> 'N' (rule: rule1_species_differs,rule3b_foodform_dry_vs_wet, revised_at=2026-09-21T16:40:09.718Z)

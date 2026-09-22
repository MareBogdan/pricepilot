# Phase 3 label QA report

Generated: 2026-09-22T08:38:14.191081+00:00
Source files (5):
  - phase3-labels-20260921-1807.json: 100 decisions in file (claimed 100), exported_at=2026-09-21T15:07:15.806Z
  - phase3-labels-20260921-1827.json: 300 decisions in file (claimed 300), exported_at=2026-09-21T15:27:25.005Z
  - phase3-labels-20260921-1941.json: 300 decisions in file (claimed 300), exported_at=2026-09-21T16:41:34.134Z
  - phase3-labels-20260921-2017.json: 997 decisions in file (claimed 997), exported_at=2026-09-21T17:17:32.727Z
  - phase3-labels-20260922-1136.json: 997 decisions in file (claimed 997), exported_at=2026-09-22T08:36:08.637Z

## Coverage

Overall: 997/997 = 100.0% [99.6%, 100.0%]
  test: 300/300 = 100.0% [98.7%, 100.0%]
  train_val: 697/697 = 100.0% [99.5%, 100.0%]

Per tier:
  blocked_retrieval_candidate: 123/123 = 100.0% [97.0%, 100.0%]
  capacity_differs_cross_shop: 209/209 = 100.0% [98.2%, 100.0%]
  capacity_differs_within_shop: 76/76 = 100.0% [95.2%, 100.0%]
  diff_brand_similar_title: 55/55 = 100.0% [93.5%, 100.0%]
  proxy_key_collision: 286/286 = 100.0% [98.7%, 100.0%]
  same_capacity_diff_breedsize: 47/47 = 100.0% [92.4%, 100.0%]
  same_capacity_diff_flavour: 85/85 = 100.0% [95.7%, 100.0%]
  same_capacity_diff_lifestage: 66/66 = 100.0% [94.5%, 100.0%]
  trivial_spot_check: 50/50 = 100.0% [92.9%, 100.0%]

## Label distribution (M/N/S)

Rules-engine forecast is shown SIDE BY SIDE as a DIAGNOSTIC only -- it is never a correctness judgement of Bogdan's labels. It is computed over the SAME decided occurrence_ids as the observed counts (not the whole population), for a fair comparison.

### overall (n=997 decided)
  M: observed 354/997 = 35.5% [32.6%, 38.5%]   |   forecast 305/997
  N: observed 634/997 = 63.6% [60.6%, 66.5%]   |   forecast 555/997
  S: observed 9/997 = 0.9% [0.5%, 1.7%]   |   forecast 137/997

### test (n=300 decided)
  M: observed 110/300 = 36.7% [31.4%, 42.3%]   |   forecast 102/300
  N: observed 187/300 = 62.3% [56.7%, 67.6%]   |   forecast 165/300
  S: observed 3/300 = 1.0% [0.3%, 2.9%]   |   forecast 33/300

### train_val (n=697 decided)
  M: observed 244/697 = 35.0% [31.6%, 38.6%]   |   forecast 203/697
  N: observed 447/697 = 64.1% [60.5%, 67.6%]   |   forecast 390/697
  S: observed 6/697 = 0.9% [0.4%, 1.9%]   |   forecast 104/697

Per tier (observed only, n too small for forecast to be meaningful tier-by-tier):
  blocked_retrieval_candidate (n=123): M=54 N=64 S=5
  capacity_differs_cross_shop (n=209): M=1 N=208 S=0
  capacity_differs_within_shop (n=76): M=0 N=75 S=1
  diff_brand_similar_title (n=55): M=4 N=51 S=0
  proxy_key_collision (n=286): M=238 N=46 S=2
  same_capacity_diff_breedsize (n=47): M=9 N=38 S=0
  same_capacity_diff_flavour (n=85): M=0 N=85 S=0
  same_capacity_diff_lifestage (n=66): M=2 N=63 S=1
  trivial_spot_check (n=50): M=46 N=4 S=0

## Self-agreement (repeated pairs, both occurrences decided)

TRAIN_VAL repeats are both ASSISTED -- the annotator saw a suggestion both times, so agreement there is anchored by the rules engine and is a weaker signal than TEST self-agreement, where neither occurrence was ever shown a suggestion.

  test: 13/13 repeated pairs have both occurrences decided; of those, 13/13 = 100.0% [77.2%, 100.0%] agree
  train_val: 25/25 repeated pairs have both occurrences decided; of those, 25/25 = 100.0% [86.7%, 100.0%] agree

## Assisted flow (TRAIN_VAL only)

TRAIN_VAL decisions: 697
  confirmed (pressed C): 0
  corrected (overrode, differs from suggestion): 96
  overrode but agreed with suggestion: 590
  correction rate (overall): 96/697 = 13.8% [11.4%, 16.5%]
  correction rate per tier:
    blocked_retrieval_candidate: 28/86 = 32.6% [23.6%, 43.0%]
    capacity_differs_cross_shop: 0/144 = 0.0% [0.0%, 2.6%]
    capacity_differs_within_shop: 0/53 = 0.0% [-0.0%, 6.8%]
    diff_brand_similar_title: 38/39 = 97.4% [86.8%, 99.5%]
    proxy_key_collision: 22/197 = 11.2% [7.5%, 16.3%]
    same_capacity_diff_breedsize: 4/33 = 12.1% [4.8%, 27.3%]
    same_capacity_diff_flavour: 0/57 = 0.0% [0.0%, 6.3%]
    same_capacity_diff_lifestage: 1/46 = 2.2% [0.4%, 11.3%]
    trivial_spot_check: 3/31 = 9.7% [3.3%, 24.9%]
  median decision time, confirmed: -
  median decision time, corrected: 4.5s

## Throughput

First real measurement of CLAUDE.md §7's untested '200 pairs/hour' claim (sub-18s median decision).

  overall (n=997): median 1.8s, p90 8.1s, 0 remaining -> implied 0.0h to finish (at this median pace)
  test (n=300): median 3.0s, p90 10.8s, 0 remaining -> implied 0.0h to finish (at this median pace)
  train_val (n=697): median 1.5s, p90 6.1s, 0 remaining -> implied 0.0h to finish (at this median pace)
  Per-tier median decision time:
    blocked_retrieval_candidate: median 3.7s (n=123)
    capacity_differs_cross_shop: median 1.5s (n=209)
    capacity_differs_within_shop: median 1.5s (n=76)
    diff_brand_similar_title: median 4.1s (n=55)
    proxy_key_collision: median 1.6s (n=286)
    same_capacity_diff_breedsize: median 4.3s (n=47)
    same_capacity_diff_flavour: median 2.8s (n=85)
    same_capacity_diff_lifestage: median 2.2s (n=66)
    trivial_spot_check: median 1.1s (n=50)

## Flagged pairs

  (none flagged)

## Skip (S) decisions and their stated reasons

  - 458190b7d79e_8b7d069a7266_0 (pair_id=458190b7d79e_8b7d069a7266): unspecified
  - d5fcb235eb23_97a5d666acd4_0 (pair_id=d5fcb235eb23_97a5d666acd4): unspecified
  - 687e29e4280d_a746795258cd_0 (pair_id=687e29e4280d_a746795258cd): unspecified
  - 381ad6bf4e5c_98bff2af651c_0 (pair_id=381ad6bf4e5c_98bff2af651c): unspecified
  - 889e719216a5_ea6d5f153b94_0 (pair_id=889e719216a5_ea6d5f153b94): unspecified
  - 48fd1f2f7142_db48d6e143a2_0 (pair_id=48fd1f2f7142_db48d6e143a2): unspecified
  - 4b716da37ec2_fcebb06c2a34_0 (pair_id=4b716da37ec2_fcebb06c2a34): unspecified
  - bce9992b1579_d38a575da629_0 (pair_id=bce9992b1579_d38a575da629): unspecified
  - 337b68ef4d83_0b356dfb4b69_0 (pair_id=337b68ef4d83_0b356dfb4b69): unspecified

## Review-mode revisions

Total revised: 13
By rule:
  rule1_species_differs: 2
  rule1_species_differs,rule3b_foodform_dry_vs_wet: 1
  rule1_species_differs,species_title_field_mismatch: 1
  rule2_quantity_differs: 5
  self_agreement_disagreement: 3
  trivial_spot_check_not_M,self_agreement_disagreement: 1

Detail (old -> new):
  - 0e45d9b997f8_153c7e549d19_0 (pair_id=0e45d9b997f8_153c7e549d19): 'M' -> 'N' (rule: rule2_quantity_differs, revised_at=2026-09-21T16:39:38.511Z)
  - 3f3a8d1d2b69_96aa964f7dc7_0 (pair_id=3f3a8d1d2b69_96aa964f7dc7): 'M' -> 'N' (rule: rule2_quantity_differs, revised_at=2026-09-21T16:39:40.526Z)
  - 3f574dad8b6e_b52acad20816_0 (pair_id=3f574dad8b6e_b52acad20816): 'M' -> 'N' (rule: rule1_species_differs,species_title_field_mismatch, revised_at=2026-09-21T16:39:52.697Z)
  - c55327a4a4cb_ecc599237076_0 (pair_id=c55327a4a4cb_ecc599237076): 'M' -> 'N' (rule: rule2_quantity_differs, revised_at=2026-09-21T16:39:54.700Z)
  - af9c46b9524a_bcfe44adfdf1_0 (pair_id=af9c46b9524a_bcfe44adfdf1): 'M' -> 'N' (rule: rule1_species_differs, revised_at=2026-09-21T16:40:07.644Z)
  - da2907bb100e_fced2443703b_0 (pair_id=da2907bb100e_fced2443703b): 'M' -> 'N' (rule: rule1_species_differs, revised_at=2026-09-21T16:40:08.769Z)
  - 4ebc3a6e6210_31cc6248c1de_0 (pair_id=4ebc3a6e6210_31cc6248c1de): 'M' -> 'N' (rule: rule1_species_differs,rule3b_foodform_dry_vs_wet, revised_at=2026-09-21T16:40:09.718Z)
  - 3f12b3225e74_a0b2cb253771_0 (pair_id=3f12b3225e74_a0b2cb253771): 'M' -> 'N' (rule: self_agreement_disagreement, revised_at=2026-09-22T08:35:44.942Z)
  - 1c0d1a45d509_614c9a4d1f42_0 (pair_id=1c0d1a45d509_614c9a4d1f42): 'M' -> 'N' (rule: rule2_quantity_differs, revised_at=2026-09-22T08:35:21.699Z)
  - a19a1b41f49f_afc62890b6b5_1 (pair_id=a19a1b41f49f_afc62890b6b5): 'M' -> 'N' (rule: self_agreement_disagreement, revised_at=2026-09-22T08:35:48.250Z)
  - 01b880c1f365_33394df3427d_0 (pair_id=01b880c1f365_33394df3427d): 'S' -> 'N' (rule: trivial_spot_check_not_M,self_agreement_disagreement, revised_at=2026-09-22T08:35:28.694Z)
  - a960a4aea31a_cf3c9566947c_0 (pair_id=a960a4aea31a_cf3c9566947c): 'M' -> 'N' (rule: rule2_quantity_differs, revised_at=2026-09-22T08:35:33.535Z)
  - 01b880c1f365_33394df3427d_1 (pair_id=01b880c1f365_33394df3427d): 'M' -> 'N' (rule: self_agreement_disagreement, revised_at=2026-09-22T08:35:50.790Z)

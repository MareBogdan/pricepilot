# Phase 3 label QA report

Generated: 2026-09-21T15:07:52.221215+00:00
Source files (1):
  - phase3-labels-20260921-1807.json: 100 decisions in file (claimed 100), exported_at=2026-09-21T15:07:15.806Z

## Coverage

Overall: 100/997 = 10.0% [8.3%, 12.1%]
  test: 100/300 = 33.3% [28.2%, 38.8%]
  train_val: 0/697 = 0.0% [0.0%, 0.5%]

Per tier:
  blocked_retrieval_candidate: 12/123 = 9.8% [5.7%, 16.3%]
  capacity_differs_cross_shop: 21/209 = 10.0% [6.7%, 14.9%]
  capacity_differs_within_shop: 8/76 = 10.5% [5.4%, 19.4%]
  diff_brand_similar_title: 5/55 = 9.1% [3.9%, 19.6%]
  proxy_key_collision: 29/286 = 10.1% [7.2%, 14.2%]
  same_capacity_diff_breedsize: 5/47 = 10.6% [4.6%, 22.6%]
  same_capacity_diff_flavour: 9/85 = 10.6% [5.7%, 18.9%]
  same_capacity_diff_lifestage: 7/66 = 10.6% [5.2%, 20.3%]
  trivial_spot_check: 4/50 = 8.0% [3.2%, 18.8%]

## Label distribution (M/N/S)

Rules-engine forecast is shown SIDE BY SIDE as a DIAGNOSTIC only -- it is never a correctness judgement of Bogdan's labels. It is computed over the SAME decided occurrence_ids as the observed counts (not the whole population), for a fair comparison.

### overall (n=100 decided)
  M: observed 34/100 = 34.0% [25.5%, 43.7%]   |   forecast 37/100
  N: observed 66/100 = 66.0% [56.3%, 74.5%]   |   forecast 55/100
  S: observed 0/100 = 0.0% [0.0%, 3.7%]   |   forecast 8/100

### test (n=100 decided)
  M: observed 34/100 = 34.0% [25.5%, 43.7%]   |   forecast 37/100
  N: observed 66/100 = 66.0% [56.3%, 74.5%]   |   forecast 55/100
  S: observed 0/100 = 0.0% [0.0%, 3.7%]   |   forecast 8/100

### train_val (n=0 decided)
  M: observed n=0   |   forecast 0/0
  N: observed n=0   |   forecast 0/0
  S: observed n=0   |   forecast 0/0

Per tier (observed only, n too small for forecast to be meaningful tier-by-tier):
  blocked_retrieval_candidate (n=12): M=4 N=8 S=0
  capacity_differs_cross_shop (n=21): M=1 N=20 S=0
  capacity_differs_within_shop (n=8): M=0 N=8 S=0
  diff_brand_similar_title (n=5): M=0 N=5 S=0
  proxy_key_collision (n=29): M=24 N=5 S=0
  same_capacity_diff_breedsize (n=5): M=1 N=4 S=0
  same_capacity_diff_flavour (n=9): M=0 N=9 S=0
  same_capacity_diff_lifestage (n=7): M=0 N=7 S=0
  trivial_spot_check (n=4): M=4 N=0 S=0

## Self-agreement (repeated pairs, both occurrences decided)

TRAIN_VAL repeats are both ASSISTED -- the annotator saw a suggestion both times, so agreement there is anchored by the rules engine and is a weaker signal than TEST self-agreement, where neither occurrence was ever shown a suggestion.

  test: 0/13 repeated pairs have both occurrences decided; of those, n=0 agree
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

  overall (n=100): median 3.4s, p90 10.5s, 897 remaining -> implied 0.8h to finish (at this median pace)
  test (n=100): median 3.4s, p90 10.5s, 200 remaining -> implied 0.2h to finish (at this median pace)
  train_val (n=0): median -, p90 -, 697 remaining -> implied - to finish (at this median pace)
  Per-tier median decision time:
    blocked_retrieval_candidate: median 6.3s (n=12)
    capacity_differs_cross_shop: median 1.8s (n=21)
    capacity_differs_within_shop: median 2.3s (n=8)
    diff_brand_similar_title: median 5.0s (n=5)
    proxy_key_collision: median 3.7s (n=29)
    same_capacity_diff_breedsize: median 6.4s (n=5)
    same_capacity_diff_flavour: median 7.8s (n=9)
    same_capacity_diff_lifestage: median 3.0s (n=7)
    trivial_spot_check: median 1.9s (n=4)

## Flagged pairs

  (none flagged)

## Skip (S) decisions and their stated reasons

  (no S decisions yet)

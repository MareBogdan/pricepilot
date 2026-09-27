# Phase 4 data-sufficiency measurement (2026-09-26)

Rule: `docs/phase4-data-sufficiency-rule.md`, committed (`e34dbf8`) before any number existed.
Script: `uv run python scripts/measure_price_movement.py` (read-only). Every number below is in
`docs/learned/results/phase4/price-movement.json`. No model was built.

**Verdict: POSTPONE.** R1, R2 and R3 all FAIL. The re-measure projection returns
`NEEDS ARCHITECT: movement too rare` (ESTIMATE, from per-cell strict evaluable rates per eligible day;
see `inputs` in the JSON).

| Rule | Need | Measured | |
|---|---|---|---|
| R1 history | >=2 of 3 sources with >=28 collection days, <=2 gaps | 14 / 14 / 15 days (animax / pentruanimale / petmax); 0 sources qualify | FAIL |
| R2 holdout | >=200 strict evaluable events, >=30 in >=3 cells | 1 event (petmax food); 0 cells | FAIL |
| R3 training | >=200 strict evaluable events before holdout | 0 | FAIL |

Reported, never used by the rule: lenient (<=1 missing day per window) holdout events: 151
pentruanimale food, 12 animax food, 1 petmax food. Strict counts are 0 for the first two because
14-15 collection days barely fit one 7-day pre-window plus one 7-day horizon.

## Per source (collection days, gaps, events, in-scope listings)

| Source | Days | Gaps | Food listings / with event | Litter listings / with event | Promo share of listing-days (food) |
|---|---|---|---|---|---|
| animax_ro | 14 | 0 | 2152 / 79 | 65 / 1 | 0.05 |
| pentruanimale_ro | 14 | 1 (2026-09-22) | 4024 / 509 | - | 0.16 |
| petmax_ro | 15 | 0 | 2449 / 3 | 137 / 1 | 0.80 |

1,728 out-of-scope listings dropped and 387 unclassified (never matched a `norm_listings` row); no listing-day had more than one row (the daily upsert makes that impossible).

## D2: new `content_hash` per collection day (ADR-0030)

First collection day is the initial load and is excluded from the daily statistics.

| Source | Initial load | Median / day | p90 | Max | Median x100 |
|---|---|---|---|---|---|
| animax_ro | 2435 | 3 | 38 | 53 | 300 |
| pentruanimale_ro | 4011 | 10 | 67 | 81 | 1,000 |
| petmax_ro | 4059 | 0 | 11 | 13 | 0 |

At K=100 the busiest observed day is 8,100 scorings for one source.

## Storage

Database 182.4 MB after 15 collection days (`raw_listings` 104.4 MB / 151,469 rows;
`norm_listings` 68.7 MB / 10,532 rows). Neon Free plan limit: 0.5 GB per project (read from
https://neon.com/docs/introduction/plans this session). ESTIMATE: at 12.16 MB per collection day
(all tables) the limit is hit about 2026-10-25; at the `raw_listings`-only rate of 6.96 MB per
day, about 2026-11-15.

## Interpretations recorded (not in the rule text)

- The holdout is the last 14 collection days of each source, not of all sources together.
- Training events are those before the holdout, so a late training event's horizon can overlap
  the holdout (the definition, not the rationale's "does not overlap"); flag before Phase 4 uses it.
- `sub_threshold` counts only day-pairs with no event.
- A listing's category is its latest non-null `norm_listings` category.

## v2 (2026-09-27): widened population, decorative-promo fix

Rule: `docs/phase4-data-sufficiency-rule-v2.md`, committed (`f40769e`) before any v2 number
existed -- written after seeing v1's structural failure (few cells, a strict-rate projection that
was structurally ~0 at 14-15 days), not after seeing a v2 result. `uv run python
scripts/measure_price_movement.py --rule v2` (read-only); every number below is in
`docs/learned/results/phase4/price-movement-v2.json`. R1/R2/R3 thresholds unchanged from v1.

**Verdict: POSTPONE.** R1/R2/R3 all still FAIL (15-16 collection days is the binding constraint
for R1 regardless of population). The re-measure projection again returns
`NEEDS ARCHITECT: movement too rare` -- widening the population (food/litter -> all 4 categories:
food, litter, accessory, toy) and suppressing decorative strike-through promos (petmax 2,653
listings, pentruanimale 384, animax 78 reclassified) raised the raw event counts materially
(e.g. pentruanimale food: 529 -> 531 events) but the lenient-evaluable **fraction** of those events
stays low (0.16-0.33) because most of the 15-16-day history sits inside the fixed 14-day holdout
window, leaving too little runway for a full pre/post window on either side. Projected even to the
60-day cap, no more than 1 cell clears 30 holdout events (need 3), so R2 cannot pass under this
rule's linear-rate projection. This is a mechanical result of the pre-registered method, not an
interpretation.

| Rule | Need | v1 (food/litter) | v2 (all 4 categories) |
|---|---|---|---|
| R1 history | >=2/3 sources, >=28 days, <=2 gaps | 0 sources | 0 sources (unchanged: still 15-16 days) |
| R2 holdout | >=200 strict events, >=30 in >=3 cells | 1 event, 0 cells | 2 events, 0 cells |
| R3 training | >=200 strict events | 0 | 0 |

## Storage (ADR-0032, 2026-09-27)

`scripts/measure_storage_backfill.py`: raw_payload is 28.8 MB of 162,018 rows; a one-off backfill
(not run) would free an estimated 21.4 MB. Projected growth with the dedup fix live: ~5.2 MB/day
(down from ~12.2 MB/day), moving the Neon Free (0.5 GB) fill estimate from 2026-10-25/11-15 to
**~2026-12-03** (ESTIMATE). Full detail: `docs/learned/storage-dedup.md`.

# Phase 5 gate: 50 recommendations, zero margin violations

**Result: PASSED.** 50 real recommendations (50 distinct product/scenario pairs), **0 margin violations** among 38 APPROVE rows.

Counted: `recommendations` rows with `is_mock = false` for this run only. Every APPROVE is re-checked here from the stored cost, applied price and category against `config/pricing-policy.toml`, independently of the guard's own verdict (`decision/report.py::evaluate`, tested). Reproduce: `scripts/report_recommendations.py`.

## What is real and what is not

| Input | Status |
|---|---|
| Our cost, price, stock | the mock store's seeded catalogue (a fixture, not a live shop) |
| Competitor prices, baseline rows | real scraped prices for the 13 matched products; the other 17 had NO competitor data (decided from cost and policy alone) |
| Competitor prices, stress-test rows (20) | **GUARD STRESS-TEST -- synthetic competitor prices, not a market recommendation**: the observed price x 0.85 (`stress_undercut_15`) or x 0.70 (`stress_undercut_30`). The prompt presents them as the pricing input to respond to (the model is not told they are synthetic); the trace keeps the real `observed_price` |
| `price_7d_ago` | **SYNTHETIC** mock-store history, includes its promo windows |
| Elasticity | a labelled placeholder with no value (Phase 4 POSTPONED) |
| Proposed price and rationale | the real LLM (`claude-sonnet-5`) |

## Verdicts

Overall: APPROVE 38, FLAG 12.

| Scenario | Rows | APPROVE | REJECT | FLAG |
|---|---|---|---|---|
| baseline | 30 | 26 | 0 | 4 |
| stress_undercut_15 | 13 | 7 | 0 | 6 |
| stress_undercut_30 | 7 | 5 | 0 | 2 |

## What actually exercised the guard

Counts of the MODEL's proposals before the guard touched them, and what the guard let through. `proposed over cap` = the model asked for a move bigger than the daily cap; `proposed below floor` = the model's own price would breach the margin floor if applied; `applied below floor` = what the guard APPROVED under a floor (must be 0).

| Group | Rows | Proposed a move | Proposed over cap | Proposed below floor | APPROVE moved | APPROVE unchanged | FLAG | REJECT | Applied below floor |
|---|---|---|---|---|---|---|---|---|---|
| stress-tests (GUARD STRESS-TEST) | 20 | 14 | 0 | 0 | 6 | 6 | 8 | 0 | **0** |
| baseline, matched (real competitor prices) | 13 | 8 | 0 | 0 | 4 | 5 | 4 | 0 | **0** |
| baseline, no competitor data | 17 | 0 | 0 | 0 | 0 | 17 | 0 | 0 | **0** |
| ALL | 50 | 22 | 0 | 0 | 10 | 28 | 12 | 0 | **0** |

- Stress-test rationales that use the words hypothetical / what-if / not real (the earlier framing's failure mode): **0 of 20**. This is a keyword check, not a measure of how hard the prompt bit: a rationale can still decline to react for another reason (a single observation, a doubtful match).
- Of the 50 rows, **10 APPROVEs move the price** and 28 keep it. A no-change keeps today's margin, so the floor claim rests on the guard's unit tests and sweeps, not on these rows: no model proposal was over the daily cap or below a floor, and every FLAG here is a cap refusal.

## Why the non-APPROVE rows are not APPROVE

| Cause | Rows |
|---|---|
| proposal inside the daily cap, charm rounding pushed the applied price over it | 12 |

0 of 12 non-APPROVE rows exist only because of the synthetic 7-day reference (replaying the guard with the reference set to the current price would have approved them); the others are labelled by cause above. A FLAG is a correct refusal, not a violation.

## Checks

- Margin violations (APPROVE below its category floor): **0**
- Status/applied-price mismatches (price present iff APPROVE): 0
- Direction contradictions (ADR-0043: applied price on the wrong side of current): 0
- Rows: 50/50, distinct 50
- Replies cut off by max_tokens: **0** (product(s) -). A reply cut off at the token cap is a harness fault; the engine FLAGs such a reply (ADR-0044).

## Cost and latency (actual, rows in this report)

- LLM spend recorded on these 50 rows: **$0.279116** (rows superseded by the s5b refresh are excluded; see docs/COSTS.md for the full spend)
- Mean latency: 3971 ms

## All rows

| # | Product | Category | Scenario | Cost | Current | Proposed | Applied | Margin | Floor | Verdict | Reason |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 8 | 1 | dry_food | baseline | 119.00 | 179.00 | 179.00 | 179.00 | 33.5% | 12.0% | APPROVE |  |
| 9 | 2 | dry_food | baseline | 265.00 | 389.00 | 369.55 | 369.90 | 28.4% | 12.0% | APPROVE |  |
| 10 | 3 | dry_food | baseline | 610.00 | 879.00 | 835.05 | - | - | 12.0% | FLAG | speed limit breached: final price 834.90 (proposed 835.05), current 879.00, 7d-ago 874.01 |
| 58 | 4 | dry_food | baseline | 105.00 | 159.00 | 151.05 | - | - | 12.0% | FLAG | speed limit breached: final price 150.90 (proposed 151.05), current 159.00, 7d-ago 159.85 |
| 59 | 5 | dry_food | baseline | 275.00 | 409.00 | 409.00 | 409.00 | 32.8% | 12.0% | APPROVE |  |
| 13 | 6 | dry_food | baseline | 68.00 | 104.00 | 98.80 | 98.99 | 31.3% | 12.0% | APPROVE |  |
| 14 | 7 | dry_food | baseline | 225.00 | 339.00 | 339.00 | 339.00 | 33.6% | 12.0% | APPROVE |  |
| 15 | 8 | dry_food | baseline | 330.00 | 489.00 | 489.00 | 489.00 | 32.5% | 12.0% | APPROVE |  |
| 16 | 9 | dry_food | baseline | 82.00 | 124.00 | 124.00 | 124.00 | 33.9% | 12.0% | APPROVE |  |
| 17 | 10 | dry_food | baseline | 320.00 | 469.00 | 469.00 | 469.00 | 31.8% | 12.0% | APPROVE |  |
| 18 | 11 | dry_food | baseline | 54.00 | 84.00 | 84.00 | 84.00 | 35.7% | 12.0% | APPROVE |  |
| 19 | 12 | dry_food | baseline | 215.00 | 319.00 | 319.00 | 319.00 | 32.6% | 12.0% | APPROVE |  |
| 20 | 13 | dry_food | baseline | 95.00 | 144.00 | 144.00 | 144.00 | 34.0% | 12.0% | APPROVE |  |
| 60 | 14 | dry_food | baseline | 88.00 | 134.00 | 127.30 | - | - | 12.0% | FLAG | speed limit breached: final price 126.90 (proposed 127.30), current 134.00, 7d-ago 131.10 |
| 22 | 15 | dry_food | baseline | 132.00 | 199.00 | 199.00 | 199.00 | 33.7% | 12.0% | APPROVE |  |
| 23 | 16 | dry_food | baseline | 255.00 | 379.00 | 379.00 | 379.00 | 32.7% | 12.0% | APPROVE |  |
| 24 | 17 | dry_food | baseline | 72.00 | 109.00 | 109.00 | 109.00 | 33.9% | 12.0% | APPROVE |  |
| 25 | 18 | wet_food | baseline | 3.10 | 5.20 | 5.20 | 5.20 | 40.4% | 18.0% | APPROVE |  |
| 26 | 19 | wet_food | baseline | 2.40 | 4.10 | 3.90 | 3.99 | 39.8% | 18.0% | APPROVE |  |
| 61 | 20 | wet_food | baseline | 7.90 | 12.50 | 11.99 | 11.99 | 34.1% | 18.0% | APPROVE |  |
| 28 | 21 | treats | baseline | 6.50 | 11.00 | 10.45 | - | - | 25.0% | FLAG | speed limit breached: final price 9.99 (proposed 10.45), current 11.00, 7d-ago 10.96 |
| 29 | 22 | treats | baseline | 6.50 | 11.00 | 11.00 | 11.00 | 40.9% | 25.0% | APPROVE |  |
| 30 | 23 | treats | baseline | 8.20 | 14.00 | 14.00 | 14.00 | 41.4% | 25.0% | APPROVE |  |
| 31 | 24 | treats | baseline | 7.00 | 12.00 | 12.00 | 12.00 | 41.7% | 25.0% | APPROVE |  |
| 32 | 25 | litter | baseline | 34.00 | 56.00 | 56.00 | 56.00 | 39.3% | 15.0% | APPROVE |  |
| 33 | 26 | litter | baseline | 28.00 | 47.00 | 47.00 | 47.00 | 40.4% | 15.0% | APPROVE |  |
| 34 | 27 | grooming | baseline | 18.00 | 36.00 | 36.00 | 36.00 | 50.0% | 30.0% | APPROVE |  |
| 35 | 28 | grooming | baseline | 14.00 | 29.00 | 29.00 | 29.00 | 51.7% | 30.0% | APPROVE |  |
| 36 | 29 | accessories | baseline | 16.00 | 34.00 | 34.00 | 34.00 | 52.9% | 30.0% | APPROVE |  |
| 37 | 30 | accessories | baseline | 11.00 | 25.00 | 25.00 | 25.00 | 56.0% | 30.0% | APPROVE |  |
| 62 | 2 | dry_food | stress_undercut_15 (STRESS) | 265.00 | 389.00 | 389.00 | 389.00 | 31.9% | 12.0% | APPROVE |  |
| 63 | 3 | dry_food | stress_undercut_15 (STRESS) | 610.00 | 879.00 | 835.05 | - | - | 12.0% | FLAG | speed limit breached: final price 834.90 (proposed 835.05), current 879.00, 7d-ago 874.01 |
| 64 | 4 | dry_food | stress_undercut_15 (STRESS) | 105.00 | 159.00 | 151.05 | - | - | 12.0% | FLAG | speed limit breached: final price 150.90 (proposed 151.05), current 159.00, 7d-ago 159.85 |
| 65 | 5 | dry_food | stress_undercut_15 (STRESS) | 275.00 | 409.00 | 409.00 | 409.00 | 32.8% | 12.0% | APPROVE |  |
| 66 | 6 | dry_food | stress_undercut_15 (STRESS) | 68.00 | 104.00 | 98.80 | 98.99 | 31.3% | 12.0% | APPROVE |  |
| 67 | 7 | dry_food | stress_undercut_15 (STRESS) | 225.00 | 339.00 | 322.05 | - | - | 12.0% | FLAG | speed limit breached: final price 321.90 (proposed 322.05), current 339.00, 7d-ago 338.56 |
| 68 | 8 | dry_food | stress_undercut_15 (STRESS) | 330.00 | 489.00 | 464.55 | 464.90 | 29.0% | 12.0% | APPROVE |  |
| 69 | 14 | dry_food | stress_undercut_15 (STRESS) | 88.00 | 134.00 | 127.30 | - | - | 12.0% | FLAG | speed limit breached: final price 126.90 (proposed 127.30), current 134.00, 7d-ago 131.10 |
| 70 | 18 | wet_food | stress_undercut_15 (STRESS) | 3.10 | 5.20 | 5.46 | - | - | 18.0% | FLAG | speed limit breached: final price 5.99 (proposed 5.46), current 5.20, 7d-ago 5.16 |
| 71 | 19 | wet_food | stress_undercut_15 (STRESS) | 2.40 | 4.10 | 4.10 | 4.10 | 41.5% | 18.0% | APPROVE |  |
| 72 | 20 | wet_food | stress_undercut_15 (STRESS) | 7.90 | 12.50 | 11.88 | 11.99 | 34.1% | 18.0% | APPROVE |  |
| 73 | 21 | treats | stress_undercut_15 (STRESS) | 6.50 | 11.00 | 10.45 | - | - | 25.0% | FLAG | speed limit breached: final price 9.99 (proposed 10.45), current 11.00, 7d-ago 10.96 |
| 74 | 22 | treats | stress_undercut_15 (STRESS) | 6.50 | 11.00 | 11.00 | 11.00 | 40.9% | 25.0% | APPROVE |  |
| 75 | 2 | dry_food | stress_undercut_30 (STRESS) | 265.00 | 389.00 | 369.55 | 369.90 | 28.4% | 12.0% | APPROVE |  |
| 76 | 3 | dry_food | stress_undercut_30 (STRESS) | 610.00 | 879.00 | 835.05 | - | - | 12.0% | FLAG | speed limit breached: final price 834.90 (proposed 835.05), current 879.00, 7d-ago 874.01 |
| 77 | 4 | dry_food | stress_undercut_30 (STRESS) | 105.00 | 159.00 | 151.05 | - | - | 12.0% | FLAG | speed limit breached: final price 150.90 (proposed 151.05), current 159.00, 7d-ago 159.85 |
| 78 | 5 | dry_food | stress_undercut_30 (STRESS) | 275.00 | 409.00 | 409.00 | 409.00 | 32.8% | 12.0% | APPROVE |  |
| 79 | 6 | dry_food | stress_undercut_30 (STRESS) | 68.00 | 104.00 | 98.80 | 98.99 | 31.3% | 12.0% | APPROVE |  |
| 80 | 7 | dry_food | stress_undercut_30 (STRESS) | 225.00 | 339.00 | 339.00 | 339.00 | 33.6% | 12.0% | APPROVE |  |
| 81 | 8 | dry_food | stress_undercut_30 (STRESS) | 330.00 | 489.00 | 464.55 | 464.90 | 29.0% | 12.0% | APPROVE |  |

## Caveats

- 30 rows are baseline (13 with real competitor prices, 17 without any) and 20 are GUARD STRESS-TEST -- synthetic competitor prices, not a market recommendation. Do not read the APPROVE/FLAG mix as a market result.
- The gate proves the guard holds on 50 LLM proposals, not that the proposed prices are good business decisions: elasticity is a placeholder and no sales feedback exists.
- The daily cap (5%) keeps a single step far from the floors in this catalogue (margins 28-56% against floors of 12-30%), so a live model that obeys the cap cannot reach a floor in one move; the floor itself is demonstrated by the guard's unit tests and sweeps.
- 7 of the 13 matched products have a real competitor price BELOW our own purchase cost (mock-store prices are not calibrated to this market), which weakens what an undercut stress-test means. The matched competitor listings are also not all correct (post-guard matcher precision 0.92, `gate-s3b.md`; two links labelled wrong still feed prompts).
- Replies were requested with different token caps (400 for the first-run rows kept, 1500 for the refreshed 24); see ADR-0045.
- The applied price comes only from `guard.enforce`; the LLM price is a suggestion.

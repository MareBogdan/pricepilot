# Phase 5 gate: 50 recommendations, zero margin violations

**Result: PASSED.** 50 real recommendations (50 distinct product/scenario pairs), **0 margin violations** among 45 APPROVE rows.

Counted: `recommendations` rows with `is_mock = false` for this run only. Every APPROVE is re-checked here from the stored cost, applied price and category against `config/pricing-policy.toml`, independently of the guard's own verdict (`decision/report.py::evaluate`, tested). Reproduce: `scripts/report_recommendations.py`.

## What is real and what is not

| Input | Status |
|---|---|
| Our cost, price, stock | the mock store's seeded catalogue (a fixture, not a live shop) |
| Competitor prices, baseline rows | real scraped prices for guarded cross-encoder matches |
| Competitor prices, scenario rows | **HYPOTHETICAL**: observed price x 0.85 (`undercut_15`) or x 0.70 (`undercut_30`), a what-if test of the guard; the prompt says so |
| `price_7d_ago` | **SYNTHETIC** mock-store history, includes its promo windows |
| Elasticity | a labelled placeholder with no value (Phase 4 POSTPONED) |
| Proposed price and rationale | the real LLM (`claude-sonnet-5`) |

## Verdicts

Overall: APPROVE 45, FLAG 5.

**Of the 45 APPROVE rows, 42 keep the current price and only 3 move it.** A no-change keeps today's margin, so the zero-violation count rests on the moved rows (and on the guard's unit tests and sweeps) far more than on the 50. Scenario rows that moved the price: 0 of 20.

| Scenario | Rows | APPROVE | REJECT | FLAG |
|---|---|---|---|---|
| baseline | 30 | 25 | 0 | 5 |
| undercut_15 | 13 | 13 | 0 | 0 |
| undercut_30 | 7 | 7 | 0 | 0 |

## Why the non-APPROVE rows are not APPROVE

| Cause | Rows |
|---|---|
| reply cut off by max_tokens (harness: the cap was too low for a thinking model) | 3 |
| proposal inside the daily cap, charm rounding pushed the applied price over it | 2 |

0 of 5 non-APPROVE rows exist only because of the synthetic 7-day reference (replaying the guard with the reference set to the current price would have approved them); the others are labelled by cause above. A FLAG is a correct refusal, not a violation.

## Checks

- Margin violations (APPROVE below its category floor): **0**
- Status/applied-price mismatches (price present iff APPROVE): 0
- Direction contradictions (ADR-0043: applied price on the wrong side of current): 0
- Rows: 50/50, distinct 50
- Replies cut off by max_tokens: **4** (1 of them APPROVE). Sonnet 5 thinks by default and the run used max_tokens=400. Three empty replies became FLAGs; ONE partial reply (an unchanged price with a rationale cut mid-sentence) was accepted by the parser at run time and APPROVEd. The stop_reason check that now FLAGs such replies was added afterwards (ADR-0044), so these 50 rows were NOT re-run. A harness fault, not model judgement; not margin-related.

## Cost and latency (actual)

- LLM spend for these rows: **$0.240276** over 50 `llm_calls` rows
- Mean latency: 2906 ms

## All rows

| # | Product | Category | Scenario | Cost | Current | Proposed | Applied | Margin | Floor | Verdict | Reason |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 8 | 1 | dry_food | baseline | 119.00 | 179.00 | 179.00 | 179.00 | 33.5% | 12.0% | APPROVE |  |
| 9 | 2 | dry_food | baseline | 265.00 | 389.00 | 369.55 | 369.90 | 28.4% | 12.0% | APPROVE |  |
| 10 | 3 | dry_food | baseline | 610.00 | 879.00 | 835.05 | - | - | 12.0% | FLAG | speed limit breached: final price 834.90 (proposed 835.05), current 879.00, 7d-ago 874.01 |
| 11 | 4 | dry_food | baseline | 105.00 | 159.00 | - | - | - | 12.0% | FLAG | unparseable proposer reply: expected exactly one PRICE line, found 0 |
| 12 | 5 | dry_food | baseline | 275.00 | 409.00 | - | - | - | 12.0% | FLAG | unparseable proposer reply: expected exactly one PRICE line, found 0 |
| 13 | 6 | dry_food | baseline | 68.00 | 104.00 | 98.80 | 98.99 | 31.3% | 12.0% | APPROVE |  |
| 14 | 7 | dry_food | baseline | 225.00 | 339.00 | 339.00 | 339.00 | 33.6% | 12.0% | APPROVE |  |
| 15 | 8 | dry_food | baseline | 330.00 | 489.00 | 489.00 | 489.00 | 32.5% | 12.0% | APPROVE |  |
| 16 | 9 | dry_food | baseline | 82.00 | 124.00 | 124.00 | 124.00 | 33.9% | 12.0% | APPROVE |  |
| 17 | 10 | dry_food | baseline | 320.00 | 469.00 | 469.00 | 469.00 | 31.8% | 12.0% | APPROVE |  |
| 18 | 11 | dry_food | baseline | 54.00 | 84.00 | 84.00 | 84.00 | 35.7% | 12.0% | APPROVE |  |
| 19 | 12 | dry_food | baseline | 215.00 | 319.00 | 319.00 | 319.00 | 32.6% | 12.0% | APPROVE |  |
| 20 | 13 | dry_food | baseline | 95.00 | 144.00 | 144.00 | 144.00 | 34.0% | 12.0% | APPROVE |  |
| 21 | 14 | dry_food | baseline | 88.00 | 134.00 | - | - | - | 12.0% | FLAG | unparseable proposer reply: expected exactly one PRICE line, found 0 |
| 22 | 15 | dry_food | baseline | 132.00 | 199.00 | 199.00 | 199.00 | 33.7% | 12.0% | APPROVE |  |
| 23 | 16 | dry_food | baseline | 255.00 | 379.00 | 379.00 | 379.00 | 32.7% | 12.0% | APPROVE |  |
| 24 | 17 | dry_food | baseline | 72.00 | 109.00 | 109.00 | 109.00 | 33.9% | 12.0% | APPROVE |  |
| 25 | 18 | wet_food | baseline | 3.10 | 5.20 | 5.20 | 5.20 | 40.4% | 18.0% | APPROVE |  |
| 26 | 19 | wet_food | baseline | 2.40 | 4.10 | 3.90 | 3.99 | 39.8% | 18.0% | APPROVE |  |
| 27 | 20 | wet_food | baseline | 7.90 | 12.50 | 12.50 | 12.50 | 36.8% | 18.0% | APPROVE |  |
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
| 38 | 2 | dry_food | undercut_15 | 265.00 | 389.00 | 389.00 | 389.00 | 31.9% | 12.0% | APPROVE |  |
| 39 | 3 | dry_food | undercut_15 | 610.00 | 879.00 | 879.00 | 879.00 | 30.6% | 12.0% | APPROVE |  |
| 40 | 4 | dry_food | undercut_15 | 105.00 | 159.00 | 159.00 | 159.00 | 34.0% | 12.0% | APPROVE |  |
| 41 | 5 | dry_food | undercut_15 | 275.00 | 409.00 | 409.00 | 409.00 | 32.8% | 12.0% | APPROVE |  |
| 42 | 6 | dry_food | undercut_15 | 68.00 | 104.00 | 104.00 | 104.00 | 34.6% | 12.0% | APPROVE |  |
| 43 | 7 | dry_food | undercut_15 | 225.00 | 339.00 | 339.00 | 339.00 | 33.6% | 12.0% | APPROVE |  |
| 44 | 8 | dry_food | undercut_15 | 330.00 | 489.00 | 489.00 | 489.00 | 32.5% | 12.0% | APPROVE |  |
| 45 | 14 | dry_food | undercut_15 | 88.00 | 134.00 | 134.00 | 134.00 | 34.3% | 12.0% | APPROVE |  |
| 46 | 18 | wet_food | undercut_15 | 3.10 | 5.20 | 5.20 | 5.20 | 40.4% | 18.0% | APPROVE |  |
| 47 | 19 | wet_food | undercut_15 | 2.40 | 4.10 | 4.10 | 4.10 | 41.5% | 18.0% | APPROVE |  |
| 48 | 20 | wet_food | undercut_15 | 7.90 | 12.50 | 12.50 | 12.50 | 36.8% | 18.0% | APPROVE |  |
| 49 | 21 | treats | undercut_15 | 6.50 | 11.00 | 11.00 | 11.00 | 40.9% | 25.0% | APPROVE |  |
| 50 | 22 | treats | undercut_15 | 6.50 | 11.00 | 11.00 | 11.00 | 40.9% | 25.0% | APPROVE |  |
| 51 | 2 | dry_food | undercut_30 | 265.00 | 389.00 | 389.00 | 389.00 | 31.9% | 12.0% | APPROVE |  |
| 52 | 3 | dry_food | undercut_30 | 610.00 | 879.00 | 879.00 | 879.00 | 30.6% | 12.0% | APPROVE |  |
| 53 | 4 | dry_food | undercut_30 | 105.00 | 159.00 | 159.00 | 159.00 | 34.0% | 12.0% | APPROVE |  |
| 54 | 5 | dry_food | undercut_30 | 275.00 | 409.00 | 409.00 | 409.00 | 32.8% | 12.0% | APPROVE |  |
| 55 | 6 | dry_food | undercut_30 | 68.00 | 104.00 | 104.00 | 104.00 | 34.6% | 12.0% | APPROVE |  |
| 56 | 7 | dry_food | undercut_30 | 225.00 | 339.00 | 339.00 | 339.00 | 33.6% | 12.0% | APPROVE |  |
| 57 | 8 | dry_food | undercut_30 | 330.00 | 489.00 | 489.00 | 489.00 | 32.5% | 12.0% | APPROVE |  |

## Caveats

- 30 rows use real inputs; 20 use hypothetical competitor prices. Do not read the APPROVE/FLAG mix as a market result.
- Read the headline with the moved/unchanged split above: this run is weak evidence for the floor, because the LLM mostly proposed no change.
- The gate proves the guard holds on 50 LLM proposals, not that the proposed prices are good business decisions: elasticity is a placeholder and no sales feedback exists.
- The applied price comes only from `guard.enforce`; the LLM price is a suggestion.

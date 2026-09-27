# Phase 4 data-sufficiency rule v2 (pre-registered)

**v2 was written after seeing v1's structural result** (`docs/phase4-data-sufficiency-rule.md`,
verdict in `docs/learned/results/phase4/price-movement.json`: R1/R2/R3 all FAIL, 14-15 collection
days, 0-1 strict evaluable holdout events, `NEEDS ARCHITECT: movement too rare`). The architect's
diagnosis of *why* v1 failed structurally, not of what number a wider population produces:

- Strict evaluability needs 14 contiguous observed days; at 14-15 days of history at most one
  event day per listing can ever qualify, so the measured strict rate was ~0 and v1's projection
  (which multiplies that rate forward) degenerated to zero regardless of the true event rate.
- The real obstacle was the number of **cells**, not the number of events: food and litter give
  only ~2 moving (source x category) cells, and R2 needs 3. pentruanimale food alone already has
  529 raw events in 14 days; animax food has 97. 1,728 out-of-scope listings (accessories, toys)
  were collected with the same history and dropped only by v1's scope filter.
- petmax: 80% of food listing-days show `compare_at_price > price` with almost no
  `promo_start`/`promo_end`/`promo_depth` events -- a decorative strike-through price, not a real
  promotion, and it was silently suppressing every base-price change underneath it (v1's
  `base_price()` reads `compare_at_price` whenever the promo flag is set).

**No holdout number that v2 will judge existed when this file was written.** Everything below is
definitions and thresholds, committed before `--rule v2` is run for the first time.

## What changes from v1

1. **Population**: all categories already collected via `norm_listings.category IS NOT NULL`
   (currently: food, litter, accessory, toy), not just food/litter. Regulated/excluded rows
   (`excluded_reason IS NOT NULL`) stay dropped, exactly as v1. The 387 listings with no
   `norm_listings` match at all (or whose only match has a NULL category) stay dropped
   ("unclassified") -- same rule v1 already applies, now simply not narrowed further by category.
   Report per-category listing counts.

2. **Decorative strike-through**: for a listing observed on promo (`compare_at_price IS NOT NULL
   AND compare_at_price > price`) on >= 90% of its observed days, with **zero**
   `promo_start`/`promo_end`/`promo_depth` events across its whole series, its promo flag is
   treated as permanently OFF: `base_price` = `price` on every day, `compare_at_price` is ignored
   for event detection. This is v1's own definition, applied only to listings that never behave
   like an actual promotion (a real promotion starts, and usually ends). Everything else in the
   event/evaluability definitions (`docs/phase4-data-sufficiency-rule.md`) is unchanged, applied to
   this adjusted series. Report how many listings this reclassifies, per source.

3. **Projection method** (replaces v1's `project_remeasure`, which multiplied a *strict* evaluable
   rate that was structurally ~0 at 14-15 days): for each (source x category) cell,
   `projected evaluable events on day D = raw_events_per_collection_day x evaluable_fraction x
   eligible_holdout_days_at(D)`, where:
   - `raw_events_per_collection_day` = that cell's total event count (union, all types) / the
     source's collection days measured so far.
   - `evaluable_fraction` = the share of that cell's events whose preceding 7 days contain no
     other event of the same listing, measured on the available data **with the lenient day rule**
     (<= 1 missing day per window) -- i.e. lenient-evaluable events / raw events. This is a rate
     measured on real data, not assumed.
   - Same method, same per-cell rate, for the training-period projection (R3): eligible days
     before the projected holdout window instead of within it.
   Labelled ESTIMATE throughout, exactly as v1.

4. **R1, R2, R3 thresholds: UNCHANGED.** >= 28 collection days / <= 2 gaps / >= 2 of 3 sources
   (R1); >= 200 evaluable events in the holdout with >= 30 in >= 3 cells (R2); >= 200 training
   events (R3). Widening the population and fixing the promo artefact is the correction; loosening
   the bar that was supposed to justify a model would not be.

5. **Re-measure date**: the first date at which R1-R3 are all projected to hold, by the method
   above. If that date is beyond 60 collection days (`PROJECTION_CAP_DAYS`), the verdict is
   `NEEDS ARCHITECT` again, not a date -- the same discipline as v1.

Everything not listed above (event definitions, evaluability, temporal holdout, listing identity,
daily observation collapsing) is unchanged from `docs/phase4-data-sufficiency-rule.md`.

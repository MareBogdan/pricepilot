# Phase 4 data-sufficiency rule (pre-registered)

Written and committed BEFORE any measurement number was computed. Wording may be fixed later;
thresholds may not. Architect's rule, recorded 2026-09-26.

## Definitions

- **Listing** = (source, external_id); fall back to (source, source_product_id), then
  (source, url). Report how many listings used each key. Excluded rows
  (`excluded_reason IS NOT NULL`) and out-of-scope categories (not food/litter, via
  `norm_listings.category` on `content_hash`) are dropped. A listing whose title changes keeps
  its identity (`content_hash` may change).
- **Daily observation** = one row per (listing, collected_date). If a day has more than one row,
  take the last by id and report how many such days existed.
- **Collection day** = a calendar date with a `scrape_runs` row for that source with status ok
  AND at least 1 `raw_listings` row that day. **Gap** = a date between the source's first and
  last collection day that is not a collection day.
- **Promo** on a day = `compare_at_price IS NOT NULL AND compare_at_price > price`.
- **Base price** on a day = `compare_at_price` if promo, else `price`.
- **Event** at day t for a listing = observed on t-1 and t, and either:
  - `base_change`: |base_t / base_{t-1} - 1| >= 2%; or
  - `promo_start` / `promo_end`: the promo flag flips; or
  - `promo_depth`: promo on both days and |price_t / price_{t-1} - 1| >= 2%.

  One event may carry several types; count each type and also count events (union).
  Changes with 0 < |delta| < 2% are counted separately as `sub_threshold` (rounding noise),
  never as events.
- **Evaluable event** = an event at t where the listing is observed on ALL 7 days t-7..t-1 with
  no event among them (stable pre-window: the naive 7-day average is well defined), AND observed
  on ALL 7 days t..t+6 (the forecast horizon). Also report a lenient count allowing at most 1
  missing day in each window; it is reported, never used by the rule.
- **Temporal holdout** = evaluable events whose t falls in the last 14 collection days (the
  future the model is graded on); **training events** = evaluable events before that.

## Rule (thresholds fixed now, before the numbers)

PROCEED with the Phase 4 model only if ALL hold:

- **R1 history:** >= 28 collection days, <= 2 gaps, for at least 2 of the 3 sources.
- **R2 holdout:** >= 200 evaluable events in the temporal holdout, with >= 30 in each of
  >= 3 (source x category) cells.
- **R3 training:** >= 200 evaluable events before the holdout.

Why: a 7-day pre-window + 7-day horizon + a 14-day holdout that does not overlap training needs
>= 28 days; 200 events gives a paired MAE comparison against the naive baseline a usable CI; 30
per cell is the minimum to report any per-category elasticity estimate.

Otherwise **POSTPONE**: Phase 4 is paused, Phase 5 (RAG + decision engine) starts while
collection continues. The postponement records a **re-measure date** = the first date at which
R1-R3 are projected to hold, projecting each source's observed daily evaluable-event rate
forward linearly (label it ESTIMATE). If even at 60 collection days R2 is projected to fail,
write `NEEDS ARCHITECT: movement too rare` instead of a date. The architect then reframes the
phase (e.g. promo events only, or a longer horizon); Claude Code does not.

# Pricing policy — PricePilot mock store

Status: DRAFT v0.1 (2026-09-27), written by the architect, pending Bogdan's approval.
Scope: the mock store in `services/mock_store`. This is a realistic but fictional policy for a
Romanian online pet-supplies shop.

This document is the RAG corpus for Phase 5. It is policy text, not a data source. Every number
the decision engine acts on (cost, current price, margin, stock, competitor prices) comes from
SQL. The thresholds below are mirrored in a structured config that the Python guardrail reads.
The guardrail never parses this text.

## 1. Minimum margin by category

Margin means (price excluding VAT − purchase cost) / price excluding VAT. A recommendation that
would put a product below its category floor is rejected, whatever the rationale says.

- Dry food: at least 12%. It is a traffic driver, and customers compare it across shops.
- Wet food: at least 18%.
- Treats: at least 25%.
- Litter: at least 15%. It is bulky, and its shipping cost absorbs part of the margin.
- Grooming and accessories: at least 30%. They are rarely compared across shops.

## 2. Distributor-restricted brands

Some brands are sold under a distributor agreement with a minimum advertised price (MAP). For
these brands the shop never advertises below the distributor's recommended retail price. It does
not match a competitor who does. If a competitor undercuts a MAP brand, the correct action is to
flag the product for review, not to lower the price. The list of MAP brands lives in the database
and is the only authority on which brands are restricted.

## 3. Products excluded from automatic discounting

- Veterinary and prescription diets are never repriced automatically. They are also outside the
  project's scope and filtered out at ingest.
- Products with fewer than 3 units in stock are not discounted. A discount cannot sell stock the
  shop does not have.
- New products (listed less than 14 days ago) keep their launch price.
- Any product a human has manually locked is left untouched.

## 4. Speed of change

- A price may move at most 5% per day and at most 15% per rolling 7 days, in either direction.
- A larger move requires human approval, even when a competitor has moved further.
- The shop does not chase short promotions. A competitor price that has held for fewer than 2
  consecutive days is observed, not reacted to.

## 5. Competitor response

- Only matched competitor listings count. A listing whose match score is below the serving
  threshold is ignored.
- Promotions (`compare_at_price` above the price) are treated differently from base-price cuts.
  The shop may match a competitor's base price, subject to the margin floor. It does not match a
  temporary promotion unless the promotion has lasted 7 days or more.
- Permanent "strike-through" prices are not promotions. This covers a shop that shows a
  compare-at price almost every day without it ever changing.
- The shop aims to be at or slightly above the cheapest credible competitor, not below it.
  Undercutting the market is not a goal.

## 6. Rounding

- Final prices end in ,99 RON below 100 RON and in ,90 RON from 100 RON upward.
- Rounding is applied last and must never push a price below the margin floor. If it would,
  round up instead.

## 7. When unsure

If the inputs disagree, do nothing and flag the product for review. This covers stale competitor
data, a missing cost, or a match with a low score. Doing nothing is always an acceptable
recommendation. A wrong price is not.

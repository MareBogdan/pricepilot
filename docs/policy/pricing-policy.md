# Pricing policy — PricePilot mock store

Status: APPROVED v0.2 (2026-09-27, Bogdan). Supersedes draft v0.1.
Scope: the mock store in `services/mock_store`. A realistic but fictional policy for a Romanian
online pet-supplies shop.

This document is the RAG corpus for Phase 5 — policy text, not a data source. Every number the
engine acts on — our cost, current price, stock, competitor prices — comes from structured queries
(our figures from the mock-store API, competitor listings from SQL), never from this text. The
thresholds below are mirrored in a structured config the Python guardrail reads; the guardrail
never parses this document.

## 1. Minimum margin by category

Margin means (shelf price − purchase cost) / shelf price, from the mock store's `current_price`
and `purchase_cost` (both gross RON; the store models no VAT). A recommendation that would put a
product below its category floor is rejected, whatever the rationale says.

- Dry food: at least 12%. A traffic driver, compared across shops.
- Wet food: at least 18%.
- Treats: at least 25%.
- Litter: at least 15%. Bulky, and shipping absorbs part of the margin.
- Grooming and accessories: at least 30%. Rarely compared across shops.

## 2. Distributor-restricted brands

Some brands sell under a distributor agreement with a minimum advertised price (MAP). The shop
never advertises these below the recommended retail price and does not match a competitor who
does; if one undercuts a MAP brand, flag the product for review rather than lower the price. The
list of MAP brands lives in the database and is the only authority on which brands are restricted.

## 3. Products excluded from automatic discounting

- Veterinary and prescription diets are never repriced automatically; they are outside scope and
  filtered out at ingest.
- Products with fewer than 3 units in stock are not discounted — a discount cannot sell stock the
  shop does not have.
- New products (listed less than 14 days ago) keep their launch price.
- Any product a human has manually locked is left untouched.

## 4. Speed of change

- A price may move at most 5% per day and at most 15% per rolling 7 days, in either direction.
- A larger move requires human approval, even if a competitor moved further.
- The shop does not chase short promotions. A competitor price held for fewer than 2 consecutive
  days is observed, not reacted to.

## 5. Competitor response

- Only matched competitor listings count. A listing whose match score is below the serving
  threshold is ignored.
- Promotions (`compare_at_price` above the price) differ from base-price cuts. The shop may match a
  competitor's base price, subject to the margin floor; it does not match a temporary promotion
  unless it has lasted 7+ days.
- Permanent "strike-through" prices are not promotions — a shop showing a compare-at price almost
  every day without it ever changing.
- The shop aims to be at or slightly above the cheapest credible competitor, not below it.
  Undercutting the market is not a goal.

## 6. Rounding

- Final prices end in ,99 RON below 100 RON and in ,90 RON from 100 RON upward.
- Rounding is applied last and must never push a price below the margin floor. If it would, round
  up instead.

## 7. When unsure

If the inputs disagree, do nothing and flag the product for review — stale competitor data, a
missing cost, or a low-score match. Doing nothing is always an acceptable recommendation. A wrong
price is not.

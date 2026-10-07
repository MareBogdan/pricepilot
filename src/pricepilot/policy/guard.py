"""The deterministic margin/price guard (CLAUDE.md section 6, hard architectural rule 2:
guardrails live in code, not in prompts). This is the final authority over a price an LLM
proposes in later Phase 5 sessions -- it never parses `docs/policy/pricing-policy.md`, and it
never returns a price below a category's margin floor, including after charm rounding.

All money math is `Decimal` (ADR-0007): a margin comparison on `float` is a real bug, not a
style preference -- `Decimal("0.1") + Decimal("0.2") == Decimal("0.3")` and `float` fails that.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from pricepilot.policy.thresholds import PricingPolicyThresholds, load_thresholds

# A charm value can always be pushed high enough to clear any floor in (0, 1) -- margin is
# strictly increasing in price for a fixed positive cost -- so this is a safety valve against an
# infinite loop from a future config bug (e.g. cost <= 0), never expected to trigger in practice.
_MAX_CHARM_STEPS = 100_000


class MissingReferencePrice(ValueError):
    """Raised by `within_speed_limits` when the 7-day reference price is absent.

    A missing reference must never silently pass the speed check -- on a real change
    (`proposed_price != current_price`), `enforce` catches this specifically and returns FLAG,
    never APPROVE or a silent REJECT. A genuine no-change never reaches `within_speed_limits` at
    all (session 1b, 2026-09-28): no movement means there is nothing to check a reference against,
    so a missing or stale 7-day price does not block APPROVing the unchanged price.
    """


class GuardStatus(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    FLAG = "FLAG"


@dataclass(frozen=True, slots=True)
class GuardDecision:
    status: GuardStatus
    price: Decimal | None
    reason: str | None

    @classmethod
    def approve(cls, price: Decimal) -> GuardDecision:
        return cls(status=GuardStatus.APPROVE, price=price, reason=None)

    @classmethod
    def reject(cls, reason: str) -> GuardDecision:
        return cls(status=GuardStatus.REJECT, price=None, reason=reason)

    @classmethod
    def flag(cls, reason: str) -> GuardDecision:
        return cls(status=GuardStatus.FLAG, price=None, reason=reason)


def _require_positive(name: str, value: Decimal) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")


def margin(price: Decimal, cost: Decimal) -> Decimal:
    """Gross margin fraction: `(price - cost) / price`, matching mock-store `Product.margin_pct`
    (which returns the same quantity as a percent, x100 -- this returns the fraction).

    A non-positive `price` or `cost` is corrupt input, not a real margin (review finding 3,
    2026-09-28: `cost <= 0` would otherwise make every floor trivially pass) -- raises rather
    than returning a number that looks valid."""
    _require_positive("price", price)
    _require_positive("cost", cost)
    return (price - cost) / price


def meets_floor(
    category: str,
    price: Decimal,
    cost: Decimal,
    *,
    thresholds: PricingPolicyThresholds | None = None,
) -> bool:
    """Whether `price` clears `category`'s margin floor. Fail closed: an unknown category is a
    hard error, never silently approved (CLAUDE.md section 0.4)."""
    t = thresholds or load_thresholds()
    try:
        floor = t.margin_floor[category]  # type: ignore[index]
    except KeyError:
        raise ValueError(f"unknown category {category!r}: not in the margin_floor config") from None
    return margin(price, cost) >= Decimal(str(floor))


def within_speed_limits(
    proposed_price: Decimal,
    current_price: Decimal,
    price_7d_ago: Decimal | None,
    *,
    thresholds: PricingPolicyThresholds | None = None,
) -> bool:
    """Whether the move from `current_price` to `proposed_price` clears both the daily cap
    (vs. `current_price`) and the rolling 7-day cap (vs. `price_7d_ago`), in either direction."""
    if price_7d_ago is None:
        raise MissingReferencePrice(
            "price_7d_ago is required to check the rolling 7-day speed limit"
        )
    _require_positive("current_price", current_price)
    _require_positive("price_7d_ago", price_7d_ago)
    t = thresholds or load_thresholds()
    daily_change = abs(proposed_price - current_price) / current_price
    weekly_change = abs(proposed_price - price_7d_ago) / price_7d_ago
    max_daily = Decimal(str(t.speed_of_change.max_daily_fraction))
    max_weekly = Decimal(str(t.speed_of_change.max_weekly_fraction))
    return daily_change <= max_daily and weekly_change <= max_weekly


def is_discountable(stock: int, *, thresholds: PricingPolicyThresholds | None = None) -> bool:
    """A discount (price decrease) needs enough stock to sell into; a non-discount move (price
    increase or unchanged) is never blocked by stock."""
    t = thresholds or load_thresholds()
    return stock >= t.discount_eligibility.min_stock_units


def _fraction_for(value: Decimal, t: PricingPolicyThresholds) -> Decimal:
    threshold = Decimal(str(t.rounding.charm_threshold))
    return (
        Decimal(str(t.rounding.below_cents))
        if value < threshold
        else Decimal(str(t.rounding.at_or_above_cents))
    )


def charm_round(
    price: Decimal,
    category: str,
    cost: Decimal,
    *,
    thresholds: PricingPolicyThresholds | None = None,
) -> Decimal:
    """Round `price` to the charm value implied by the configured threshold (…,99 below it, …,90
    from it upward: nearest within that regime, with one correction at the threshold itself since
    the two regimes are not evenly spaced), then step UP one charm value at a time if that value
    would breach `category`'s margin floor. Never rounds down past the floor."""
    t = thresholds or load_thresholds()

    fraction = _fraction_for(price, t)
    whole = (price - fraction).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    candidate = whole + fraction
    # The charm fraction can flip exactly once, right at the config threshold (e.g. 99.99 vs.
    # 100.90) -- recompute once against the candidate itself and re-derive `whole` if it changed.
    refined = _fraction_for(candidate, t)
    if refined != fraction:
        fraction = refined
        whole = (price - fraction).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        candidate = whole + fraction

    steps = 0
    while not meets_floor(category, candidate, cost, thresholds=t):
        steps += 1
        if steps > _MAX_CHARM_STEPS:
            raise RuntimeError(
                f"charm_round could not clear the {category} floor after {_MAX_CHARM_STEPS} steps"
            )
        whole += 1
        fraction = _fraction_for(whole + fraction, t)
        candidate = whole + fraction

    return candidate.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _charm_at(whole: int, t: PricingPolicyThresholds) -> Decimal:
    """The charm value with integer part `whole`: `whole.99` below the threshold, `whole.90` from
    it upward. Strictly increasing in `whole` (99.99 -> 100.90)."""
    below = Decimal(str(t.rounding.below_cents))
    at_or_above = Decimal(str(t.rounding.at_or_above_cents))
    threshold = Decimal(str(t.rounding.charm_threshold))
    return Decimal(whole) + (below if whole + below < threshold else at_or_above)


def charm_ceil(value: Decimal, *, thresholds: PricingPolicyThresholds | None = None) -> Decimal:
    """The smallest charm value `>= value`."""
    t = thresholds or load_thresholds()
    whole = max(0, int(value) - 1)
    while _charm_at(whole, t) < value:
        whole += 1
    return _charm_at(whole, t)


def charm_floor(
    value: Decimal, *, thresholds: PricingPolicyThresholds | None = None
) -> Decimal | None:
    """The largest charm value `<= value`, or None if there is none (value below the cheapest
    charm value, `0.99`)."""
    t = thresholds or load_thresholds()
    whole = int(value) + 1
    while whole >= 0 and _charm_at(whole, t) > value:
        whole -= 1
    return _charm_at(whole, t) if whole >= 0 else None


def enforce(
    *,
    category: str,
    cost: Decimal,
    current_price: Decimal,
    proposed_price: Decimal,
    stock: int,
    price_7d_ago: Decimal | None,
    thresholds: PricingPolicyThresholds | None = None,
) -> GuardDecision:
    """The single entry point: charm round FIRST (floor-safe), then every other check runs
    against that final price -- never against the unrounded proposal. Rounding can move a price
    by up to ~1 RON, which previously let an APPROVE slip past the eligibility or speed check
    that only ever saw the unrounded proposal (review findings 1-2, 2026-09-28: an unchanged
    179.00 -> 179.00 proposal on a zero-stock product silently rounded down to an unchecked
    178.90 discount). Checking the price actually applied is the only way to guarantee every rule
    holds for the price that comes out.

    Order: no-change short-circuit -> charm round -> keep the move's direction -> re-check floor ->
    eligibility -> speed limit; the floor re-check, eligibility and speed limit all run on the
    final price. A genuine no-change (`proposed_price == current_price`)
    is approved unrounded, never manufactured into a move (session 1b, 2026-09-28) -- unless it
    already sits below the floor, which FLAGs instead of silently keeping a sub-floor price. Since
    there is no movement to measure, a no-change never reaches the eligibility or speed check --
    a missing or stale `price_7d_ago` does not block it (policy section 7: "doing nothing is
    always acceptable"). Never returns APPROVE with a price below the category floor. An unknown
    `category`, or a non-positive `cost`/`current_price`/`proposed_price`/`price_7d_ago`, raises
    (fail closed) rather than returning any GuardDecision (review finding 3, 2026-09-28)."""
    t = thresholds or load_thresholds()
    _require_positive("cost", cost)
    _require_positive("current_price", current_price)
    _require_positive("proposed_price", proposed_price)
    if price_7d_ago is not None:
        _require_positive("price_7d_ago", price_7d_ago)

    # 0. A genuine no-change is not a move: no mock-store catalogue price is itself a charm
    # value, so rounding it would manufacture an unintended discount/increase out of a "keep the
    # price" recommendation (policy section 7: "doing nothing is always acceptable"). Short-circuit
    # before charm_round ever runs. A no-change that is already below the floor still can't be
    # silently kept -- FLAG for human review rather than APPROVE a sub-floor price.
    if proposed_price == current_price:
        if not meets_floor(category, current_price, cost, thresholds=t):
            return GuardDecision.flag(
                f"no-change proposal keeps {current_price}, already below the {category} floor"
            )
        return GuardDecision.approve(current_price)

    # 1. Charm round the proposal first. Floor-safe by construction (steps up if the charm value
    # would breach the floor); this also raises here for an unknown category (fail closed).
    final_price = charm_round(proposed_price, category, cost, thresholds=t)

    # 1b. Direction (ADR-0043): "nearest charm value" can land on the wrong side of
    # `current_price` (5.20 -> proposed 5.36 -> 4.99 turned a +3% rise into a -4% cut). The applied
    # price must never contradict the intended direction, so re-anchor it on the correct side.
    if proposed_price > current_price and final_price < current_price:
        # Intended increase: the smallest charm value not below current. Floor-safe without a
        # step-up: it is >= current > the floor-safe `charm_round` result, and margin rises with
        # price; the step-2 floor re-check below remains the backstop.
        final_price = charm_ceil(current_price, thresholds=t)
    elif proposed_price < current_price and final_price > current_price:
        # Intended decrease: the largest charm value not above current, if it clears the floor.
        lower = charm_floor(current_price, thresholds=t)
        if lower is None or not meets_floor(category, lower, cost, thresholds=t):
            return GuardDecision.flag(
                f"direction cannot be kept: the {category} floor needs a price above the "
                f"current {current_price}, but a decrease was proposed ({proposed_price})"
            )
        final_price = lower

    # 2. Re-check the floor -- a backstop; charm_round should already guarantee it.
    if not meets_floor(category, final_price, cost, thresholds=t):
        return GuardDecision.reject(
            f"rounding produced {final_price}, still below the {category} floor -- guard bug"
        )

    # 3. Eligibility, against the price actually applied: a discount needs enough stock.
    if final_price < current_price and not is_discountable(stock, thresholds=t):
        return GuardDecision.reject(
            f"discount blocked: stock {stock} is below the minimum "
            f"{t.discount_eligibility.min_stock_units} units required for a discount"
        )

    # 4. Speed limit, against the price actually applied. A missing 7-day reference, or a genuine
    # breach (including one introduced by rounding), is a FLAG for human review -- never a silent
    # pass and never an outright REJECT, per policy section 4 ("requires human approval").
    try:
        speed_ok = within_speed_limits(final_price, current_price, price_7d_ago, thresholds=t)
    except MissingReferencePrice as exc:
        return GuardDecision.flag(str(exc))
    if not speed_ok:
        return GuardDecision.flag(
            f"speed limit breached: final price {final_price} (proposed {proposed_price}), "
            f"current {current_price}, 7d-ago {price_7d_ago}"
        )

    return GuardDecision.approve(final_price)

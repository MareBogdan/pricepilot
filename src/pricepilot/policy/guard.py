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

    A missing reference must never silently pass the speed check -- `enforce` catches this
    specifically and returns FLAG, never APPROVE or a silent REJECT.
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


def margin(price: Decimal, cost: Decimal) -> Decimal:
    """Gross margin fraction: `(price - cost) / price`, matching mock-store `Product.margin_pct`
    (which returns the same quantity as a percent, x100 -- this returns the fraction)."""
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
    """Round `price` to the nearest charm value (…,99 below the config threshold, …,90 from it
    upward), then step UP one charm value at a time if the nearest one would breach `category`'s
    margin floor. Never rounds down past the floor."""
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
    """The single entry point: eligibility -> margin floor -> speed limit -> charm round ->
    re-check floor after rounding. Never returns APPROVE with a price below the category floor.
    An unknown `category` raises (fail closed) rather than returning any GuardDecision."""
    t = thresholds or load_thresholds()

    # 1. Eligibility: a discount (price decrease) needs enough stock; an increase never blocked.
    if proposed_price < current_price and not is_discountable(stock, thresholds=t):
        return GuardDecision.reject(
            f"discount blocked: stock {stock} is below the minimum "
            f"{t.discount_eligibility.min_stock_units} units required for a discount"
        )

    # 2. Margin floor on the proposed price. Unknown category raises here (fail closed).
    if not meets_floor(category, proposed_price, cost, thresholds=t):
        floor = t.margin_floor[category]  # type: ignore[index]
        return GuardDecision.reject(
            f"margin floor breached: {margin(proposed_price, cost)} < {floor} for {category}"
        )

    # 3. Speed limit. A missing 7-day reference is a FLAG, never a silent pass.
    try:
        speed_ok = within_speed_limits(proposed_price, current_price, price_7d_ago, thresholds=t)
    except MissingReferencePrice as exc:
        return GuardDecision.flag(str(exc))
    if not speed_ok:
        return GuardDecision.reject(
            f"speed limit breached: proposed {proposed_price}, current {current_price}, "
            f"7d-ago {price_7d_ago}"
        )

    # 4. Charm round, floor-safe by construction (rounds up if the nearest value would breach).
    final_price = charm_round(proposed_price, category, cost, thresholds=t)

    # 5. Re-check the floor after rounding -- a backstop; charm_round should already guarantee it.
    if not meets_floor(category, final_price, cost, thresholds=t):
        return GuardDecision.reject(
            f"rounding produced {final_price}, still below the {category} floor -- guard bug"
        )

    return GuardDecision.approve(final_price)

"""Phase 5 session 1: the pricing-policy thresholds config + the deterministic margin/price
guard (CLAUDE.md section 6). This guard produces the Phase 5 gate figure ("zero margin
violations"), so every margin-affecting path here has a computed expected value -- no smoke
tests. All thresholds come from the real `config/pricing-policy.toml` (APPROVED v0.2, ADR-0033),
never a hand-rolled fixture, so a passing suite also proves the shipped config parses correctly.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from pricepilot.policy.guard import (
    GuardStatus,
    MissingReferencePrice,
    charm_round,
    enforce,
    is_discountable,
    margin,
    meets_floor,
    within_speed_limits,
)
from pricepilot.policy.thresholds import (
    ALL_CATEGORIES,
    PricingPolicyThresholds,
    load_thresholds,
)

T = load_thresholds()

# ---------------------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------------------


def test_default_config_has_exactly_six_categories_matching_the_policy() -> None:
    assert set(T.margin_floor) == set(ALL_CATEGORIES)
    assert len(ALL_CATEGORIES) == 6
    # Numbers from docs/policy/pricing-policy.md section 1 (APPROVED v0.2).
    assert T.margin_floor["dry_food"] == pytest.approx(0.12)
    assert T.margin_floor["wet_food"] == pytest.approx(0.18)
    assert T.margin_floor["treats"] == pytest.approx(0.25)
    assert T.margin_floor["litter"] == pytest.approx(0.15)
    assert T.margin_floor["grooming"] == pytest.approx(0.30)
    assert T.margin_floor["accessories"] == pytest.approx(0.30)


def test_default_config_speed_and_discount_and_rounding() -> None:
    assert T.speed_of_change.max_daily_fraction == pytest.approx(0.05)
    assert T.speed_of_change.max_weekly_fraction == pytest.approx(0.15)
    assert T.discount_eligibility.min_stock_units == 3
    assert T.rounding.charm_threshold == pytest.approx(100)
    assert T.rounding.below_cents == pytest.approx(0.99)
    assert T.rounding.at_or_above_cents == pytest.approx(0.90)


def test_loader_rejects_a_missing_category(tmp_path: Path) -> None:
    bad = tmp_path / "bad.toml"
    bad.write_text(
        """
        [margin_floor]
        dry_food = 0.12
        wet_food = 0.18
        treats = 0.25
        litter = 0.15
        grooming = 0.30
        # accessories missing

        [speed_of_change]
        max_daily_fraction = 0.05
        max_weekly_fraction = 0.15

        [discount_eligibility]
        min_stock_units = 3

        [rounding]
        charm_threshold = 100
        below_cents = 0.99
        at_or_above_cents = 0.90
        """,
        encoding="utf-8",
    )
    load_thresholds.cache_clear()
    with pytest.raises(ValidationError, match="accessories"):
        load_thresholds(bad)
    load_thresholds.cache_clear()


def test_loader_rejects_a_floor_outside_zero_one(tmp_path: Path) -> None:
    bad = tmp_path / "bad_floor.toml"
    bad.write_text(
        """
        [margin_floor]
        dry_food = 12.0
        wet_food = 0.18
        treats = 0.25
        litter = 0.15
        grooming = 0.30
        accessories = 0.30

        [speed_of_change]
        max_daily_fraction = 0.05
        max_weekly_fraction = 0.15

        [discount_eligibility]
        min_stock_units = 3

        [rounding]
        charm_threshold = 100
        below_cents = 0.99
        at_or_above_cents = 0.90
        """,
        encoding="utf-8",
    )
    load_thresholds.cache_clear()
    with pytest.raises(ValidationError):
        load_thresholds(bad)
    load_thresholds.cache_clear()


def test_loader_rejects_a_non_positive_limit(tmp_path: Path) -> None:
    bad = tmp_path / "bad_limit.toml"
    bad.write_text(
        """
        [margin_floor]
        dry_food = 0.12
        wet_food = 0.18
        treats = 0.25
        litter = 0.15
        grooming = 0.30
        accessories = 0.30

        [speed_of_change]
        max_daily_fraction = 0.0
        max_weekly_fraction = 0.15

        [discount_eligibility]
        min_stock_units = 3

        [rounding]
        charm_threshold = 100
        below_cents = 0.99
        at_or_above_cents = 0.90
        """,
        encoding="utf-8",
    )
    load_thresholds.cache_clear()
    with pytest.raises(ValidationError):
        load_thresholds(bad)
    load_thresholds.cache_clear()


# ---------------------------------------------------------------------------------------
# margin / meets_floor -- each category floor at / just below / just above
# ---------------------------------------------------------------------------------------

# cost chosen so the exact-floor breakeven price is a clean 100.00 for every category:
# cost = 100 * (1 - floor).
_FLOOR_COST_AT_100: dict[str, str] = {
    "dry_food": "88.00",
    "wet_food": "82.00",
    "treats": "75.00",
    "litter": "85.00",
    "grooming": "70.00",
    "accessories": "70.00",
}


@pytest.mark.parametrize("category", list(ALL_CATEGORIES))
def test_meets_floor_at_the_exact_boundary(category: str) -> None:
    cost = Decimal(_FLOOR_COST_AT_100[category])
    floor = Decimal(str(T.margin_floor[category]))
    assert margin(Decimal("100.00"), cost) == floor
    assert meets_floor(category, Decimal("100.00"), cost, thresholds=T) is True


@pytest.mark.parametrize("category", list(ALL_CATEGORIES))
def test_meets_floor_just_below_the_boundary(category: str) -> None:
    cost = Decimal(_FLOOR_COST_AT_100[category])
    assert meets_floor(category, Decimal("99.99"), cost, thresholds=T) is False


@pytest.mark.parametrize("category", list(ALL_CATEGORIES))
def test_meets_floor_just_above_the_boundary(category: str) -> None:
    cost = Decimal(_FLOOR_COST_AT_100[category])
    assert meets_floor(category, Decimal("100.01"), cost, thresholds=T) is True


def test_grooming_and_accessories_share_the_same_floor() -> None:
    assert T.margin_floor["grooming"] == T.margin_floor["accessories"] == pytest.approx(0.30)


def test_unknown_category_raises_not_silently_approved() -> None:
    with pytest.raises(ValueError, match="unknown category"):
        meets_floor("fish_tanks", Decimal("100.00"), Decimal("50.00"), thresholds=T)


# ---------------------------------------------------------------------------------------
# charm_round -- floor-safe rounding
# ---------------------------------------------------------------------------------------


def test_charm_round_below_100_ends_in_99() -> None:
    # Nearest charm value to 83.20 with a floor that is trivially satisfied.
    result = charm_round(Decimal("83.20"), "treats", Decimal("5.00"), thresholds=T)
    assert result == Decimal("82.99")


def test_charm_round_at_or_above_100_ends_in_90() -> None:
    result = charm_round(Decimal("178.55"), "accessories", Decimal("10.00"), thresholds=T)
    assert result == Decimal("178.90")


def test_charm_round_steps_up_when_the_nearest_value_would_breach_the_floor() -> None:
    """dry_food floor 0.12, cost 88.00 -> breakeven 100.00. Proposed 100.30 clears the floor
    (margin ~0.1226), but its nearest charm value (99.99) would NOT (margin ~0.1199) -- the
    guard must step up to the next charm value (100.90), never settle below the floor."""
    cost = Decimal("88.00")
    proposed = Decimal("100.30")
    assert meets_floor("dry_food", proposed, cost, thresholds=T) is True
    # The naive nearest charm value would breach the floor.
    assert meets_floor("dry_food", Decimal("99.99"), cost, thresholds=T) is False
    result = charm_round(proposed, "dry_food", cost, thresholds=T)
    assert result == Decimal("100.90")
    assert meets_floor("dry_food", result, cost, thresholds=T) is True


# ---------------------------------------------------------------------------------------
# within_speed_limits -- daily and 7-day caps at the boundary
# ---------------------------------------------------------------------------------------


def test_daily_cap_at_the_boundary_passes() -> None:
    assert (
        within_speed_limits(Decimal("105.00"), Decimal("100.00"), Decimal("100.00"), thresholds=T)
        is True
    )


def test_daily_cap_just_over_the_boundary_fails() -> None:
    assert (
        within_speed_limits(Decimal("105.01"), Decimal("100.00"), Decimal("100.00"), thresholds=T)
        is False
    )


def test_weekly_cap_at_the_boundary_passes() -> None:
    # Daily change 3/112 (~2.7%) stays under 5%; weekly change is exactly 15%.
    assert (
        within_speed_limits(Decimal("115.00"), Decimal("112.00"), Decimal("100.00"), thresholds=T)
        is True
    )


def test_weekly_cap_just_over_the_boundary_fails() -> None:
    assert (
        within_speed_limits(Decimal("115.01"), Decimal("112.00"), Decimal("100.00"), thresholds=T)
        is False
    )


def test_missing_seven_day_reference_raises() -> None:
    with pytest.raises(MissingReferencePrice):
        within_speed_limits(Decimal("105.00"), Decimal("100.00"), None, thresholds=T)


# ---------------------------------------------------------------------------------------
# is_discountable
# ---------------------------------------------------------------------------------------


def test_is_discountable_boundary() -> None:
    assert is_discountable(2, thresholds=T) is False
    assert is_discountable(3, thresholds=T) is True
    assert is_discountable(0, thresholds=T) is False


# ---------------------------------------------------------------------------------------
# enforce() -- the composed entry point
# ---------------------------------------------------------------------------------------


def test_enforce_approves_a_clean_increase() -> None:
    decision = enforce(
        category="dry_food",
        cost=Decimal("88.00"),
        current_price=Decimal("150.00"),
        proposed_price=Decimal("155.00"),
        stock=2,  # below the discount minimum, but this is an increase -- must not matter
        price_7d_ago=Decimal("148.00"),
        thresholds=T,
    )
    assert decision.status is GuardStatus.APPROVE
    assert decision.price == Decimal("154.90")
    assert decision.reason is None


def test_enforce_rejects_a_discount_when_stock_is_below_minimum() -> None:
    decision = enforce(
        category="dry_food",
        cost=Decimal("88.00"),
        current_price=Decimal("150.00"),
        proposed_price=Decimal("140.00"),
        stock=2,
        price_7d_ago=Decimal("150.00"),
        thresholds=T,
    )
    assert decision.status is GuardStatus.REJECT
    assert decision.price is None
    assert "discount blocked" in (decision.reason or "")


def test_enforce_allows_a_discount_when_stock_meets_minimum() -> None:
    decision = enforce(
        category="dry_food",
        cost=Decimal("88.00"),
        current_price=Decimal("150.00"),
        proposed_price=Decimal("145.00"),
        stock=3,
        price_7d_ago=Decimal("150.00"),
        thresholds=T,
    )
    assert decision.status is GuardStatus.APPROVE


def test_enforce_self_corrects_a_badly_low_proposal_but_flags_the_resulting_jump() -> None:
    """A proposal far below the category floor is corrected upward by charm_round (never
    approved below the floor: dry_food 0.12, cost 88 -> breakeven 100.00, so 90.00 gets bumped to
    100.90). The resulting jump from current_price then trips the speed limit -- FLAGged for
    human review, never a silent REJECT-and-forget or a silent APPROVE."""
    decision = enforce(
        category="dry_food",
        cost=Decimal("88.00"),
        current_price=Decimal("95.00"),
        proposed_price=Decimal("90.00"),  # margin (90-88)/90 = 0.0222, far below the 0.12 floor
        stock=10,
        price_7d_ago=Decimal("95.00"),
        thresholds=T,
    )
    assert decision.status is GuardStatus.FLAG
    assert decision.price is None
    assert "speed limit" in (decision.reason or "")


def test_enforce_flags_a_speed_limit_breach() -> None:
    """Policy section 4: 'a larger move requires human approval' -- FLAG, not REJECT."""
    decision = enforce(
        category="accessories",
        cost=Decimal("10.00"),
        current_price=Decimal("100.00"),
        proposed_price=Decimal("120.00"),  # 20% daily move, over the 5% cap
        stock=10,
        price_7d_ago=Decimal("100.00"),
        thresholds=T,
    )
    assert decision.status is GuardStatus.FLAG
    assert decision.price is None
    assert "speed limit" in (decision.reason or "")


def test_enforce_catches_a_rounding_induced_discount_on_zero_stock() -> None:
    """Regression, review finding 1 (2026-09-28): current_price 179.00 is not itself a charm
    value, so a genuine (small) INCREASE proposal, 179.05, rounds DOWN to 178.90 -- a real
    discount relative to current_price. Checking eligibility against the unrounded proposal
    (179.05 > current, "not a discount") used to let this through on a zero-stock product;
    checking the final price catches it. (proposed != current here -- the exact-no-change case is
    covered separately by the session 1b no-change short-circuit tests below.)"""
    decision = enforce(
        category="dry_food",
        cost=Decimal("119.00"),
        current_price=Decimal("179.00"),
        proposed_price=Decimal("179.05"),
        stock=0,
        price_7d_ago=Decimal("179.00"),
        thresholds=T,
    )
    assert decision.status is GuardStatus.REJECT
    assert decision.price is None
    assert "discount blocked" in (decision.reason or "")


def test_enforce_catches_a_rounding_induced_speed_breach() -> None:
    """Regression, review finding 2 (2026-09-28): the raw proposal (10.50 vs current 10.00) sits
    exactly at the 5% daily cap, but its charm-rounded value (10.99) does not (9.9%). Checking the
    speed limit against the unrounded proposal used to APPROVE the breach; checking the final
    price FLAGs it instead."""
    decision = enforce(
        category="accessories",
        cost=Decimal("1.00"),
        current_price=Decimal("10.00"),
        proposed_price=Decimal("10.50"),
        stock=10,
        price_7d_ago=Decimal("10.00"),
        thresholds=T,
    )
    assert decision.status is GuardStatus.FLAG
    assert decision.price is None
    assert "speed limit" in (decision.reason or "")


# ---------------------------------------------------------------------------------------
# enforce() -- session 1b: a genuine no-change is approved unrounded, never manufactured
# into a move (2026-09-28). No mock-store catalogue price is itself a charm value.
# ---------------------------------------------------------------------------------------


def test_enforce_no_change_above_floor_is_approved_unrounded() -> None:
    """The exact scenario that used to become an unchecked discount: 179.00 is not a charm
    value, so the old round-first order turned an unchanged proposal into 178.90. Now it is
    APPROVEd at exactly 179.00 -- not rounded at all."""
    decision = enforce(
        category="dry_food",
        cost=Decimal("119.00"),
        current_price=Decimal("179.00"),
        proposed_price=Decimal("179.00"),
        stock=0,  # would block a real discount -- irrelevant here, this is not a move
        price_7d_ago=Decimal("179.00"),
        thresholds=T,
    )
    assert decision.status is GuardStatus.APPROVE
    assert decision.price == Decimal("179.00")
    assert decision.reason is None


def test_enforce_no_change_at_exact_floor_is_approved() -> None:
    """The floor boundary is inclusive (meets_floor uses >=) on the no-change path too."""
    decision = enforce(
        category="dry_food",
        cost=Decimal("88.00"),
        current_price=Decimal("100.00"),  # margin exactly 0.12, the dry_food floor
        proposed_price=Decimal("100.00"),
        stock=10,
        price_7d_ago=Decimal("100.00"),
        thresholds=T,
    )
    assert decision.status is GuardStatus.APPROVE
    assert decision.price == Decimal("100.00")


def test_enforce_no_change_below_floor_flags_instead_of_approving() -> None:
    """A no-change must never APPROVE a price already below the floor -- FLAG for human review.
    dry_food floor 0.12; cost 95.00 / price 100.00 -> margin 0.05, well under it."""
    decision = enforce(
        category="dry_food",
        cost=Decimal("95.00"),
        current_price=Decimal("100.00"),
        proposed_price=Decimal("100.00"),
        stock=10,
        price_7d_ago=Decimal("100.00"),
        thresholds=T,
    )
    assert decision.status is GuardStatus.FLAG
    assert decision.price is None
    assert "below the dry_food floor" in (decision.reason or "")


def test_enforce_no_change_approves_even_with_a_missing_seven_day_reference() -> None:
    """A no-change never reaches the speed check (reviewer note, session 1b review): there is no
    movement to measure, so a missing `price_7d_ago` does not block APPROVing the unchanged price.
    Contrast with `test_enforce_flags_a_missing_seven_day_reference` below, where the proposal IS
    a real change and a missing reference correctly FLAGs."""
    decision = enforce(
        category="dry_food",
        cost=Decimal("88.00"),
        current_price=Decimal("150.00"),
        proposed_price=Decimal("150.00"),
        stock=10,
        price_7d_ago=None,
        thresholds=T,
    )
    assert decision.status is GuardStatus.APPROVE
    assert decision.price == Decimal("150.00")


def test_enforce_flags_a_missing_seven_day_reference() -> None:
    decision = enforce(
        category="accessories",
        cost=Decimal("10.00"),
        current_price=Decimal("100.00"),
        proposed_price=Decimal("102.00"),
        stock=10,
        price_7d_ago=None,
        thresholds=T,
    )
    assert decision.status is GuardStatus.FLAG
    assert decision.price is None
    assert "price_7d_ago" in (decision.reason or "")


def test_enforce_raises_on_an_unknown_category() -> None:
    with pytest.raises(ValueError, match="unknown category"):
        enforce(
            category="fish_tanks",
            cost=Decimal("10.00"),
            current_price=Decimal("100.00"),
            proposed_price=Decimal("102.00"),
            stock=10,
            price_7d_ago=Decimal("100.00"),
            thresholds=T,
        )


def test_enforce_never_returns_a_price_below_the_floor_even_after_rounding() -> None:
    """Same construction as the charm_round step-up test, through the full enforce() path."""
    decision = enforce(
        category="dry_food",
        cost=Decimal("88.00"),
        current_price=Decimal("100.00"),
        proposed_price=Decimal("100.30"),
        stock=10,
        price_7d_ago=Decimal("100.00"),
        thresholds=T,
    )
    assert decision.status is GuardStatus.APPROVE
    assert decision.price == Decimal("100.90")
    assert meets_floor("dry_food", decision.price, Decimal("88.00"), thresholds=T) is True


# ---------------------------------------------------------------------------------------
# Input validation -- non-positive money is corrupt data, not a valid margin (review finding 3)
# ---------------------------------------------------------------------------------------


def test_margin_rejects_non_positive_price_or_cost() -> None:
    with pytest.raises(ValueError, match="price must be positive"):
        margin(Decimal("0"), Decimal("5.00"))
    with pytest.raises(ValueError, match="cost must be positive"):
        margin(Decimal("10.00"), Decimal("-1.00"))


def test_within_speed_limits_rejects_non_positive_reference_prices() -> None:
    with pytest.raises(ValueError, match="current_price must be positive"):
        within_speed_limits(Decimal("10.00"), Decimal("0"), Decimal("10.00"), thresholds=T)
    with pytest.raises(ValueError, match="price_7d_ago must be positive"):
        within_speed_limits(Decimal("10.00"), Decimal("10.00"), Decimal("-1.00"), thresholds=T)


@pytest.mark.parametrize(
    "override",
    [
        {"cost": Decimal("0")},
        {"current_price": Decimal("-5.00")},
        {"proposed_price": Decimal("0")},
        {"price_7d_ago": Decimal("-1.00")},
    ],
)
def test_enforce_rejects_non_positive_inputs(override: dict[str, Decimal]) -> None:
    kwargs = {
        "category": "accessories",
        "cost": Decimal("10.00"),
        "current_price": Decimal("100.00"),
        "proposed_price": Decimal("102.00"),
        "stock": 10,
        "price_7d_ago": Decimal("100.00"),
        "thresholds": T,
    }
    kwargs.update(override)
    with pytest.raises(ValueError, match="must be positive"):
        enforce(**kwargs)  # type: ignore[arg-type]


def test_thresholds_are_frozen() -> None:
    with pytest.raises(ValidationError):
        T.margin_floor = {}  # type: ignore[misc]


def test_pricing_policy_thresholds_type_is_exported() -> None:
    assert isinstance(T, PricingPolicyThresholds)

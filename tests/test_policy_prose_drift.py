"""Prose/TOML drift (Phase 5 s2 open issue, ADR-0042): every numeric threshold that
`docs/policy/pricing-policy.md` states must equal `config/pricing-policy.toml`.

The guard reads only the TOML; the LLM is shown the prose as reference text. If the two ever
disagree, the model would cite a number the code does not enforce. This test fails on that drift --
and, via the sweep at the bottom, on a NEW number added to the prose that nothing here checks.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pytest

from pricepilot.policy.thresholds import load_thresholds

POLICY_MD = Path(__file__).resolve().parents[1] / "docs" / "policy" / "pricing-policy.md"

# Prose bullet label -> the TOML categories it covers.
FLOOR_BULLETS = {
    "Dry food": ["dry_food"],
    "Wet food": ["wet_food"],
    "Treats": ["treats"],
    "Litter": ["litter"],
    "Grooming and accessories": ["grooming", "accessories"],
}


@pytest.fixture(scope="module")
def prose() -> str:
    return POLICY_MD.read_text(encoding="utf-8")


def pct(fraction: float) -> Decimal:
    return Decimal(str(fraction)) * 100


def test_margin_floors_in_prose_equal_toml(prose: str) -> None:
    t = load_thresholds()
    for label, categories in FLOOR_BULLETS.items():
        m = re.search(rf"^- {re.escape(label)}: at least (\d+(?:\.\d+)?)%", prose, re.MULTILINE)
        assert m, f"policy prose has no floor bullet for {label!r} -- was section 1 restructured?"
        for category in categories:
            assert Decimal(m.group(1)) == pct(t.margin_floor[category]), (  # type: ignore[index]
                f"{category}: prose says {m.group(1)}%, TOML says {pct(t.margin_floor[category])}%"  # type: ignore[index]
            )


def test_speed_limits_in_prose_equal_toml(prose: str) -> None:
    t = load_thresholds()
    m = re.search(
        r"at most (\d+(?:\.\d+)?)% per day and at most (\d+(?:\.\d+)?)% per rolling 7 days", prose
    )
    assert m, "policy prose no longer states the daily/weekly caps in the expected sentence"
    assert Decimal(m.group(1)) == pct(t.speed_of_change.max_daily_fraction)
    assert Decimal(m.group(2)) == pct(t.speed_of_change.max_weekly_fraction)


def test_discount_stock_minimum_in_prose_equals_toml(prose: str) -> None:
    t = load_thresholds()
    m = re.search(r"fewer than (\d+) units in stock are not discounted", prose)
    assert m, "policy prose no longer states the discount stock minimum in the expected sentence"
    assert int(m.group(1)) == t.discount_eligibility.min_stock_units


def test_rounding_rule_in_prose_equals_toml(prose: str) -> None:
    t = load_thresholds()
    m = re.search(
        r"end in ,(\d+) RON below (\d+) RON and in ,(\d+) RON from (\d+) RON upward", prose
    )
    assert m, "policy prose no longer states the charm-rounding rule in the expected sentence"
    assert Decimal(f"0.{m.group(1)}") == Decimal(str(t.rounding.below_cents))
    assert Decimal(f"0.{m.group(3)}") == Decimal(str(t.rounding.at_or_above_cents))
    assert Decimal(m.group(2)) == Decimal(m.group(4)) == Decimal(str(t.rounding.charm_threshold))


def test_every_percentage_in_prose_is_one_the_tests_above_check(prose: str) -> None:
    """The sweep: a percentage added to the prose (or edited out of a sentence the regexes above
    match) that no test pins down fails here, instead of drifting silently."""
    t = load_thresholds()
    checked = {pct(v) for v in t.margin_floor.values()}
    checked |= {
        pct(t.speed_of_change.max_daily_fraction),
        pct(t.speed_of_change.max_weekly_fraction),
    }
    found = {Decimal(x) for x in re.findall(r"(\d+(?:\.\d+)?)%", prose)}
    unchecked = found - checked
    assert not unchecked, f"percentages in the policy prose with no TOML counterpart: {unchecked}"


# Numbers the prose states that have NO key in the TOML yet (guard scope gaps, ADR-0034: the mock
# store has no `listed_at` / promotion-duration data). They are reference text only. If one of them
# gains a TOML key, move it into a real comparison above and drop it from this list.
UNCONFIGURED_DAY_COUNTS = {"14", "2", "7"}


def test_day_counts_in_prose_are_the_known_unconfigured_ones(prose: str) -> None:
    found = set(re.findall(r"(\d+)\+? (?:consecutive )?days?", prose))
    assert found <= UNCONFIGURED_DAY_COUNTS, f"new day-count threshold in prose: {found}"

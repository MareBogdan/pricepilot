"""Typed, validated loader for `config/pricing-policy.toml`.

This is the ONE place a policy threshold literal may live (CLAUDE.md section 9: "A metric/number
with no script behind it" and "A margin check implemented inside a prompt" must never happen).
`src/pricepilot/policy/guard.py` reads thresholds only through this module -- never by parsing
`docs/policy/pricing-policy.md` and never by hardcoding a number of its own.
"""

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Mirrors services/mock_store/app.py Product.category exactly -- verified against _CATALOGUE
# (CLAUDE.md Phase 5 session 1 brief). Kept as a plain tuple/Literal here rather than imported
# from `services`, since `src/` does not depend on the mock-store fixture package.
Category = Literal["dry_food", "wet_food", "treats", "litter", "grooming", "accessories"]
ALL_CATEGORIES: tuple[Category, ...] = (
    "dry_food",
    "wet_food",
    "treats",
    "litter",
    "grooming",
    "accessories",
)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "pricing-policy.toml"

# A margin floor is a fraction of shelf price, strictly between 0 and 1 (0% or 100%+ is not a
# real floor and signals a typo, e.g. "12" instead of "0.12").
Fraction = Annotated[float, Field(gt=0.0, lt=1.0)]
Positive = Annotated[float, Field(gt=0.0)]


class SpeedOfChange(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_daily_fraction: Positive
    max_weekly_fraction: Positive


class DiscountEligibility(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    min_stock_units: Annotated[int, Field(gt=0)]


class Rounding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    charm_threshold: Positive
    below_cents: Positive
    at_or_above_cents: Positive


class PricingPolicyThresholds(BaseModel):
    """The full set of structured thresholds behind the Phase 5 margin/price guard."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    margin_floor: dict[Category, Fraction]
    speed_of_change: SpeedOfChange
    discount_eligibility: DiscountEligibility
    rounding: Rounding

    @model_validator(mode="after")
    def _all_categories_present(self) -> PricingPolicyThresholds:
        missing = set(ALL_CATEGORIES) - set(self.margin_floor)
        if missing:
            raise ValueError(f"margin_floor is missing categories: {sorted(missing)}")
        return self


@lru_cache(maxsize=1)
def load_thresholds(path: Path | None = None) -> PricingPolicyThresholds:
    """Parse and validate `config/pricing-policy.toml` (or `path`, for tests)."""
    config_path = path or DEFAULT_CONFIG_PATH
    with config_path.open("rb") as f:
        raw = tomllib.load(f)
    return PricingPolicyThresholds.model_validate(raw)

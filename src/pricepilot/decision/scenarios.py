"""The 50-recommendation plan for Phase 5 session 5 (ADR-0042): the unit is one recommendation per
(product, scenario).

* **30 baseline** rows -- every catalogue product on its REAL inputs (scenario `None`). Products
  with matched competitor prices get them; the rest are decided from cost and policy alone.
* **20 scenario** rows -- HYPOTHETICAL what-ifs on matched products, to put price pressure on the
  margin floor: `undercut_15` (every matched competitor price x 0.85) on every matched product,
  then `undercut_30` (x 0.70) on the lowest-id `UNDERCUT_30_COUNT` matched products.

A scenario changes the competitor prices the proposer SEES; our own cost, price and stock stay the
database's. The snapshot carries a note that is rendered into the prompt, and each competitor JSON
keeps the real `observed_price`, so a scenario row can never be mistaken for market data.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal

from pricepilot.decision.engine import ProductSnapshot

SCENARIO_FACTORS: dict[str, Decimal] = {
    "undercut_15": Decimal("0.85"),
    "undercut_30": Decimal("0.70"),
}
UNDERCUT_30_COUNT = 7
EXPECTED_TOTAL = 50


@dataclass(frozen=True, slots=True)
class PlanItem:
    product_id: int
    scenario: str | None  # None = baseline, real inputs


def build_plan(product_ids: Iterable[int], matched_product_ids: Iterable[int]) -> list[PlanItem]:
    """Baseline for every product, `undercut_15` for every matched one, `undercut_30` for the
    `UNDERCUT_30_COUNT` lowest-id matched ones. Deterministic and ordered."""
    all_ids = sorted(set(product_ids))
    matched = sorted(set(matched_product_ids))
    unknown = set(matched) - set(all_ids)
    if unknown:
        raise ValueError(f"matched product ids not in the catalogue: {sorted(unknown)}")
    plan = [PlanItem(pid, None) for pid in all_ids]
    plan += [PlanItem(pid, "undercut_15") for pid in matched]
    plan += [PlanItem(pid, "undercut_30") for pid in matched[:UNDERCUT_30_COUNT]]
    return plan


def apply_scenario(snapshot: ProductSnapshot, scenario: str | None) -> ProductSnapshot:
    """The snapshot the proposer is shown under `scenario`. `None` returns it unchanged."""
    if scenario is None:
        return snapshot
    if scenario not in SCENARIO_FACTORS:
        raise ValueError(f"unknown scenario {scenario!r}; choose from {sorted(SCENARIO_FACTORS)}")
    if not snapshot.competitors:
        raise ValueError(f"scenario {scenario!r} needs matched competitor prices; none for product")
    factor = SCENARIO_FACTORS[scenario]
    competitors = tuple(
        replace(
            c,
            price=(c.price * factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            observed_price=c.price,
        )
        for c in snapshot.competitors
    )
    note = (
        f"scenario {scenario}: the competitor prices below are the observed prices x {factor}. "
        "This is a what-if test of the price guard, not what the shops charge."
    )
    return replace(snapshot, competitors=competitors, scenario_note=note)

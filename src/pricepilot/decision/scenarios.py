"""The 50-recommendation plan for Phase 5 (ADR-0042, reframed by ADR-0045): one recommendation per
(product, scenario).

* **30 baseline** rows -- every catalogue product on its REAL inputs (scenario `None`). Products
  with matched competitor prices get them; the rest are decided from cost and policy alone.
* **20 GUARD STRESS-TEST** rows -- the matched products again, with every matched competitor price
  scaled down so the model is invited to undercut: `stress_undercut_15` (x 0.85) on every matched
  product, then `stress_undercut_30` (x 0.70) on the lowest-id `STRESS_30_COUNT` matched products.

A stress-test changes the competitor prices the proposer SEES and nothing else: our own cost, price
and stock stay the database's. The PROMPT presents those prices as the pricing input to respond to
(an earlier version announced them as hypothetical and the model ignored them, ADR-0045). The
deception is of the model under test only, and it is disclosed everywhere a human reads the result:
the row's `scenario` starts with `stress_`, each competitor JSON keeps the real `observed_price`,
and the gate report labels these rows "GUARD STRESS-TEST -- synthetic competitor prices, not a market
recommendation".
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal

from pricepilot.decision.engine import ProductSnapshot

STRESS_PREFIX = "stress_"
# Rows replaced by a later run are relabelled (never deleted); they must never be acted on.
SUPERSEDED_RUN_LABEL = "s5-superseded"
SCENARIO_FACTORS: dict[str, Decimal] = {
    "stress_undercut_15": Decimal("0.85"),
    "stress_undercut_30": Decimal("0.70"),
}
STRESS_30_COUNT = 7
EXPECTED_TOTAL = 50


@dataclass(frozen=True, slots=True)
class PlanItem:
    product_id: int
    scenario: str | None  # None = baseline, real inputs


def is_stress(scenario: str | None) -> bool:
    return scenario is not None and scenario.startswith(STRESS_PREFIX)


def build_plan(product_ids: Iterable[int], matched_product_ids: Iterable[int]) -> list[PlanItem]:
    """Baseline for every product, `stress_undercut_15` for every matched one,
    `stress_undercut_30` for the `STRESS_30_COUNT` lowest-id matched ones. Deterministic, ordered."""
    all_ids = sorted(set(product_ids))
    matched = sorted(set(matched_product_ids))
    unknown = set(matched) - set(all_ids)
    if unknown:
        raise ValueError(f"matched product ids not in the catalogue: {sorted(unknown)}")
    plan = [PlanItem(pid, None) for pid in all_ids]
    plan += [PlanItem(pid, "stress_undercut_15") for pid in matched]
    plan += [PlanItem(pid, "stress_undercut_30") for pid in matched[:STRESS_30_COUNT]]
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
    return replace(snapshot, competitors=competitors)

"""The Phase 5 gate check over stored recommendations (ADR-0042): 50 real recommendations, ZERO
margin violations.

Pure functions over `Recommendation` rows, so the assertion logic is unit-tested without a database
or an LLM. The margin check here is an INDEPENDENT recomputation from the stored `cost`,
`guard_final_price` and `category` against `config/pricing-policy.toml` -- it does not trust the
guard's own verdict. Mock rows (`is_mock`) are refused: they can never count toward the gate.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from pricepilot.models import Recommendation
from pricepilot.policy.guard import GuardStatus, enforce, margin
from pricepilot.policy.thresholds import PricingPolicyThresholds, load_thresholds

EXPECTED_TOTAL = 50

CAUSE_UNPARSEABLE = "unparseable LLM reply (LLM)"
CAUSE_REFUSED = "guard refused an input it could not judge (LLM)"
CAUSE_DAILY = "move larger than the daily cap (LLM)"
CAUSE_SYNTHETIC = "weekly cap or missing reference, against the SYNTHETIC price_7d_ago"
CAUSE_DIRECTION = "intended cut impossible above the floor (LLM)"
CAUSE_BELOW_FLOOR = "kept price already below the floor"
CAUSE_DISCOUNT = "discount blocked by low stock (LLM)"
CAUSE_OTHER = "other"


@dataclass(frozen=True, slots=True)
class Violation:
    recommendation_id: int | None
    product_id: int
    scenario: str | None
    detail: str


@dataclass
class GateReport:
    total: int
    distinct: int
    status_counts: Counter[str]
    by_scenario: dict[str, Counter[str]]
    cause_counts: Counter[str]
    margin_violations: list[Violation] = field(default_factory=list)
    structure_violations: list[Violation] = field(default_factory=list)
    direction_violations: list[Violation] = field(default_factory=list)
    expected_total: int = EXPECTED_TOTAL

    @property
    def complete(self) -> bool:
        return self.total == self.expected_total and self.distinct == self.total

    @property
    def passed(self) -> bool:
        """The Phase 5 gate: the full set of distinct recommendations, no margin violation and no
        broken invariant between status and applied price."""
        return self.complete and not self.margin_violations and not self.structure_violations


def _scenario_key(scenario: str | None) -> str:
    return scenario or "baseline"


def classify_cause(row: Recommendation, thresholds: PricingPolicyThresholds) -> str | None:
    """Why a non-APPROVE row is not an APPROVE. For a speed-limit FLAG the decision is replayed with
    `price_7d_ago` set to `current_price`: if the guard then APPROVEs, only the synthetic 7-day
    reference blocked it (the daily cap alone would have passed); otherwise the LLM's move itself
    was too large."""
    if row.guard_status == GuardStatus.APPROVE:
        return None
    reason = row.guard_reason or ""
    if reason.startswith("unparseable proposer reply"):
        return CAUSE_UNPARSEABLE
    if reason.startswith("guard refused"):
        return CAUSE_REFUSED
    if reason.startswith("discount blocked"):
        return CAUSE_DISCOUNT
    if reason.startswith("direction cannot be kept"):
        return CAUSE_DIRECTION
    if "already below" in reason:
        return CAUSE_BELOW_FLOOR
    if reason.startswith("price_7d_ago is required"):
        return CAUSE_SYNTHETIC
    if reason.startswith("speed limit breached") and row.llm_proposed_price is not None:
        replay = enforce(
            category=row.category,
            cost=row.cost,
            current_price=row.current_price,
            proposed_price=row.llm_proposed_price,
            stock=row.stock,
            price_7d_ago=row.current_price,
            thresholds=thresholds,
        )
        return CAUSE_SYNTHETIC if replay.status == GuardStatus.APPROVE else CAUSE_DAILY
    return CAUSE_OTHER


def evaluate(
    rows: Sequence[Recommendation],
    *,
    thresholds: PricingPolicyThresholds | None = None,
    expected_total: int = EXPECTED_TOTAL,
) -> GateReport:
    t = thresholds or load_thresholds()
    if any(r.is_mock for r in rows):
        raise ValueError("mock rows can never count toward the Phase 5 gate")

    report = GateReport(
        total=len(rows),
        distinct=len({(r.product_id, r.scenario) for r in rows}),
        status_counts=Counter(str(r.guard_status) for r in rows),
        by_scenario={},
        cause_counts=Counter(),
        expected_total=expected_total,
    )
    for r in rows:
        report.by_scenario.setdefault(_scenario_key(r.scenario), Counter())[
            str(r.guard_status)
        ] += 1
        cause = classify_cause(r, t)
        if cause is not None:
            report.cause_counts[cause] += 1

        approved = r.guard_status == GuardStatus.APPROVE
        if approved != (r.guard_final_price is not None):
            report.structure_violations.append(
                Violation(
                    r.id, r.product_id, r.scenario, "applied price present iff APPROVE broken"
                )
            )
        if not approved or r.guard_final_price is None:
            continue

        floor = Decimal(str(t.margin_floor[r.category]))  # type: ignore[index]
        achieved = margin(r.guard_final_price, r.cost)
        if achieved < floor:
            report.margin_violations.append(
                Violation(
                    r.id,
                    r.product_id,
                    r.scenario,
                    f"{r.category}: final {r.guard_final_price} on cost {r.cost} is margin "
                    f"{achieved:.4f} < floor {floor}",
                )
            )
        proposed = r.llm_proposed_price
        if proposed is not None and (
            (proposed > r.current_price and r.guard_final_price < r.current_price)
            or (proposed < r.current_price and r.guard_final_price > r.current_price)
        ):
            report.direction_violations.append(
                Violation(
                    r.id,
                    r.product_id,
                    r.scenario,
                    f"proposed {proposed} vs current {r.current_price} but applied "
                    f"{r.guard_final_price}",
                )
            )
    return report

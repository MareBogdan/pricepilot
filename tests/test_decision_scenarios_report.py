"""Phase 5 session 5 (ADR-0042): the 50-recommendation plan, the hypothetical scenarios, and the
zero-violation gate logic. Offline, $0: rows are built in memory and the guard is the real one."""

from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal

import pytest

from pricepilot.decision.engine import CompetitorPrice, ProductSnapshot, build_prompt
from pricepilot.decision.report import (
    CAUSE_DAILY,
    CAUSE_ROUNDING,
    CAUSE_SYNTHETIC,
    CAUSE_TRUNCATED,
    CAUSE_UNPARSEABLE,
    GateReport,
    classify_cause,
    evaluate,
    summarise_moves,
)
from pricepilot.decision.scenarios import (
    EXPECTED_TOTAL,
    apply_scenario,
    build_plan,
    is_stress,
)
from pricepilot.models import Recommendation
from pricepilot.policy.thresholds import load_thresholds

T = load_thresholds()
# The real DB shape on 2026-10-07: 30 products, 13 with a guarded match (ids from product_matches).
ALL_IDS = list(range(1, 31))
MATCHED = [2, 3, 4, 5, 6, 7, 8, 14, 18, 19, 20, 21, 22]


# ---------------------------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------------------------


def test_plan_is_30_baseline_plus_13_plus_7_scenarios_all_distinct() -> None:
    plan = build_plan(ALL_IDS, MATCHED)
    assert len(plan) == EXPECTED_TOTAL == 50
    assert len(set(plan)) == 50
    assert Counter(i.scenario for i in plan) == {
        None: 30,
        "stress_undercut_15": 13,
        "stress_undercut_30": 7,
    }
    assert {i.product_id for i in plan if i.scenario is None} == set(ALL_IDS)
    assert {i.product_id for i in plan if i.scenario == "stress_undercut_15"} == set(MATCHED)
    # stress_undercut_30 goes to the 7 LOWEST-id matched products
    assert [i.product_id for i in plan if i.scenario == "stress_undercut_30"] == [
        2,
        3,
        4,
        5,
        6,
        7,
        8,
    ]


def test_plan_is_independent_of_input_order_and_duplicates() -> None:
    a = build_plan(ALL_IDS, MATCHED)
    b = build_plan(reversed(ALL_IDS), list(reversed(MATCHED)) + MATCHED)
    assert a == b


def test_plan_rejects_a_matched_product_outside_the_catalogue() -> None:
    with pytest.raises(ValueError, match="not in the catalogue"):
        build_plan([1, 2, 3], [2, 99])


# ---------------------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------------------


def snap(competitors: tuple[CompetitorPrice, ...]) -> ProductSnapshot:
    return ProductSnapshot(
        product_id=20, sku="S", title="Brit", brand="Brit", category="wet_food",
        cost=Decimal("7.90"), current_price=Decimal("12.50"), stock=39, net_weight_g=400,
        competitors=competitors, price_7d_ago=Decimal("12.53"),
    )  # fmt: skip


RIVALS = (
    CompetitorPrice("animax_ro", Decimal("12.99"), Decimal("0.99"), date(2026, 10, 6), True, "A"),
    CompetitorPrice("pentruanimale_ro", Decimal("10.99"), Decimal("0.95"), date(2026, 10, 6), True, "B"),
)  # fmt: skip


def test_baseline_is_returned_unchanged() -> None:
    s = snap(RIVALS)
    assert apply_scenario(s, None) is s


def test_undercut_scales_competitor_prices_and_keeps_our_own_numbers() -> None:
    s = apply_scenario(snap(RIVALS), "stress_undercut_15")
    # 12.99 x 0.85 = 11.0415 -> 11.04 ; 10.99 x 0.85 = 9.3415 -> 9.34 (HALF_UP)
    assert [c.price for c in s.competitors] == [Decimal("11.04"), Decimal("9.34")]
    assert [c.observed_price for c in s.competitors] == [Decimal("12.99"), Decimal("10.99")]
    assert (s.cost, s.current_price, s.stock, s.price_7d_ago) == (
        Decimal("7.90"), Decimal("12.50"), 39, Decimal("12.53"),
    )  # fmt: skip
    assert [c.price for c in apply_scenario(snap(RIVALS), "stress_undercut_30").competitors] == [
        Decimal("9.09"),  # 12.99 x 0.70 = 9.093
        Decimal("7.69"),  # 10.99 x 0.70 = 7.693
    ]


def test_a_stress_test_is_presented_as_pricing_input_and_labelled_in_the_trace() -> None:
    """ADR-0045: the earlier prompt announced 'hypothetical what-if' and the model ignored the
    prices (20 of 20 rationales). The prompt now carries the scaled prices as ordinary input; the
    label lives in the row (`scenario` starts with `stress_`) and the JSON keeps the real price."""
    s = apply_scenario(snap(RIVALS), "stress_undercut_30")
    prompt = build_prompt(s, [], T)
    assert "- animax_ro: 9.09 RON" in prompt  # 12.99 x 0.70, shown as the competitor's price
    for word in ("HYPOTHETICAL", "what-if", "stress", "scenario", "synthetic competitor"):
        assert word.lower() not in prompt.lower().replace("synthetic mock-store history", "")
    assert s.competitors[0].to_json()["observed_price"] == "12.99"
    assert is_stress("stress_undercut_15") and not is_stress(None) and not is_stress("baseline")
    assert "observed_price" not in snap(RIVALS).competitors[0].to_json()  # a real input has none


def test_scenarios_reject_unknown_names_and_products_without_matches() -> None:
    with pytest.raises(ValueError, match="unknown scenario"):
        apply_scenario(snap(RIVALS), "undercut_99")
    with pytest.raises(ValueError, match="needs matched competitor prices"):
        apply_scenario(snap(()), "stress_undercut_15")


# ---------------------------------------------------------------------------------------
# The zero-violation gate logic
# ---------------------------------------------------------------------------------------


def row(
    i: int,
    status: str,
    final: str | None,
    *,
    category: str = "wet_food",
    cost: str = "7.90",
    current: str = "12.50",
    proposed: str | None = "12.13",
    scenario: str | None = None,
    reason: str | None = None,
    stock: int = 39,
    is_mock: bool = False,
) -> Recommendation:
    return Recommendation(
        id=i,
        product_id=i,
        scenario=scenario,
        is_mock=is_mock,
        category=category,
        cost=Decimal(cost),
        current_price=Decimal(current),
        stock=stock,
        llm_proposed_price=None if proposed is None else Decimal(proposed),
        guard_status=status,
        guard_final_price=None if final is None else Decimal(final),
        guard_reason=reason,
    )


def full_set() -> list[Recommendation]:
    return [row(i, "APPROVE", "11.99") for i in range(1, 51)]


def test_a_clean_set_of_50_passes() -> None:
    report = evaluate(full_set(), thresholds=T)
    assert isinstance(report, GateReport)
    assert report.total == report.distinct == 50
    assert report.complete and report.passed
    assert report.margin_violations == [] and report.status_counts == {"APPROVE": 50}


def test_one_approve_below_the_floor_fails_the_gate() -> None:
    rows = full_set()
    # wet_food floor 18%: (9.00 - 7.90) / 9.00 = 12.2% -> a violation the guard "approved"
    rows[7] = row(8, "APPROVE", "9.00", proposed="9.00")
    report = evaluate(rows, thresholds=T)
    assert not report.passed
    assert len(report.margin_violations) == 1
    v = report.margin_violations[0]
    assert v.product_id == 8 and "floor" in v.detail


def test_an_approve_exactly_on_the_floor_is_not_a_violation() -> None:
    # cost 82.00, final 100.00 -> margin exactly 0.18 = the wet_food floor
    rows = full_set()
    rows[0] = row(1, "APPROVE", "100.00", cost="82.00", current="100.00", proposed="100.00")
    assert evaluate(rows, thresholds=T).margin_violations == []


def test_a_non_approve_row_is_never_a_margin_violation() -> None:
    rows = full_set()
    rows[3] = row(4, "FLAG", None, proposed="8.30", reason="speed limit breached: x")
    report = evaluate(rows, thresholds=T)
    assert report.margin_violations == [] and report.status_counts == {"APPROVE": 49, "FLAG": 1}
    assert report.passed  # a FLAG is a correct refusal, not a violation


def test_fewer_or_duplicate_rows_are_incomplete_and_do_not_pass() -> None:
    assert not evaluate(full_set()[:49], thresholds=T).passed
    dup = full_set()
    dup[1] = row(1, "APPROVE", "11.99")  # same (product, scenario) as row 1
    report = evaluate(dup, thresholds=T)
    assert report.total == 50 and report.distinct == 49 and not report.passed


def test_mock_rows_are_refused() -> None:
    rows = full_set()
    rows[0] = row(1, "APPROVE", "11.99", is_mock=True)
    with pytest.raises(ValueError, match="mock rows"):
        evaluate(rows, thresholds=T)


def test_status_and_price_must_agree() -> None:
    rows = full_set()
    rows[0] = row(1, "FLAG", "11.99", reason="x")  # an applied price on a FLAG
    assert evaluate(rows, thresholds=T).structure_violations


def test_a_direction_contradiction_is_reported_separately() -> None:
    rows = full_set()
    rows[0] = row(1, "APPROVE", "11.99", proposed="12.80")  # asked +, applied below current 12.50
    report = evaluate(rows, thresholds=T)
    assert len(report.direction_violations) == 1 and report.margin_violations == []


def test_by_scenario_breakdown() -> None:
    rows = full_set()
    rows[0] = row(1, "FLAG", None, scenario="stress_undercut_15", reason="speed limit breached: x")
    report = evaluate(rows, thresholds=T)
    assert report.by_scenario["stress_undercut_15"] == {"FLAG": 1}
    assert report.by_scenario["baseline"] == {"APPROVE": 49}


# ---------------------------------------------------------------------------------------
# Where a FLAG comes from: the LLM, or the synthetic 7-day reference
# ---------------------------------------------------------------------------------------


def test_flag_caused_only_by_the_synthetic_weekly_reference() -> None:
    # 25.00 -> proposed 25.50 -> charm 25.99 is +3.96% on the day (inside the 5% cap), but the
    # synthetic price 7 days ago is 21.00, so the 15% weekly cap trips (+23.8%). With the reference
    # neutralised the guard APPROVEs -> the FLAG is the synthetic reference's doing.
    r = row(
        1, "FLAG", None, category="treats", cost="10.00", current="25.00", proposed="25.50",
        reason="speed limit breached: final price 25.99 ...",
    )  # fmt: skip
    r.price_7d_ago = Decimal("21.00")
    assert classify_cause(r, T) == CAUSE_SYNTHETIC


def test_flag_caused_by_a_move_too_large_for_the_daily_cap() -> None:
    r = row(
        1, "FLAG", None, category="treats", cost="6.50", current="11.00", proposed="9.50",
        reason="speed limit breached: final price 9.99 ...",
    )  # fmt: skip
    r.price_7d_ago = Decimal("11.00")
    assert classify_cause(r, T) == CAUSE_DAILY  # -9% on the day: the LLM's move, not the reference


def test_unparseable_reply_and_approve_causes() -> None:
    assert (
        classify_cause(
            row(1, "FLAG", None, proposed=None, reason="unparseable proposer reply: x"), T
        )
        == CAUSE_UNPARSEABLE
    )
    assert classify_cause(row(1, "APPROVE", "11.99"), T) is None


def test_truncated_replies_are_counted_and_attributed_to_the_harness() -> None:
    empty = row(1, "FLAG", None, proposed=None, reason="unparseable proposer reply: x")
    empty.llm_stop_reason = "max_tokens"
    cut_but_approved = row(2, "APPROVE", "11.99")
    cut_but_approved.llm_stop_reason = "max_tokens"  # parsed, guard approved: still reported
    rows = [empty, cut_but_approved] + [row(i, "APPROVE", "11.99") for i in range(3, 51)]
    report = evaluate(rows, thresholds=T)
    assert classify_cause(empty, T) == CAUSE_TRUNCATED
    assert [v.product_id for v in report.truncated] == [1, 2]
    assert report.cause_counts == {CAUSE_TRUNCATED: 1}
    assert report.passed  # truncation is not a margin violation


def test_flag_where_rounding_alone_pushed_an_in_cap_proposal_over_the_cap() -> None:
    # 879.00 -> proposed 835.05 is exactly -5.0% (inside the cap); the nearest charm value 834.90
    # is -5.02%, so the daily cap trips. The LLM respected the cap; rounding did not.
    r = row(
        1, "FLAG", None, category="dry_food", cost="610.00", current="879.00", proposed="835.05",
        reason="speed limit breached: final price 834.90 (proposed 835.05) ...", stock=82,
    )  # fmt: skip
    r.price_7d_ago = Decimal("874.01")
    assert classify_cause(r, T) == CAUSE_ROUNDING


def test_approve_rows_are_split_into_moved_and_unchanged() -> None:
    rows = [row(i, "APPROVE", "12.50", current="12.50", proposed="12.50") for i in range(1, 49)]
    rows += [row(49, "APPROVE", "11.99"), row(50, "APPROVE", "12.99", proposed="12.80")]
    report = evaluate(rows, thresholds=T)
    assert (report.approve_unchanged, report.approve_moved) == (48, 2)


# ---------------------------------------------------------------------------------------
# What the guard actually saw: MoveSummary (the s5b evidence)
# ---------------------------------------------------------------------------------------


def test_move_summary_counts_proposals_before_the_guard_and_applied_after() -> None:
    rows = [
        # asked a big cut that breaches the wet_food floor and the cap; guard FLAGged it
        row(1, "FLAG", None, proposed="8.30", reason="speed limit breached: x"),
        # asked a -5% cut inside the cap and above the floor; guard approved a charm price
        row(2, "APPROVE", "11.99", proposed="11.90"),
        # asked for no change
        row(3, "APPROVE", "12.50", proposed="12.50"),
        # asked a cut on low stock; guard rejected
        row(4, "REJECT", None, proposed="12.00", reason="discount blocked: x"),
        # unparseable: no proposal at all
        row(5, "FLAG", None, proposed=None, reason="unparseable proposer reply: x"),
    ]
    m = summarise_moves(rows, thresholds=T)
    assert m.total == 5
    assert m.proposed_move == 3  # rows 1, 2, 4 (row 3 unchanged, row 5 none)
    # 8.30: margin (8.30-7.90)/8.30 = 4.8% < 18% ; 11.90: 33.6% ; 12.00: 34.2% -> only row 1
    assert m.proposed_below_floor == 1
    # daily cap 5% of 12.50 = 0.625: 8.30 is -33.6% (over); 11.90 is -4.8%; 12.00 is -4.0%
    assert m.proposed_over_cap == 1
    assert (m.approve_moved, m.approve_unchanged, m.flag, m.reject) == (1, 1, 2, 1)
    assert m.applied_below_floor == 0


def test_move_summary_counts_an_applied_price_under_the_floor() -> None:
    bad = row(1, "APPROVE", "9.00", proposed="9.00")  # wet_food margin 12.2% < 18%
    assert summarise_moves([bad], thresholds=T).applied_below_floor == 1

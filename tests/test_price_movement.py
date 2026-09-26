"""Hand-built in-memory series only (no DB) for scripts/measure_price_movement.py."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from measure_price_movement import (  # noqa: E402
    Obs,
    classify_pair,
    collapse_last_by_id,
    evaluable_events,
    find_events,
    gaps_between,
    holdout_start,
    make_obs,
    project_remeasure,
)

D0 = date(2026, 1, 1)


def day(n: int) -> date:
    return D0 + timedelta(days=n)


def flat(n_days: int, price: str = "100", start: int = 0) -> dict[date, Obs]:
    return {day(i): make_obs(price) for i in range(start, start + n_days)}


def test_base_change_at_exactly_two_percent_counts() -> None:
    types, sub = classify_pair(make_obs("100"), make_obs("102"))
    assert types == {"base_change"} and not sub
    types, sub = classify_pair(make_obs("100"), make_obs("98"))
    assert types == {"base_change"}


def test_base_change_just_below_two_percent_is_sub_threshold() -> None:
    types, sub = classify_pair(make_obs("100"), make_obs("101.99"))
    assert types == set() and sub
    types, sub = classify_pair(make_obs("100"), make_obs("100"))
    assert types == set() and not sub


def test_promo_start_and_end_flip() -> None:
    # promo start: base goes price(100) -> compare_at(100) unchanged, flag flips
    types, _ = classify_pair(make_obs("100"), make_obs("80", "100"))
    assert types == {"promo_start"}
    types, _ = classify_pair(make_obs("80", "100"), make_obs("100"))
    assert types == {"promo_end"}


def test_promo_depth_needs_promo_both_days() -> None:
    types, _ = classify_pair(make_obs("80", "100"), make_obs("70", "100"))
    assert types == {"promo_depth"}
    types, sub = classify_pair(make_obs("80", "100"), make_obs("79.5", "100"))
    assert types == set() and sub  # 0.625% price move under promo: rounding noise


def test_compare_at_not_above_price_is_not_promo() -> None:
    types, _ = classify_pair(make_obs("100"), make_obs("100", "100"))
    assert types == set()


def _series_with_event_at(t: int, total: int) -> dict[date, Obs]:
    s = flat(total)
    for i in range(t, total):
        s[day(i)] = make_obs("110")
    return s


def test_isolated_event_is_evaluable() -> None:
    s = _series_with_event_at(10, 20)
    assert evaluable_events(s, lenient=False) == [day(10)]


def test_event_inside_prewindow_makes_next_event_non_evaluable() -> None:
    s = flat(30)
    for i in range(10, 30):
        s[day(i)] = make_obs("110")
    for i in range(14, 30):
        s[day(i)] = make_obs("125")  # second event 4 days after the first
    events, _ = find_events(s)
    assert set(events) == {day(10), day(14)}
    assert day(14) not in evaluable_events(s, lenient=False)  # day(10) is in t-7..t-1


def test_first_event_still_evaluable_when_next_is_after_horizon_start() -> None:
    # events at 10 and 14: event 10's horizon (10..16) is fully observed, pre-window clean,
    # so it is evaluable; the horizon may contain later events (only the pre-window is checked).
    s = flat(30)
    for i in range(10, 30):
        s[day(i)] = make_obs("110")
    for i in range(14, 30):
        s[day(i)] = make_obs("125")
    assert evaluable_events(s, lenient=False) == [day(10)]


def test_missing_day_strict_vs_lenient() -> None:
    s = _series_with_event_at(10, 20)
    del s[day(5)]  # one missing day in the pre-window
    assert evaluable_events(s, lenient=False) == []
    assert evaluable_events(s, lenient=True) == [day(10)]
    del s[day(3)]
    del s[day(4)]
    assert evaluable_events(s, lenient=True) == []  # >1 missing in the pre-window


def test_missing_horizon_day_strict_vs_lenient() -> None:
    s = _series_with_event_at(10, 20)
    del s[day(14)]
    events, _ = find_events(s)
    assert day(10) in events
    assert evaluable_events(s, lenient=False) == []
    assert evaluable_events(s, lenient=True) == [day(10)]


def test_event_needs_observation_on_previous_day() -> None:
    s = flat(20)
    del s[day(9)]
    for i in range(10, 20):
        s[day(i)] = make_obs("110")
    events, _ = find_events(s)
    assert day(10) not in events  # t-1 unobserved: no event can be detected


def test_multiple_rows_on_one_day_take_last_by_id() -> None:
    rows = [
        (5, day(0), make_obs("100")),
        (9, day(0), make_obs("120")),
        (7, day(0), make_obs("110")),
        (11, day(1), make_obs("100")),
    ]
    series, multi = collapse_last_by_id(rows)
    assert multi == 1
    assert series[day(0)].price == 120 and series[day(1)].price == 100


def test_gaps_between_first_and_last_only() -> None:
    days = {day(0), day(1), day(4), day(5)}
    assert gaps_between(days) == [day(2), day(3)]
    assert gaps_between(set()) == []


def test_event_with_several_types_counted_once_in_union() -> None:
    # promo starts AND base moves: prev price 100, now price 70 with compare_at 120 (base 100->120)
    s = flat(9)
    s[day(9)] = make_obs("70", "120")
    events, _ = find_events(s)
    assert events[day(9)] == {"base_change", "promo_start"}
    assert len(events) == 1


def test_promo_depth_at_exactly_two_percent_counts() -> None:
    types, _ = classify_pair(make_obs("50", "100"), make_obs("51", "100"))
    assert types == {"promo_depth"}


def test_prewindow_boundary_event_at_t_minus_7_blocks_t_minus_8_does_not() -> None:
    def series(first_event: int) -> dict[date, Obs]:
        s = flat(40)
        for i in range(first_event, 40):
            s[day(i)] = make_obs("110")
        for i in range(20, 40):
            s[day(i)] = make_obs("125")
        return s

    assert day(20) not in evaluable_events(series(13), lenient=False)  # event at t-7
    assert day(20) in evaluable_events(series(12), lenient=False)  # event at t-8


def test_lenient_rejects_two_missing_horizon_days() -> None:
    s = _series_with_event_at(10, 20)
    del s[day(13)]
    del s[day(15)]
    assert evaluable_events(s, lenient=True) == []


def test_holdout_start_is_14th_last_collection_day_and_short_sources() -> None:
    days = {day(i) for i in range(30)}
    assert holdout_start(days) == day(16)
    assert holdout_start({day(i) for i in range(5)}) == day(0)  # fewer than 14: all holdout
    assert holdout_start(set()) == date.max


def _proj(days: int, gaps: int, cells: dict[str, int]) -> dict[str, object]:
    return {"days": days, "gaps": gaps, "cells": cells}


def test_projection_returns_date_when_rates_are_high() -> None:
    src = {
        "a": _proj(20, 0, {"food": 700, "litter": 700}),
        "b": _proj(20, 0, {"food": 700, "litter": 700}),
        "c": _proj(20, 0, {"food": 700}),
    }
    out = project_remeasure(src, day(0))  # type: ignore[arg-type]
    assert "date" in out and out["collection_days_added"] >= 8  # R1 needs 28 days


def test_projection_needs_architect_when_movement_too_rare() -> None:
    src = {"a": _proj(20, 0, {"food": 1}), "b": _proj(20, 0, {"food": 0}), "c": _proj(20, 0, {})}
    out = project_remeasure(src, day(0))  # type: ignore[arg-type]
    assert out["flag"] == "NEEDS ARCHITECT: movement too rare"


def test_projection_cells_must_reach_30_not_just_total() -> None:
    # huge single cell: total >= 200 but only 1 cell >= 30, so R2 never holds
    src = {"a": _proj(20, 0, {"food": 10_000}), "b": _proj(20, 0, {}), "c": _proj(20, 0, {})}
    out = project_remeasure(src, day(0))  # type: ignore[arg-type]
    assert "date" not in out


def test_projection_flags_unreachable_r1_when_gaps_exceed_two() -> None:
    src = {
        "a": _proj(40, 3, {"food": 900}),
        "b": _proj(40, 5, {"food": 900}),
        "c": _proj(20, 0, {}),
    }
    out = project_remeasure(src, day(0))  # type: ignore[arg-type]
    assert "R1 unreachable" in out["flag"]

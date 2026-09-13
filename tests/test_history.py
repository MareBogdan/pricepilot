"""STEP 4 (session note 2026-09-12): `make status` counts *consecutive* days of history and
names any gap date explicitly — CLAUDE.md §7's gate is ≥7 consecutive days, and a span-based
count silently hides a missed day in the middle. Pure-logic tests only; `compute_history()`
itself needs a database and is exercised in Step 6's end-to-end run, not here.
"""

from __future__ import annotations

from datetime import date, timedelta

from pricepilot.history import consecutive_days_from

DAY0 = date(2026, 9, 1)


def _days(*offsets: int) -> set[date]:
    return {DAY0 + timedelta(days=o) for o in offsets}


def test_no_history_is_zero_days_no_gaps() -> None:
    assert consecutive_days_from(set()) == (0, [])


def test_single_day_is_one_consecutive_day() -> None:
    consecutive, gaps = consecutive_days_from(_days(0))
    assert consecutive == 1
    assert gaps == []


def test_unbroken_run_counts_every_day() -> None:
    consecutive, gaps = consecutive_days_from(_days(0, 1, 2, 3, 4, 5, 6))
    assert consecutive == 7
    assert gaps == []


def test_a_gap_in_the_middle_is_named_and_caps_the_consecutive_count() -> None:
    """Days 0,1,2 then a gap at 3, then 4,5,6 — the naive span is 7 days, but only 3 are
    actually consecutive up to the most recent date."""
    consecutive, gaps = consecutive_days_from(_days(0, 1, 2, 4, 5, 6))
    assert consecutive == 3, "must count back from the most recent date, not the whole span"
    assert gaps == [DAY0 + timedelta(days=3)]


def test_gap_is_named_even_when_it_does_not_cap_the_streak() -> None:
    """A gap further back than the current unbroken run must still be visible — a silent gap
    is what costs the Phase 1 gate (CLAUDE.md §7)."""
    consecutive, gaps = consecutive_days_from(_days(0, 2, 3, 4, 5, 6, 7))
    assert consecutive == 6  # 2..7
    assert gaps == [DAY0 + timedelta(days=1)]


def test_multiple_gaps_are_all_named() -> None:
    consecutive, gaps = consecutive_days_from(_days(0, 3, 6))
    assert consecutive == 1  # only day 6 (the most recent) is unbroken
    assert gaps == [DAY0 + timedelta(days=n) for n in (1, 2, 4, 5)]


# ---------------------------------------------------------------------------
# 2026-09-13 session: the project-wide gate (CLAUDE.md §7) is a *union* of every source's
# collected_date values (`compute_history()`), and that union can hide one source's own gap
# behind another source's dates — exactly the shape a cron drifting across midnight could
# produce (`runner.py`'s `collected_date` is the run's real wall-clock start, per-source).
# `compute_history_by_source()` (DB-backed, not exercised here — same scoping note as above)
# runs this same pure function per source instead of on the union; these tests demonstrate, at
# the pure-function level, exactly what the union hides and the per-source breakdown recovers.
# ---------------------------------------------------------------------------


def test_a_source_specific_gap_is_invisible_in_the_project_wide_union() -> None:
    """Source A misses day 3 entirely; source B collects every day. The project-wide gate
    (the union of both sources' dates) shows a full, gapless streak — A's own outage on day 3
    is real but completely masked. This is the exact risk STEP 3 asks to guard against: a gate
    that looks healthy while one source has silently stopped collecting."""
    a_dates = _days(0, 1, 2, 4, 5, 6)  # missing day 3
    b_dates = _days(0, 1, 2, 3, 4, 5, 6)  # unbroken
    union = a_dates | b_dates

    union_consecutive, union_gaps = consecutive_days_from(union)
    assert union_consecutive == 7
    assert union_gaps == [], (
        "the union hides A's gap — this is the masking this step guards against"
    )

    a_consecutive, a_gaps = consecutive_days_from(a_dates)
    assert a_consecutive == 3, "A's own streak is capped at the gap, visible per-source"
    assert a_gaps == [DAY0 + timedelta(days=3)]


def test_a_source_that_stopped_collecting_is_stale_even_with_no_internal_gap() -> None:
    """Source A collected days 0-3 and then stopped (no run since) while B kept going through
    day 6. A's own date set has no internal gap — `consecutive_days_from` alone cannot tell
    "stopped" from "just started" — so staleness (last collected date vs. the project-wide
    latest) is a separate check `compute_history_by_source`'s caller makes, not something the
    gap-detection function itself can report."""
    a_dates = _days(0, 1, 2, 3)
    b_dates = _days(0, 1, 2, 3, 4, 5, 6)

    a_consecutive, a_gaps = consecutive_days_from(a_dates)
    assert a_gaps == [], "no internal gap - the problem is staleness, not a hole in the middle"
    assert a_consecutive == 4
    assert max(a_dates) != max(b_dates), "the staleness this test is about: A's last date is old"

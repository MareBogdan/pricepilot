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

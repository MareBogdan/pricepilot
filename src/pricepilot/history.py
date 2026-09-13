"""Consecutive days of collection history — the other half of the Phase 1 gate (CLAUDE.md §7).

STEP 4 (session note 2026-09-12): counting the *span* between the first and last collected date
is not the same as counting *consecutive* days — a single missed day in the middle silently
inflates the number `make status` used to report. This module walks backward from the most
recent collected date, stops at the first gap, and names every gap date in the observed span
explicitly, because a silent gap is exactly what costs the Phase 1 gate.

Reads `raw_listings.collected_date` (migration 0002, ADR-0016) across **all sources** — the
CLAUDE.md §7 gate is ≥7 consecutive days of history for the project, not per source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select

from pricepilot.db import session_scope
from pricepilot.models import RawListing

HISTORY_TARGET_DAYS = 7


@dataclass
class HistoryReport:
    consecutive_days: int
    first_date: date | None
    last_date: date | None
    gap_dates: list[date] = field(default_factory=list)
    target: int = HISTORY_TARGET_DAYS

    @property
    def met(self) -> bool:
        return self.consecutive_days >= self.target

    @property
    def span_days(self) -> int:
        """Calendar days from the first collected date to the last, inclusive. Always
        `>= consecutive_days`; the gap between them is exactly `len(gap_dates)`."""
        if self.first_date is None or self.last_date is None:
            return 0
        return (self.last_date - self.first_date).days + 1


def consecutive_days_from(dates: set[date]) -> tuple[int, list[date]]:
    """Pure: given the calendar dates with at least one ingested listing, return the run of
    consecutive days ending at the most recent date, plus every gap date within the observed
    span (first collected date to last). Pure and DB-free so `tests/test_history.py` can
    exercise every case — no history, one day, an unbroken run, a run with a gap — without a
    database.
    """
    if not dates:
        return 0, []
    last = max(dates)
    first = min(dates)

    consecutive = 0
    cursor = last
    while cursor in dates:
        consecutive += 1
        cursor -= timedelta(days=1)

    span = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    gaps = [d for d in span if d not in dates]
    return consecutive, gaps


def compute_history() -> HistoryReport:
    """The DB-backed report `scripts/status.py` prints."""
    with session_scope() as session:
        dates = {
            d
            for d in session.execute(select(RawListing.collected_date).distinct()).scalars()
            if d is not None
        }
    if not dates:
        return HistoryReport(consecutive_days=0, first_date=None, last_date=None, gap_dates=[])
    consecutive, gaps = consecutive_days_from(dates)
    return HistoryReport(
        consecutive_days=consecutive,
        first_date=min(dates),
        last_date=max(dates),
        gap_dates=gaps,
    )


def compute_history_by_source() -> dict[str, HistoryReport]:
    """The same computation `compute_history()` does, broken out per source.

    2026-09-13 session note (STATE.md): the project-wide count above is a **union** of every
    source's `collected_date` values. That is deliberate — CLAUDE.md §7's gate is ≥7 consecutive
    days for the project, not per source — but it means one source silently missing a day is
    invisible in the project-wide number as long as another source collected that same day. A
    cron drifting far enough to land a run's `collected_date` on the wrong side of midnight
    (`runner.py`'s `started_at.date()`, real wall-clock, never the cron's intended trigger time)
    would produce exactly that shape: one source with a gap, masked by the others.

    This function changes no gate and fixes nothing — it exists so `make status` can print each
    source's own date list, consecutive count, and gaps explicitly, so a per-source gap is visible
    the day it happens rather than discovered only once it happens to coincide with every other
    source's gap too.
    """
    with session_scope() as session:
        rows = session.execute(
            select(RawListing.source, RawListing.collected_date).distinct()
        ).all()

    dates_by_source: dict[str, set[date]] = {}
    for source, collected_date in rows:
        if collected_date is None:
            continue
        dates_by_source.setdefault(source, set()).add(collected_date)

    reports: dict[str, HistoryReport] = {}
    for source, dates in dates_by_source.items():
        consecutive, gaps = consecutive_days_from(dates)
        reports[source] = HistoryReport(
            consecutive_days=consecutive,
            first_date=min(dates),
            last_date=max(dates),
            gap_dates=gaps,
        )
    return reports

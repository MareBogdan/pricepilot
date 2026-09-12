"""`scrape_runs.error_detail` — session note (2026-09-12): a bare error *count* was
un-diagnosable after the fact, twice (petmax's skipped_out_of_scope reasons, pentruanimale's 3
unexplained parse errors). `_error_detail` persists the actual strings, capped.
"""

from __future__ import annotations

from pricepilot.scrapers.runner import (
    MAX_ERROR_LENGTH,
    MAX_PERSISTED_ERRORS,
    _error_detail,
)


def test_no_errors_is_none_not_an_empty_list() -> None:
    assert _error_detail([]) is None


def test_errors_are_persisted_verbatim_under_the_cap() -> None:
    errors = ["one thing broke", "another thing broke"]
    assert _error_detail(errors) == errors


def test_errors_are_capped_in_count() -> None:
    errors = [f"error {i}" for i in range(MAX_PERSISTED_ERRORS + 10)]
    detail = _error_detail(errors)
    assert detail is not None
    # capped errors + one summary line about how many more were dropped
    assert len(detail) == MAX_PERSISTED_ERRORS + 1
    assert detail[:MAX_PERSISTED_ERRORS] == errors[:MAX_PERSISTED_ERRORS]
    assert "10 more errors" in detail[-1]


def test_a_single_error_is_capped_in_length() -> None:
    long_error = "x" * (MAX_ERROR_LENGTH * 3)
    detail = _error_detail([long_error])
    assert detail is not None
    assert len(detail[0]) == MAX_ERROR_LENGTH

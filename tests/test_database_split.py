"""STEP 2 (session note 2026-09-12): a test run must never be able to write to Neon.

Enforced mechanically in `tests/conftest.py::pytest_configure`, not by convention. This file
is the self-test proving the guard actually trips — the same reasoning as
`test_powershell_ascii.py` / DECISIONS.md ADR-0013: a rule with no failing test is a
suggestion, not a rule.
"""

from __future__ import annotations

import pytest

from tests.conftest import (
    NeonGuardError,
    assert_safe_for_tests,
    resolve_test_database_url,
)

NEON_URL = "postgresql+psycopg://neondb_owner:x@ep-foo.c-5.eu-central-1.aws.neon.tech/neondb"
LOCAL_URL = "postgresql+psycopg://pricepilot:change_me_locally@localhost:5433/pricepilot"


def test_no_test_database_url_falls_back_to_fully_offline() -> None:
    """Matches CI's `check` job: no DATABASE_URL set, the suite must still pass."""
    assert resolve_test_database_url({}) is None


def test_test_database_url_wins_even_if_database_url_is_neon() -> None:
    """A developer's real .env has DATABASE_URL=Neon. Tests must ignore it entirely."""
    env = {"DATABASE_URL": NEON_URL, "TEST_DATABASE_URL": LOCAL_URL}
    assert resolve_test_database_url(env) == LOCAL_URL


def test_offline_run_is_always_safe() -> None:
    assert_safe_for_tests(None)  # does not raise


def test_local_docker_url_is_safe() -> None:
    assert_safe_for_tests(LOCAL_URL)  # does not raise


def test_guard_actually_trips_on_a_neon_host() -> None:
    """The self-test: if this ever stops raising, the guard has gone vacuous."""
    with pytest.raises(NeonGuardError):
        assert_safe_for_tests(NEON_URL)


def test_guard_is_wired_into_pytest_configure() -> None:
    """Confirms the hook is actually present, not just the helper functions it calls."""
    from tests import conftest

    assert hasattr(conftest, "pytest_configure")

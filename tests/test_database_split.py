"""STEP 2 (session note 2026-09-12): a test run must never be able to write to Neon.

Enforced mechanically in `tests/conftest.py::pytest_configure`, not by convention. This file
is the self-test proving the guard actually trips — the same reasoning as
`test_powershell_ascii.py` / DECISIONS.md ADR-0013: a rule with no failing test is a
suggestion, not a rule.
"""

from __future__ import annotations

import os

import pytest

from pricepilot.config import Settings
from tests.conftest import (
    OFFLINE_SENTINEL_DATABASE_URL,
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


def test_missing_test_database_url_cannot_fall_back_to_envs_neon_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for a `reviewer` catch (2026-09-28): the old `pytest_configure` popped
    `DATABASE_URL` when `TEST_DATABASE_URL` was absent, expecting that to mean "fully offline".
    It didn't -- `Settings(env_file=".env")` falls back to `.env`'s own `DATABASE_URL` (the real
    Neon credential on a developer machine) whenever the OS environment variable is absent, and
    only an explicit OS-level value wins over that fallback. Session 2 added the first test in
    this repo that touches a live database, ran under a completely normal `pytest` invocation
    with no `TEST_DATABASE_URL` exported as a real env var, and silently hit Neon.

    Calls the REAL `pytest_configure` hook (not a hand-simulation of its logic) against a
    deliberately clean environment, then builds a REAL `Settings()` -- reading the real `.env` on
    disk, exactly like production code does -- and asserts it can never resolve to Neon no matter
    what `.env` holds. Would have failed under the pre-fix code on any machine whose real `.env`
    (like this project's) has a genuine Neon `DATABASE_URL`."""
    from tests.conftest import pytest_configure

    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert resolve_test_database_url(dict(os.environ)) is None

    pytest_configure(config=None)  # type: ignore[arg-type]  # only reads/writes os.environ

    resolved = Settings().database_url
    assert resolved == OFFLINE_SENTINEL_DATABASE_URL
    assert_safe_for_tests(resolved)  # does not raise -- not a neon.tech host

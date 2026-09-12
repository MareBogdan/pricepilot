"""Shared fixtures.

CLAUDE.md §9: a scraper must never hit a live site during tests. Nothing in this suite
makes an outbound request; adapters are always exercised against tests/fixtures/.

Session note (2026-09-12): two databases exist now. `DATABASE_URL` is Neon — the collected
data, authoritative, never touched by a test run. `TEST_DATABASE_URL` is the local docker
Postgres — tests and offline development. See DECISIONS.md ADR-0014 and .env.example.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from services.mock_store.app import app as mock_store_app

# ---------------------------------------------------------------------------
# STEP 2: a test run must never be able to write to Neon — enforced mechanically here,
# not by convention. See DECISIONS.md ADR-0014 and tests/test_database_split.py, which is
# the self-test proving this guard actually trips (same reasoning as ADR-0013).
# ---------------------------------------------------------------------------

# Host fragments that identify the real collected-data database. A list rather than one
# literal so a future move to another managed host is still caught by intent, not string luck.
FORBIDDEN_DATABASE_HOST_FRAGMENTS: tuple[str, ...] = ("neon.tech",)


class NeonGuardError(RuntimeError):
    """Raised by `pytest_configure` if a test run could reach the Neon database."""


def resolve_test_database_url(env: dict[str, str]) -> str | None:
    """What `DATABASE_URL` should be for a test run, given the process environment.

    Pure function so `tests/test_database_split.py` can exercise every branch without
    spawning a real pytest subprocess. `TEST_DATABASE_URL` unset means fully offline
    (CLAUDE.md CI job: no DATABASE_URL, /health must degrade rather than crash).
    """
    return env.get("TEST_DATABASE_URL") or None


def assert_safe_for_tests(database_url: str | None) -> None:
    """Raises `NeonGuardError` if `database_url` looks like the real Neon database.

    `None` (fully offline) is always safe.
    """
    if database_url is None:
        return
    lowered = database_url.lower()
    for fragment in FORBIDDEN_DATABASE_HOST_FRAGMENTS:
        if fragment in lowered:
            raise NeonGuardError(
                f"A test run resolved DATABASE_URL to a host containing {fragment!r}. "
                "Tests must use TEST_DATABASE_URL (local docker Postgres) or run fully "
                "offline — never the collected-data database. See DECISIONS.md ADR-0014."
            )


def pytest_configure(config: pytest.Config) -> None:
    """Re-point `DATABASE_URL` before any test module is collected.

    This runs before collection, so no test — and no module-level code in one — can ever
    see a Neon URL sitting in `.env`: the environment variable pydantic-settings actually
    reads is overwritten here first, unconditionally, regardless of what any test author
    does later. See DECISIONS.md ADR-0014.
    """
    test_url = resolve_test_database_url(dict(os.environ))
    if test_url:
        os.environ["DATABASE_URL"] = test_url
    else:
        os.environ.pop("DATABASE_URL", None)
    assert_safe_for_tests(os.environ.get("DATABASE_URL"))


@pytest.fixture
def mock_store() -> TestClient:
    return TestClient(mock_store_app)

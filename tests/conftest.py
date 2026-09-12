"""Shared fixtures.

CLAUDE.md §9: a scraper must never hit a live site during tests. Nothing in this suite
makes an outbound request; adapters are always exercised against tests/fixtures/.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from services.mock_store.app import app as mock_store_app


@pytest.fixture
def mock_store() -> TestClient:
    return TestClient(mock_store_app)

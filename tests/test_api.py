"""Main API. The Phase 0 gate requires /health to respond."""

from __future__ import annotations

from fastapi.testclient import TestClient

from pricepilot import __version__
from pricepilot.api.main import app

client = TestClient(app)


def test_health_responds_without_a_database() -> None:
    """The API must report a missing database, not crash on it."""
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in {"ok", "degraded"}
    assert body["version"] == __version__
    assert isinstance(body["database"], bool)
    # status and database must agree
    assert (body["status"] == "ok") == body["database"]

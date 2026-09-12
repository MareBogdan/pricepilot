"""`PoliteClient`'s robots.txt handling, offline via `httpx.MockTransport` (CLAUDE.md §9: a
scraper must never hit a live site during tests — this file never does).

ADR-0020 (session note 2026-09-13): `RobotFileParser.read()` fetches with a bare
`urllib.request.urlopen()`, which sends Python's generic default User-Agent, not the honest one
`PoliteClient` is configured with. Found against pentruanimale.ro: our real, identified client got
HTTP 200 on every request — including robots.txt itself — while the anonymous stdlib fetch of the
exact same robots.txt URL got 403, which `RobotFileParser` interprets as "disallow everything".
That produced a false block: the shop never blocked our actual crawler, our own compliance check
was silently using a different, unidentified one. `PoliteClient._robots_for` now fetches
robots.txt through the same `self._client` (and therefore the same honest User-Agent) as every
other request.
"""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest

from pricepilot.config import get_settings
from pricepilot.scrapers.base import PoliteClient

HONEST_UA = "TestBot/1.0 (+mailto:test@example.com; test suite)"


@pytest.fixture(autouse=True)
def _honest_user_agent(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """`PoliteClient.__init__` refuses to run without a real `SCRAPER_USER_AGENT` (base.py's
    `require_honest_user_agent`) — set one for the duration of this module's tests only."""
    monkeypatch.setenv("SCRAPER_USER_AGENT", HONEST_UA)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _client(handler: httpx.MockTransport | object) -> PoliteClient:
    """A `PoliteClient` wired to a mock transport instead of the network."""
    return PoliteClient("test_source", transport=httpx.MockTransport(handler))


def test_robots_txt_is_fetched_with_our_own_honest_user_agent() -> None:
    """The regression this whole file exists to prevent: confirm the robots.txt request itself
    carries our configured identity, not whatever a bare urlopen() would have sent."""
    seen_user_agents: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_user_agents.append(request.headers.get("user-agent"))
        return httpx.Response(200, text="User-agent: *\nDisallow: /private\n")

    client = _client(handler)
    assert client.may_fetch("https://example.test/ok") is True
    assert seen_user_agents == [HONEST_UA]


def test_403_on_robots_txt_disallows_everything() -> None:
    """Matches RobotFileParser.read()'s own documented behaviour for 401/403 — a shop that
    actively blocks robots.txt access is treated conservatively, not as "assume allowed"."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    client = _client(handler)
    assert client.may_fetch("https://example.test/anything") is False


def test_401_on_robots_txt_also_disallows_everything() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    client = _client(handler)
    assert client.may_fetch("https://example.test/anything") is False


def test_404_on_robots_txt_allows_everything() -> None:
    """A shop with no robots.txt at all — matches stdlib's documented other-4xx behaviour."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = _client(handler)
    assert client.may_fetch("https://example.test/anything") is True


def test_real_rules_are_honoured_when_robots_txt_is_reachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="User-agent: *\nDisallow: /private\n")

    client = _client(handler)
    assert client.may_fetch("https://example.test/private/page") is False
    assert client.may_fetch("https://example.test/public/page") is True


def test_robots_txt_fetched_once_per_origin_and_cached() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, text="User-agent: *\n")

    client = _client(handler)
    client.may_fetch("https://example.test/a")
    client.may_fetch("https://example.test/b")
    assert calls == 1


def test_network_failure_fetching_robots_txt_refuses_rather_than_assumes_allowed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = _client(handler)
    from pricepilot.scrapers.base import RobotsDisallowed

    with pytest.raises(RobotsDisallowed):
        client.may_fetch("https://example.test/anything")

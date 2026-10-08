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


# -- Crawl-delay ------------------------------------------------------------


def _slept_before_second_request(
    monkeypatch: pytest.MonkeyPatch, robots: str, *, min_delay: str = "2", max_delay: str = "4"
) -> list[float]:
    """Run two `get()`s against a mock origin and return every `time.sleep` duration requested
    (the real sleep is stubbed out, so the test is instant)."""
    monkeypatch.setenv("SCRAPER_MIN_DELAY_SECONDS", min_delay)
    monkeypatch.setenv("SCRAPER_MAX_DELAY_SECONDS", max_delay)
    get_settings.cache_clear()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=robots)
        return httpx.Response(200, text="<html></html>")

    sleeps: list[float] = []
    monkeypatch.setattr("pricepilot.scrapers.base.time.sleep", sleeps.append)
    # Freeze the clock so "time since the last request" is 0 and the full delay is requested.
    monkeypatch.setattr("pricepilot.scrapers.base.time.monotonic", lambda: 1000.0)
    client = _client(handler)
    client.get("https://example.test/a")
    client.get("https://example.test/b")
    return sleeps


def test_declared_crawl_delay_raises_the_pause_between_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps = _slept_before_second_request(monkeypatch, "User-agent: *\nCrawl-delay: 10\n")
    assert len(sleeps) == 1
    assert sleeps[0] >= 10.0  # configured 2-4 s alone would have been below this


def test_crawl_delay_is_matched_to_our_own_agent_not_other_bots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """petmax.ro declares 5-20 s for named bots and nothing for `*`. A delay that belongs to
    another bot must not slow us down, and one addressed to us must apply."""
    others = "User-agent: bingbot\nCrawl-delay: 20\n\nUser-agent: *\nDisallow: /private\n"
    sleeps = _slept_before_second_request(monkeypatch, others)
    assert 2.0 <= sleeps[0] <= 4.0

    ours = "User-agent: TestBot\nCrawl-delay: 15\n"
    sleeps = _slept_before_second_request(monkeypatch, ours)
    assert sleeps[0] >= 15.0


def test_crawl_delay_never_lowers_the_configured_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps = _slept_before_second_request(monkeypatch, "User-agent: *\nCrawl-delay: 1\n")
    assert 2.0 <= sleeps[0] <= 4.0

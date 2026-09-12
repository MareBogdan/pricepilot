"""The `Scraper` protocol, the validated boundary type, and the polite HTTP fetcher.

Every adapter splits in two:

* `parse(html, page_url)` — pure, offline, deterministic. This is what the tests run.
* `scrape(...)` — the only part that touches the network, and the only part subject to
  rate limiting and `robots.txt`.

Keeping them apart is what makes CLAUDE.md §9's "a scraper hitting a live site during
tests" structurally impossible rather than a rule someone has to remember.
"""

from __future__ import annotations

import hashlib
import random
import re
import time
import unicodedata
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol, runtime_checkable
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from pricepilot.config import get_settings


class ScraperConfigError(RuntimeError):
    """Raised when the scraper is not safe to run — e.g. no honest contact in the User-Agent."""


class RobotsDisallowed(RuntimeError):
    """Raised when `robots.txt` forbids the URL. Never caught and ignored."""


# ---------------------------------------------------------------------------
# The validated boundary type
# ---------------------------------------------------------------------------


class Listing(BaseModel):
    """One purchasable variant, as offered by one shop at one moment.

    Pydantic validates at the boundary (CLAUDE.md §7 Phase 1), so a markup change that
    starts yielding empty titles or zero prices fails loudly at parse time instead of
    quietly poisoning the price series.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    source_product_id: str | None = None
    url: str
    title: str = Field(min_length=3)
    brand: str | None = None
    price: Decimal = Field(gt=0)
    currency: str = "RON"
    compare_at_price: Decimal | None = Field(default=None, gt=0)
    in_stock: bool | None = None
    raw_payload: dict[str, object] | None = None

    @field_validator("title")
    @classmethod
    def _collapse_whitespace(cls, v: str) -> str:
        return " ".join(v.split())

    @property
    def content_hash(self) -> str:
        """sha256 of the normalized title. Phase 2 caches attribute extraction on this so
        the LLM never re-runs on an unchanged title (CLAUDE.md §5 — largest cost risk)."""
        return hashlib.sha256(normalize_title(self.title).encode("utf-8")).hexdigest()

    @property
    def is_discounted(self) -> bool:
        return self.compare_at_price is not None and self.compare_at_price > self.price


def normalize_title(title: str) -> str:
    """Lowercase, strip diacritics, collapse whitespace.

    Deliberately minimal: this exists so `content_hash` is stable across the diacritic
    inconsistency CLAUDE.md §7 documents ("Hrană" vs "Hrana"). Real attribute extraction
    is Phase 2 and does not belong here.
    """
    folded = unicodedata.normalize("NFKD", title.lower())
    stripped = "".join(c for c in folded if not unicodedata.combining(c))
    return " ".join(stripped.split())


@dataclass
class ScrapeResult:
    """What one adapter run produced. `errors` carries parse failures that were skipped
    rather than raised, so a single broken card cannot lose a whole page of prices."""

    source: str
    listings: list[Listing] = field(default_factory=list)
    pages_fetched: int = 0
    errors: list[str] = field(default_factory=list)
    skipped_out_of_scope: int = 0


# ---------------------------------------------------------------------------
# The protocol every adapter implements
# ---------------------------------------------------------------------------


@runtime_checkable
class Scraper(Protocol):
    """Implemented once per source. `name` is the key used in `raw_listings.source`,
    in `scrape_runs.source`, and as the fixture directory name."""

    name: str

    def parse(self, html: str, page_url: str) -> tuple[list[Listing], list[str]]:
        """Pure. Returns (listings, errors). Never performs I/O."""
        ...

    def scrape(self, limit: int | None = None, dry_run: bool = False) -> ScrapeResult:
        """Fetches and parses. The only method that touches the network."""
        ...


# ---------------------------------------------------------------------------
# Politeness
# ---------------------------------------------------------------------------


def require_honest_user_agent() -> str:
    """CLAUDE.md §5.4: honest User-Agent with a contact, and the contact is never committed.

    The address lives in `SCRAPER_USER_AGENT` in `.env`; the repo ships only a placeholder in
    `.env.example`. A scraper that finds the placeholder fails here rather than introducing
    itself to a shop with a fake address.
    """
    user_agent = get_settings().scraper_user_agent.strip()
    if not user_agent:
        raise ScraperConfigError(
            "SCRAPER_USER_AGENT is empty. Set it in .env — see .env.example (CLAUDE.md §5.4)."
        )
    if "@" not in user_agent:
        raise ScraperConfigError(
            f"SCRAPER_USER_AGENT carries no contact address: {user_agent!r}. "
            "A shop that objects must be able to reach a human (CLAUDE.md §5.4)."
        )
    if "you@example.com" in user_agent:
        raise ScraperConfigError(
            "SCRAPER_USER_AGENT still holds the .env.example placeholder 'you@example.com'. "
            "Put your real address in .env — it is never committed."
        )
    return user_agent


class PoliteClient:
    """An `httpx` client that sleeps between requests and refuses `robots.txt`-disallowed URLs.

    The delay is the maximum of the configured floor and the source's declared `Crawl-delay`,
    so a shop asking for more than 2 seconds gets it.
    """

    def __init__(
        self,
        source: str,
        crawl_delay_floor: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        settings = get_settings()
        self.source = source
        self.user_agent = require_honest_user_agent()
        self._min = max(settings.scraper_min_delay_seconds, crawl_delay_floor or 0.0)
        self._max = max(settings.scraper_max_delay_seconds, self._min)
        self._robots: dict[str, RobotFileParser] = {}
        self._last_request: float | None = None
        self._client = httpx.Client(
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8",
            },
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
            # Injection seam for tests only (e.g. httpx.MockTransport) — CLAUDE.md §9 forbids a
            # scraper hitting a live site during tests, and this is what lets tests/test_base.py
            # exercise the real robots.txt request path (headers, status handling) with no
            # network at all. `None` (the default) means "use httpx's real transport", unchanged.
            transport=transport,
        )

    def __enter__(self) -> PoliteClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # -- robots -------------------------------------------------------------

    def _robots_for(self, url: str) -> RobotFileParser:
        """Fetch and parse `robots.txt` for `url`'s origin.

        Deliberately does **not** call `RobotFileParser.read()`: that method fetches with a bare
        `urllib.request.urlopen()`, which sends Python's generic default User-Agent — not the
        honest, configured one every other request on this client uses. A shop that 403s
        unidentified/anonymous traffic while happily allowing our real, honestly-identified
        client would otherwise produce a false "everything disallowed" reading — found against
        pentruanimale.ro (ADR-0020): the real client got 200 on every request, robots.txt
        included, while stdlib's anonymous fetch of the same URL got 403. Fetching through
        `self._client` instead means the compliance check sees exactly what our crawler sees.
        """
        parts = urlparse(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            robots_url = f"{origin}/robots.txt"
            parser = RobotFileParser()
            parser.set_url(robots_url)
            try:
                response = self._client.get(robots_url)
            except httpx.HTTPError as exc:  # unreachable robots.txt: refuse, never assume allowed
                raise RobotsDisallowed(f"could not read {robots_url}: {exc}") from exc
            # Mirrors RobotFileParser.read()'s own status-code handling (see its source), just
            # sourced from our identified fetch instead of an anonymous one.
            if response.status_code in (401, 403):
                parser.disallow_all = True  # type: ignore[attr-defined]  # real attr, undeclared in typeshed
            elif 400 <= response.status_code < 500:
                parser.allow_all = True  # type: ignore[attr-defined]  # real attr, undeclared in typeshed
            elif response.status_code < 400:
                parser.parse(response.text.splitlines())
            # >=500: matches stdlib's own behaviour for that case — neither flag is set and
            # nothing is parsed, so can_fetch() falls through to its default of allowing.
            self._robots[origin] = parser
        return self._robots[origin]

    def may_fetch(self, url: str) -> bool:
        return self._robots_for(url).can_fetch(self.user_agent, url)

    def declared_crawl_delay(self, url: str) -> float | None:
        raw = self._robots_for(url).crawl_delay(self.user_agent)
        return float(raw) if raw is not None else None

    # -- fetching -----------------------------------------------------------

    def _sleep(self) -> None:
        if self._last_request is None:
            return
        wait = random.uniform(self._min, self._max) - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)

    def get(self, url: str) -> str:
        if not self.may_fetch(url):
            raise RobotsDisallowed(f"robots.txt disallows {url} for {self.user_agent!r}")
        self._sleep()
        response = self._client.get(url)
        self._last_request = time.monotonic()
        response.raise_for_status()
        return response.text

    def get_many(self, urls: Sequence[str]) -> Iterator[tuple[str, str]]:
        for url in urls:
            yield url, self.get(url)


# ---------------------------------------------------------------------------
# Shared parsing helpers
# ---------------------------------------------------------------------------

# `\s` matches the non-breaking space these shops use as a thousands separator, so the
# character class does not need to name it — and naming it literally would put a raw U+00A0
# into the source, which ruff then flags as an ambiguous character.
_MONEY = re.compile(r"\d[\d.\s]*(?:,\d+)?")
_WHITESPACE = re.compile(r"\s")


def parse_romanian_money(text: str) -> Decimal | None:
    """`"249,11 Lei"` -> `Decimal("249.11")`.

    Romanian shops write the decimal separator as a comma and the thousands separator as a
    dot, a space, or a non-breaking space. Getting this wrong turns "1.234,50 lei" into
    1.23 lei, which is a silent thousandfold margin error rather than a crash — hence a
    dedicated function and a test.
    """
    match = _MONEY.search(text)
    if not match:
        return None
    raw = _WHITESPACE.sub("", match.group(0)).replace(".", "").replace(",", ".")
    try:
        value = Decimal(raw)
    except ArithmeticError:
        return None
    return value if value > 0 else None

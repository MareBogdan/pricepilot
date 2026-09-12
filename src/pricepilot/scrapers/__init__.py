"""Phase 1 — collection.

One adapter per source, all behind the `Scraper` protocol in `base.py`. Adapters are pure
parsers over saved HTML plus a polite fetcher; the parsing half is what the tests exercise,
offline, against `tests/fixtures/<source>/` (CLAUDE.md §5.1).

`SCRAPERS` is the registry `scripts/scrape.py` and the daily schedule resolve `--source` against.
Each adapter joins it when it is finished — one source at a time, on a schedule, rather than three
at once (DECISIONS.md ADR-0010).
"""

from pricepilot.scrapers.base import Listing, Scraper, ScrapeResult
from pricepilot.scrapers.petmax import PetmaxScraper

SCRAPERS: dict[str, type[PetmaxScraper]] = {
    PetmaxScraper.name: PetmaxScraper,
}

__all__ = ["SCRAPERS", "Listing", "PetmaxScraper", "ScrapeResult", "Scraper"]

"""`petmax.ro` — the anchor source (CLAUDE.md §7 Phase 1).

Gomag platform, fully server-rendered. Verified 2026-09-12 against
`tests/fixtures/petmax_ro/` — see `docs/SOURCES.md` for the recon notes.

**Why this source is the anchor.** Each product card carries a `data-Gomag` attribute holding
the list price and the final price as machine-readable JSON:

    data-Gomag='{"Lei_price":"249.11","Lei_final_price":"199.29", ...}'

So the current price *and* the pre-discount price come out of the markup without parsing
Romanian decimal commas out of display text. `compare_at_price` is what drives promotion
detection in Phase 4, and this is the only verified source that hands it over cleanly.

The display text (`<s class="price-full">249,11 Lei</s>`) is parsed as a cross-check: if the
two disagree the card is rejected rather than ingested, because a silent price error poisons a
time series that cannot be rebuilt.

**Structure.** One row per purchasable size — no variant grouping, so no product-page fetch is
needed. Pagination is `?p=N`, zero-based, advertised by `<link rel="next">`.

**Not fetched.** Facet URLs carry `?_crawl=0`; `robots.txt` disallows `/ajax/loadProducts*` and
`/*?c=*`. This adapter follows `?p=N` only and touches neither.
"""

from __future__ import annotations

import json
from decimal import Decimal

from selectolax.parser import HTMLParser, Node

from pricepilot.config import get_settings
from pricepilot.scrapers.base import (
    Listing,
    PoliteClient,
    ScrapeResult,
    parse_romanian_money,
)

SOURCE = "petmax_ro"
BASE_URL = "https://www.petmax.ro"

# Categories collected on the daily schedule. STEP 5 (session note 2026-09-12): the original six
# (food and treats — where cross-shop overlap lives, CLAUDE.md §7's 400-product gate) cannot
# reach the 3,000-in-scope-listings gate from petmax alone. Expanded to the smallest in-scope set
# that reliably clears it: litter, grooming/hygiene, accessories and toys for dogs and cats, per
# CLAUDE.md §7's product-scope list. Recon (one page per category, 2026-09-12) estimated ~4,990
# listings and ~208 page requests across all 13 — see docs/SOURCES.md for the per-category
# breakdown and the request-count / wall-clock estimate.
DEFAULT_CATEGORIES: tuple[str, ...] = (
    "hrana-uscata-caini",
    "hrana-umeda-caini",
    "recompense-delicioase-caini",
    "hrana-uscata-pisici",
    "hrana-umeda-pisici",
    "recompense-delicioase-pisici",
    "asternut-litiera-nisip-silicat",
    "igiena-si-ingrijire-caini",
    "igiena-si-ingrijire-pisici",
    "accesorii-caini",
    "accesorii-pisici",
    "jucarii-caini",
    "jucarii-pisici",
)

# CLAUDE.md §7 Phase 1: regulated products are filtered **at ingest, not later**. The category
# allowlist above already excludes petmax's pharmacy tree (`farmacie-*`, `antiparazitare-*`,
# `deparazitare-*`, `diete-veterinare-*`, `antibiotice-*`, `afectiuni-*`, `dermatologice-*`).
# This is the second line of defence, for a regulated item mis-filed into a food category.
REGULATED_TITLE_TOKENS: tuple[str, ...] = (
    "antiparazitar",
    "deparazitare",
    "vaccin",
    "pipeta",
    "pipete",
    "antibiotic",
    "veterinary diet",
    "dieta veterinara",
    "prescription diet",
    "vet diet",
    "comprimate",
    "antiinflamator",
)

# The two prices must agree to the leu. Gomag rounds the display text, so an exact-cent match is
# too strict; a whole-leu disagreement means the card is not what the parser thinks it is.
PRICE_CROSSCHECK_TOLERANCE = Decimal("1.00")


def _text(node: Node | None) -> str:
    return node.text(strip=True) if node is not None else ""


def is_regulated(title: str) -> bool:
    """True if the title names a regulated product (CLAUDE.md §7 Phase 1)."""
    lowered = title.lower()
    return any(token in lowered for token in REGULATED_TITLE_TOKENS)


class PetmaxScraper:
    """Adapter for `petmax.ro`. Implements the `Scraper` protocol."""

    name = SOURCE

    def __init__(
        self,
        categories: tuple[str, ...] = DEFAULT_CATEGORIES,
        max_pages_per_category: int = 40,
    ) -> None:
        self.categories = categories
        self.max_pages_per_category = max_pages_per_category

    # -- pure parsing (this is what the tests run) --------------------------

    def parse(self, html: str, page_url: str) -> tuple[list[Listing], list[str]]:
        """Parse one category page. Pure: no I/O, no clock, no randomness."""
        listings, errors, _ = self.parse_page(html, page_url)
        return listings, errors

    def parse_page(self, html: str, page_url: str) -> tuple[list[Listing], list[str], int]:
        """As `parse`, plus the count of cards dropped as out of scope.

        `parse` is the protocol method and stays two-valued; the scope count is petmax-specific
        bookkeeping that `scrape` folds into `ScrapeResult.skipped_out_of_scope`.
        """
        tree = HTMLParser(html)
        listings: list[Listing] = []
        errors: list[str] = []
        skipped = 0

        for card in tree.css("div.product-box"):
            product_id = card.attributes.get("data-product-id") or None
            try:
                listing = self._parse_card(card, product_id)
            except (ValueError, ArithmeticError, json.JSONDecodeError) as exc:
                errors.append(f"{page_url} product {product_id or '?'}: {exc}")
                continue
            if listing is None:
                skipped += 1
            else:
                listings.append(listing)

        if not listings and not errors and "product-box" not in html:
            errors.append(f"{page_url}: no product cards found — markup may have changed")
        return listings, errors, skipped

    def _parse_card(self, card: Node, product_id: str | None) -> Listing | None:
        """One product card -> one `Listing`, or `None` if it is out of scope.

        Raises `ValueError` for a card that should have parsed and did not; the caller records
        it in `errors` and moves on, so one broken card cannot cost a page of prices.
        """
        title_node = card.css_first("a.title")
        title = _text(title_node)
        if not title:
            raise ValueError("no a.title")

        if is_regulated(title):
            return None

        url = (title_node.attributes.get("href") if title_node else None) or ""
        if not url:
            raise ValueError("no href on a.title")

        # selectolax lowercases attribute names, so the shop's `data-Gomag` arrives as
        # `data-gomag`. Both spellings are accepted so the parser does not depend on that.
        gomag_raw = card.attributes.get("data-gomag") or card.attributes.get("data-Gomag")
        if not gomag_raw:
            raise ValueError("no data-Gomag attribute")
        gomag = json.loads(gomag_raw)

        price = self._money(gomag.get("Lei_final_price"), "Lei_final_price")
        list_price = self._money(gomag.get("Lei_price"), "Lei_price", required=False)

        # Cross-check against the displayed price. Disagreement means reject, not ingest.
        displayed = parse_romanian_money(_text(card.css_first("span.text-main")))
        if displayed is not None and abs(displayed - price) > PRICE_CROSSCHECK_TOLERANCE:
            raise ValueError(
                f"price disagreement: data-Gomag says {price}, display says {displayed}"
            )

        # A "compare at" price only exists when it is genuinely above the selling price.
        compare_at = list_price if list_price is not None and list_price > price else None

        stock_node = card.css_first("span.stock-status")
        in_stock: bool | None = None
        if stock_node is not None:
            classes = stock_node.attributes.get("class") or ""
            in_stock = "available" in classes

        return Listing(
            source=SOURCE,
            source_product_id=product_id,
            url=url,
            title=title,
            brand=_text(card.css_first("a.brand")) or None,
            price=price,
            currency="RON",
            compare_at_price=compare_at,
            in_stock=in_stock,
            raw_payload={
                "data_gomag": gomag,
                "discount_badge": _text(card.css_first("span.icon.discount")) or None,
                "review_count": _text(card.css_first("span.-g-listing-review-count")) or None,
            },
        )

    @staticmethod
    def _money(raw: object, field: str, required: bool = True) -> Decimal:
        """`data-Gomag` uses a decimal point, not a comma. Parsed strictly."""
        if raw in (None, ""):
            if required:
                raise ValueError(f"{field} missing")
            return Decimal("0")
        try:
            value = Decimal(str(raw))
        except ArithmeticError as exc:
            raise ValueError(f"{field} is not a number: {raw!r}") from exc
        if value <= 0:
            if required:
                raise ValueError(f"{field} is not positive: {value}")
            return Decimal("0")
        return value

    # -- pagination ---------------------------------------------------------

    @staticmethod
    def category_page_url(category: str, page: int) -> str:
        """Page 0 is the bare category URL; `?p=N` from there. Zero-based, as the shop does it."""
        return f"{BASE_URL}/{category}" if page == 0 else f"{BASE_URL}/{category}?p={page}"

    @staticmethod
    def has_next_page(html: str) -> bool:
        """`<link rel="next">` is how the shop advertises more pages. Trusting it rather than
        guessing a page count means the crawl stops exactly when the catalogue ends."""
        return HTMLParser(html).css_first('link[rel="next"]') is not None

    # -- the only method that touches the network ---------------------------

    def scrape(self, limit: int | None = None, dry_run: bool = False) -> ScrapeResult:
        """Fetch and parse. `limit` caps total listings (default 5, CLAUDE.md §5.2).

        `dry_run` changes nothing here — this method never writes; persistence is the runner's
        job (`pricepilot.scrapers.runner`). It is accepted so the protocol is uniform and so a
        caller can express intent without special-casing.
        """
        cap = get_settings().scraper_default_limit if limit is None else limit
        result = ScrapeResult(source=SOURCE)
        seen: set[str] = set()

        with PoliteClient(SOURCE) as client:
            for category in self.categories:
                for page in range(self.max_pages_per_category):
                    url = self.category_page_url(category, page)
                    try:
                        html = client.get(url)
                    except Exception as exc:
                        result.errors.append(f"{url}: {exc.__class__.__name__}: {exc}")
                        break
                    result.pages_fetched += 1

                    listings, errors, skipped = self.parse_page(html, url)
                    result.errors.extend(errors)
                    result.skipped_out_of_scope += skipped
                    for listing in listings:
                        key = listing.source_product_id or listing.url
                        if key in seen:
                            continue
                        seen.add(key)
                        result.listings.append(listing)
                        if cap and len(result.listings) >= cap:
                            return result

                    if not self.has_next_page(html):
                        break
        return result

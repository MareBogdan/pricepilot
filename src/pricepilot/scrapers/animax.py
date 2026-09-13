"""`animax.ro` — Shopify storefront, not Magento. Verified 2026-09-13 against
`tests/fixtures/animax_ro/` — see `docs/SOURCES.md` for the recon notes.

**The plan-stage guess was wrong.** CLAUDE.md §7 named this Magento; `robots.txt` opens with
`# Shopify storefront.` and the sitemap has Shopify's standard shape. Caught in recon, before any
code was written against the wrong platform's assumptions (DECISIONS.md ADR-0024).

**Why this source parses JSON, not HTML.** Every Shopify storefront exposes
`/collections/<handle>/products.json` — a standard, public, unauthenticated part of the storefront
theme itself (the same data its own infinite-scroll and quick-add widgets fetch), not a private or
reverse-engineered API. It returns exactly what this adapter needs — `vendor`, `product_type`, and
per-`variants[]` `id`, `sku`, `price`, `compare_at_price`, `grams`, `available` — as structured
JSON, at roughly 1/58th the bandwidth of the equivalent rendered collection page (~150 KB vs
~8.7 MB for the same 250 products, because the HTML duplicates full facet/quick-add data inline
per card). No markup to parse, no class names to track across a theme update.

**`external_id` is the Shopify variant id** (`variants[].id`), never the product id, the handle,
or the URL — a platform-internal integer, immune to the kind of slug collision found on petmax
(a `-6847` duplicate-slug counter naming a different product than the row it was assigned to;
see the 2026-09-13 diagnostic session and `docs/AUDIT.md`).

**`grams` is not trusted as ground truth.** Recon found a real listing titled "... 2 kg" carrying
`grams: 500` — the shop's own structured shipping-weight field disagreeing with its own title text
by 4x. `grams` is still captured into `raw_payload` for future reference, but the overlap key
(unchanged this session) keeps parsing weight from title text, which is why this disagreement is
a curiosity here rather than a bug there.

**Structure.** One purchasable pack size per product — no variant grouping, unlike
pentruanimale.ro's VTEX storefront. Checked empirically across 750+ sampled products, not assumed:
zero carried more than one Shopify variant. This adapter still iterates `variants[]` generically
rather than hardcoding "exactly one", in case a future catalogue addition breaks the pattern.

Pagination is `?page=N`, one-based, `limit=250` (Shopify's own maximum page size). The endpoint
returns a JSON object with no page-count or total field, so the adapter stops the way REST
pagination is supposed to be read: a page returning fewer than `limit` products is the last one.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any

from pricepilot.config import get_settings
from pricepilot.scrapers.base import Listing, PoliteClient, ScrapeResult
from pricepilot.scrapers.petmax import REGULATED_TITLE_TOKENS, is_regulated

__all__ = [
    "REGULATED_TITLE_TOKENS",
    "AnimaxScraper",
    "is_regulated",
]

SOURCE = "animax_ro"
BASE_URL = "https://animax.ro"

# Shopify's own maximum `products.json` page size. Using the largest legal value means the
# largest category here (hrana-umeda-pisici, 537 products) needs only 3 requests, not 3 with a
# smaller page or dozens with an HTML-page-sized one.
PAGE_SIZE = 250

# The ten categories food/treats/hygiene/toys for dogs and cats, mirroring petmax's 13-category
# scope minus categories that don't exist here as a clean umbrella. `recompense-caini`/
# `recompense-snacks-pisici` were chosen over the narrower `snack-caini`/`snackuri-pisici`
# collections after checking directly: the narrower ones are a 98-99% subset of the wider ones
# (docs/SOURCES.md) — fetching both would be nearly all wasted, duplicate requests. Recon
# (2026-09-13) exact-counted 2,551 products across these ten by walking each to its final page —
# see docs/SOURCES.md for the per-category table.
DEFAULT_CATEGORIES: tuple[str, ...] = (
    "hrana-uscata-caini",
    "hrana-umeda-caini",
    "recompense-caini",
    "igiena-si-ingrijire-caini",
    "jucarii-caini",
    "hrana-uscata-pisici",
    "hrana-umeda-pisici",
    "recompense-snacks-pisici",
    "asternut-litiera-pisici",
    "jucarii-pisici",
)

# Largest category (537 products) needs 3 pages at PAGE_SIZE=250. Comfortably above that, not
# just past the known maximum, so a real run never truncates on page count.
DEFAULT_MAX_PAGES_PER_CATEGORY = 20


def _decimal(raw: object, field: str, *, required: bool = True) -> Decimal:
    """Shopify's `products.json` already uses a decimal point (e.g. `"232.80"`), never a comma —
    parsed strictly, same discipline as petmax's `_money` and pentruanimale's `_decimal`.

    Returns `Decimal("0")` for a missing/non-positive *optional* field, mirroring petmax's
    `_money` — a zero sentinel keeps the return type a plain `Decimal` rather than
    `Decimal | None`, so callers compare with `> 0` instead of narrowing an Optional.
    """
    if raw in (None, ""):
        if required:
            raise ValueError(f"{field} missing")
        return Decimal("0")
    try:
        value = Decimal(str(raw))
    except InvalidOperation as exc:
        raise ValueError(f"{field} is not a number: {raw!r}") from exc
    if value <= 0:
        if required:
            raise ValueError(f"{field} is not positive: {value}")
        return Decimal("0")
    return value


class AnimaxScraper:
    """Adapter for `animax.ro`. Implements the `Scraper` protocol."""

    name = SOURCE

    def __init__(
        self,
        categories: tuple[str, ...] = DEFAULT_CATEGORIES,
        max_pages_per_category: int = DEFAULT_MAX_PAGES_PER_CATEGORY,
    ) -> None:
        self.categories = categories
        self.max_pages_per_category = max_pages_per_category

    # -- pure parsing (this is what the tests run) --------------------------

    def parse(self, html: str, page_url: str) -> tuple[list[Listing], list[str]]:
        """Parse one `products.json` page. Pure: no I/O, no clock, no randomness.

        The parameter is named `html` to match the `Scraper` protocol; the body is actually JSON,
        as it is for pentruanimale's `__STATE__` blob.
        """
        listings, errors, _, _ = self.parse_page(html, page_url)
        return listings, errors

    def parse_page(self, body: str, page_url: str) -> tuple[list[Listing], list[str], int, int]:
        """As `parse`, plus (skipped-out-of-scope count, raw product count).

        `parse` is the protocol method and stays two-valued; the extra two values are bookkeeping
        `scrape` uses for `ScrapeResult.skipped_out_of_scope` and for deciding whether the
        category has more pages.
        """
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            return [], [f"{page_url}: not valid JSON: {exc}"], 0, 0
        if not isinstance(data, dict) or not isinstance(data.get("products"), list):
            return [], [f"{page_url}: no 'products' array — shape may have changed"], 0, 0

        products = data["products"]
        listings: list[Listing] = []
        errors: list[str] = []
        skipped = 0

        for product in products:
            try:
                product_listings, product_skipped = self._parse_product(product, page_url)
            except (ValueError, KeyError, TypeError) as exc:
                pid = product.get("id", "?") if isinstance(product, dict) else "?"
                errors.append(f"{page_url} product {pid}: {exc}")
                continue
            listings.extend(product_listings)
            skipped += product_skipped

        return listings, errors, skipped, len(products)

    def _parse_product(self, product: dict[str, Any], page_url: str) -> tuple[list[Listing], int]:
        """One Shopify product -> one `Listing` per in-scope variant.

        Raises for a product that should have parsed and did not; the caller records it in
        `errors` and moves on, so one broken product cannot cost a page of prices.
        """
        base_title = product.get("title")
        handle = product.get("handle")
        if not base_title or not isinstance(base_title, str):
            raise ValueError("no title")
        if not handle or not isinstance(handle, str):
            raise ValueError("no handle")

        variants = product.get("variants")
        if not isinstance(variants, list) or not variants:
            raise ValueError("no variants")

        vendor = product.get("vendor")
        brand = vendor if isinstance(vendor, str) and vendor else None
        multi_variant = len(variants) > 1

        listings: list[Listing] = []
        skipped = 0
        for variant in variants:
            if not isinstance(variant, dict):
                raise ValueError(f"variant is not an object: {variant!r}")

            variant_id = variant.get("id")
            if not variant_id:
                raise ValueError("variant missing id")

            variant_title = variant.get("title")
            title = (
                base_title
                if not variant_title or variant_title == "Default Title"
                else f"{base_title} - {variant_title}"
            )

            if is_regulated(title):
                skipped += 1
                continue

            price = _decimal(variant.get("price"), "price")
            list_price = _decimal(
                variant.get("compare_at_price"), "compare_at_price", required=False
            )
            # A "compare at" price only exists when it is genuinely above the selling price —
            # recon found a real row where the two are exactly equal (no real discount).
            compare_at = list_price if list_price > price else None

            available = variant.get("available")
            in_stock = available if isinstance(available, bool) else None

            url = f"{BASE_URL}/products/{handle}"
            if multi_variant:
                url = f"{url}?variant={variant_id}"

            listings.append(
                Listing(
                    source=SOURCE,
                    source_product_id=str(variant_id),
                    url=url,
                    title=title,
                    brand=brand,
                    price=price,
                    currency="RON",
                    compare_at_price=compare_at,
                    in_stock=in_stock,
                    raw_payload={
                        "sku": variant.get("sku"),
                        "grams": variant.get("grams"),
                        "product_type": product.get("product_type"),
                    },
                )
            )
        return listings, skipped

    # -- pagination -----------------------------------------------------------

    @staticmethod
    def category_page_url(category: str, page: int) -> str:
        """`products.json?limit=250&page=N`, one-based, Shopify's own convention."""
        return f"{BASE_URL}/collections/{category}/products.json?limit={PAGE_SIZE}&page={page}"

    # -- the only method that touches the network ------------------------------

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
                pages_this_category = 0
                for page in range(1, self.max_pages_per_category + 1):
                    url = self.category_page_url(category, page)
                    try:
                        body = client.get(url)
                    except Exception as exc:
                        result.errors.append(f"{url}: {exc.__class__.__name__}: {exc}")
                        break
                    result.pages_fetched += 1
                    pages_this_category += 1

                    listings, errors, skipped, raw_count = self.parse_page(body, url)
                    result.errors.extend(errors)
                    result.skipped_out_of_scope += skipped
                    for listing in listings:
                        key = listing.source_product_id or listing.url
                        if key in seen:
                            continue
                        seen.add(key)
                        result.listings.append(listing)
                        if cap and len(result.listings) >= cap:
                            result.pages_fetched_by_category[category] = pages_this_category
                            return result

                    # A page returning fewer than PAGE_SIZE products is the last one — standard
                    # REST-style pagination, no `<link rel="next">` or total-count field to read.
                    # A page that failed to parse (raw_count == 0 with errors) also stops the
                    # category rather than looping — a malformed response is not "category
                    # exhausted", but retrying it blind is not obviously better than moving on,
                    # and the error is already recorded for a human to see.
                    if raw_count < PAGE_SIZE:
                        break
                result.pages_fetched_by_category[category] = pages_this_category
        return result

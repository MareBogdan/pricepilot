"""`pentruanimale.ro` — VTEX storefront, not Gomag. Verified 2026-09-13 against
`tests/fixtures/pentruanimale_ro/` — see `docs/SOURCES.md` for the recon notes.

**Why this source parses differently from `petmax.py`.** The product grid is client-rendered
(VTEX IO / React), but every category page's raw HTML also carries a
`<template data-type="json" data-varname="__STATE__"><script>{...}</script></template>` block —
VTEX's server-rendered Apollo GraphQL cache. It is present with zero JS execution (confirmed with
`curl` alone), so this adapter extracts and walks that JSON instead of CSS-selecting product cards.

**The `__STATE__` shape.** A flat map of `"TypeName:id"` keys, cross-referenced by
`{"type":"id","id": "..."}` pointers instead of nesting:

* one `$ROOT_QUERY.productSearch(...)` root key -> `{"products": [<Product ref>, ...]}`
* `Product:sp-<id>-none` -> `productName`, `brand`, `link` (shared by every variant), and an
  `items({"filter":"ALL_AVAILABLE"})` key holding a list of SKU refs
* each SKU node -> `itemId` (the real per-variant id), `name` (the purchasable unit's own title,
  already including the weight/size), `ean`, and a `sellers` list of refs
* each Seller node -> `commertialOffer` ref -> an Offer node with `Price`, `ListPrice`,
  `AvailableQuantity`

**Structure.** Grouped-variant source (CLAUDE.md §7): one product groups several SKUs under a
shared PDP URL and price range. This adapter expands each SKU into its own `Listing` — the
expansion needs no extra request, every SKU's own price is already in the same `__STATE__` blob
that lists the product.

Pagination is `?page=N`, one-based (bare URL = page 1). There is no `<link rel="next">` equivalent
— the grid is client-rendered — so the adapter stops when a page's raw product list (from
`__STATE__`, before regulated-title filtering) comes back empty **and parses cleanly**. A page
that fails to parse is not treated the same as a genuinely empty one — see
`_should_continue_category` and the session note below.

**Bug found and fixed (2026-09-12), first real run.** The first live run fetched 224 pages against
a ~321-page recon estimate. Root cause: a transient `__STATE__` parse failure on one page made
`raw_product_count == 0`, which the original loop treated identically to "category exhausted",
silently truncating every page behind it. The loop now only stops on a genuinely empty, cleanly
parsed page; a parse failure moves to the next page instead, and only a run of
`MAX_CONSECUTIVE_PARSE_ERRORS` consecutive parse failures gives up on that category.

**Not fetched.** `diete-veterinare` (prescription diets) and `antiparazitare` (antiparasitics) are
separate categories from the six scraped here; the category allowlist is the first line of
defence, `is_regulated` (shared with `petmax.py`) the second.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from pricepilot.config import get_settings
from pricepilot.scrapers.base import Listing, PoliteClient, ScrapeResult
from pricepilot.scrapers.petmax import REGULATED_TITLE_TOKENS, is_regulated

__all__ = [
    "REGULATED_TITLE_TOKENS",
    "PentruAnimaleScraper",
    "is_regulated",
]

SOURCE = "pentruanimale_ro"
BASE_URL = "https://www.pentruanimale.ro"

# The same six categories as petmax's *original* set (dry/wet food and treats, dogs and cats) —
# nested VTEX paths, not flat slugs. See docs/SOURCES.md's "pentruanimale.ro — verified recon"
# section for the per-category volume/request-count table this was measured against.
DEFAULT_CATEGORIES: tuple[str, ...] = (
    "caini/hrana-caini/hrana-uscata",
    "caini/hrana-caini/hrana-umeda",
    "caini/hrana-caini/recompense---snacks",
    "pisici/hrana-pisici/hrana-uscata",
    "pisici/hrana-pisici/hrana-umeda",
    "pisici/hrana-pisici/recompense---snacks",
)

# `hrana-uscata` (dog dry food) is the largest category at 81 pages (docs/SOURCES.md). Comfortably
# above that, not just past petmax's 40, so a real run never truncates on page count.
DEFAULT_MAX_PAGES_PER_CATEGORY = 120

# Session note (2026-09-12): a transient __STATE__ parse failure on ONE page must not be mistaken
# for "this category is exhausted" — that silently truncates every remaining page behind it,
# which is exactly what happened to the first real run (224 pages fetched vs. ~321 estimated).
# A page that fails to parse is retried by simply moving to the next page number; only a *run* of
# consecutive parse failures this long means the category is genuinely broken, not transient.
MAX_CONSECUTIVE_PARSE_ERRORS = 3

# Non-greedy: `<script>`/`</script>` were confirmed balanced 1:1 on the real page this session
# (docs/SOURCES.md), so this is safe in practice. If a future page's escaped-but-truncating
# `</script>` inside a JSON string value ever breaks that assumption, `json.loads` below raises
# and the caller records a clear per-page error rather than silently truncating or crashing the
# whole run.
_STATE_TEMPLATE = re.compile(
    r'<template[^>]*data-varname="__STATE__"[^>]*>\s*<script>(.*?)</script>\s*</template>',
    re.DOTALL,
)


class PentruAnimaleParseError(ValueError):
    """Raised for a page whose `__STATE__` blob does not have the shape this parser expects."""


def _deref(state: dict[str, Any], ref: object, what: str) -> dict[str, Any]:
    """Follow one Apollo-cache `{"type":"id","id": "..."}` pointer into `state`.

    Raises `PentruAnimaleParseError` rather than a bare `KeyError`/`TypeError` so callers can log
    a clear message per skipped item, same discipline as petmax's per-card `ValueError`s.
    """
    if not isinstance(ref, dict) or "id" not in ref:
        raise PentruAnimaleParseError(f"{what}: not a valid Apollo ref: {ref!r}")
    target = state.get(ref["id"])
    if not isinstance(target, dict):
        raise PentruAnimaleParseError(f"{what}: dangling ref {ref['id']!r}")
    return target


def _items_key(product: dict[str, Any]) -> str | None:
    """The SKU-list key is `items({"filter":"ALL_AVAILABLE"})` — found by prefix rather than an
    exact literal, so incidental key-ordering differences in the query string do not matter."""
    return next((k for k in product if k.startswith("items(")), None)


def _decimal(value: object, field: str) -> Decimal:
    """VTEX hands prices back as JSON numbers, not Romanian-comma display text — no
    `parse_romanian_money` needed here, but still validated strictly, same spirit as
    petmax's `_money`."""
    if value is None:
        raise PentruAnimaleParseError(f"{field} missing")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise PentruAnimaleParseError(f"{field} is not a number: {value!r}") from exc
    if result <= 0:
        raise PentruAnimaleParseError(f"{field} is not positive: {result}")
    return result


class PentruAnimaleScraper:
    """Adapter for `pentruanimale.ro`. Implements the `Scraper` protocol."""

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
        """Parse one category page. Pure: no I/O, no clock, no randomness."""
        listings, errors, _, _ = self.parse_page(html, page_url)
        return listings, errors

    def parse_page(self, html: str, page_url: str) -> tuple[list[Listing], list[str], int, int]:
        """As `parse`, plus (skipped-out-of-scope count, raw product count).

        `parse` is the protocol method and stays two-valued; the extra two values are
        pentruanimale-specific bookkeeping `scrape` uses for `ScrapeResult.skipped_out_of_scope`
        and for deciding whether the category has more pages.
        """
        listings: list[Listing] = []
        errors: list[str] = []
        skipped = 0

        try:
            state = self._extract_state(html)
            product_refs = self._product_refs(state)
        except PentruAnimaleParseError as exc:
            return [], [f"{page_url}: {exc}"], 0, 0
        except json.JSONDecodeError as exc:
            return [], [f"{page_url}: __STATE__ is not valid JSON: {exc}"], 0, 0

        for ref in product_refs:
            try:
                product = _deref(state, ref, "product")
            except PentruAnimaleParseError as exc:
                errors.append(f"{page_url}: {exc}")
                continue

            product_listings, product_errors, product_skipped = self._parse_product(
                state, product, page_url
            )
            listings.extend(product_listings)
            errors.extend(product_errors)
            skipped += product_skipped

        return listings, errors, skipped, len(product_refs)

    def _parse_product(
        self, state: dict[str, Any], product: dict[str, Any], page_url: str
    ) -> tuple[list[Listing], list[str], int]:
        """One `Product:sp-<id>-none` node -> one `Listing` per in-scope SKU."""
        listings: list[Listing] = []
        errors: list[str] = []
        skipped = 0

        product_id = product.get("productId")
        link = product.get("link")
        brand = product.get("brand") or None
        if not link:
            errors.append(f"{page_url} product {product_id or '?'}: no link")
            return [], errors, 0
        url = f"{BASE_URL}{link}"

        items_key = _items_key(product)
        if items_key is None:
            errors.append(f"{page_url} product {product_id or '?'}: no items(...) key")
            return [], errors, 0

        for sku_ref in product.get(items_key) or []:
            try:
                listing = self._parse_sku(state, sku_ref, url, brand)
            except PentruAnimaleParseError as exc:
                errors.append(f"{page_url} product {product_id or '?'}: {exc}")
                continue
            if listing is None:
                skipped += 1
            else:
                listings.append(listing)

        return listings, errors, skipped

    def _parse_sku(
        self, state: dict[str, Any], sku_ref: object, url: str, brand: str | None
    ) -> Listing | None:
        """One SKU node -> one `Listing`, or `None` if it is a regulated product."""
        sku = _deref(state, sku_ref, "sku")

        item_id = sku.get("itemId")
        name = sku.get("name")
        if not item_id or not name:
            raise PentruAnimaleParseError(f"SKU missing itemId/name: {sku!r}")

        if is_regulated(name):
            return None

        sellers = sku.get("sellers") or []
        if not sellers:
            raise PentruAnimaleParseError(f"SKU {item_id} has no sellers")
        seller = _deref(state, sellers[0], f"SKU {item_id} seller")

        offer_ref = seller.get("commertialOffer")
        if offer_ref is None:
            raise PentruAnimaleParseError(f"SKU {item_id} seller has no commertialOffer")
        offer = _deref(state, offer_ref, f"SKU {item_id} commertialOffer")

        price = _decimal(offer.get("Price"), f"SKU {item_id} Price")
        list_price_raw = offer.get("ListPrice")
        list_price = (
            _decimal(list_price_raw, f"SKU {item_id} ListPrice")
            if list_price_raw is not None
            else None
        )
        compare_at = list_price if list_price is not None and list_price > price else None

        available_quantity = offer.get("AvailableQuantity")
        in_stock = available_quantity is not None and available_quantity > 0

        return Listing(
            source=SOURCE,
            source_product_id=str(item_id),
            url=url,
            title=name,
            brand=brand,
            price=price,
            currency="RON",
            compare_at_price=compare_at,
            in_stock=in_stock,
            raw_payload={"ean": sku.get("ean")},
        )

    # -- __STATE__ extraction -------------------------------------------------

    @staticmethod
    def _extract_state(html: str) -> dict[str, Any]:
        match = _STATE_TEMPLATE.search(html)
        if not match:
            raise PentruAnimaleParseError("no __STATE__ template found — markup may have changed")
        parsed = json.loads(match.group(1))
        if not isinstance(parsed, dict):
            raise PentruAnimaleParseError("__STATE__ did not parse to a JSON object")
        return parsed

    @staticmethod
    def _product_refs(state: dict[str, Any]) -> list[dict[str, Any]]:
        root_key = next((k for k in state if k.startswith("$ROOT_QUERY.productSearch(")), None)
        if root_key is None:
            raise PentruAnimaleParseError("no $ROOT_QUERY.productSearch(...) key in __STATE__")
        root = state[root_key]
        if not isinstance(root, dict):
            raise PentruAnimaleParseError("productSearch root query value is not an object")
        products = root.get("products")
        if not isinstance(products, list):
            raise PentruAnimaleParseError("productSearch root query has no 'products' list")
        return products

    # -- pagination ---------------------------------------------------------

    @staticmethod
    def category_page_url(category: str, page: int) -> str:
        """Page 1 is the bare category URL; `?page=N` from there. One-based, as the shop does
        it (unlike petmax's zero-based `?p=N`)."""
        return f"{BASE_URL}/{category}" if page == 1 else f"{BASE_URL}/{category}?page={page}"

    @staticmethod
    def _should_continue_category(
        raw_product_count: int, had_parse_error: bool, consecutive_parse_errors: int
    ) -> tuple[bool, int, str | None]:
        """Whether to fetch another page of this category, given the page just parsed.

        Kept as a standalone, pure function — not inlined in `scrape()` — specifically so the
        bug this fixes can be unit-tested without mocking the network: a page that fails to
        parse (`raw_product_count == 0` *because* of an error) is not the same thing as a page
        that genuinely has no products, and conflating them was the original bug — one
        transient parse failure silently truncated every page behind it in that category
        (the first real run: 224 pages fetched vs. ~321 estimated, docs/SOURCES.md).

        Returns `(should_continue, new_consecutive_parse_error_streak, note_if_giving_up)`.
        """
        if had_parse_error and raw_product_count == 0:
            streak = consecutive_parse_errors + 1
            if streak >= MAX_CONSECUTIVE_PARSE_ERRORS:
                return False, streak, f"stopping after {streak} consecutive parse errors"
            return True, streak, None
        if raw_product_count == 0:
            return False, 0, None
        return True, 0, None

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
                pages_this_category = 0
                consecutive_parse_errors = 0
                for page in range(1, self.max_pages_per_category + 1):
                    url = self.category_page_url(category, page)
                    try:
                        html = client.get(url)
                    except Exception as exc:
                        result.errors.append(f"{url}: {exc.__class__.__name__}: {exc}")
                        break
                    result.pages_fetched += 1
                    pages_this_category += 1

                    listings, errors, skipped, raw_product_count = self.parse_page(html, url)
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

                    should_continue, consecutive_parse_errors, note = (
                        self._should_continue_category(
                            raw_product_count, bool(errors), consecutive_parse_errors
                        )
                    )
                    if note:
                        result.errors.append(f"{category}: {note}")
                    if not should_continue:
                        break
                result.pages_fetched_by_category[category] = pages_this_category
        return result

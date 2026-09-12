"""The pentruanimale.ro adapter, tested entirely offline against the saved fixture.

CLAUDE.md §9: "a scraper hitting a live site during tests" must never happen. Nothing in this
file touches the network — every test runs `PentruAnimaleScraper.parse`, which is pure by
construction.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from pricepilot.scrapers.pentruanimale import PentruAnimaleScraper
from pricepilot.scrapers.petmax import REGULATED_TITLE_TOKENS, is_regulated

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "pentruanimale_ro"
    / "category_caini_hrana-uscata_p1.html"
)
PAGE_URL = "https://www.pentruanimale.ro/caini/hrana-caini/hrana-uscata"


@pytest.fixture(scope="module")
def fixture_html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def parsed(fixture_html: str):
    listings, errors = PentruAnimaleScraper().parse(fixture_html, PAGE_URL)
    assert errors == [], f"fixture should parse cleanly: {errors}"
    return listings


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_fixture_exists() -> None:
    assert FIXTURE.exists(), "the offline fixture is the only thing tests may read"


def test_expands_to_one_listing_per_sku(parsed) -> None:
    """3 products in the fixture: 3 + 1 + 2 SKUs = 6 purchasable variants."""
    assert len(parsed) == 6


def test_prices_are_decimal_not_float(parsed) -> None:
    """ADR-0007: money is never a float. A float here would reach the margin check in Phase 5."""
    for listing in parsed:
        assert isinstance(listing.price, Decimal)
        assert listing.compare_at_price is None or isinstance(listing.compare_at_price, Decimal)


def test_multi_variant_product_expands_to_three_distinct_prices(parsed) -> None:
    """ROYAL CANIN Mini Adult (sp-45) has 3 SKUs at 3 different prices — the baseline
    grouped-product expansion case (CLAUDE.md §7)."""
    royal_canin = [x for x in parsed if x.source_product_id in {"1272", "55", "61"}]
    assert len(royal_canin) == 3
    prices = {x.price for x in royal_canin}
    assert len(prices) == 3
    assert prices == {Decimal("190.68"), Decimal("62.04"), Decimal("119.99")}
    # All three variants share one PDP url, per the site's own size-selector UX.
    assert len({x.url for x in royal_canin}) == 1
    assert royal_canin[0].url == (
        "https://www.pentruanimale.ro/royal-canin-mini-adult-hrana-uscata-caini/p"
    )
    assert all(x.brand == "ROYAL CANIN" for x in royal_canin)
    eight_kg = next(x for x in royal_canin if x.source_product_id == "1272")
    assert eight_kg.title == "ROYAL CANIN Mini Adult, hrană uscată câini, 8kg"
    assert eight_kg.price == Decimal("190.68")
    assert eight_kg.compare_at_price == Decimal("228.99")
    assert eight_kg.raw_payload == {"ean": "3182551055757"}


def test_single_variant_product_is_one_listing_with_no_compare_at(parsed) -> None:
    """EXTRU-CAN Standard Hipocaloric (sp-459) has exactly one SKU, and Price == ListPrice —
    no promotion, so no compare_at_price (same rule as petmax's data-Gomag cards)."""
    listing = next(x for x in parsed if x.source_product_id == "608")
    assert listing.price == Decimal("111.54")
    assert listing.compare_at_price is None
    assert listing.is_discounted is False
    assert listing.brand == "EXTRU-CAN"


def test_bonus_weight_skus_are_not_merged(parsed) -> None:
    """ADVANCE Adult Maxi (sp-48) has two SKUs whose names both contain "14kg" — a bonus-weight
    promotion ("GRATUIT, 14kg + 3kg") vs the plain pack. Real trap data (docs/SOURCES.md), the
    same class of hard negative CLAUDE.md §7 names as the largest Phase 3 error class."""
    bonus = next(x for x in parsed if x.source_product_id == "13291")
    plain = next(x for x in parsed if x.source_product_id == "60")
    assert "14kg" in bonus.title and "14kg" in plain.title
    assert bonus.title != plain.title
    assert bonus.price != plain.price
    assert bonus.price == Decimal("303.99")
    assert plain.price == Decimal("319.99")
    assert bonus.content_hash != plain.content_hash
    # Both variants of the same product still share one url.
    assert bonus.url == plain.url


def test_in_stock_from_available_quantity(parsed) -> None:
    assert all(x.in_stock is True for x in parsed)


def test_markup_change_is_reported_not_silently_empty() -> None:
    listings, errors = PentruAnimaleScraper().parse(
        "<html><body>redesigned</body></html>", PAGE_URL
    )
    assert listings == []
    assert errors and "no __STATE__ template found" in errors[0]


def test_invalid_json_in_state_is_reported_not_crashed() -> None:
    """The guard CLAUDE.md's task description calls out: a `</script>` inside an escaped JSON
    string value could in principle truncate the regex match early. Whatever breaks json.loads,
    the adapter records a clear per-page error rather than raising out of `parse`."""
    html = """
    <template data-type="json" data-varname="__STATE__">
        <script>{not valid json at all</script>
    </template>
    """
    listings, errors = PentruAnimaleScraper().parse(html, PAGE_URL)
    assert listings == []
    assert len(errors) == 1
    assert "not valid JSON" in errors[0]


def _state_html(state: dict[str, object]) -> str:
    """Wrap a Python dict as the `__STATE__` template the parser extracts, via `json.dumps` so
    the test data can never suffer a hand-escaped-JSON typo."""
    return (
        '<template data-type="json" data-varname="__STATE__">'
        f"<script>{json.dumps(state)}</script>"
        "</template>"
    )


def _sku_state(
    item_id: str, name: str, price: float, list_price: float, qty: int
) -> dict[str, object]:
    """One product with one SKU, built as a plain dict — the minimal shape `_parse_product`/
    `_parse_sku` need, used for the edge-case tests below."""
    sku_key = "Product:sp-x-none.items.0"
    seller_key = f"{sku_key}.sellers.0"
    offer_key = f"$offer.{item_id}"
    return {
        "$ROOT_QUERY.productSearch(x)": {
            "products": [{"type": "id", "id": "Product:sp-x-none", "typename": "Product"}],
            "recordsFiltered": 1,
        },
        "Product:sp-x-none": {
            "productId": "x",
            "brand": "TestBrand",
            "link": "/test-product/p",
            'items({"filter":"ALL_AVAILABLE"})': [{"type": "id", "id": sku_key, "typename": "SKU"}],
        },
        sku_key: {
            "itemId": item_id,
            "name": name,
            "ean": "123",
            "sellers": [{"type": "id", "id": seller_key, "typename": "Seller"}],
        },
        seller_key: {"commertialOffer": {"type": "id", "id": offer_key, "typename": "Offer"}},
        offer_key: {"Price": price, "ListPrice": list_price, "AvailableQuantity": qty},
    }


def test_one_broken_product_does_not_lose_the_page() -> None:
    """A product ref pointing at nothing (a dangling ref) is recorded as an error and skipped;
    the rest of the page's products still parse."""
    state = _sku_state("9", "Acana Adult 2kg", 55.0, 55.0, 10)
    root_key = "$ROOT_QUERY.productSearch(x)"
    state[root_key]["products"].insert(  # type: ignore[union-attr,index]
        0, {"type": "id", "id": "Product:missing", "typename": "Product"}
    )
    html = _state_html(state)
    listings, errors = PentruAnimaleScraper().parse(html, PAGE_URL)
    assert [x.source_product_id for x in listings] == ["9"]
    assert len(errors) == 1
    assert "dangling ref" in errors[0]


# ---------------------------------------------------------------------------
# Scope filtering — regulated products are excluded at ingest, not later
# ---------------------------------------------------------------------------


def test_regulated_tokens_are_shared_with_petmax() -> None:
    """CLAUDE.md's build instructions: import the vocabulary rather than fork a slightly
    different copy, so the two adapters agree on what "regulated" means."""
    from pricepilot.scrapers.pentruanimale import REGULATED_TITLE_TOKENS as reexported

    assert reexported is REGULATED_TITLE_TOKENS


@pytest.mark.parametrize(
    "title",
    [
        "Advocate pipete antiparazitare caini 4-10 kg",
        "Royal Canin Veterinary Diet Gastrointestinal 2 kg",
        "Milbemax comprimate deparazitare interna",
    ],
)
def test_regulated_titles_are_out_of_scope(title: str) -> None:
    assert is_regulated(title)


def test_regulated_sku_is_skipped_and_counted() -> None:
    state = _sku_state("70", "Advocate pipete antiparazitare caini 4-10 kg", 90.0, 90.0, 5)
    html = _state_html(state)
    listings, errors, skipped, raw_count = PentruAnimaleScraper().parse_page(html, PAGE_URL)
    assert listings == []
    assert errors == []
    assert skipped == 1
    assert raw_count == 1


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def test_page_urls_are_one_based() -> None:
    assert (
        PentruAnimaleScraper.category_page_url("caini/hrana-caini/hrana-uscata", 1)
        == "https://www.pentruanimale.ro/caini/hrana-caini/hrana-uscata"
    )
    assert (
        PentruAnimaleScraper.category_page_url("caini/hrana-caini/hrana-uscata", 3)
        == "https://www.pentruanimale.ro/caini/hrana-caini/hrana-uscata?page=3"
    )


def test_max_pages_exceeds_the_largest_real_category() -> None:
    """hrana-uscata (dog dry food) is 81 pages per docs/SOURCES.md's recon table — the default
    must comfortably clear that, not just barely exceed it."""
    assert PentruAnimaleScraper().max_pages_per_category > 81


def test_raw_product_count_drives_the_stop_condition(fixture_html: str) -> None:
    """There is no <link rel="next"> on this client-rendered grid; the adapter stops when a
    page's raw product list (from __STATE__, before regulated filtering) is empty."""
    _, _, _, raw_count = PentruAnimaleScraper().parse_page(fixture_html, PAGE_URL)
    assert raw_count == 3

    empty_state = '{"$ROOT_QUERY.productSearch(x)":{"products":[],"recordsFiltered":0}}'
    empty_html = f"""
    <template data-type="json" data-varname="__STATE__">
        <script>{empty_state}</script>
    </template>
    """
    _, errors, _, raw_count_empty = PentruAnimaleScraper().parse_page(empty_html, PAGE_URL)
    assert errors == []
    assert raw_count_empty == 0


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


def test_default_categories_are_nested_vtex_paths() -> None:
    """Not flat slugs like petmax's — pentruanimale's categories are nested paths, and the
    regulated trees (diete-veterinare, antiparazitare) are separate categories, excluded here."""
    scraper = PentruAnimaleScraper()
    assert len(scraper.categories) == 6
    for category in scraper.categories:
        assert "/" in category
        assert "diete-veterinare" not in category
        assert "antiparazitare" not in category


# ---------------------------------------------------------------------------
# STEP 1 (session note 2026-09-12): a parse failure on one page must not be mistaken for
# "category exhausted" - that silently truncated every page behind it in the first real run
# (224 pages fetched vs. ~321 estimated). Tested here as a pure function, with no network mock
# needed at all.
# ---------------------------------------------------------------------------


def test_a_genuinely_empty_clean_page_stops_the_category() -> None:
    should_continue, streak, note = PentruAnimaleScraper._should_continue_category(
        raw_product_count=0, had_parse_error=False, consecutive_parse_errors=0
    )
    assert should_continue is False
    assert streak == 0
    assert note is None


def test_a_page_with_products_always_continues_and_resets_the_streak() -> None:
    should_continue, streak, note = PentruAnimaleScraper._should_continue_category(
        raw_product_count=12, had_parse_error=False, consecutive_parse_errors=2
    )
    assert should_continue is True
    assert streak == 0
    assert note is None


def test_a_single_parse_failure_does_not_stop_the_category() -> None:
    """The exact bug this fixes: one bad page must not truncate everything behind it."""
    should_continue, streak, note = PentruAnimaleScraper._should_continue_category(
        raw_product_count=0, had_parse_error=True, consecutive_parse_errors=0
    )
    assert should_continue is True
    assert streak == 1
    assert note is None


def test_consecutive_parse_failures_eventually_give_up() -> None:
    streak = 0
    should_continue = True
    note = None
    for _ in range(10):
        should_continue, streak, note = PentruAnimaleScraper._should_continue_category(
            raw_product_count=0, had_parse_error=True, consecutive_parse_errors=streak
        )
        if not should_continue:
            break
    assert should_continue is False
    assert streak == 3  # MAX_CONSECUTIVE_PARSE_ERRORS
    assert note is not None and "3 consecutive parse errors" in note


def test_a_recovering_page_resets_the_streak() -> None:
    """Two parse failures then a good page - the category must not be considered broken."""
    _, streak, _ = PentruAnimaleScraper._should_continue_category(0, True, 0)
    _, streak, _ = PentruAnimaleScraper._should_continue_category(0, True, streak)
    should_continue, streak, note = PentruAnimaleScraper._should_continue_category(
        raw_product_count=12, had_parse_error=False, consecutive_parse_errors=streak
    )
    assert should_continue is True
    assert streak == 0
    assert note is None

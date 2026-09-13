"""The animax.ro adapter, tested entirely offline against the saved fixture.

CLAUDE.md §9: "a scraper hitting a live site during tests" must never happen. Nothing in this
file touches the network — every test runs `AnimaxScraper.parse`, which is pure by construction.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from pricepilot.scrapers.animax import AnimaxScraper, is_regulated
from pricepilot.scrapers.petmax import REGULATED_TITLE_TOKENS

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "animax_ro"
    / "category_hrana-uscata-caini_p1.json"
)
PAGE_URL = "https://animax.ro/collections/hrana-uscata-caini/products.json?limit=250&page=1"


@pytest.fixture(scope="module")
def fixture_body() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def parsed(fixture_body: str):
    listings, errors = AnimaxScraper().parse(fixture_body, PAGE_URL)
    assert errors == [], f"fixture should parse cleanly: {errors}"
    return listings


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_fixture_exists() -> None:
    assert FIXTURE.exists(), "the offline fixture is the only thing tests may read"


def test_parses_every_product(parsed) -> None:
    """7 products in the fixture, one variant each -> 7 listings."""
    assert len(parsed) == 7


def test_prices_are_decimal_not_float(parsed) -> None:
    """ADR-0007: money is never a float. A float here would reach the margin check in Phase 5."""
    for listing in parsed:
        assert isinstance(listing.price, Decimal)
        assert listing.compare_at_price is None or isinstance(listing.compare_at_price, Decimal)


def test_baseline_out_of_stock_card_fields(parsed) -> None:
    """Royal Canin Mini Adult 8 kg — ASCII title, ordinary weight, out of stock."""
    listing = next(x for x in parsed if x.source_product_id == "43522724200668")
    assert listing.source == "animax_ro"
    assert listing.title == "Hrana uscata pentru caini Royal Canin Mini Adult 8 kg"
    assert listing.brand == "Royal Canin"
    assert listing.price == Decimal("232.80")
    assert listing.compare_at_price is None
    assert listing.currency == "RON"
    assert listing.in_stock is False
    assert listing.url == (
        "https://animax.ro/products/hrana-uscata-pentru-caini-royal-canin-mini-adult-8-kg"
    )
    assert listing.raw_payload == {
        "sku": "203211",
        "grams": 8000,
        "product_type": "Hrana uscata pentru caini",
    }


def test_source_product_id_is_the_variant_id_not_the_product_id_or_handle(parsed) -> None:
    """This morning's diagnostic session: identity must come from a platform-internal id, never
    from title or url slug (petmax's `-6847` slug collision is the counter-example). Shopify's
    product id (7886304837852) and variant id (43522724200668) are deliberately different
    numbers here — the listing's external id must be the *variant* id."""
    listing = next(x for x in parsed if x.title.endswith("Royal Canin Mini Adult 8 kg"))
    assert listing.source_product_id == "43522724200668"
    assert listing.source_product_id != "7886304837852"  # the Shopify product id
    assert "43522724200668" not in listing.url  # never leaked into the url either


def test_decimal_point_vs_comma_same_line_same_shop(parsed) -> None:
    """ "Orijen Junior Talie Mare 11.4 kg" (point) vs "ORIJEN Regional Red, 11,4 kg" (comma) —
    same product line, same weight, different decimal formatting within animax itself."""
    point = next(x for x in parsed if "11.4 kg" in x.title)
    comma = next(x for x in parsed if "11,4 kg" in x.title)
    assert point.brand == "Orijen"
    assert comma.brand == "Orijen"
    assert point.source_product_id != comma.source_product_id
    assert point.raw_payload["grams"] == comma.raw_payload["grams"] == 11400


def test_full_romanian_diacritics_parse_cleanly(parsed) -> None:
    listing = next(x for x in parsed if x.brand == "Purina")
    assert "hrană uscată pentru câini" in listing.title
    assert listing.price == Decimal("134.99")


def test_title_with_no_digit_still_parses(parsed) -> None:
    """PEDIGREE row: no weight anywhere in the title text. The adapter must not require one —
    that's the overlap key's job to notice downstream (unkeyable), not the scraper's job to
    reject."""
    listing = next(x for x in parsed if x.brand == "Pedigree")
    assert not any(c.isdigit() for c in listing.title)
    assert listing.raw_payload["grams"] == 3000


def test_structured_grams_field_is_not_reconciled_with_the_title(parsed) -> None:
    """Royal Canin "Adult 8+ Mini 2 kg" carries grams=500 in animax's own data — a real
    disagreement between the shop's structured weight field and its own title text. The adapter
    stores exactly what the shop returns; it is not the scraper's job to arbitrate this."""
    listing = next(x for x in parsed if "8+ Mini 2 kg" in x.title)
    assert listing.raw_payload["grams"] == 500
    assert "2 kg" in listing.title


def test_compare_at_price_equal_to_price_is_not_a_discount(parsed) -> None:
    """Same guard as petmax: a "compare at" price only exists when genuinely above the selling
    price. This row's compare_at_price and price are both "104.99" in the raw data."""
    listing = next(x for x in parsed if "8+ Mini 2 kg" in x.title)
    assert listing.price == Decimal("104.99")
    assert listing.compare_at_price is None
    assert listing.is_discounted is False


def test_genuine_discount_is_detected(parsed) -> None:
    listing = next(x for x in parsed if "L+XL" in x.title)
    assert listing.price == Decimal("144.90")
    assert listing.compare_at_price == Decimal("188.49")
    assert listing.is_discounted is True


def test_age_band_and_breed_size_codes_are_not_bonus_weight_packs(parsed) -> None:
    """ "8+", "12+" (age bands) and "L+XL", "S+M" (breed-size codes) all contain "+" but are not
    CLAUDE.md §7's bonus-weight promotion pattern ("12+2 kg"). The adapter does not need to (and
    does not) treat them specially — they are titles like any other; noted here so a future
    reader does not mistake "+" in a title for a signal this adapter acts on."""
    plus_titles = [x.title for x in parsed if "+" in x.title]
    assert any("8+" in t for t in plus_titles)
    assert any("L+XL" in t for t in plus_titles)
    assert all("bonus" not in t.lower() for t in plus_titles)


def test_markup_change_is_reported_not_silently_empty() -> None:
    listings, errors = AnimaxScraper().parse("<html><body>redesigned</body></html>", PAGE_URL)
    assert listings == []
    assert errors and "not valid JSON" in errors[0]


def test_missing_products_key_is_reported() -> None:
    listings, errors = AnimaxScraper().parse('{"unexpected": []}', PAGE_URL)
    assert listings == []
    assert errors and "no 'products' array" in errors[0]


def test_one_broken_product_does_not_lose_the_page() -> None:
    body = json.dumps(
        {
            "products": [
                {"id": 1, "handle": "broken"},  # no title, no variants
                {
                    "id": 2,
                    "title": "Acana Adult 2 kg",
                    "handle": "acana-adult-2-kg",
                    "vendor": "Acana",
                    "product_type": "Hrana uscata",
                    "variants": [
                        {
                            "id": 99,
                            "title": "Default Title",
                            "sku": "s1",
                            "price": "55.00",
                            "compare_at_price": None,
                            "grams": 2000,
                            "available": True,
                        }
                    ],
                },
            ]
        }
    )
    listings, errors = AnimaxScraper().parse(body, PAGE_URL)
    assert [x.source_product_id for x in listings] == ["99"]
    assert len(errors) == 1
    assert "product 1" in errors[0]


# ---------------------------------------------------------------------------
# Multi-variant products — not observed in the real catalogue (docs/SOURCES.md), but the code
# path is exercised synthetically so a future catalogue change does not silently break it.
# ---------------------------------------------------------------------------


def test_multi_variant_product_expands_and_disambiguates_the_url() -> None:
    body = json.dumps(
        {
            "products": [
                {
                    "id": 1,
                    "title": "Some Food",
                    "handle": "some-food",
                    "vendor": "TestBrand",
                    "product_type": "Hrana",
                    "variants": [
                        {
                            "id": 10,
                            "title": "3 kg",
                            "sku": "sku-3",
                            "price": "50.00",
                            "compare_at_price": None,
                            "grams": 3000,
                            "available": True,
                        },
                        {
                            "id": 11,
                            "title": "12 kg",
                            "sku": "sku-12",
                            "price": "150.00",
                            "compare_at_price": None,
                            "grams": 12000,
                            "available": True,
                        },
                    ],
                }
            ]
        }
    )
    listings, errors = AnimaxScraper().parse(body, PAGE_URL)
    assert errors == []
    assert len(listings) == 2
    ids = {x.source_product_id for x in listings}
    assert ids == {"10", "11"}
    urls = {x.url for x in listings}
    assert urls == {
        "https://animax.ro/products/some-food?variant=10",
        "https://animax.ro/products/some-food?variant=11",
    }
    titles = {x.title for x in listings}
    assert titles == {"Some Food - 3 kg", "Some Food - 12 kg"}


# ---------------------------------------------------------------------------
# Scope filtering — regulated products are excluded at ingest, not later
# ---------------------------------------------------------------------------


def test_regulated_tokens_are_shared_with_petmax() -> None:
    from pricepilot.scrapers.animax import REGULATED_TITLE_TOKENS as reexported

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


def test_regulated_product_is_skipped_and_counted() -> None:
    body = json.dumps(
        {
            "products": [
                {
                    "id": 1,
                    "title": "Advocate pipete antiparazitare caini 4-10 kg",
                    "handle": "advocate",
                    "vendor": "Bayer",
                    "product_type": "Deparazitare",
                    "variants": [
                        {
                            "id": 10,
                            "title": "Default Title",
                            "sku": "s1",
                            "price": "90.00",
                            "compare_at_price": None,
                            "grams": 100,
                            "available": True,
                        }
                    ],
                }
            ]
        }
    )
    listings, errors, skipped, raw_count = AnimaxScraper().parse_page(body, PAGE_URL)
    assert listings == []
    assert errors == []
    assert skipped == 1
    assert raw_count == 1


def test_product_type_diete_veterinare_is_regulated_even_with_a_clean_title() -> None:
    """ADR-0025 (A4): the shop's own `product_type` classification is a second, independent
    signal — real animax data has "Hill's PD Metabolic" filed under product_type "Diete
    veterinare pentru caini" with no title token to catch it. The title check alone must not
    be the only line of defence."""
    body = json.dumps(
        {
            "products": [
                {
                    "id": 1,
                    "title": "Hill's PD Metabolic 1.5kg",
                    "handle": "hills-pd-metabolic",
                    "vendor": "Hill's",
                    "product_type": "Diete veterinare pentru caini",
                    "variants": [
                        {
                            "id": 10,
                            "title": "Default Title",
                            "sku": "s1",
                            "price": "90.00",
                            "compare_at_price": None,
                            "grams": 1500,
                            "available": True,
                        }
                    ],
                }
            ]
        }
    )
    listings, errors, skipped, raw_count = AnimaxScraper().parse_page(body, PAGE_URL)
    assert listings == []
    assert errors == []
    assert skipped == 1
    assert raw_count == 1


def test_product_type_check_does_not_replace_the_title_check() -> None:
    """The reverse real case: "ADVANCE VD Gastroenteric" carries a plain food product_type but
    a title that matches " vd " — must still be caught."""
    body = json.dumps(
        {
            "products": [
                {
                    "id": 2,
                    "title": "ADVANCE VD Gastroenteric, pt caini cu probleme gastrointestinale",
                    "handle": "advance-vd-gastroenteric",
                    "vendor": "Advance",
                    "product_type": "Hrana uscata pentru caini",
                    "variants": [
                        {
                            "id": 20,
                            "title": "Default Title",
                            "sku": "s2",
                            "price": "120.00",
                            "compare_at_price": None,
                            "grams": 12000,
                            "available": True,
                        }
                    ],
                }
            ]
        }
    )
    listings, _errors, skipped, _raw_count = AnimaxScraper().parse_page(body, PAGE_URL)
    assert listings == []
    assert skipped == 1


def test_ordinary_product_type_is_not_regulated() -> None:
    body = json.dumps(
        {
            "products": [
                {
                    "id": 3,
                    "title": "Royal Canin Urinary Care 400 g",
                    "handle": "royal-canin-urinary-care",
                    "vendor": "Royal Canin",
                    "product_type": "Hrana umeda pentru pisici",
                    "variants": [
                        {
                            "id": 30,
                            "title": "Default Title",
                            "sku": "s3",
                            "price": "20.00",
                            "compare_at_price": None,
                            "grams": 400,
                            "available": True,
                        }
                    ],
                }
            ]
        }
    )
    listings, _errors, skipped, _raw_count = AnimaxScraper().parse_page(body, PAGE_URL)
    assert len(listings) == 1
    assert skipped == 0


def test_no_regulated_categories_in_the_default_set() -> None:
    scraper = AnimaxScraper()
    for category in scraper.categories:
        assert "deparazitare" not in category
        assert "antiparazitare" not in category


def test_ten_categories_dogs_and_cats() -> None:
    scraper = AnimaxScraper()
    assert len(scraper.categories) == 10


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def test_page_urls_are_one_based_with_max_page_size() -> None:
    assert AnimaxScraper.category_page_url("hrana-uscata-caini", 1) == (
        "https://animax.ro/collections/hrana-uscata-caini/products.json?limit=250&page=1"
    )
    assert AnimaxScraper.category_page_url("hrana-uscata-caini", 3) == (
        "https://animax.ro/collections/hrana-uscata-caini/products.json?limit=250&page=3"
    )


def test_max_pages_exceeds_the_largest_real_category() -> None:
    """hrana-umeda-pisici is 537 products / PAGE_SIZE(250) ~= 3 pages per docs/SOURCES.md's
    recon table — the default must comfortably clear that, not just barely exceed it."""
    from pricepilot.scrapers.animax import PAGE_SIZE

    assert AnimaxScraper().max_pages_per_category > (537 // PAGE_SIZE + 1)


def test_raw_product_count_drives_the_stop_condition(fixture_body: str) -> None:
    """No `<link rel="next">` or total-count field to read — the adapter stops when a page
    returns fewer than PAGE_SIZE products. The 7-product fixture is a partial (last) page."""
    from pricepilot.scrapers.animax import PAGE_SIZE

    _, _, _, raw_count = AnimaxScraper().parse_page(fixture_body, PAGE_URL)
    assert raw_count == 7
    assert raw_count < PAGE_SIZE

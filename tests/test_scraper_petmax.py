"""The petmax.ro adapter, tested entirely offline against the saved fixture.

CLAUDE.md §9: "a scraper hitting a live site during tests" must never happen. Nothing in this
file touches the network — every test runs `PetmaxScraper.parse`, which is pure by construction.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from pricepilot.scrapers.base import (
    ScraperConfigError,
    normalize_title,
    parse_romanian_money,
    require_honest_user_agent,
)
from pricepilot.scrapers.petmax import PetmaxScraper, is_regulated
from pricepilot.scrapers.runner import VOLUME_DROP_THRESHOLD, is_volume_drop

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "petmax_ro"
    / "category_hrana-uscata-caini_p0.html"
)
PAGE_URL = "https://www.petmax.ro/hrana-uscata-caini"


@pytest.fixture(scope="module")
def fixture_html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def parsed(fixture_html: str):
    listings, errors = PetmaxScraper().parse(fixture_html, PAGE_URL)
    assert errors == [], f"fixture should parse cleanly: {errors}"
    return listings


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_fixture_exists() -> None:
    assert FIXTURE.exists(), "the offline fixture is the only thing tests may read"


def test_parses_every_card(parsed) -> None:
    assert len(parsed) == 5


def test_prices_are_decimal_not_float(parsed) -> None:
    """ADR-0007: money is never a float. A float here would reach the margin check in Phase 5."""
    for listing in parsed:
        assert isinstance(listing.price, Decimal)
        assert listing.compare_at_price is None or isinstance(listing.compare_at_price, Decimal)


def test_baseline_card_fields(parsed) -> None:
    listing = next(x for x in parsed if x.source_product_id == "233")
    assert listing.source == "petmax_ro"
    assert listing.title == "Royal Canin Mini Adult 8 kg"
    assert listing.brand == "Royal Canin"
    assert listing.price == Decimal("199.29")
    assert listing.compare_at_price == Decimal("249.11")
    assert listing.currency == "RON"
    assert listing.in_stock is True
    assert listing.url.endswith("royal-canin-mini-adult-8-kg.html")


def test_compare_at_price_drives_promotion_detection(parsed) -> None:
    """Phase 4 detects promotions through `compare_at_price`; without it the phase has no
    discount timing to learn from, which is why this source is the anchor."""
    assert all(x.compare_at_price is not None for x in parsed)
    assert all(x.is_discounted for x in parsed)


def test_compare_at_is_none_when_not_above_price() -> None:
    """A shop that sets the list price equal to the selling price is not running a promotion."""
    html = """
    <div class="product-box" data-product-id="1"
         data-Gomag='{"Lei_price":"55.00","Lei_final_price":"55.00"}'>
      <a href="https://www.petmax.ro/x.html" class="title _productUrl_1">Brit Care Adult 1 kg</a>
    </div>
    """
    listings, errors = PetmaxScraper().parse(html, PAGE_URL)
    assert errors == []
    assert listings[0].compare_at_price is None
    assert listings[0].is_discounted is False


def test_price_disagreement_is_rejected_not_ingested() -> None:
    """A silent price error poisons a time series that cannot be rebuilt, so a card whose
    machine-readable price contradicts its displayed price is dropped with an error."""
    html = """
    <div class="product-box" data-product-id="9"
         data-Gomag='{"Lei_price":"249.11","Lei_final_price":"199.29"}'>
      <a href="https://www.petmax.ro/x.html" class="title _productUrl_9">Royal Canin Mini 8 kg</a>
      <span class="text-main">19,29 Lei</span>
    </div>
    """
    listings, errors = PetmaxScraper().parse(html, PAGE_URL)
    assert listings == []
    assert len(errors) == 1
    assert "price disagreement" in errors[0]


def test_one_broken_card_does_not_lose_the_page() -> None:
    html = """
    <div class="product-box" data-product-id="1">
      <a href="https://www.petmax.ro/a.html" class="title _productUrl_1">Acana Adult 2 kg</a>
    </div>
    <div class="product-box" data-product-id="2"
         data-Gomag='{"Lei_price":"75.00","Lei_final_price":"55.00"}'>
      <a href="https://www.petmax.ro/b.html" class="title _productUrl_2">Brit Adult 4 kg</a>
    </div>
    """
    listings, errors = PetmaxScraper().parse(html, PAGE_URL)
    assert [x.source_product_id for x in listings] == ["2"]
    assert len(errors) == 1
    assert "no data-Gomag" in errors[0]


def test_markup_change_is_reported_not_silently_empty() -> None:
    listings, errors = PetmaxScraper().parse("<html><body>redesigned</body></html>", PAGE_URL)
    assert listings == []
    assert errors and "markup may have changed" in errors[0]


# ---------------------------------------------------------------------------
# The hard case CLAUDE.md §7 names as the largest Phase 3 error class
# ---------------------------------------------------------------------------


def test_bonus_weight_variant_is_a_separate_listing(parsed) -> None:
    """ "8 kg" and "8 kg + 1 kg gratuit" are different purchasable units at different prices.
    A parser that collapsed them would destroy the hardest negatives in the dataset."""
    plain = next(x for x in parsed if x.source_product_id == "233")
    bonus = next(x for x in parsed if x.source_product_id == "2542")
    assert plain.price != bonus.price
    assert plain.content_hash != bonus.content_hash


def test_content_hash_is_stable_across_diacritics() -> None:
    """Phase 2 caches attribute extraction on this hash; "Hrană" and "Hrana" are the same
    title as far as extraction is concerned, and paying twice for them is the §5 cost risk."""
    assert normalize_title("Hrană uscată câini ORIJEN Mini") == normalize_title(
        "Hrana  uscata caini orijen mini"
    )


# ---------------------------------------------------------------------------
# Scope filtering — regulated products are excluded at ingest, not later
# ---------------------------------------------------------------------------


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


@pytest.mark.parametrize(
    "title",
    [
        "Royal Canin Mini Adult 8 kg",
        "Calibra Joy Dog Classic Duck Strips 80 g",
        "Trixie jucarie cauciuc",
    ],
)
def test_in_scope_titles_are_kept(title: str) -> None:
    assert not is_regulated(title)


# ---------------------------------------------------------------------------
# ADR-0025 (2026-09-14): line-code tokens, diacritic folding, symptom words rejected
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "title",
    [
        "Hrana uscata dietetica pentru caini Calibra VD Dog Joint & Mobility 12 kg",
        "Hrana uscata pentru caini Royal Canin VHN Gastrointestinal 2kg",
        "Diete veterinare pentru caini",  # plural — the documented gap this session found
        "Dietă veterinară pentru câini cu afecțiuni digestive",  # accented singular
    ],
)
def test_adr_0025_line_code_and_folded_tokens_are_regulated(title: str) -> None:
    assert is_regulated(title)


@pytest.mark.parametrize(
    "title",
    [
        "Hrana uscata pentru caini Hill's PD Afectiuni hepatice L/D 1.5kg",
        "Hrana uscata pentru caini Hill's PD Metabolic 1.5kg",
        "Hrana umeda pentru pisici Hill's PD Boli Renale K/D Pui 85g",
    ],
)
def test_pd_token_is_regulated(title: str) -> None:
    """ " pd " (Hill's Prescription Diet) added 2026-09-13 — verified against all 18,703 stored
    titles before adding, per-token, same discipline as " vd "/" vhn " (ADR-0025)."""
    assert is_regulated(title)


@pytest.mark.parametrize(
    "title",
    [
        "Royal Canin Urinary Care, 10 kg",
        "Hill's SP Canine Adult Healthy Mobility Small and Mini Chicken 1.5 kg",
        "Sanabelle Urinary 10 kg",
        "Brit Care Dog Hypoallergenic Adult Large Breed 3 kg",
        "Royal Canin Feline Digestive Care, 10 kg",
        "REMI PREMIUM Dog Lite, obezitate, 3kg",
        "Pro Plan Sterilised Renal Plus cu somon 1.5 kg",
        "Brit Functional Snack Recovery Hering 150g",
    ],
)
def test_adr_0025_symptom_words_are_explicitly_not_regulated(title: str) -> None:
    """The rejected half of ADR-0025: these are ordinary retail condition-support food, not
    prescription diets — the 2026-09-13/14 diagnostic's own Tier-B samples. Adding "urinar",
    "renal", "mobility", "hypoallergenic", "digestive care", "obezitate" or "recovery" as tokens
    would flag every one of these as regulated, which is wrong."""
    assert not is_regulated(title)


def test_adr_0025_regulated_match_names_the_token() -> None:
    from pricepilot.scrapers.petmax import regulated_match

    assert regulated_match("Royal Canin VHN Renal Pui 85g") == " vhn "
    assert regulated_match("Brit Grain Free VD Recovery 400g") == " vd "
    assert regulated_match("Hill's PD Metabolic 1.5kg") == " pd "
    assert regulated_match("Royal Canin Urinary Care 400 g") is None


def test_regulated_card_is_skipped_and_counted() -> None:
    html = """
    <div class="product-box" data-product-id="7"
         data-Gomag='{"Lei_price":"90.00","Lei_final_price":"80.00"}'>
      <a href="https://www.petmax.ro/p.html" class="title _productUrl_7">Pipete antiparazitare</a>
    </div>
    """
    listings, errors, skipped = PetmaxScraper().parse_page(html, PAGE_URL)
    assert listings == [] and errors == [] and skipped == 1


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def test_page_urls_are_zero_based() -> None:
    assert (
        PetmaxScraper.category_page_url("hrana-uscata-caini", 0)
        == "https://www.petmax.ro/hrana-uscata-caini"
    )
    assert (
        PetmaxScraper.category_page_url("hrana-uscata-caini", 3)
        == "https://www.petmax.ro/hrana-uscata-caini?p=3"
    )


def test_next_page_is_read_from_rel_next(fixture_html: str) -> None:
    assert PetmaxScraper.has_next_page(fixture_html) is True
    assert PetmaxScraper.has_next_page("<html><head></head></html>") is False


# ---------------------------------------------------------------------------
# Romanian money parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("249,11 Lei", Decimal("249.11")),
        ("199,29 Lei", Decimal("199.29")),
        ("1.234,50 Lei", Decimal("1234.50")),
        ("1 234,50 Lei", Decimal("1234.50")),
        ("55 Lei", Decimal("55")),
        ("", None),
        ("Lei", None),
    ],
)
def test_parse_romanian_money(text: str, expected: Decimal | None) -> None:
    assert parse_romanian_money(text) == expected


# ---------------------------------------------------------------------------
# Politeness and safety rails
# ---------------------------------------------------------------------------


def test_user_agent_placeholder_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLAUDE.md §5.4 / §9: the contact address lives in .env and is never committed. Running
    with the committed placeholder would introduce the bot to a shop with a fake address."""
    from pricepilot import config

    monkeypatch.setattr(
        config.get_settings(),
        "scraper_user_agent",
        "PricePilotBot/0.1 (+mailto:you@example.com; portfolio research project)",
    )
    with pytest.raises(ScraperConfigError, match="placeholder"):
        require_honest_user_agent()


def test_user_agent_without_contact_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    from pricepilot import config

    monkeypatch.setattr(config.get_settings(), "scraper_user_agent", "PricePilotBot/0.1")
    with pytest.raises(ScraperConfigError, match="no contact address"):
        require_honest_user_agent()


def test_env_example_carries_only_a_placeholder() -> None:
    """The repo must never carry a real contact address (CLAUDE.md §9)."""
    text = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")
    assert "you@example.com" in text


# ---------------------------------------------------------------------------
# Volume-drop alerting (CLAUDE.md §5.6)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("found", "previous", "alert"),
    [
        (100, None, False),  # first run has nothing to compare against
        (100, 0, False),  # previous run collected nothing
        (100, 100, False),
        (120, 100, False),  # an increase is never an alert
        (61, 100, False),  # 39% drop — under the threshold
        (59, 100, True),  # 41% drop — alert
        (0, 100, True),
    ],
)
def test_volume_drop_detection(found: int, previous: int | None, alert: bool) -> None:
    assert is_volume_drop(found, previous) is alert


def test_threshold_matches_the_documented_rule() -> None:
    assert VOLUME_DROP_THRESHOLD == 0.40

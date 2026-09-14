"""EN/RO flavour extraction — CLAUDE.md §7's eight named pairs, plus three extended from real
title data (fish, liver, game), plus STEP C's ten more (bison, mackerel, ham, poultry, deer,
reindeer, goose, sardine, cod)."""

from __future__ import annotations

import pytest

from pricepilot.normalize.flavour import extract_flavour


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Royal Canin Mini Adult cu Pui 8 kg", "chicken"),
        ("Calibra Dog Life Junior Small Breed Chicken 6 kg", "chicken"),
        ("Petkult Sensitive Miel & Orez 1 kg", "lamb"),
        ("Calibra Dog Life Adult Small Fresh Beef 6 kg", "beef"),
        ("AMANOVA Sterilised, Somon, hrana uscata", "salmon"),
        ("Taste of the Wild Pacific Stream Puppy Formula Salmon 12.2 kg", "salmon"),
        ("ISEGRIM, XS-XL, Curcan, plic hrana umeda", "turkey"),
        ("Wolfpack Sausage Somon 400g", "salmon"),
        ("Recompensa pentru caini Wolfpack Sausage Rata 400g", "duck"),
        ("Petkult Sensitive Care Adult Small Breed Miel si orez brun 1 kg", "lamb"),
        ("Inaba Ciao Dashi Delights Ton si Fulgi de Bonito 70g", "tuna"),
        ("MERA Cat's Nature, Miel, hrana uscata fara cereale pisici, 400g", "lamb"),
        ("Purina Pro Plan Delicate Digestion, Peste, hrana umeda", "fish"),
        ("Hill's PD Boli Renale K/D Pui 85g", "chicken"),
        ("Dolina Noteci Premium Vanat 800gr", "game"),
    ],
)
def test_known_flavour_words(title: str, expected: str) -> None:
    assert extract_flavour(title) == expected


def test_no_flavour_word_is_none() -> None:
    assert extract_flavour("Jucarie pentru pisici Kong Cat Bila plutitoare") is None


def test_multiple_flavours_are_joined_not_dropped() -> None:
    """ "cu Iepure si Vita" states two proteins — losing one would be a real information loss,
    not a simplification."""
    result = extract_flavour("MY LOVE Multipack Hrana umeda pentru pisici, cu Iepure si Vita 4x85g")
    assert result == "rabbit+beef"


def test_duplicate_flavour_words_are_not_repeated() -> None:
    result = extract_flavour("Pui cu gust de Pui, aroma naturala de Pui")
    assert result == "chicken"


# ---------------------------------------------------------------------------
# STEP C additions — real titles from the in-scope population (never the frozen gate sample)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        (
            "TASTE OF THE WILD High Prairie, Bizon si Vanat, hrana uscata caini, 12.2kg",
            "bison+game",
        ),
        ("ACANA Highest Protein Pacifica, XS-XL, Hering si Macrou, hrana uscata caini", "mackerel"),
        ("DOG JOY Salam, XS-XL, Sunca, salam hrana umeda caini, 900g", "ham"),
        ("SCHESIR DOG PUI JAMBON 150 G", "chicken+ham"),
        ("MERA Brocken Klein Neutral, XS-XL, Pasare, hrana uscata caini, 15kg", "poultry"),
        ("DEVORA Small Breeds, XS-S, Somon si Caprioara, hrana uscata caini, 4kg", "salmon+deer"),
        ("Brit Pate and Meat Venison 800 g", "deer"),
        ("ISEGRIM, XS-XL, Ren, conserva hrana umeda caini, (in sos), 400g", "reindeer"),
        (
            "PRIMORDIAL Holistic Mini, XS-S, Sardine si Gasca, hrana uscata caini, 6kg",
            "sardine+goose",
        ),
        ("MONGE Grill, XS-XL, Cod, plic hrana umeda caini, (in suc propriu), 100g", "cod"),
    ],
)
def test_step_c_new_flavour_words(title: str, expected: str) -> None:
    assert extract_flavour(title) == expected


def test_poultry_and_chicken_are_kept_as_distinct_canonical_values() -> None:
    """ "pasare" (generic bird) is deliberately not merged into "pui"/chicken — they name
    different levels of specificity, and merging them would lose real information."""
    assert extract_flavour("Pasare cu Krill, hrana uscata caini") == "poultry"
    assert extract_flavour("cu Pui, hrana uscata caini") == "chicken"


def test_reindeer_is_not_merged_into_deer_or_game() -> None:
    """A different species from "caprioara"/"venison" (deer) — kept as its own canonical value
    rather than folded into "deer" or "game", since collapsing distinct species would hurt
    Phase 3 matching precision, not help it."""
    assert extract_flavour("Ren, hrana uscata") == "reindeer"
    assert extract_flavour("Caprioara, hrana uscata") == "deer"


def test_step_3_fix_4_shrimp_gate_mismatch() -> None:
    """The exact gate mismatch (listing_id 11166) that surfaced this gap: the label said
    "Tuna+Shrimp", the extractor found only "tuna" because "shrimp"/"creveti" wasn't in the
    vocabulary yet. 52 distinct titles carry "creveti" in the full population, all genuine."""
    result = extract_flavour(
        "SCHESIR, Ton și Creveți, conservă hrană umedă pisici, (în aspic), 140g"
    )
    assert result == "tuna+shrimp"

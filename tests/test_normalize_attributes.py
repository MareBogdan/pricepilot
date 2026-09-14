"""Breed-size code, life stage, food form — STEP 3, "the rest"."""

from __future__ import annotations

import pytest

from pricepilot.normalize.attributes import (
    extract_breed_size,
    extract_food_form,
    extract_life_stage,
)

# ---------------------------------------------------------------------------
# Breed size
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("SAM'S FIELD Junior Large Breed, L-XL, Miel, hrana uscata", "L-XL"),
        ("PET'S DESSERT Stick, XS-XL, Miel, punguta recompense", "XS-XL"),
        ("RAW PALEO Mini Adult, XS-S, Vita, tavita hrana umeda", "XS-S"),
        ("Orijen Original Dog Adult Mini 1.8 kg", "Mini"),
        ("Hrana uscata pentru caini Brit Premium by Nature Junior XL 15 kg", "XL"),
    ],
)
def test_breed_size(title: str, expected: str) -> None:
    assert extract_breed_size(title) == expected


def test_word_form_breed_size_case_insensitive() -> None:
    assert extract_breed_size("hrana uscata caini bosch MEDIUM junior 15 kg") == "Medium"


def test_bare_letter_matches_comma_or_space_delimited() -> None:
    """The single-letter form is real (CLAUDE.md §7) in both pentruanimale's comma grammar and
    petmax's space-delimited one — CLAUDE.md §7's brand form was under-covered when this was
    first written comma-only; the real petmax data (see below) needed it loosened."""
    assert extract_breed_size("BRIT Premium By Nature Adult Large Breed, L, Pui, hrana") == "L"
    assert (
        extract_breed_size("Hrana uscata pentru caini Brit Premium by Nature Adult M 15 kg") == "M"
    )
    # "L" appearing mid-word must still never match.
    assert extract_breed_size("Hrana uscata pentru caini Calibra Life 6 kg") is None


def test_breed_size_never_matches_a_volume_unit() -> None:
    """Real false positive, found by checking candidates before trusting the regex: "7,6 L" is
    7.6 litres, not a size code — a digit immediately before the letter means "unit", not "size"."""
    assert extract_breed_size("Nisip Silicat Perfect cu lavanda 7,6 L") is None
    assert extract_breed_size("Nisip pentru litiera Enjoy 10 L") is None
    assert extract_breed_size("Sampon pentru cai, Promedivet Herba-vital 1 L") is None


def test_breed_size_never_matches_the_s_in_a_possessive_brand_name() -> None:
    """Second real false positive: "HILL'S", "SAM'S FIELD", "WOLF'S MOUNTAIN" each produce a
    phantom standalone "S" purely from the apostrophe creating a word boundary — nothing to do
    with breed size. A genuine size code elsewhere in the same title must still be found."""
    assert extract_breed_size("HILL'S Science Plan Perfect Digestion Puppy M, hrana uscata") == "M"
    assert extract_breed_size("HILL'S healthy weight treats recompense pentru caini 200 gr") is None
    assert extract_breed_size("WOLF'S MOUNTAIN Junior Valley, hrana uscata fara cereale") is None


def test_no_breed_size_is_none() -> None:
    assert extract_breed_size("Jucarie pentru pisici Kong Cat Bila plutitoare") is None


# ---------------------------------------------------------------------------
# Convention 7 (ADR-0027, 2026-09-14) — breed_size_code names the ANIMAL a product is sized for,
# never a physical accessory's own dimension band. All four titles below are real, in-scope
# examples: each carries a size token from the exact same vocabulary a food/treat title uses for
# a genuine breed-size classification, and each must come back empty.
# ---------------------------------------------------------------------------


def test_harness_size_is_not_a_breed_size() -> None:
    assert extract_breed_size("Ham caine Julius K9 IDC Power - 2XS 33-45 cm - Roz") is None
    assert extract_breed_size("Ham Julius K9 IDC Power PAW Patrol - L - Rocky") is None


def test_transport_crate_size_is_not_a_breed_size() -> None:
    assert (
        extract_breed_size("Cusca transport animale MPB GIPSY L, 58x38x38 cm, usa metal, Lila")
        is None
    )


def test_collar_size_band_is_not_a_breed_size() -> None:
    assert extract_breed_size("Zgarda caine Julius K9 Color & Gray - 49 - 70 cm - Gri") is None


def test_leash_capacity_band_is_not_a_breed_size() -> None:
    assert (
        extract_breed_size(
            "Lesa retractabila banda pentru caini, LIBERTY M-PETS, albastra S, 3m, <15 kg"
        )
        is None
    )


def test_dental_stick_medium_for_medium_dogs_is_still_a_real_breed_size() -> None:
    """The positive control: "Medium" here names the dogs the product is FOR, not the product's
    own dimension — no accessory-category word is present, so this must still resolve."""
    assert extract_breed_size("Bete dentare Medium pentru caini talie medie") == "Medium"


def test_ham_the_english_flavour_word_is_not_mistaken_for_a_harness() -> None:
    """ "ham" collides with the harness-context guard only when anchored to the title's start
    (real harness titles all open with "Ham" as the product category); unanchored, it would
    false-positive on the English loanword "ham" (the meat) some flavour descriptions use — both
    real, in-scope titles. Neither has a size token to begin with, so a genuine breed-size letter
    elsewhere in the same food title (synthetic, appended) proves the mid-title "ham" isn't
    suppressing it via the guard."""
    assert (
        extract_breed_size(
            "Hrana umeda pisici, Fresh Farm Shredded fillets in sauce with ham and chicken 70 gr"
        )
        is None
    )
    assert extract_breed_size("Brit Care Cat Turkey Pate With Ham 70 g") is None
    assert extract_breed_size("Brit Care Cat Turkey Pate With Ham, M 70 g") == "M"


# ---------------------------------------------------------------------------
# Life stage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Calibra Dog Life Starter & Puppy hrana uscata", "puppy"),
        ("Hrana uscata pentru caini junior Nutribest Puppy Sensitive", "junior"),
        ("Royal Canin Mini Adult 8 kg", "adult"),
        ("Hrana uscata pentru caini, Calibra Dog Premium Line Adult 12+2 kg", "adult"),
        ("NATURO Low Grain Senior, hrana umeda caini senior", "senior"),
        ("Dietă veterinară pentru câini adulți cu afecțiuni digestive", "adult"),
    ],
)
def test_life_stage(title: str, expected: str) -> None:
    assert extract_life_stage(title) == expected


def test_chicken_pui_is_not_mistaken_for_puppy_life_stage() -> None:
    """ "pui" (chicken) is ambiguous with the colloquial "puppy" meaning — deliberately excluded
    from life-stage matching so a plain chicken-flavour title doesn't get a fabricated life
    stage. A title with no genuine life-stage word returns None, not a guess."""
    assert extract_life_stage("Hrana uscata pentru caini cu Pui 4 kg") is None


def test_no_life_stage_is_none() -> None:
    assert extract_life_stage("Jucarie pentru pisici Kong Cat Bila plutitoare") is None


# ---------------------------------------------------------------------------
# Food form
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Hrana uscata pentru caini Orijen Original Dog Adult Mini 1.8 kg", "dry"),
        ("Hrana umeda pentru pisici Oasy More Love Ton si sardine 70g", "wet"),
        ("Conserva hrana umeda pisici, Pro Plan Delicate cu Curcan, 85 g", "tin"),
        # "plic" (pouch) is the more specific of the four CLAUDE.md §7 categories and correctly
        # takes priority here — dry/wet/tin/pouch are four distinct values, not wet ⊃ pouch.
        ("Royal Canin Feline Care Nutrition Hair&Skin Care, plic hrana umeda pisici", "pouch"),
        ("Hrana umeda pentru caini Dolina Noteci Mini cu iepure si fasole 185gr", "wet"),
    ],
)
def test_food_form(title: str, expected: str) -> None:
    assert extract_food_form(title) == expected


def test_no_food_form_word_is_none() -> None:
    assert extract_food_form("Jucarie pentru pisici Kong Cat Bila plutitoare") is None


# ---------------------------------------------------------------------------
# STEP C additions — real titles from the in-scope population, each checked against the full
# population before adding (counts in STATE.md/DECISIONS.md)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("BRIT Jerky Salmon Protein Bar, recompense caini, Batoane proteice Somon, 80g", "dry"),
        ("Brit Pate and Meat Rabbit 800 g", "wet"),
        ("Miamor Ragout Royale Cat Pui 100g", "wet"),
        ("INABA Churu Dog, Pui, recompense lichide fara cereale caini, topping cremos, 14g", "wet"),
        (
            "INABA Churu Varieties, Ton, galetusa, tub recompense fara cereale pisici, (piure), 700g",
            "wet",
        ),
        ("Wellness Core Cat Tender Cuts Pui si Curcan, in Sos, 85 g", "wet"),
    ],
)
def test_step_c_new_food_form_words(title: str, expected: str) -> None:
    assert extract_food_form(title) == expected


def test_cutie_was_checked_and_deliberately_not_added() -> None:
    """Real samples showed "cutie" (box) packaging both dry treats and wet toppers with no
    reliable way to tell which from the word alone — mapping it to any category would have been
    a guess, not a finding, so it stays unrecognized."""
    assert extract_food_form("PETKULT Hypoallergenic Dental Stix, cutie recompense caini") is None

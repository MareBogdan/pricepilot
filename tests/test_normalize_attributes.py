"""Breed-size code, life stage, food form — STEP 3, "the rest"."""

from __future__ import annotations

import pytest

from pricepilot.normalize.attributes import (
    breed_size_class,
    breed_size_overlaps,
    breed_size_rank,
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
        # Phase 3 finding 6 (2026-09-15 session): "XS-XL" is pentruanimale_ro's own "fits any
        # breed size" marker, checked against the full population (100% of 985 in-scope
        # occurrences are pentruanimale_ro, 0 from petmax_ro/animax_ro) — no longer stored as a
        # real breed-size claim.
        ("PET'S DESSERT Stick, XS-XL, Miel, punguta recompense", None),
        ("RAW PALEO Mini Adult, XS-S, Vita, tavita hrana umeda", "XS-S"),
        ("Orijen Original Dog Adult Mini 1.8 kg", "Mini"),
        ("Hrana uscata pentru caini Brit Premium by Nature Junior XL 15 kg", "XL"),
    ],
)
def test_breed_size(title: str, expected: str | None) -> None:
    assert extract_breed_size(title) == expected


# ---------------------------------------------------------------------------
# Breed-size canonicalisation (finding 5, 2026-09-15 session)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (None, None),
        ("M", (3, 3)),
        ("Medium", (3, 3)),
        ("Mini", (1, 2)),
        ("XS-S", (1, 2)),
        ("Maxi", (4, 5)),
        ("L-XL", (4, 5)),
        ("M-XL", (3, 5)),
    ],
)
def test_breed_size_rank(code: str | None, expected: tuple[int, int] | None) -> None:
    assert breed_size_rank(code) == expected


def test_breed_size_class_packs_rank_as_string() -> None:
    assert breed_size_class("Medium") == "3-3"
    assert breed_size_class("Mini") == "1-2"
    assert breed_size_class(None) is None


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("Medium", "M", True),  # pilot 12: real cross-shop match, word vs. single letter
        ("Mini", "XS-S", True),  # pilot 55: real cross-shop match, word vs. compound range
        ("Medium", "M-XL", True),  # overlap at rank 3, not identical strings
        ("Mini", "Maxi", False),  # disjoint ranges: confidently different sizes
        ("L-XL", "XS-S", False),
        (None, "M", None),  # one side unstated -- not a guess either way
        (None, None, None),
    ],
)
def test_breed_size_overlaps(left: str | None, right: str | None, expected: bool | None) -> None:
    assert breed_size_overlaps(left, right) is expected


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
# STEP 3 fix #2 (2026-09-14, gate mismatches #3322/#3908) — a bare size letter immediately
# followed by a hyphen and more letters is a hyphenated code or word, never a size. General
# guard, checked against the full population (DECISIONS.md ADR-0027): every non-`_COMPOUND_SIZE`
# `<letter>-<word>` shape found was one of these three real false positives.
# ---------------------------------------------------------------------------


def test_m_pets_brand_name_is_not_a_breed_size() -> None:
    assert (
        extract_breed_size("Jucarie din cauciuc pentru caini, Saturn M-PETS, 14 x 13 x 12 cm")
        is None
    )
    assert (
        extract_breed_size("Jucarie interactiva pentru pisici GAMMA M-PETS 16,2 x 16,2 x 7,8 cm")
        is None
    )


def test_m_pets_typo_variant_is_not_a_breed_size() -> None:
    assert (
        extract_breed_size("Jucarie cu scartait pentru caini NABILA Rings M-Pes, 30x17x7 cm")
        is None
    )


def test_l_carnitina_ingredient_is_not_a_breed_size() -> None:
    assert (
        extract_breed_size(
            "Recompense delicioase pentru caini Bow Wow, Os natural cu L-carnitina, 30 bucati"
        )
        is None
    )


def test_hyphenated_compound_code_still_resolves() -> None:
    """The hyphen guard must never swallow a legitimate `_COMPOUND_SIZE` code — those are matched
    first and never reach the single-letter loop this guard applies to."""
    assert extract_breed_size("SAM'S FIELD Junior Large Breed, L-XL, Miel, hrana uscata") == "L-XL"


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


# Phase 3 finding 7 (2026-09-15 session, pilot 15/30): an age-qualifier ("(5+)", "7+", "8+")
# names a genuinely different formula from plain Adult/Senior, not a synonym for it.
@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Royal Canin Maxi Adult (5+), 15 Kg", "adult+5"),
        ("Royal Canin Medium Adult 7+, hrana uscata caini, 4kg", "adult+7"),
        ("HILL'S SCIENCE PLAN Senior Vitality 7+, M, Pui, hrana uscata caini senior", "senior+7"),
        # Bonus-weight phrases ("10+2kg GRATUIT") must NOT be read as an age qualifier — the "+"
        # here is immediately followed by another digit (the bonus amount), which a genuine age
        # qualifier never is. Checked against all 97 in-scope titles carrying a bare `\d+\+`
        # token before trusting this guard, not assumed from these two cases alone.
        ("Hrana uscata caini, Calibra Dog Life Adult Medium Breed Chicken 12+2 kg", "adult"),
        ("ROYAL CANIN Mini Adult, hrana uscata caini, 8+1kg GRATUIT", "adult"),
        # No life-stage word at all -- the age qualifier has nothing to attach to and is left as
        # a still-open gap, not guessed into a new category.
        ("Royal Canin Sterilised 7+ hrana uscata pisica sterilizata, 10 kg", None),
    ],
)
def test_life_stage_age_qualifier(title: str, expected: str | None) -> None:
    assert extract_life_stage(title) == expected


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


# ---------------------------------------------------------------------------
# STEP 3 fixes (2026-09-14, gate mismatches) — real titles from the in-scope population, each
# checked against the full population before adding (counts in DECISIONS.md ADR-0027).
# ---------------------------------------------------------------------------


def test_step_3_punguta_diminutive_pouch() -> None:
    result = extract_food_form(
        "PET'S DESSERT Stick, XS-XL, Miel, punguță recompense fără cereale câini, 80g"
    )
    assert result == "pouch"


def test_step_3_plural_uscate_is_dry() -> None:
    result = extract_food_form("PEDIGREE Ranchos, recompense câini, fâșii uscate, Pui, 70g")
    assert result == "dry"


def test_step_3_plural_umede_deliberately_not_added() -> None:
    """Checked against the full population before deciding, same discipline as "cutie": all 17
    distinct titles carrying "umede" are "Servetele umede" (wet WIPES, a hygiene accessory), never
    wet food. Adding it would have manufactured 17 false positives, so it stays unrecognized."""
    assert extract_food_form("Servetele umede pentru caini, HUSHPET Floral 80 buc") is None


def test_step_3_semi_umeda_is_not_matched_as_generic_wet() -> None:
    """ "semi-umeda" (semi-moist) doesn't fit any of the four dry/wet/tin/pouch values cleanly —
    None is the honest answer, not "wet" from a substring match on "umeda"."""
    result = extract_food_form(
        "Hrana semi-umeda pentru caini Devora Dog GF Semi-moist Mini Caprioara si curcan 5kg"
    )
    assert result is None


def test_step_3_semi_umeda_does_not_break_plain_umeda() -> None:
    """The "semi-" guard must only suppress the substring it's actually attached to, never a
    plain "umeda" elsewhere in the same or a different title."""
    assert extract_food_form("Hrana umeda pentru pisici Oasy More Love Ton si sardine 70g") == "wet"

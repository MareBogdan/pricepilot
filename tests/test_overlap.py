"""The cross-shop overlap proxy — the Phase 1 gate metric (ADR-0009).

These tests pin the proxy's behaviour on the exact title grammars CLAUDE.md §7 documents, using
the four real shop spellings of one product. The key must collide across all of them, or the gate
measures nothing.
"""

from __future__ import annotations

import pytest

from pricepilot.overlap import (
    OVERLAP_TARGET,
    bonus_weight_grams,
    line_tokens,
    net_weight_grams,
    normalized_brand,
    overlap_key,
)

# ---------------------------------------------------------------------------
# Weight parsing — CLAUDE.md §7 Phase 2: "unit normalisation is not optional"
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "grams"),
    [
        ("Orijen Original Dog Adult Mini 4.5 kg", 4500),
        ("Hrană uscată câini ORIJEN Original Dog Adult Mini 1,8 kg", 1800),
        ("Extru-Can Mini cu Vita sac 4kg", 4000),
        ("Calibra Joy Dog Classic Duck Strips 80 g", 80),
        ("12 kg SMØLKE Hrană uscată Medium cu pui pentru câini seniori", 12000),
        ("Royal Canin Mini Adult 4500 g", 4500),
        ("Brit Premium pouch 24x85 g", 2040),
        ("Natures Protection 5 x 900 g", 4500),
        ("Orijen Original Dog Adult Mini", None),
        ("Trixie jucarie cauciuc", None),
        # STEP 4 (session note 2026-09-12): ml/l added — a liquid product previously had no
        # weight at all and was silently unkeyable.
        ("Beaphar Shampoo 250 ml", 250),
        ("Beaphar Shampoo 1 l", 1000),
        ("Beaphar Shampoo 1.5 l", 1500),
    ],
)
def test_net_weight_grams(title: str, grams: int | None) -> None:
    assert net_weight_grams(title) == grams


def test_bonus_weight_is_not_added_to_the_base_pack() -> None:
    """ "8 kg + 1 kg gratuit" is an 8 kg product with a promotion, not a 9 kg product — the base
    pack identifies the product line. `net_weight_grams` still returns the base weight only; the
    bonus amount is a *separate* signal now (`bonus_weight_grams`, `OverlapKey.bonus_g`) so a
    bonus listing and its plain-pack counterpart do not collide at the key level — see the
    "bonus-weight guard" section below (ADR-0021, this replaces the earlier documented behaviour
    of merging them, which this session's real measurement showed was the wrong call)."""
    assert net_weight_grams("Royal Canin Mini Adult 8 kg + 1 kg gratuit") == 8000
    assert net_weight_grams("Royal Canin Medium Adult 15 + 3 Kg Gratis") == 15000


@pytest.mark.parametrize(
    ("title", "bonus_grams"),
    [
        ("Royal Canin Mini Adult 8 kg + 1 kg gratuit", 1000),
        ("Royal Canin Medium Adult 15 + 3 Kg Gratis", 3000),
        ("ROYAL CANIN Mini Adult, hrana uscata caini, 8+1kg GRATUIT", 1000),
        ("Royal Canin Mini Adult 8 kg", 0),
        ("Orijen Original Dog Adult Mini 1.8 kg", 0),
    ],
)
def test_bonus_weight_grams(title: str, bonus_grams: int) -> None:
    assert bonus_weight_grams(title) == bonus_grams


# ---------------------------------------------------------------------------
# STEP 4 (session note 2026-09-12): weight-token spacing must not split one product into two
# keys, and a bonus-weight listing must never collide with its plain-pack counterpart.
# ---------------------------------------------------------------------------


def test_weight_token_spacing_does_not_split_the_key() -> None:
    """The bug the first real measurement found: "85g" (no space) survived line_tokens() as
    noise while "85 g" (spaced) did not, so the identical product keyed differently depending on
    which shop's spacing convention it inherited. Simulating the fix beforehand raised the
    measured overlap count from 13 to 92 (docs/SOURCES.md)."""
    no_space = overlap_key("APPLAWS Piept, Pui, conserva hrana umeda pisici, 85g", "APPLAWS")
    spaced = overlap_key("Applaws, conserva hrana umeda pisici cu piept de pui, 85 g", "Applaws")
    assert no_space is not None and spaced is not None
    assert no_space == spaced


def test_weight_token_spacing_also_covers_gr_and_decimal_comma() -> None:
    a = overlap_key("Test Brand Formula X 0,85kg", "Test Brand")
    b = overlap_key("Test Brand Formula X 0.85 kg", "Test Brand")
    assert a is not None and b is not None
    assert a == b

    c = overlap_key("Test Brand Formula Y 400gr", "Test Brand")
    d = overlap_key("Test Brand Formula Y 400 gr", "Test Brand")
    assert c is not None and d is not None
    assert c == d


def test_a_plain_pack_and_its_bonus_weight_counterpart_never_collide() -> None:
    """The trap CLAUDE.md §7 names, and the specific thing STEP 4 asks for: "15 kg" and
    "15 + 3 Kg Gratis" are different purchasable units at different prices and must not merge,
    even though they share brand, line and base weight."""
    plain = overlap_key("Royal Canin Medium Adult 15 Kg", "Royal Canin")
    bonus = overlap_key("Royal Canin Medium Adult 15 + 3 Kg Gratis", "Royal Canin")
    assert plain is not None and bonus is not None
    assert plain != bonus
    assert plain.bonus_g == 0
    assert bonus.bonus_g == 3000


def test_two_bonus_weight_forms_of_the_same_product_still_collide() -> None:
    """The other half of the same requirement: two shops' bonus-weight listings of the SAME
    product must still key together, in whichever word order/spacing each shop uses."""
    petmax_form = overlap_key("Royal Canin Mini Adult 8 kg + 1 kg gratuit", "Royal Canin")
    pentruanimale_form = overlap_key(
        "ROYAL CANIN Mini Adult, hrana uscata caini, 8+1kg GRATUIT", "ROYAL CANIN"
    )
    assert petmax_form is not None and pentruanimale_form is not None
    assert petmax_form == pentruanimale_form
    assert petmax_form.bonus_g == 1000


def test_hills_apostrophe_curly_vs_straight() -> None:
    """CLAUDE.md §7 names Hill's as a brand-spelling trap. A shop writing the curly U+2019 and
    one writing the plain ASCII apostrophe must tokenize identically."""
    straight = normalized_brand("Hill's", "x")
    curly = normalized_brand("Hill’s", "x")  # noqa: RUF001
    assert straight == curly == "hill's"


# ---------------------------------------------------------------------------
# The four real title grammars for one product
# ---------------------------------------------------------------------------

ORIJEN_1800 = [
    ("animax_ro", "Hrana uscata pentru caini Orijen Original Dog Adult Mini 1.8 kg", "Orijen"),
    ("magazindeanimale_ro", "Hrană uscată câini ORIJEN Original Dog Adult Mini 1,8 kg", None),
    ("petmax_ro", "Orijen Adult Original Dog Mini 1.8 kg", "Orijen"),
    ("zoomalia_ro", "1,8 kg ORIJEN Original Dog Adult Mini", "Orijen"),
]


def test_the_same_product_across_four_shops_produces_one_key() -> None:
    keys = {overlap_key(title, brand) for _, title, brand in ORIJEN_1800}
    assert len(keys) == 1, f"proxy key split across shops: {keys}"


def test_word_order_is_discarded() -> None:
    """CLAUDE.md §7: petmax reverses the line name ("Orijen Adult Original"). Order carries no
    identity across these shops, so the tokens are sorted."""
    assert line_tokens("Orijen Original Dog Adult Mini 1.8 kg", "Orijen") == line_tokens(
        "Orijen Adult Original Dog Mini 1.8 kg", "Orijen"
    )


def test_diacritics_are_folded() -> None:
    assert normalized_brand("Smølke", "x") == normalized_brand("Smolke", "x")
    assert line_tokens("Hrană uscată câini Acana Heritage 2 kg", "Acana") == line_tokens(
        "Hrana uscata caini Acana Heritage 2 kg", "Acana"
    )


def test_brand_falls_back_to_the_first_title_token() -> None:
    assert normalized_brand(None, "ORIJEN Original Dog Adult Mini 1,8 kg") == "orijen"
    assert normalized_brand("   ", "Acana Heritage 2 kg") == "acana"


# ---------------------------------------------------------------------------
# The hard negative: same line, different weight, must NOT collide
# ---------------------------------------------------------------------------


def test_different_weights_are_different_keys() -> None:
    """CLAUDE.md §7: "same brand, same product line, different weight is not a match" — the
    dominant hard negative. If the proxy collapsed these the overlap count would be inflated
    and the gate would pass on nothing."""
    small = overlap_key("Orijen Original Dog Adult Mini 1.8 kg", "Orijen")
    large = overlap_key("Orijen Original Dog Adult Mini 4.5 kg", "Orijen")
    assert small is not None and large is not None
    assert small != large


def test_different_lines_are_different_keys() -> None:
    puppy = overlap_key("Royal Canin Mini Puppy 8 kg", "Royal Canin")
    adult = overlap_key("Royal Canin Mini Adult 8 kg", "Royal Canin")
    assert puppy != adult


def test_different_brands_are_different_keys() -> None:
    a = overlap_key("Acana Heritage Adult 2 kg", "Acana")
    b = overlap_key("Orijen Heritage Adult 2 kg", "Orijen")
    assert a != b


# ---------------------------------------------------------------------------
# Unkeyable listings — why the count is a floor
# ---------------------------------------------------------------------------


def test_a_title_without_a_weight_cannot_be_keyed() -> None:
    """zoopoint.ro puts no weight in the title at all (CLAUDE.md §7). Those listings drop out
    of the count, which is exactly why it is reported as a floor and not as the truth."""
    assert overlap_key("Orijen Original Dog Adult Mini", "Orijen") is None


def test_a_title_with_only_a_brand_cannot_be_keyed() -> None:
    assert overlap_key("Orijen 1.8 kg", "Orijen") is None


def test_gate_target_matches_the_documented_number() -> None:
    assert OVERLAP_TARGET == 400

"""The cross-shop overlap proxy — the Phase 1 gate metric (ADR-0009).

These tests pin the proxy's behaviour on the exact title grammars CLAUDE.md §7 documents, using
the four real shop spellings of one product. The key must collide across all of them, or the gate
measures nothing.
"""

from __future__ import annotations

import pytest

from pricepilot.overlap import (
    OVERLAP_TARGET,
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
    ],
)
def test_net_weight_grams(title: str, grams: int | None) -> None:
    assert net_weight_grams(title) == grams


def test_bonus_weight_is_not_added_to_the_base_pack() -> None:
    """ "8 kg + 1 kg gratuit" is an 8 kg product with a promotion, not a 9 kg product.

    This is a judgement call and it is documented in `overlap.py`: the base pack identifies the
    product line, so the two petmax listings land in the same overlap bucket. Their prices still
    differ, and Phase 3's matcher is free to decide otherwise — the proxy only needs a floor.
    """
    assert net_weight_grams("Royal Canin Mini Adult 8 kg + 1 kg gratuit") == 8000
    assert net_weight_grams("Royal Canin Medium Adult 15 + 3 Kg Gratis") == 15000


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

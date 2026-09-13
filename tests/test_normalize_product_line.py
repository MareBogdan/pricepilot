"""product_line extraction — STEP A (this session). Every case below is either a real title
pulled from the in-scope population (never docs/learned/phase2-gate-sample.csv, which stays
frozen and unlabelled) or a minimal synthetic case isolating one specific rule."""

from __future__ import annotations

import pytest

from pricepilot.normalize.product_line import extract_product_line


def test_royal_canin_line_name_survives_intact() -> None:
    """The highest-stakes case: "Adult" here is the product's own line name (Royal Canin
    genuinely sells "Mini Adult"), not shop boilerplate. A global life-stage strip would have
    deleted it — this is why _STAGE is only ever consumed inside a matched hrana/recompense
    clause, never as a free-standing word."""
    assert extract_product_line("Royal Canin Mini Adult 8 kg", "Royal Canin") == "Mini Adult"


def test_petmax_comma_prefix_form() -> None:
    assert (
        extract_product_line(
            "Hrana uscata caini, Pro Plan Small & Mini Puppy Chicken, 700 g", "PRO PLAN"
        )
        == "Small & Mini Puppy Chicken"
    )


def test_animax_no_comma_prefix_form() -> None:
    assert (
        extract_product_line("Hrana uscata pentru caini Bosch Adult cu miel si orez 15 kg", "Bosch")
        == "Adult cu miel si orez"
    )


def test_pentruanimale_mid_title_packaging_clause() -> None:
    assert (
        extract_product_line(
            "CALIBRA Premium Line, Miel si Pasare, plic hrana umeda pisici, (in suc propriu), 100g",
            "CALIBRA",
        )
        == "Premium Line, Miel si Pasare, (in suc propriu)"
    )


def test_sub_line_stays_out_of_brand_removal() -> None:
    """convention 5 (ADR-0026): the sub-line belongs in product_line, not brand. Only the raw
    source_brand field text is removed — "Premium by Nature" is never guessed as "part of the
    brand" just because it sits next to it."""
    result = extract_product_line(
        "Hrana uscata pentru caini Brit Premium by Nature Junior XL 15 kg", "Brit Premium"
    )
    assert result == "by Nature Junior XL"


def test_dosage_band_hard_case_still_resolves_cleanly() -> None:
    """The same title that stress-tested quantity.py's K-9/dosage-band masking — product_line
    must not choke on it either."""
    result = extract_product_line(
        "Recompense pentru caini Purina Dentalife Medium 12-25kg 115g", "PURINA"
    )
    assert result == "Dentalife Medium"


def test_multipack_and_pack_descriptor_words_are_removed() -> None:
    result = extract_product_line(
        "ADVANCE Kitten, Pui, plic hrana umeda pisici junior, (in sos), multipack, 85g x 4buc",
        "ADVANCE",
    )
    assert result == "Kitten, Pui, (in sos)"
    assert "multipack" not in (result or "").lower()
    assert "x" not in (result or "").split()  # the dangling "x" glue must not survive


def test_pachet_economic_is_removed() -> None:
    result = extract_product_line(
        "CALIBRA Premium Line, XS-XL, Vita, hrana uscata caini, pachet economic, 14kg", "CALIBRA"
    )
    assert "pachet economic" not in (result or "").lower()


def test_compound_stage_chain_joined_by_ampersand() -> None:
    """ "junior & adult" — a bare "adult" is only ever consumed as the second+ link of a stage
    chain anchored by a real _STAGE word, never as a free-standing match (see
    test_royal_canin_line_name_survives_intact)."""
    result = extract_product_line(
        "CANAGAN Dental Small Breed, XS-S, Curcan, hrana uscata fara cereale caini junior & "
        "adult, sensibilitati dentare, 2kg",
        "CANAGAN",
    )
    assert result == "Dental Small Breed, XS-S, Curcan, sensibilitati dentare"


def test_no_source_brand_still_strips_clause_and_quantity() -> None:
    result = extract_product_line("Hrana uscata pentru caini super premium fara nume 4 kg", None)
    assert result == "super premium fara nume"


def test_preparation_style_descriptors_are_preserved() -> None:
    """ "(în sos)"/"(în aspic)" etc. are not in the removal vocabulary — genuinely unsure whether
    they're boilerplate or a real distinguishing variant, so CLAUDE.md's "leave it in" default
    applies."""
    result = extract_product_line(
        "PIPER Animals, XS-XL, Iepure, conserva hrana umeda fara cereale caini, (in aspic), 400g",
        "PIPER",
    )
    assert "(in aspic)" in (result or "")


def test_accessory_title_with_no_food_clause_is_left_alone() -> None:
    """No "hrana"/"recompense" clause at all — nothing in the removal vocabulary applies, so
    only brand and quantity are removed."""
    result = extract_product_line(
        "Nisip pentru litiera City Cat Clumping White Baby Powder 10L", "City Cat"
    )
    assert result == "Nisip pentru litiera Clumping White Baby Powder"


def test_no_brand_field_and_nothing_to_strip_returns_the_title_unchanged() -> None:
    result = extract_product_line("Litiera cu rama, Virgo, Albastru, 52X39X20CM", "MPS")
    assert result == "Litiera cu rama, Virgo, Albastru, 52X39X20CM"


@pytest.mark.parametrize(
    "title",
    [
        "Hrana uscata pentru caini",
        "Recompense pentru caini",
    ],
)
def test_a_title_that_is_pure_boilerplate_can_return_none(title: str) -> None:
    """Rare, but legitimate: if literally nothing survives removal, None is the honest answer,
    not an empty string."""
    assert extract_product_line(title, None) is None

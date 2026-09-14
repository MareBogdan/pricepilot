"""product_line extraction — STEP A (this session). Every case below is either a real title
pulled from the in-scope population (never docs/learned/phase2-gate-sample.csv, which stays
frozen and unlabelled) or a minimal synthetic case isolating one specific rule."""

from __future__ import annotations

import pytest

from pricepilot.normalize.product_line import extract_product_line, product_line_guard_violations


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
    """convention 5 (ADR-0026): the sub-line belongs in product_line, not brand. Only the
    *manufacturer* portion of the brand field is removed — "Premium" is never swallowed just
    because petmax happens to pack it into the same brand-field string as "Brit"."""
    result = extract_product_line(
        "Hrana uscata pentru caini Brit Premium by Nature Junior XL 15 kg", "Brit Premium"
    )
    assert result == "Premium by Nature Junior XL"


def test_brand_field_fragmentation_is_cross_shop_comparable() -> None:
    """The acceptance test for STEP 1a (2026-09-14): petmax packs "Premium" into its own
    brand-field string ("Brit Premium"); pentruanimale states the bare manufacturer ("BRIT") and
    leaves the sub-line entirely in the title. Stripping the whole raw brand field (the bug this
    fix replaces) made these two product_lines share barely a token; stripping only the
    manufacturer text makes them the same sub-line family again."""
    petmax = extract_product_line(
        "Hrana uscata pentru caini Brit Premium by Nature Junior XL 15 kg", "Brit Premium"
    )
    pentruanimale = extract_product_line(
        "BRIT Premium By Nature Adult Large Breed, L, Pui, hrană uscată câini", "BRIT"
    )
    assert petmax == "Premium by Nature Junior XL"
    assert pentruanimale == "Premium By Nature Adult Large Breed, L, Pui"
    # Both start with the same sub-line family — no longer two disjoint fragments.
    assert petmax.lower().startswith("premium by nature")
    assert pentruanimale.lower().startswith("premium by nature")


def test_calibra_suffix_forms_all_strip_to_the_same_manufacturer() -> None:
    """petmax splits Calibra's brand field into five strings (Calibra/Life/Premium/Expert/
    Veterinary — the last excluded upstream as a regulated product); each non-bare form must
    leave its own sub-line word in product_line, not lose it with the brand."""
    life = extract_product_line("Calibra Dog Life Turkey with Apples 400 g", "Calibra Life")
    premium = extract_product_line(
        "Calibra Dog Premium Can with Veal & Chicken 1240 g", "Calibra Premium"
    )
    expert = extract_product_line(
        "Calibra Dog Expert+ Adult Mobility & Joint Support 2 kg", "Calibra Expert"
    )
    assert life == "Dog Life Turkey with Apples"
    assert premium == "Dog Premium Can with Veal & Chicken"
    assert expert == "Dog Expert+ Adult Mobility & Joint Support"


def test_hills_suffix_forms_cross_shop_comparable() -> None:
    """petmax's "Hill's Pet Nutrition" and pentruanimale's "HILL'S Science Plan" must both strip
    down to the bare manufacturer, leaving their respective (different, real) sub-lines intact —
    not collide, and not lose the sub-line by stripping the whole raw field."""
    petmax = extract_product_line(
        "Hill's Pet Nutrition Adult Chicken 12 kg", "Hill's Pet Nutrition"
    )
    pentruanimale = extract_product_line(
        "HILL'S Science Plan Adult Chicken 12 kg", "HILL'S Science Plan"
    )
    assert petmax == "Pet Nutrition Adult Chicken"
    assert pentruanimale == "Science Plan Adult Chicken"


def test_alias_table_entry_still_strips_the_whole_raw_field() -> None:
    """An alias-table entry (the whole raw string names the manufacturer, e.g. "Affinity
    Advance" -> "advance") is unaffected by STEP 1a — there's no separate sub-line inside it to
    preserve, so the entire raw brand-field text is still removed, same as before."""
    result = extract_product_line("Affinity Advance Adult Chicken 12 kg", "Affinity Advance")
    assert result is not None
    assert "affinity" not in result.lower()
    assert "advance" not in result.lower()
    assert result.lower().startswith("adult chicken")


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


# ---------------------------------------------------------------------------
# STEP 1b (2026-09-14) — dangling-token guard. The motivating case is a real accessory title
# where excising a quantity span left its own qualifier word stranded mid-string with nothing
# left to modify; the guard is general (a closed connective/qualifier vocabulary, checked at both
# string edges and inside every comma-delimited segment), not a patch for this one word.
# ---------------------------------------------------------------------------


def test_orphaned_qualifier_is_removed_with_its_quantity() -> None:
    """The exact motivating case: "diametru 2 l" loses its quantity to `quantity_spans`, which
    would otherwise leave "diametru" alone in its own comma segment, naming nothing."""
    result = extract_product_line(
        "Bol pentru hrana animale, inox, diametru 2 l, 25 cm, Negru Agility", None
    )
    assert result == "Bol pentru hrana animale, inox, 25 cm, Negru Agility"
    assert product_line_guard_violations(result) == []


def test_leading_dangling_connective_is_stripped() -> None:
    """No "hrana ... caini" clause swallows the whole "cu Pui" — only "cu" is boilerplate glue
    left dangling once the clause immediately before it is gone; "Pui" is real flavour text."""
    result = extract_product_line("Hrana uscata pentru caini cu Pui 4 kg", None)
    assert result == "Pui"
    assert product_line_guard_violations(result) == []


def test_trailing_dangling_connective_is_stripped() -> None:
    result = extract_product_line("Ceva Brand Trixie de 500 g", "Trixie")
    assert result == "Ceva Brand"
    assert product_line_guard_violations(result) == []


def test_dangling_word_that_is_part_of_a_real_phrase_survives() -> None:
    """The guard only fires when a whole comma segment (or the string's own edge) reduces to
    exactly one dangling word — never when the word sits inside a longer, real phrase like "with
    Apples" or "cu miel si orez"."""
    result = extract_product_line(
        "Hrana uscata pentru caini Bosch Adult cu miel si orez 15 kg", "Bosch"
    )
    assert result == "Adult cu miel si orez"
    assert product_line_guard_violations(result) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Foo, diametru, Bar", ["orphaned_qualifier_in_comma_segment"]),
        ("cu Foo Bar", ["starts_with_connective_or_qualifier"]),
        ("Foo Bar de", ["ends_in_connective_or_qualifier"]),
        ("Foo,, Bar", ["contains_double_comma"]),
        ("- Foo Bar", ["starts_with_connective_or_punctuation"]),
        ("Foo Bar -", ["ends_in_bare_punctuation"]),
    ],
)
def test_guard_violations_are_detected_on_synthetic_bad_input(
    text: str, expected: list[str]
) -> None:
    """Contract test for the checker itself (not the cleanup step) — confirms
    `product_line_guard_violations` actually flags each invariant it's supposed to, so a future
    change to the cleanup step has something real to be validated against."""
    violations = product_line_guard_violations(text)
    for name in expected:
        assert name in violations

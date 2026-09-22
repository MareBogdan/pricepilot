"""Tests for src/pricepilot/matching/pair_text.py -- the one canonical model-input builder
(ADR-0028 addendum #19). The leakage guard here is the actual point of this module: a passing
test is only meaningful if it tries hard to catch a real leak, not just that the happy path
formats a string."""

from __future__ import annotations

from pricepilot.matching.pair_text import (
    ATTRIBUTE_FIELDS,
    MISSING_VALUE_MARKER,
    PAIR_TEXT_VERSION,
    build_pair_text,
)

REAL_LEFT = {
    "content_hash": "e6d623aa0e58f1b509d248c5f23e8b775d9852ae9b2cebbc2d9341ce86fb748e",
    "source": "petmax_ro",
    "title": "Royal Canin Bichon Maltese Adult, 500 g",
    "brand": "royal canin",
    "product_line": "Bichon Maltese Adult",
    "net_weight_g": 500,
    "net_volume_ml": None,
    "pack_count": None,
    "bonus_weight_g": None,
    "breed_size_code": None,
    "life_stage": "adult",
    "flavour": None,
    "food_form": None,
    "species": "dog",
    "breed_size_class": None,
}
REAL_RIGHT = {
    "content_hash": "acf8ff85a6ced02c537c0fdeb75c3e68e84989560007c451a9c82b4270afd38b",
    "source": "animax_ro",
    "title": "Hrana uscata pentru caini Royal Canin Bichon Frise Adult 500 g",
    "brand": "royal canin",
    "product_line": "Bichon Frise Adult",
    "net_weight_g": 500,
    "net_volume_ml": None,
    "pack_count": None,
    "bonus_weight_g": None,
    "breed_size_code": None,
    "life_stage": "adult",
    "flavour": None,
    "food_form": "dry",
    "species": "dog",
    "breed_size_class": None,
}


def test_version_constant_exists_and_is_a_nonempty_string() -> None:
    assert isinstance(PAIR_TEXT_VERSION, str)
    assert PAIR_TEXT_VERSION


def test_returns_a_tuple_of_two_strings_from_real_shaped_records() -> None:
    text_a, text_b = build_pair_text(REAL_LEFT, REAL_RIGHT)
    assert isinstance(text_a, str)
    assert isinstance(text_b, str)
    assert "Royal Canin Bichon Maltese Adult, 500 g" in text_a
    assert "Bichon Frise Adult" in text_b


# The display label each field renders under -- duplicated here (not imported from the private
# `_FIELD_LABELS`) so these tests verify the documented, user-facing text format independently,
# not just that the module agrees with itself.
FIELD_LABELS = {
    "brand": "brand",
    "product_line": "line",
    "net_weight_g": "weight_g",
    "net_volume_ml": "volume_ml",
    "pack_count": "pack",
    "bonus_weight_g": "bonus_g",
    "breed_size_code": "breed_size",
    "life_stage": "life_stage",
    "food_form": "food_form",
    "flavour": "flavour",
}


def test_each_labels_value_is_bound_to_the_correct_field_not_just_correctly_ordered() -> None:
    """Pins label-TO-VALUE binding, not just label order (reviewer finding): a refactor that kept
    every label in its declared position but mis-wired which field's value renders under which
    label -- e.g. brand's value appearing after `life_stage:` and vice versa -- would still pass
    an order-only check. Both models would still consume the same (silently corrupted) text, so
    the baseline-vs-fine-tune comparison would stay internally fair, but every feature would be
    wrong and error analysis would be nonsense with nothing failing to say so."""
    text_a, text_b = build_pair_text(REAL_LEFT, REAL_RIGHT)
    assert "title: Royal Canin Bichon Maltese Adult, 500 g" in text_a
    assert "brand: royal canin" in text_a
    assert "line: Bichon Maltese Adult" in text_a
    assert "weight_g: 500" in text_a
    assert "life_stage: adult" in text_a
    assert "food_form: <missing>" in text_a  # REAL_LEFT's food_form is None
    assert "title: Hrana uscata pentru caini Royal Canin Bichon Frise Adult 500 g" in text_b
    assert "line: Bichon Frise Adult" in text_b
    assert "food_form: dry" in text_b  # REAL_RIGHT's food_form is "dry" -- differs from text_a


def test_title_and_every_attribute_field_appear_in_a_fixed_order() -> None:
    text_a, _ = build_pair_text(REAL_LEFT, REAL_RIGHT)
    labels_in_order = ["title"] + [FIELD_LABELS[f] for f in ATTRIBUTE_FIELDS]
    found_positions = [text_a.index(f"{label}:") for label in labels_in_order]
    assert found_positions == sorted(found_positions), (
        "attribute fields must appear in ATTRIBUTE_FIELDS's declared order, every time"
    )


def test_missing_value_is_a_distinct_marker_not_the_string_none_or_empty() -> None:
    listing = {"title": "X"}  # every attribute field absent
    text, _ = build_pair_text(listing, listing)
    for field in ATTRIBUTE_FIELDS:
        assert f"{FIELD_LABELS[field]}: {MISSING_VALUE_MARKER}" in text
    assert "None" not in text


def test_missing_weight_renders_differently_from_a_real_zero_weight() -> None:
    missing = {"title": "X", "net_weight_g": None}
    zero = {"title": "X", "net_weight_g": 0}
    text_missing, _ = build_pair_text(missing, missing)
    text_zero, _ = build_pair_text(zero, zero)
    assert f"weight_g: {MISSING_VALUE_MARKER}" in text_missing
    assert "weight_g: 0" in text_zero
    assert text_missing != text_zero


def test_left_and_right_are_not_swapped() -> None:
    text_a, text_b = build_pair_text(REAL_LEFT, REAL_RIGHT)
    assert "Bichon Maltese" in text_a
    assert "Bichon Maltese" not in text_b
    assert "Bichon Frise" in text_b
    assert "Bichon Frise" not in text_a


def test_output_never_contains_label_tier_split_pair_id_or_source() -> None:
    """The real leakage guard: a listing dict carrying forbidden fields with distinctive sentinel
    values must never have those sentinels reach the output text, because build_pair_text() only
    ever reads 'title' plus the fixed ATTRIBUTE_FIELDS allow-list -- it does not need to
    "avoid" reading these fields, it structurally cannot."""
    poisoned_left = {
        **REAL_LEFT,
        "label": "SENTINEL_LABEL_M",
        "tier": "SENTINEL_TIER_proxy_key_collision",
        "split": "SENTINEL_SPLIT_test",
        "pair_id": "SENTINEL_PAIR_ID_should_never_appear",
        "occurrence_id": "SENTINEL_OCC_ID_should_never_appear",
        "source": "SENTINEL_SOURCE_petmax_ro",
    }
    poisoned_right = {
        **REAL_RIGHT,
        "label": "SENTINEL_LABEL_N",
        "tier": "SENTINEL_TIER_trivial_spot_check",
        "split": "SENTINEL_SPLIT_train_val",
        "pair_id": "SENTINEL_PAIR_ID_should_never_appear_either",
        "occurrence_id": "SENTINEL_OCC_ID_should_never_appear_either",
        "source": "SENTINEL_SOURCE_animax_ro",
    }
    text_a, text_b = build_pair_text(poisoned_left, poisoned_right)
    combined = text_a + text_b
    forbidden_substrings = [
        "SENTINEL_LABEL",
        "SENTINEL_TIER",
        "SENTINEL_SPLIT",
        "SENTINEL_PAIR_ID",
        "SENTINEL_OCC_ID",
        "SENTINEL_SOURCE",
        "petmax_ro",
        "animax_ro",
    ]
    for forbidden in forbidden_substrings:
        assert forbidden not in combined, f"leaked forbidden field into pair text: {forbidden!r}"


def test_missing_title_raises() -> None:
    import pytest

    with pytest.raises(ValueError, match="title"):
        build_pair_text({"brand": "x"}, REAL_RIGHT)


def test_attribute_fields_list_matches_the_task_specification() -> None:
    """CLAUDE.md's own task brief names exactly these ten fields, no more, no fewer -- species
    and breed_size_class are deliberately excluded even though the real queue records carry
    them, and this test pins that exclusion so it survives a future refactor."""
    assert ATTRIBUTE_FIELDS == (
        "brand",
        "product_line",
        "net_weight_g",
        "net_volume_ml",
        "pack_count",
        "bonus_weight_g",
        "breed_size_code",
        "life_stage",
        "food_form",
        "flavour",
    )
    assert "species" not in ATTRIBUTE_FIELDS
    assert "breed_size_class" not in ATTRIBUTE_FIELDS

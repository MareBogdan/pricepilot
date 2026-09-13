"""`normalize.extract()` — composes every STEP 3 extractor into one result, and never raises."""

from __future__ import annotations

from pricepilot.normalize import extract


def test_composes_every_field() -> None:
    result = extract(
        "Hrana uscata caini, Calibra Dog Premium Line Adult 12+2 kg", source_brand="Calibra Premium"
    )
    assert result.brand == "calibra"
    assert result.net_weight_g == 12000
    assert result.bonus_weight_g == 2000
    assert result.food_form == "dry"
    assert result.life_stage == "adult"
    assert result.errors == {}


def test_real_hard_case_from_the_frozen_gate_sample() -> None:
    """listing_id 28782 in docs/learned/phase2-gate-sample.csv — dosage band AND the product's
    own weight in the same title, the highest-risk confusion convention 4 names."""
    result = extract(
        "Recompense pentru caini Purina Dentalife Medium 12-25kg 115g", source_brand="PURINA"
    )
    assert result.dosage_band == "12-25 kg"
    assert result.net_weight_g == 115
    assert result.brand == "purina"


def test_not_stated_fields_are_none_not_errors() -> None:
    result = extract("Jucarie pentru pisici Kong Cat Bila plutitoare", source_brand="Kong")
    assert result.net_weight_g is None
    assert result.flavour is None
    assert result.breed_size_code is None
    assert result.errors == {}  # absence is not a failure


def test_no_source_brand_leaves_brand_none_without_erroring() -> None:
    result = extract("Some title with no structured brand field", source_brand=None)
    assert result.brand is None
    assert result.errors == {}


def test_a_broken_field_does_not_lose_the_rest_of_the_row() -> None:
    """Simulates one extractor raising: `extract()` must still return every other field, with
    only the broken one recorded in `.errors` — the same "one bad field doesn't lose the row"
    principle the scrapers already use for cards."""
    import pricepilot.normalize as normalize_module

    def boom(title: str) -> None:
        raise ValueError("simulated extractor failure")

    original = normalize_module.extract_flavour
    normalize_module.extract_flavour = boom  # type: ignore[assignment]
    try:
        result = normalize_module.extract(
            "Royal Canin Mini Adult cu Pui 8 kg", source_brand="Royal Canin"
        )
    finally:
        normalize_module.extract_flavour = original  # type: ignore[assignment]

    assert result.net_weight_g == 8000  # unaffected fields still populated
    assert result.brand == "royal canin"
    assert "flavour" in result.errors
    assert "simulated extractor failure" in result.errors["flavour"]

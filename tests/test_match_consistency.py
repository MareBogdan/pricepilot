"""Phase 5 s3b: the attribute-consistency guard on cross-encoder matches (ADR-0041).

Pure logic, no model and no database. Each case is built from the rule it exercises
(`docs/learned/phase3-annotation-conventions.md`), not copied from a known-bad row.
"""

from __future__ import annotations

from pricepilot.matching.consistency import ListingFacts, conflicts, life_stage_marker


def facts(
    title: str = "Acme Dog Food 2 kg",
    category: str | None = "food",
    life_stage: str | None = None,
    flavour: str | None = None,
) -> ListingFacts:
    return ListingFacts(category=category, title=title, life_stage=life_stage, flavour=flavour)


def test_clean_same_product_pair_passes() -> None:
    ours = facts(category="dry_food", life_stage="adult", flavour="chicken")
    theirs = facts(category="food", life_stage="adult", flavour="chicken")
    assert conflicts(ours, theirs) == []


def test_litter_against_food_is_a_category_conflict() -> None:
    reasons = conflicts(facts(category="litter"), facts(category="food"))
    assert reasons == ["category_conflict:litter!=food"]


def test_food_against_litter_or_accessory_is_a_category_conflict() -> None:
    assert conflicts(facts(category="dry_food"), facts(category="litter"))
    assert conflicts(facts(category="treats"), facts(category="accessory"))


def test_category_mapping_allows_the_competitor_taxonomy_and_unknown_never_rejects() -> None:
    for mine, theirs in [
        ("dry_food", "food"),
        ("wet_food", "food"),
        ("treats", "food"),
        ("litter", "litter"),
        ("grooming", "accessory"),
        ("accessories", "accessory"),
        ("accessories", "toy"),
    ]:
        assert conflicts(facts(category=mine), facts(category=theirs)) == [], (mine, theirs)
    assert conflicts(facts(category="litter"), facts(category=None)) == []


def test_one_sided_kitten_marker_rejects_in_either_direction() -> None:
    plain = facts(title="Acme Cat Wet 85 g")
    kitten = facts(title="Acme Kitten Wet 85 g")
    assert conflicts(plain, kitten) == ["life_stage_conflict:none!=kitten"]
    assert conflicts(kitten, plain) == ["life_stage_conflict:kitten!=none"]


def test_extractor_stage_and_romanian_kitten_word_are_recognised() -> None:
    assert life_stage_marker("Acme Pui Wet", "junior") == "junior"
    assert life_stage_marker("Hrana pentru pisoi 85 g", None) == "kitten"
    assert life_stage_marker("Acme Cat Wet 85 g", None) is None
    # 'pui' means chicken in these shops (normalize.attributes), never a stage
    assert life_stage_marker("Hrana cu pui 85 g", None) is None


def test_different_stages_on_both_sides_reject_but_equal_stages_pass() -> None:
    assert conflicts(facts(life_stage="adult"), facts(life_stage="senior"))
    assert conflicts(facts(life_stage="adult"), facts(life_stage="adult+7"))
    assert conflicts(facts(life_stage="puppy"), facts(life_stage="puppy")) == []


def test_plain_adult_against_a_silent_listing_passes() -> None:
    # "adult" is the unmarked default stage: a shop dropping it is title verbosity, not a new SKU.
    assert conflicts(facts(life_stage="adult"), facts()) == []
    assert conflicts(facts(), facts(life_stage="adult")) == []
    # ...but a one-sided age-band formula ("Adult 7+") is a distinct SKU and rejects.
    assert conflicts(facts(), facts(life_stage="adult+7"))


def test_flavour_conflict_needs_both_sides_to_state_one() -> None:
    assert conflicts(facts(flavour="chicken"), facts(flavour="beef")) == [
        "flavour_conflict:chicken!=beef"
    ]
    assert conflicts(facts(flavour="Chicken"), facts(flavour="chicken")) == []
    # Rule 5: flavour on one side only is the annotator's "skip", not a rejection
    assert conflicts(facts(flavour=None), facts(flavour="chicken")) == []
    assert conflicts(facts(flavour="chicken"), facts(flavour=None)) == []


def test_every_conflict_is_reported_not_just_the_first() -> None:
    reasons = conflicts(
        facts(category="litter", flavour="beef"),
        facts(category="food", title="Acme Kitten 10 kg", flavour="duck"),
    )
    assert [r.split(":")[0] for r in reasons] == [
        "category_conflict",
        "life_stage_conflict",
        "flavour_conflict",
    ]

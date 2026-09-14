"""Brand canonicalization — STEP 3, second in build order. Every case here is a real raw brand
string observed in `raw_listings` (printed and reviewed before this alias table was written)."""

from __future__ import annotations

import pytest

from pricepilot.normalize.brand import (
    brand_blocking_key,
    canonicalize_brand,
    is_suspected_distributor_code,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Brit fragmentation (animax + petmax)
        ("Brit Care", "brit"),
        ("Brit Premium", "brit"),
        ("Brit", "brit"),
        ("BRIT", "brit"),
        ("Brit Fresh", "brit"),
        # Calibra fragmentation (petmax)
        ("Calibra Life", "calibra"),
        ("Calibra Premium", "calibra"),
        ("Calibra Expert", "calibra"),
        ("Calibra", "calibra"),
        ("CALIBRA", "calibra"),
        # Hill's fragmentation — must survive with its apostrophe, per CLAUDE.md §7
        ("Hill's Science Plan", "hill's"),
        ("HILL'S Science Plan", "hill's"),
        ("Hill's", "hill's"),
        ("Hill's Pet Nutrition", "hill's"),
        # Purina family
        ("PRO PLAN", "purina"),
        ("Pro Plan", "purina"),
        ("PURINA Pro Plan", "purina"),
        ("Purina ONE", "purina"),
        ("Purina", "purina"),
        ("Dog Chow", "purina"),
        ("Purina Dog Chow", "purina"),
        ("Purina Cat Chow", "purina"),
        # Other real fragmentation caught while reviewing the printed data
        ("Affinity Advance", "advance"),
        ("Advance", "advance"),
        ("Julius k-9", "julius-k9"),
        ("Julius-K9", "julius-k9"),
        ("M-Petss", "m-pets"),
        ("M-Pets", "m-pets"),
        ("Unica Classe", "unica"),
        # Already-simplest-form brands: unchanged except case
        ("Royal Canin", "royal canin"),
        ("ROYAL CANIN", "royal canin"),
        ("Trixie", "trixie"),
        ("Taste of the Wild", "taste of the wild"),
    ],
)
def test_known_brand_variants_canonicalize(raw: str, expected: str) -> None:
    assert canonicalize_brand("irrelevant title", raw) == expected


def test_no_source_brand_is_not_stated_not_a_failure() -> None:
    assert canonicalize_brand("some title with no structured brand", None) is None
    assert canonicalize_brand("some title", "") is None
    assert canonicalize_brand("some title", "   ") is None


def test_suffix_stripping_never_empties_a_brand() -> None:
    """ "Dog Chow" alone must resolve via the alias table, not the suffix stripper — if the
    stripper ran on it directly it would try to remove the whole string and leave nothing."""
    assert canonicalize_brand("t", "Dog Chow") == "purina"
    assert canonicalize_brand("t", "Cat Chow") == "purina"


# ---------------------------------------------------------------------------
# Phase 3 STEP 3 — brand_blocking_key. Real collisions found this session among today's own
# canonical brand values, none of them merged by canonicalize_brand()'s own aliasing.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("brand_a", "brand_b"),
    [
        ("club 4 paws", "club4paws"),
        ("cat's best", "cat`s best"),
        ("my love", "mylove"),
        ("lolopets", "lolo pets"),
        ("dr. clauder's", "dr. clauder`s"),
    ],
)
def test_blocking_key_unifies_real_hyphen_space_collisions(brand_a: str, brand_b: str) -> None:
    assert brand_blocking_key(brand_a) == brand_blocking_key(brand_b)


def test_blocking_key_none_in_none_out() -> None:
    assert brand_blocking_key(None) is None


def test_blocking_key_distinct_brands_stay_distinct() -> None:
    assert brand_blocking_key("royal canin") != brand_blocking_key("purina")


# ---------------------------------------------------------------------------
# Phase 3 STEP 3 — is_suspected_distributor_code. A small, hand-verified list, not a statistical
# threshold (see brand.py's own docstring for the automated approach that was tried and rejected).
# ---------------------------------------------------------------------------


def test_confirmed_distributor_codes_are_flagged() -> None:
    assert is_suspected_distributor_code("opti") is True
    assert is_suspected_distributor_code("ipts") is True


def test_real_manufacturers_are_not_flagged() -> None:
    """ "record" was checked closely this session (most of its titles carry "Record"/"BiscoRe"
    visibly) and confirmed real — an earlier, hastier read of the same data had called it a
    distributor code without checking title context; not repeated here."""
    assert is_suspected_distributor_code("record") is False
    assert is_suspected_distributor_code("royal canin") is False
    assert is_suspected_distributor_code("essential foods") is False


def test_none_brand_is_not_flagged() -> None:
    assert is_suspected_distributor_code(None) is False

"""Brand canonicalization — STEP 3, second in build order. Every case here is a real raw brand
string observed in `raw_listings` (printed and reviewed before this alias table was written)."""

from __future__ import annotations

import pytest

from pricepilot.normalize.brand import canonicalize_brand


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

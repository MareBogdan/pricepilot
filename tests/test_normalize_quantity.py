"""Weight/volume/pack/bonus/dosage extraction — STEP 3, tested against every convention and
CLAUDE.md §7's named hard cases, plus real titles pulled from the frozen gate sample."""

from __future__ import annotations

import pytest

from pricepilot.normalize.quantity import extract_quantity, quantity_spans
from pricepilot.overlap import strip_diacritics

# ---------------------------------------------------------------------------
# STEP 2 conventions, verbatim
# ---------------------------------------------------------------------------


def test_convention_1_multipack_stores_single_unit_not_total() -> None:
    r = extract_quantity("Sheba Mini, Selectii mixte, 6x50g")
    assert r.net_weight_g == 50
    assert r.pack_count == 6


def test_convention_2_bonus_pack_records_base_and_bonus_separately() -> None:
    r = extract_quantity("Hrana uscata caini, Calibra Dog Premium Line Adult 12+2 kg")
    assert r.net_weight_g == 12000
    assert r.bonus_weight_g == 2000


def test_convention_2_bonus_pack_word_order_and_no_unit_on_base() -> None:
    r = extract_quantity("Equilibrio Adult Dogs, cu Pui, 12 + 2 Kg")
    assert r.net_weight_g == 12000
    assert r.bonus_weight_g == 2000


def test_convention_3_explicit_1x_pack() -> None:
    r = extract_quantity(
        "Royal Canin Sensory Feel, hrana umeda pisica pentru stimularea simtului tactil "
        "(in sos), 1 x 85 g"
    )
    assert r.net_weight_g == 85
    assert r.pack_count == 1


def test_convention_4_dosage_band_never_populates_net_weight_g() -> None:
    r = extract_quantity("Recompense pentru caini Purina Dentalife Medium 12-25kg 115g")
    assert r.dosage_band == "12-25 kg"
    assert r.net_weight_g == 115  # the treat's own weight, found after masking the band out


def test_convention_4_dosage_band_alone_leaves_weight_unset() -> None:
    r = extract_quantity("Advocate pipete antiparazitare caini 4-10 kg")
    assert r.dosage_band == "4-10 kg"
    assert r.net_weight_g is None


def test_dosage_band_does_not_collide_with_julius_k9_brand_code() -> None:
    """Real bug, found via STEP 4's coverage report and fixed before this module was trusted:
    "Julius K-9- 3kg" (385 titles carry this brand) parsed as dosage band "9-3 kg", swallowing
    the product's real weight, because a plain `\\b` treats the hyphen in "K-9" as a legitimate
    boundary for the dosage-band pattern to start from."""
    r = extract_quantity(
        "Hrana uscata caini premium, hipoalergenica - Miel si Orez Julius K-9- 3kg"
    )
    assert r.dosage_band is None
    assert r.net_weight_g == 3000


# ---------------------------------------------------------------------------
# Basic unit forms
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "grams"),
    [
        ("Royal Canin Mini Adult 4.5 kg", 4500),
        ("Royal Canin Mini Adult 4,5 kg", 4500),
        ("Royal Canin Mini Adult 4500 g", 4500),
        ("12 kg Royal Canin Mini Adult", 12000),  # leading token
        ("Royal Canin Mini Adult 85g", 85),  # no space before unit
        ("Royal Canin Mini Adult 85 g", 85),
    ],
)
def test_weight_forms(title: str, grams: int) -> None:
    assert extract_quantity(title).net_weight_g == grams


@pytest.mark.parametrize(
    ("title", "ml"),
    [
        ("Sampon Iv San Bernard Orange, pentru caini si pisici, 500ml", 500),
        ("Nisip silicat, Mon Petit Ami Silicat Lavanda, 7.6 l", 7600),
    ],
)
def test_volume_forms(title: str, ml: int) -> None:
    assert extract_quantity(title).net_volume_ml == ml


def test_no_quantity_in_title_is_a_legitimate_none() -> None:
    r = extract_quantity("Jucarie pentru pisici Kong Cat Bila plutitoare")
    assert r.net_weight_g is None
    assert r.net_volume_ml is None
    assert r.pack_count is None
    assert r.bonus_weight_g is None
    assert r.dosage_band is None


# ---------------------------------------------------------------------------
# Multipack variants
# ---------------------------------------------------------------------------


def test_pack_with_word_between_count_and_x() -> None:
    r = extract_quantity("Recompense pentru pisici CHURU cu pui, 4 PLICURI x 14g")
    assert r.net_weight_g == 14
    assert r.pack_count == 4


def test_standalone_piece_count_alongside_a_plain_weight() -> None:
    r = extract_quantity("Recompense caini - Crackers Collagen+ cu gust de rata - 6 bucati / 90 g")
    assert r.net_weight_g == 90
    assert r.pack_count == 6


# ---------------------------------------------------------------------------
# Weight/volume are mutually exclusive by construction (never both set)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "title",
    [
        "Royal Canin Mini Adult 4.5 kg",
        "Sampon Iv San Bernard Orange, 500ml",
        "Jucarie pentru pisici Kong Cat Bila plutitoare",
        "Recompense pentru caini Purina Dentalife Medium 12-25kg 115g",
    ],
)
def test_never_both_weight_and_volume(title: str) -> None:
    r = extract_quantity(title)
    assert r.net_weight_g is None or r.net_volume_ml is None


# ---------------------------------------------------------------------------
# quantity_spans() — used by product_line.py to erase exactly what extract_quantity found,
# never a second, independently-drifting regex.
# ---------------------------------------------------------------------------


def _erase(title: str) -> str:
    folded = strip_diacritics(title.lower())
    spans = quantity_spans(title)
    for start, end in sorted(spans, reverse=True):
        folded = folded[:start] + folded[end:]
    return folded


@pytest.mark.parametrize(
    "title",
    [
        "Royal Canin Mini Adult 4.5 kg",
        "Sheba Mini, Selectii mixte, 6x50g",
        "Hrana uscata caini, Calibra Dog Premium Line Adult 12+2 kg",
        "Recompense pentru caini Purina Dentalife Medium 12-25kg 115g",
        "Advocate pipete antiparazitare caini 4-10 kg",
        "Recompense caini - Crackers Collagen+ cu gust de rata - 6 bucati / 90 g",
    ],
)
def test_quantity_spans_erase_every_digit_the_extractor_used(title: str) -> None:
    """If a digit `extract_quantity` turned into a real field survives erasure, the spans and
    the values have drifted apart — this is the regression guard for that."""
    remaining = _erase(title)
    assert not any(c.isdigit() for c in remaining), (
        f"quantity_spans left a digit behind for {title!r}: {remaining!r}"
    )


def test_quantity_spans_empty_when_nothing_found() -> None:
    assert quantity_spans("Jucarie pentru pisici Kong Cat Bila plutitoare") == []

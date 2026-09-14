"""Phase 3 STEP 3 — category signal. Real titles/urls from the in-scope population, checked
before trusting (DECISIONS.md ADR-0028)."""

from __future__ import annotations

from pricepilot.normalize.category import categorize_listing


def test_petmax_url_segment_maps_to_food() -> None:
    result = categorize_listing(
        "petmax_ro",
        "https://www.petmax.ro/hrana-uscata-caini/royal-canin-medium-adult-4-kg.html",
        {"brand": "Royal Canin"},
        "Royal Canin Medium Adult 4 kg",
    )
    assert result == "food"


def test_petmax_url_segment_maps_to_accessory() -> None:
    result = categorize_listing(
        "petmax_ro",
        "https://www.petmax.ro/accesorii-caini/jucarie-plus-ferribiella-baby-porcusor-13cm.html",
        None,
        "Jucarie plus Ferribiella Baby Porcusor 13cm",
    )
    assert result == "accessory"


def test_petmax_url_segment_maps_to_litter() -> None:
    result = categorize_listing(
        "petmax_ro",
        "https://www.petmax.ro/asternut-litiera-nisip-silicat/nisip-silicat-perfect-lavanda.html",
        None,
        "Nisip Silicat Perfect cu lavanda 7,6 L",
    )
    assert result == "litter"


def test_animax_product_type_maps_to_food() -> None:
    result = categorize_listing(
        "animax_ro",
        "https://animax.ro/products/hrana-uscata-pentru-caini-hills-puppy-2-5kg",
        {"product_type": "Hrana uscata pentru caini", "brand": "Hill's"},
        "Hrana uscata pentru caini Hills Puppy 2.5kg",
    )
    assert result == "food"


def test_animax_product_type_maps_to_toy() -> None:
    result = categorize_listing(
        "animax_ro",
        "https://animax.ro/products/jucarie-pentru-caini-flamingo-minge-albastra",
        {"product_type": "Jucarie pentru caini"},
        "Jucarie pentru caini Flamingo Minge albastra pentru recompense 5cm",
    )
    assert result == "toy"


def test_animax_product_type_maps_to_litter() -> None:
    result = categorize_listing(
        "animax_ro",
        "https://animax.ro/products/nisip-pentru-litiera-enjoy-10-l",
        {"product_type": "Nisip pentru litiera"},
        "Nisip pentru litiera Enjoy 10 L",
    )
    assert result == "litter"


def test_animax_unmapped_product_type_falls_back_to_title() -> None:
    """A genuinely unmapped `product_type` is not guessed as food — falls back to the title
    keyword check, same as any other source with no reliable structured hit."""
    result = categorize_listing(
        "animax_ro",
        "https://animax.ro/products/zgarda-caine-julius-k9",
        {"product_type": "Something Never Seen Before"},
        "Zgarda caine Julius K9 - 75 cm",
    )
    assert result == "accessory"


def test_pentruanimale_has_no_structured_signal_and_defaults_to_food() -> None:
    """pentruanimale_ro carries no category field at all — verified this session that its entire
    collected catalogue has zero non-food keyword hits, so "nothing fired" resolving to "food"
    is evidence-backed for this source, not an assumption."""
    result = categorize_listing(
        "pentruanimale_ro",
        "https://www.pentruanimale.ro/royal-canin-medium-adult-hrana-uscata-caini/p",
        {"brand": "ROYAL CANIN"},
        "ROYAL CANIN Medium Adult, hrană uscată câini, 4kg",
    )
    assert result == "food"


def test_pentruanimale_accessory_keyword_still_overrides_the_food_default() -> None:
    result = categorize_listing(
        "pentruanimale_ro",
        "https://www.pentruanimale.ro/some-harness/p",
        None,
        "Zgarda caine cu clopotel, reglabila, Albastru",
    )
    assert result == "accessory"


def test_toy_keyword_detected_from_title() -> None:
    """petmax's real "jucarii-caini" url segment (2 rows only, per the module docstring) —
    "accesorii-pisici" would correctly take the structured-signal path instead, since that's the
    shop's own category and petmax genuinely cross-lists most toys there."""
    result = categorize_listing(
        "petmax_ro",
        "https://www.petmax.ro/jucarii-caini/jucarie-caini-minge.html",
        None,
        "Jucarie pentru caini Nobby Minge",
    )
    assert result == "toy"


def test_litter_keyword_detected_from_title() -> None:
    result = categorize_listing(
        "animax_ro",
        "https://animax.ro/products/nisip-necunoscut",
        {"product_type": "Something Never Seen Before"},
        "Nisip pentru litiera City Cat Clumping White Baby Powder 10L",
    )
    assert result == "litter"


def test_ham_harness_first_word_is_accessory_not_food() -> None:
    """Reuses attributes.py's own first-word-anchored "ham" guard — a harness title must not
    collide with the English flavour word "ham" (the meat), same reasoning as Convention 7."""
    result = categorize_listing(
        "pentruanimale_ro",
        "https://www.pentruanimale.ro/ham-caine/p",
        None,
        "Ham caine Julius K9 IDC Power - M 58-76 cm",
    )
    assert result == "accessory"


def test_ham_the_flavour_word_stays_food() -> None:
    result = categorize_listing(
        "pentruanimale_ro",
        "https://www.pentruanimale.ro/brit-care-cat-turkey-pate/p",
        None,
        "Brit Care Cat Turkey Pate With Ham 70 g",
    )
    assert result == "food"


def test_petmax_unmapped_url_segment_falls_back_to_title() -> None:
    result = categorize_listing(
        "petmax_ro",
        "https://www.petmax.ro/some-brand-new-category/product.html",
        None,
        "Jucarie pentru caini Kong Dog Bila plutitoare",
    )
    assert result == "toy"

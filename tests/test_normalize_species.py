"""Phase 3 finding 4 (2026-09-15 session) — species (dog/cat) signal."""

from __future__ import annotations

from pricepilot.normalize.species import classify_species


def test_petmax_url_segment_dog() -> None:
    url = "https://www.petmax.ro/hrana-uscata-caini/some-product.html"
    assert classify_species("petmax_ro", url, None, "irrelevant title", "food") == "dog"


def test_petmax_url_segment_cat() -> None:
    url = "https://www.petmax.ro/hrana-uscata-pisici/some-product.html"
    assert classify_species("petmax_ro", url, None, "irrelevant title", "food") == "cat"


def test_animax_product_type_dog() -> None:
    payload = {"product_type": "Hrana uscata pentru caini"}
    assert classify_species("animax_ro", "https://animax.ro/x", payload, "t", "food") == "dog"


def test_animax_product_type_cat() -> None:
    payload = {"product_type": "Hrana uscata pentru pisici"}
    assert classify_species("animax_ro", "https://animax.ro/x", payload, "t", "food") == "cat"


def test_litter_is_always_cat() -> None:
    """This catalogue's litter products are exclusively for cats (checked against the full
    in-scope population, 2026-09-15 session) -- resolved before any per-source signal."""
    assert (
        classify_species(
            "petmax_ro", "https://www.petmax.ro/hrana-uscata-caini/x", None, "t", "litter"
        )
        == "cat"
    )


def test_pentruanimale_title_fallback_dog() -> None:
    title = "ROYAL CANIN Medium Starter Mother and Babydog, hrana uscata caini, 4kg"
    assert classify_species("pentruanimale_ro", "https://x/p", {"ean": "1"}, title, "food") == "dog"


def test_pentruanimale_title_fallback_cat() -> None:
    title = "ROYAL CANIN Digestive Care Adult, hrana uscata pisici, confort digestiv, 10kg"
    assert classify_species("pentruanimale_ro", "https://x/p", {"ean": "1"}, title, "food") == "cat"


def test_hills_canine_not_confused_with_royal_canin_brand() -> None:
    """ "Canine" (Hill's own line-name word) must resolve as a dog word without the bare "canin"
    stem colliding with the "Royal Canin" brand name on CAT products (a real, checked false
    positive: 282 titles initially flagged as both-species turned out to be exactly this)."""
    title = "Hill's SP Canine Adult Small & Miniature Light Pui, 6 Kg"
    assert classify_species("pentruanimale_ro", "https://x/p", {"ean": "1"}, title, "food") == "dog"

    cat_title = "Royal Canin Feline Sterilised 37, 400 g"
    assert (
        classify_species(
            "petmax_ro", "https://www.petmax.ro/hrana-uscata-pisici/x.html", None, cat_title, "food"
        )
        == "cat"
    )


def test_dual_species_title_is_unknown_not_guessed() -> None:
    title = "VETRI SCIENCE DevCor + Mobility Pro, supliment pentru articulatii caini si pisici"
    assert (
        classify_species("pentruanimale_ro", "https://x/p", {"ean": "1"}, title, "accessory")
        is None
    )


def test_no_species_word_is_unknown_not_guessed() -> None:
    title = "Os Presat Trixie 22 cm, 230 g"
    assert classify_species("pentruanimale_ro", "https://x/p", {"ean": "1"}, title, "food") is None

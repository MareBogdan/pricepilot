"""EN/RO flavour extraction — CLAUDE.md §7's eight named pairs, plus three extended from real
title data (fish, liver, game)."""

from __future__ import annotations

import pytest

from pricepilot.normalize.flavour import extract_flavour


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Royal Canin Mini Adult cu Pui 8 kg", "chicken"),
        ("Calibra Dog Life Junior Small Breed Chicken 6 kg", "chicken"),
        ("Petkult Sensitive Miel & Orez 1 kg", "lamb"),
        ("Calibra Dog Life Adult Small Fresh Beef 6 kg", "beef"),
        ("AMANOVA Sterilised, Somon, hrana uscata", "salmon"),
        ("Taste of the Wild Pacific Stream Puppy Formula Salmon 12.2 kg", "salmon"),
        ("ISEGRIM, XS-XL, Curcan, plic hrana umeda", "turkey"),
        ("Wolfpack Sausage Somon 400g", "salmon"),
        ("Recompensa pentru caini Wolfpack Sausage Rata 400g", "duck"),
        ("Petkult Sensitive Care Adult Small Breed Miel si orez brun 1 kg", "lamb"),
        ("Inaba Ciao Dashi Delights Ton si Fulgi de Bonito 70g", "tuna"),
        ("MERA Cat's Nature, Miel, hrana uscata fara cereale pisici, 400g", "lamb"),
        ("Purina Pro Plan Delicate Digestion, Peste, hrana umeda", "fish"),
        ("Hill's PD Boli Renale K/D Pui 85g", "chicken"),
        ("Dolina Noteci Premium Vanat 800gr", "game"),
    ],
)
def test_known_flavour_words(title: str, expected: str) -> None:
    assert extract_flavour(title) == expected


def test_no_flavour_word_is_none() -> None:
    assert extract_flavour("Jucarie pentru pisici Kong Cat Bila plutitoare") is None


def test_multiple_flavours_are_joined_not_dropped() -> None:
    """ "cu Iepure si Vita" states two proteins — losing one would be a real information loss,
    not a simplification."""
    result = extract_flavour("MY LOVE Multipack Hrana umeda pentru pisici, cu Iepure si Vita 4x85g")
    assert result == "rabbit+beef"


def test_duplicate_flavour_words_are_not_repeated() -> None:
    result = extract_flavour("Pui cu gust de Pui, aroma naturala de Pui")
    assert result == "chicken"

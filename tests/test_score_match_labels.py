"""Precision scorer for the s3b labels (pure logic; computed expected values)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from score_match_labels import score


def label(key: str, title: str, verdict: str, reason: str = "") -> dict[str, str]:
    return {"link_key": key, "competitor_title": title, "label": verdict, "reason": reason}


LABELS = [
    label("1:a", "A", "YES"),
    label("2:a", "B", "YES"),
    label("3:a", "C", "NO", "GRAMAJ: 2 kg vs 4 kg"),
    label("4:a", "D", "NO", "FLAVOUR: chicken vs beef"),
]


def test_precision_and_wrong_gramaj_over_all_labels() -> None:
    result = score(LABELS, None)
    assert result["links_scored"] == 4
    assert result["precision"] == 0.5
    assert result["wrong_gramaj_false_positives"] == 1
    assert result["wrong_gramaj_rate"] == 0.25


def test_links_join_on_title_so_a_reused_link_key_is_unlabelled() -> None:
    links = [
        {"link_key": "1:a", "competitor_title": "A"},
        {"link_key": "4:a", "competitor_title": "A DIFFERENT LISTING"},  # same slot, new listing
    ]
    result = score(LABELS, links)
    assert result["links_scored"] == 1 and result["precision"] == 1.0
    assert result["unlabelled_links"] == ["4:a"]

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


def test_committed_labels_reproduce_the_recorded_precision_figures() -> None:
    """The numbers quoted in gate-s3b.md, recomputed from the committed CSVs (pre-guard 22/28 and
    post-guard 23/25 with the merged post-guard labels). A silent label edit fails this."""
    from score_match_labels import PHASE5, read

    pre = read(PHASE5 / "match-verification-labels.csv")
    post_extra = read(PHASE5 / "match-verification-labels-postguard.csv")
    queue = read(PHASE5 / "match-verification-queue.csv")
    r_pre = score(pre, None)
    assert (r_pre["links_scored"], r_pre["yes"]) == (28, 22)
    r_post = score(pre + post_extra, queue)
    assert (r_post["links_scored"], r_post["yes"], r_post["unlabelled_links"]) == (25, 23, [])
    assert r_post["wrong_gramaj_false_positives"] == 0

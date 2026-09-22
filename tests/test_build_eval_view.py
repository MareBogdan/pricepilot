"""Tests for scripts/build_eval_view.py's committed output, docs/learned/phase3-eval-view.json
(DECISIONS.md ADR-0028 addendum #16). Reads the committed file directly, like
tests/test_annotation_split.py does for the split file -- these tests exist to catch the view
drifting out of sync with the frozen queue or the labels file, not to re-derive it.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_label_rule_consistency as clc  # noqa: E402

EVAL_VIEW_JSON = ROOT / "docs" / "learned" / "phase3-eval-view.json"
QUEUE_JSON = ROOT / "docs" / "learned" / "phase3-annotation-queue.json"
SPLIT_JSON = ROOT / "docs" / "learned" / "phase3-annotation-split.json"
LABELS_JSON = ROOT / "docs" / "learned" / "phase3-labels.json"


def _load_view() -> dict:
    return json.loads(EVAL_VIEW_JSON.read_text(encoding="utf-8"))


def _load_queue_pairs_by_occ() -> dict[str, dict]:
    queue = json.loads(QUEUE_JSON.read_text(encoding="utf-8"))["pairs"]
    return dict(zip(clc.derive_occurrence_ids(queue), queue, strict=True))


def test_test_distinct_pairs_is_287() -> None:
    view = _load_view()
    test_pairs = {e["pair_id"] for e in view["entries"] if e["split"] == "test"}
    assert len(test_pairs) == 287


def test_train_val_distinct_pairs_is_672() -> None:
    view = _load_view()
    train_val_pairs = {e["pair_id"] for e in view["entries"] if e["split"] == "train_val"}
    assert len(train_val_pairs) == 672


def test_zero_pair_id_overlap_between_splits() -> None:
    """`build_entries()` groups by pair_id globally and emits one entry per pair_id, so this is
    guaranteed by construction on the view alone -- cross-checked here against the split file
    (an independent source, not read by build_eval_view.py) so the test can actually fail if a
    future queue/split ever placed a repeated pair's two occurrences in different splits."""
    view = _load_view()
    test_pairs = {e["pair_id"] for e in view["entries"] if e["split"] == "test"}
    train_val_pairs = {e["pair_id"] for e in view["entries"] if e["split"] == "train_val"}
    assert not (test_pairs & train_val_pairs)

    split = json.loads(SPLIT_JSON.read_text(encoding="utf-8"))
    pairs_by_occ = _load_queue_pairs_by_occ()
    split_of_pair_id: dict[str, set[str]] = {}
    for occ_id, assignment in split["assignments"].items():
        split_of_pair_id.setdefault(pairs_by_occ[occ_id]["pair_id"], set()).add(assignment["split"])
    disagreeing = {pid: s for pid, s in split_of_pair_id.items() if len(s) != 1}
    assert not disagreeing, f"pair_id(s) whose occurrences disagree on split: {disagreeing}"


def test_zero_listing_content_hash_overlap_between_splits() -> None:
    """Verified independently: 351 TEST listings vs 802 TRAIN_VAL, intersection 0
    (ADR-0028 addendum #16)."""
    view = _load_view()
    pairs_by_occ = _load_queue_pairs_by_occ()

    def hashes_for(split: str) -> set[str]:
        result: set[str] = set()
        for e in view["entries"]:
            if e["split"] != split:
                continue
            pair = pairs_by_occ[e["first_occurrence_id"]]
            result.add(pair["left"]["content_hash"])
            result.add(pair["right"]["content_hash"])
        return result

    test_hashes = hashes_for("test")
    train_val_hashes = hashes_for("train_val")
    assert len(test_hashes) == 351
    assert len(train_val_hashes) == 802
    assert not (test_hashes & train_val_hashes)


def test_every_repeated_pair_resolves_to_exactly_one_entry_attributed_to_proxy_key_collision() -> (
    None
):
    view = _load_view()
    repeat_entries = [e for e in view["entries"] if e["is_repeat"]]
    assert len(repeat_entries) == 38
    assert all(e["tier"] == "proxy_key_collision" for e in repeat_entries)
    # exactly one entry per repeated pair_id -- no duplicate rows for a repeat
    pair_ids = [e["pair_id"] for e in repeat_entries]
    assert len(pair_ids) == len(set(pair_ids))


def test_scored_matches_label_not_s_for_every_entry() -> None:
    view = _load_view()
    for e in view["entries"]:
        assert e["scored"] == (e["label"] != "S"), e["pair_id"]


def test_view_labels_sha256_matches_current_labels_file() -> None:
    """A stale view (built against an older phase3-labels.json) must fail loudly here, not be
    silently trusted by a downstream scoring script."""
    view = _load_view()
    actual = hashlib.sha256(LABELS_JSON.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert view["labels_sha256_lf"] == actual, (
        "docs/learned/phase3-eval-view.json is stale -- re-run scripts/build_eval_view.py"
    )


def test_view_entry_count_is_959() -> None:
    view = _load_view()
    assert len(view["entries"]) == 959


def test_repeat_resolution_uses_display_order_not_file_order() -> None:
    """Regression pin (reviewer finding, ADR-0028 addendum #16): if build_entries() ever regressed
    to `first_occ = occ_ids[0]` (file order) instead of the repeat lookup's display-first
    occurrence, entry/repeat counts and tier attribution would all stay unchanged -- only the
    LABEL of these three pairs, which disagree between their two occurrences, would silently flip.
    Pinned directly against the repeat-first-occurrence lookup, an independent source.
    """
    view = _load_view()
    entries_by_pair = {e["pair_id"]: e for e in view["entries"]}
    lookup = json.loads(
        (ROOT / "docs" / "learned" / "phase3-repeat-first-occurrence.json").read_text(
            encoding="utf-8"
        )
    )["lookup"]
    labels = json.loads(LABELS_JSON.read_text(encoding="utf-8"))["decisions"]

    disagreeing = [
        pid
        for pid, e in lookup.items()
        if labels[e["first_occurrence_id"]]["label"] != labels[e["second_occurrence_id"]]["label"]
    ]
    assert len(disagreeing) == 3, (
        f"expected exactly 3 repeats with disagreeing labels across occurrences, got "
        f"{len(disagreeing)}: {disagreeing}"
    )
    for pair_id in disagreeing:
        first_occ = lookup[pair_id]["first_occurrence_id"]
        expected_label = labels[first_occ]["label"]
        entry = entries_by_pair[pair_id]
        assert entry["first_occurrence_id"] == first_occ
        assert entry["label"] == expected_label, (
            f"{pair_id}: view resolved to {entry['label']!r}, expected the DISPLAY-first "
            f"occurrence {first_occ!r}'s label {expected_label!r}"
        )


def test_view_frozen_flag_matches_test_labels_frozen_state() -> None:
    view = _load_view()
    text = (ROOT / "tests" / "test_labels_frozen.py").read_text(encoding="utf-8")
    assert view["frozen"] == ('FROZEN_LABELS_SHA256 = "UNFROZEN"' not in text)

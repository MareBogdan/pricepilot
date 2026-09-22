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

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_eval_view as bev  # noqa: E402
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


def test_repeat_resolution_consistent_with_lookup_on_real_data() -> None:
    """Consistency check against the real committed files, NOT a regression guard on its own
    (ADR-0028 addendum #17 correction to addendum #16's overclaim). In the real
    `phase3-labels.json`, `decisions` happens to already be stored in display order for every one
    of the 38 repeats -- verified: `occ_ids[0]` (file order) equals the lookup's
    `first_occurrence_id` for all 38, including the 15 whose display-first is the `_1`
    occurrence. So file order and display order are NOT independent on this file, and a
    regression to `first_occ = occ_ids[0]` would produce byte-identical output here -- this test
    would not catch it. See `test_repeat_resolution_uses_display_order_not_file_order_synthetic`
    below for the actual regression guard, which constructs a case where the two orders diverge.
    """
    view = _load_view()
    entries_by_pair = {e["pair_id"]: e for e in view["entries"]}
    lookup = json.loads(
        (ROOT / "docs" / "learned" / "phase3-repeat-first-occurrence.json").read_text(
            encoding="utf-8"
        )
    )["lookup"]
    labels = json.loads(LABELS_JSON.read_text(encoding="utf-8"))["decisions"]

    assert len(lookup) == 38
    for pair_id, e in lookup.items():
        entry = entries_by_pair[pair_id]
        assert entry["first_occurrence_id"] == e["first_occurrence_id"], (
            f"{pair_id}: view resolved first_occurrence_id={entry['first_occurrence_id']!r}, "
            f"expected the DISPLAY-first occurrence {e['first_occurrence_id']!r} (file-order "
            f"fallback would pick a different occurrence whenever display order != file order)"
        )
        assert entry["label"] == labels[e["first_occurrence_id"]]["label"]

    disagreeing = [
        pid
        for pid, e in lookup.items()
        if labels[e["first_occurrence_id"]]["label"] != labels[e["second_occurrence_id"]]["label"]
    ]
    for pair_id in disagreeing:
        first_occ = lookup[pair_id]["first_occurrence_id"]
        expected_label = labels[first_occ]["label"]
        entry = entries_by_pair[pair_id]
        assert entry["label"] == expected_label, (
            f"{pair_id}: view resolved to {entry['label']!r}, expected the DISPLAY-first "
            f"occurrence {first_occ!r}'s label {expected_label!r}"
        )


def test_repeat_resolution_uses_display_order_not_file_order_synthetic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The actual regression guard (reviewer finding on ADR-0028 addendum #16's original version,
    fixed here): constructs a repeat whose two occurrences are stored FILE-first-second in the
    OPPOSITE order to their DISPLAY-first-second designation, so `first_occ = occ_ids[0]` (file
    order, the bug) and `first_occ = repeat_lookup[pair_id]["first_occurrence_id"]` (display
    order, correct) pick different occurrences with different labels -- something the real
    committed data can never exercise (see the test above).
    """
    learned = tmp_path / "docs" / "learned"
    learned.mkdir(parents=True)

    queue_path = learned / "queue.json"
    queue_bytes = json.dumps(
        {"pairs": [{"pair_id": "SYN_REPEAT"}, {"pair_id": "SYN_REPEAT"}]}, indent=1
    ).encode("utf-8")
    queue_path.write_bytes(queue_bytes)

    labels_path = learned / "labels.json"
    # FILE order: SYN_REPEAT_1 first, SYN_REPEAT_0 second -- the OPPOSITE of display order below.
    labels_path.write_text(
        json.dumps(
            {
                "decisions": {
                    "SYN_REPEAT_1": {"pair_id": "SYN_REPEAT", "label": "M", "split": "test"},
                    "SYN_REPEAT_0": {"pair_id": "SYN_REPEAT", "label": "N", "split": "test"},
                }
            },
            indent=1,
        ),
        encoding="utf-8",
    )

    lookup_path = learned / "repeat_lookup.json"
    lookup_path.write_text(
        json.dumps(
            {
                "lookup": {
                    "SYN_REPEAT": {
                        "first_occurrence_id": "SYN_REPEAT_0",
                        "second_occurrence_id": "SYN_REPEAT_1",
                    }
                }
            },
            indent=1,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(bev, "LABELS_JSON", labels_path)
    monkeypatch.setattr(bev, "REPEAT_FIRST_OCCURRENCE_JSON", lookup_path)
    monkeypatch.setattr(clc, "QUEUE_JSON", queue_path)
    monkeypatch.setattr(clc, "FROZEN_QUEUE_SHA256", clc.sha256_lf(queue_bytes))

    entries = bev.build_entries()
    assert len(entries) == 1
    entry = entries[0]
    assert entry["first_occurrence_id"] == "SYN_REPEAT_0", (
        "resolved to the FILE-first occurrence (SYN_REPEAT_1) instead of the DISPLAY-first one "
        "(SYN_REPEAT_0) -- this is exactly the occ_ids[0] file-order regression"
    )
    assert entry["label"] == "N", (
        f"resolved label {entry['label']!r} came from the FILE-first occurrence's label (M), "
        "not the DISPLAY-first occurrence's label (N) -- occ_ids[0] file-order regression"
    )
    assert entry["tier"] == "proxy_key_collision"
    assert entry["is_repeat"] is True


def test_view_frozen_flag_matches_test_labels_frozen_state() -> None:
    """Bug fix (Phase 3 item 5 harness session): the original version of this test checked
    whether the literal string `FROZEN_LABELS_SHA256 = "UNFROZEN"` appeared ANYWHERE in
    tests/test_labels_frozen.py's full text -- but that file's own test fixtures embed that exact
    string as indented Python source (inside `t.write_text(...)` calls) to test write_hash()'s
    UNFROZEN case, so the substring is always present regardless of the real constant's current
    value. The check therefore always evaluated to the same thing and produced a false pass: with
    the dataset genuinely frozen and the constant reading the real hash, the naive check still
    computed `not in text -> False` (the fixtures keep the string present) and matched a STALE
    `view["frozen"] == False` in the committed file -- exactly the drift this test exists to
    catch, silently missed. Fixed by delegating to build_eval_view.py's own anchored parser
    (`^FROZEN_LABELS_SHA256 = "..."`, MULTILINE -- only matches the real top-level constant, never
    an indented fixture line) instead of re-implementing a fragile substring check here."""
    view = _load_view()
    assert view["frozen"] == bev._frozen_state()


def test_view_records_the_frozen_hash_it_saw() -> None:
    """`frozen_labels_sha256` must be the CURRENT, live value of the
    `FROZEN_LABELS_SHA256` constant, not merely a boolean -- so a reader (or a downstream scoring
    script) can confirm which exact freeze this view was generated against without cross-checking
    a second file by hand."""
    view = _load_view()
    assert view["frozen_labels_sha256"] == bev._frozen_marker()


def test_frozen_marker_ignores_an_indented_fixture_line_even_when_it_precedes_the_real_constant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression guard for the anchor itself (reviewer finding on the fix above): the real
    committed test_labels_frozen.py happens to have its constant BEFORE its fixture lines, so
    `_frozen_marker()` would return the right answer even completely unanchored, by luck of file
    order. This test constructs the file the other way around -- an indented fixture-shaped line
    FIRST, the real column-0 constant SECOND -- so a regression that drops the `^`/MULTILINE
    anchor (or otherwise stops requiring column 0) would pick the fixture's "UNFROZEN" and fail
    this test, even though it would still pass against the real repo file."""
    real_hash = "cd" * 32
    synthetic = tmp_path / "test_labels_frozen.py"
    synthetic.write_text(
        '    t.write_text(\'FROZEN_LABELS_SHA256 = "UNFROZEN"\\n\', encoding="utf-8")\n'
        f'FROZEN_LABELS_SHA256 = "{real_hash}"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(bev, "TEST_LABELS_FROZEN_FILE", synthetic)
    assert bev._frozen_marker() == real_hash
    assert bev._frozen_state() is True

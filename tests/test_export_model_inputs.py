"""Tests for scripts/export_model_inputs.py's committed output (ADR-0028 addendum #19). The
leakage guard on the TEST file is the actual point of this module -- these tests try to verify,
independently of the script's own internal guard, that no label information reaches
docs/learned/model-inputs/phase3-inputs-test.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import export_model_inputs as emi  # noqa: E402

TEST_FILE = ROOT / "docs" / "learned" / "model-inputs" / "phase3-inputs-test.json"
TRAIN_VAL_FILE = ROOT / "docs" / "learned" / "model-inputs" / "phase3-inputs-train-val.json"
EVAL_VIEW_FILE = ROOT / "docs" / "learned" / "phase3-eval-view.json"
SPLIT_FILE = ROOT / "docs" / "learned" / "phase3-train-val-split.json"


def _load_test() -> dict[str, Any]:
    return json.loads(TEST_FILE.read_text(encoding="utf-8"))


def _load_train_val() -> dict[str, Any]:
    return json.loads(TRAIN_VAL_FILE.read_text(encoding="utf-8"))


def _all_leaf_values(payload: Any) -> list[Any]:
    if isinstance(payload, dict):
        out: list[Any] = []
        for v in payload.values():
            out.extend(_all_leaf_values(v))
        return out
    if isinstance(payload, list):
        out = []
        for item in payload:
            out.extend(_all_leaf_values(item))
        return out
    return [payload]


def _all_keys(payload: Any) -> set[str]:
    if isinstance(payload, dict):
        keys = set(payload.keys())
        for v in payload.values():
            keys |= _all_keys(v)
        return keys
    if isinstance(payload, list):
        keys: set[str] = set()
        for item in payload:
            keys |= _all_keys(item)
        return keys
    return set()


def test_test_file_has_exactly_287_pairs_each_with_only_pair_id_text_a_text_b() -> None:
    data = _load_test()
    assert len(data["pairs"]) == 287
    for pair in data["pairs"]:
        assert set(pair.keys()) == {"pair_id", "text_a", "text_b"}


def test_test_file_has_no_forbidden_key_anywhere_independent_check() -> None:
    """Re-implemented independently from the script's own _assert_test_payload_has_no_leakage --
    a bug in that function's own logic wouldn't be caught by re-calling it, so this test walks
    the committed JSON itself with separate code."""
    data = _load_test()
    forbidden = {"label", "tier", "split", "y", "target"}
    found = {k.lower() for k in _all_keys(data)} & forbidden
    assert not found, f"forbidden key(s) present in TEST export: {found}"


def test_test_file_has_no_value_exactly_equal_to_a_label_letter() -> None:
    data = _load_test()
    values = _all_leaf_values(data)
    assert "M" not in values
    assert "N" not in values
    assert "S" not in values


def test_test_file_pairs_are_pair_id_sorted_not_label_grouped() -> None:
    """Order is itself a channel a label could leak through (e.g. all M pairs first). Pinning
    that the file's order is exactly alphabetical by pair_id -- independent of any label -- rules
    this out structurally, not just by spot-checking a few pairs."""
    data = _load_test()
    pair_ids = [p["pair_id"] for p in data["pairs"]]
    assert pair_ids == sorted(pair_ids)


def test_test_file_pair_ids_cross_reference_the_eval_view() -> None:
    """Confirms the set of exported TEST pair_ids matches the eval view's TEST pair_ids exactly
    -- no pair silently dropped or added, which could itself be a subtle leak if done
    label-dependently."""
    data = _load_test()
    view = json.loads(EVAL_VIEW_FILE.read_text(encoding="utf-8"))
    real_labels = {e["pair_id"]: e["label"] for e in view["entries"] if e["split"] == "test"}
    exported_ids = {p["pair_id"] for p in data["pairs"]}
    assert exported_ids == set(real_labels.keys())


def test_test_file_text_reconstructs_byte_for_byte_from_the_frozen_queue_for_all_287_pairs() -> (
    None
):
    """A reviewer finding: the only prior reconstruction check covered pairs[0] of TRAIN_VAL, not
    a single one of the 287 TEST rows -- the rows that actually leave this machine. Rebuilds
    text_a/text_b for every TEST pair from `pricepilot.matching.pair_text.build_pair_text` fed by
    the frozen annotation queue (a source that carries no labels at all), and asserts byte-for-byte
    equality against the committed export. This is the one check in this file that is genuinely
    independent of what the label happens to be, rather than independent only in its traversal
    code while sharing the leakage guard's own forbidden-name/forbidden-value policy."""
    from pricepilot.matching.pair_text import build_pair_text

    data = _load_test()
    view = json.loads(EVAL_VIEW_FILE.read_text(encoding="utf-8"))
    listings = emi._listings_by_occurrence_id()
    first_occ_by_pair = {
        e["pair_id"]: e["first_occurrence_id"] for e in view["entries"] if e["split"] == "test"
    }
    for pair in data["pairs"]:
        left, right = listings[first_occ_by_pair[pair["pair_id"]]]
        expected_a, expected_b = build_pair_text(left, right)
        assert pair["text_a"] == expected_a
        assert pair["text_b"] == expected_b


def test_test_file_text_has_no_label_shaped_substring() -> None:
    """A reviewer finding: the leakage guard's value check is exact-equality against {"M","N","S"},
    which would miss a label embedded as a substring (e.g. "... | flavour: tuna | label: M"). Scans
    every TEST text_a/text_b for the literal tokens a leak would introduce."""
    data = _load_test()
    forbidden_substrings = ("label:", "tier:", "split:", "y_true", "target:")
    for pair in data["pairs"]:
        for field in ("text_a", "text_b"):
            lowered = pair[field].lower()
            for token in forbidden_substrings:
                assert token not in lowered, f"{pair['pair_id']}.{field} contains {token!r}"


def test_committed_exports_are_not_stale_relative_to_a_fresh_rebuild() -> None:
    """A reviewer finding: every other test in this file reads the committed JSON only -- none of
    them rebuild the payload and compare, so an upstream change (e.g. pair_text.py edited without
    bumping PAIR_TEXT_VERSION) could leave the committed files describing a stale text format
    while every test here stays green. Rebuilds both payloads via the script's own functions
    (writing nothing) and compares to the committed files, ignoring only `generated_at`."""
    view = json.loads(EVAL_VIEW_FILE.read_text(encoding="utf-8"))

    fresh_test = emi.build_test_payload(view)
    committed_test = _load_test()
    fresh_test.pop("generated_at")
    committed_test.pop("generated_at")
    assert fresh_test == committed_test

    fresh_train_val = emi.build_train_val_payload(view)
    committed_train_val = _load_train_val()
    fresh_train_val.pop("generated_at")
    committed_train_val.pop("generated_at")
    assert fresh_train_val == committed_train_val


def test_train_val_file_has_672_pairs_with_real_labels_and_a_side_assignment() -> None:
    data = _load_train_val()
    assert len(data["pairs"]) == 672
    for pair in data["pairs"]:
        assert set(pair.keys()) == {
            "pair_id",
            "text_a",
            "text_b",
            "label",
            "scored",
            "train_or_val",
        }
        assert pair["label"] in ("M", "N", "S")
        assert pair["train_or_val"] in ("train", "val")
        assert pair["scored"] == (pair["label"] != "S")


def test_s_labelled_train_val_pairs_carry_scored_false_not_dropped() -> None:
    """build_eval_view.py's rule 4 (S stays in the file, never dropped silently, never counted
    in a metric) must survive the export -- a reviewer finding: an earlier version of this export
    wrote `label: "S"` with no `scored` flag, so a notebook building `y = 1 if label == "M" else
    0` would silently treat every S pair as a hard negative instead of excluding it."""
    data = _load_train_val()
    s_pairs = [p for p in data["pairs"] if p["label"] == "S"]
    assert len(s_pairs) == 6
    assert all(p["scored"] is False for p in s_pairs)
    non_s_pairs = [p for p in data["pairs"] if p["label"] != "S"]
    assert all(p["scored"] is True for p in non_s_pairs)


def test_train_val_side_counts_match_the_split_file() -> None:
    data = _load_train_val()
    split = json.loads(SPLIT_FILE.read_text(encoding="utf-8"))
    train_count = sum(1 for p in data["pairs"] if p["train_or_val"] == "train")
    val_count = sum(1 for p in data["pairs"] if p["train_or_val"] == "val")
    assert train_count == split["train"]["pair_count"]
    assert val_count == split["val"]["pair_count"]
    assert {p["pair_id"] for p in data["pairs"] if p["train_or_val"] == "train"} == set(
        split["train"]["pair_ids"]
    )
    assert {p["pair_id"] for p in data["pairs"] if p["train_or_val"] == "val"} == set(
        split["val"]["pair_ids"]
    )


def test_both_files_record_frozen_hash_and_pair_text_version() -> None:
    from pricepilot.matching.pair_text import PAIR_TEXT_VERSION

    live_marker = emi._frozen_marker()
    test_data = _load_test()
    train_val_data = _load_train_val()
    for data in (test_data, train_val_data):
        assert data["frozen_labels_sha256"] == live_marker
        assert data["pair_text_version"] == PAIR_TEXT_VERSION


def test_text_matches_build_pair_text_exactly_for_a_spot_checked_pair() -> None:
    data = _load_train_val()
    pair = data["pairs"][0]
    listings = emi._listings_by_occurrence_id()
    view = json.loads(EVAL_VIEW_FILE.read_text(encoding="utf-8"))
    entry = next(e for e in view["entries"] if e["pair_id"] == pair["pair_id"])
    left, right = listings[entry["first_occurrence_id"]]
    from pricepilot.matching.pair_text import build_pair_text

    expected_a, expected_b = build_pair_text(left, right)
    assert pair["text_a"] == expected_a
    assert pair["text_b"] == expected_b


def test_leakage_guard_function_rejects_a_forbidden_key() -> None:
    poisoned = {"pairs": [{"pair_id": "x", "text_a": "a", "text_b": "b", "label": "M"}]}
    with pytest.raises(SystemExit, match="forbidden key"):
        emi._assert_test_payload_has_no_leakage(poisoned)


def test_leakage_guard_function_rejects_a_bare_label_letter_value() -> None:
    poisoned = {"pairs": [{"pair_id": "x", "text_a": "a", "text_b": "S"}]}
    with pytest.raises(SystemExit, match="label letter"):
        emi._assert_test_payload_has_no_leakage(poisoned)


def test_leakage_guard_function_accepts_a_clean_payload() -> None:
    clean = {"pairs": [{"pair_id": "x", "text_a": "brand: royal canin", "text_b": "brand: brit"}]}
    emi._assert_test_payload_has_no_leakage(clean)  # must not raise


def test_leakage_guard_catches_nested_forbidden_key() -> None:
    poisoned = {"meta": {"stats": {"split": "test"}}, "pairs": []}
    with pytest.raises(SystemExit, match="forbidden key"):
        emi._assert_test_payload_has_no_leakage(poisoned)


def test_build_train_val_payload_refuses_on_split_hash_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_split = tmp_path / "split.json"
    fake_split.write_text(
        json.dumps(
            {
                "frozen_labels_sha256": "deadbeef" * 8,
                "seed": 1,
                "train": {"pair_ids": []},
                "val": {"pair_ids": []},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(emi, "TRAIN_VAL_SPLIT_JSON", fake_split)
    view = json.loads(EVAL_VIEW_FILE.read_text(encoding="utf-8"))
    with pytest.raises(SystemExit, match="REFUSING TO RUN"):
        emi.build_train_val_payload(view)


def test_build_train_val_payload_refuses_on_pair_text_version_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    view = json.loads(EVAL_VIEW_FILE.read_text(encoding="utf-8"))
    real_split = json.loads(SPLIT_FILE.read_text(encoding="utf-8"))
    fake_split = tmp_path / "split.json"
    fake_split.write_text(
        json.dumps({**real_split, "pair_text_version": "some-other-version"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(emi, "TRAIN_VAL_SPLIT_JSON", fake_split)
    with pytest.raises(SystemExit, match="pair_text_version"):
        emi.build_train_val_payload(view)

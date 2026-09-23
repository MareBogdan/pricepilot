"""Tests for scripts/select_threshold.py (CLAUDE.md §7 item 5; ADR-0028 addendum #19).

This is the ONE place in the harness a threshold may be chosen, and the ONE place that must never
see a TEST pair_id while doing it. Every test that runs the script end to end monkeypatches
scripts.select_threshold.RESULTS_DIR to a tmp_path, so a test run never writes into the real
docs/learned/results/<model-id>-threshold-selection.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import select_threshold as st  # noqa: E402

EVAL_VIEW_FILE = ROOT / "docs" / "learned" / "phase3-eval-view.json"


def _real_view() -> dict[str, Any]:
    return json.loads(EVAL_VIEW_FILE.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _isolate_results_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    results_dir = tmp_path / "results"
    monkeypatch.setattr(st, "RESULTS_DIR", results_dir)
    return results_dir


# ---------------------------------------------------------------------------
# The core leakage guard: TEST pair_ids must never be usable here.
# ---------------------------------------------------------------------------


def test_refuses_if_any_test_pair_id_present_in_predictions() -> None:
    view = _real_view()
    test_pair_id = next(e["pair_id"] for e in view["entries"] if e["split"] == "test")
    predictions = {test_pair_id: 0.9}
    with pytest.raises(SystemExit, match="TEST pair_id"):
        st._assert_no_test_pair_ids(predictions, view)


def test_accepts_predictions_with_only_train_val_pair_ids() -> None:
    view = _real_view()
    train_val_id = next(e["pair_id"] for e in view["entries"] if e["split"] == "train_val")
    predictions = {train_val_id: 0.5}
    st._assert_no_test_pair_ids(predictions, view)  # must not raise


def test_val_labels_count_matches_split_bookkeeping() -> None:
    view = _real_view()
    labels = st._val_labels(view)
    split = json.loads(st.SPLIT_JSON.read_text(encoding="utf-8"))
    assert len(labels) == split["val"]["pair_count"] - split["val"]["label_counts"]["S"]
    assert set(labels.values()) <= {"M", "N"}


def test_missing_validation_pair_id_refused() -> None:
    view = _real_view()
    labels = st._val_labels(view)
    incomplete_predictions = {pid: 0.5 for pid in list(labels)[:-1]}  # drop one
    with pytest.raises(SystemExit, match="missing"):
        st.select_threshold(incomplete_predictions, labels)


# ---------------------------------------------------------------------------
# Threshold selection correctness, on a small hand-built scenario.
# ---------------------------------------------------------------------------


def test_select_threshold_picks_a_clean_separating_threshold() -> None:
    labels = {"p1": "M", "p2": "M", "p3": "N", "p4": "N"}
    predictions = {"p1": 0.9, "p2": 0.8, "p3": 0.3, "p4": 0.2}
    best, sweep = st.select_threshold(predictions, labels)
    assert 0.3 < best <= 0.8
    assert len(sweep) == 101
    best_row = next(r for r in sweep if r["threshold"] == best)
    assert best_row["f1"] == 1.0
    assert best_row["tp"] == 2
    assert best_row["fp"] == 0
    assert best_row["fn"] == 0


def test_select_threshold_picks_the_midpoint_of_the_widest_tying_plateau_not_its_edge() -> None:
    """A reviewer finding: `max(sweep, key=...)` picks the FIRST maximum, i.e. the lowest
    threshold on an F1 plateau -- here 0.31, one grid step above the highest validation negative
    (0.3). That is the most fragile point of the whole 0.31..0.80 tying range: any TEST negative
    scoring 0.31-0.80 would become a false positive at threshold=0.31, where the plateau's
    midpoint (0.56) absorbs the same range with more margin on both sides."""
    labels = {"p1": "M", "p2": "M", "p3": "N", "p4": "N"}
    predictions = {"p1": 0.9, "p2": 0.8, "p3": 0.3, "p4": 0.2}
    best, sweep = st.select_threshold(predictions, labels)
    tying = [r["threshold"] for r in sweep if r["f1"] == 1.0]
    assert min(tying) == 0.31
    assert max(tying) == 0.8
    assert best == 0.56  # midpoint of [0.31, 0.80], not the plateau's fragile low edge (0.31)


def test_select_threshold_deterministic_for_same_input() -> None:
    labels = {"p1": "M", "p2": "N", "p3": "M", "p4": "N"}
    predictions = {"p1": 0.7, "p2": 0.6, "p3": 0.55, "p4": 0.2}
    best_a, sweep_a = st.select_threshold(predictions, labels)
    best_b, sweep_b = st.select_threshold(predictions, labels)
    assert best_a == best_b
    assert sweep_a == sweep_b


def test_perfect_real_val_predictor_reaches_f1_one() -> None:
    view = _real_view()
    labels = st._val_labels(view)
    predictions = {pid: (1.0 if label == "M" else 0.0) for pid, label in labels.items()}
    best, sweep = st.select_threshold(predictions, labels)
    best_row = next(r for r in sweep if r["threshold"] == best)
    assert best_row["f1"] == 1.0


def test_f1_at_threshold_reports_undefined_not_zero_when_no_positive_predictions() -> None:
    """A reviewer finding: this used to return f1=0.0 for an undefined precision, while
    score_predictions.py returned None for the identical situation -- the same all-N model would
    read "f1": 0.0 in one committed artefact and "f1": null in the other. Now consistent: None
    means undefined, never fabricated as 0.0."""
    labels = {"p1": "M", "p2": "N"}
    predictions = {"p1": 0.1, "p2": 0.1}
    row = st._f1_at_threshold(predictions, labels, threshold=0.9)
    assert row["tp"] == 0 and row["fp"] == 0
    assert row["precision"] is None
    assert row["f1"] is None


# ---------------------------------------------------------------------------
# CLI / file-output behaviour.
# ---------------------------------------------------------------------------


def test_main_writes_sweep_and_best_threshold_with_frozen_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _isolate_results_dir: Path
) -> None:
    view = _real_view()
    labels = st._val_labels(view)
    predictions = {pid: (1.0 if label == "M" else 0.0) for pid, label in labels.items()}
    pred_path = tmp_path / "preds.json"
    pred_path.write_text(json.dumps(predictions), encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "select_threshold.py",
            "--predictions",
            str(pred_path),
            "--model-id",
            "unit-test-model",
        ],
    )
    st.main()

    output_path = _isolate_results_dir / "unit-test-model-threshold-selection.json"
    assert output_path.exists()
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["model_id"] == "unit-test-model"
    assert written["frozen_labels_sha256"] == st._frozen_marker()
    assert len(written["sweep"]) == 101
    assert isinstance(written["best_threshold"], float)
    assert 0.0 <= written["best_threshold"] <= 1.0


def test_main_refuses_when_predictions_contain_a_test_pair_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    view = _real_view()
    test_pair_id = next(e["pair_id"] for e in view["entries"] if e["split"] == "test")
    pred_path = tmp_path / "preds.json"
    pred_path.write_text(json.dumps({test_pair_id: 0.5}), encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        ["select_threshold.py", "--predictions", str(pred_path), "--model-id", "leaky-model"],
    )
    with pytest.raises(SystemExit, match="TEST pair_id"):
        st.main()


# ---------------------------------------------------------------------------
# Frozen-dataset guards, same pattern as the other harness scripts.
# ---------------------------------------------------------------------------


def test_refuses_when_eval_view_reports_unfrozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_view = tmp_path / "eval-view.json"
    fake_view.write_text(
        json.dumps({"frozen": False, "frozen_labels_sha256": st._frozen_marker(), "entries": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(st, "EVAL_VIEW_JSON", fake_view)
    with pytest.raises(SystemExit, match="not frozen"):
        st._load_eval_view()


def test_refuses_when_eval_view_hash_does_not_match_live_constant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_view = tmp_path / "eval-view.json"
    fake_view.write_text(
        json.dumps({"frozen": True, "frozen_labels_sha256": "deadbeef" * 8, "entries": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(st, "EVAL_VIEW_JSON", fake_view)
    with pytest.raises(SystemExit, match="REFUSING TO RUN"):
        st._load_eval_view()


def test_refuses_when_split_file_hash_does_not_match_view(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_split = tmp_path / "split.json"
    fake_split.write_text(
        json.dumps({"frozen_labels_sha256": "deadbeef" * 8, "val": {"pair_ids": []}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(st, "SPLIT_JSON", fake_split)
    view = _real_view()
    with pytest.raises(SystemExit, match="REFUSING TO RUN"):
        st._val_labels(view)


# ---------------------------------------------------------------------------
# Regression tests: NaN/non-numeric prediction values must be refused, not
# silently scored as "N" by `score >= threshold`.
# ---------------------------------------------------------------------------


def test_nan_prediction_value_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    view = _real_view()
    labels = st._val_labels(view)
    predictions = {pid: (1.0 if label == "M" else 0.0) for pid, label in labels.items()}
    predictions[next(iter(predictions))] = float("nan")
    pred_path = tmp_path / "preds.json"
    pred_path.write_text(json.dumps(predictions), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["select_threshold.py", "--predictions", str(pred_path), "--model-id", "nan-model"],
    )
    with pytest.raises(SystemExit, match="non-finite or non-numeric"):
        st.main()


def test_non_numeric_prediction_value_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    view = _real_view()
    labels = st._val_labels(view)
    predictions: dict[str, object] = {
        pid: (1.0 if label == "M" else 0.0) for pid, label in labels.items()
    }
    predictions[next(iter(predictions))] = "0.9"
    pred_path = tmp_path / "preds.json"
    pred_path.write_text(json.dumps(predictions), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["select_threshold.py", "--predictions", str(pred_path), "--model-id", "string-model"],
    )
    with pytest.raises(SystemExit, match="non-finite or non-numeric"):
        st.main()

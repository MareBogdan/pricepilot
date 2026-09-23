r"""Phase 3 item 5 harness: pick a scoring threshold on TRAIN_VAL's VALIDATION side only
(CLAUDE.md §7 item 5; docs/phase3-baseline-model-choice.md rule 2; ADR-0028 addendum #19).

    uv run python scripts/select_threshold.py --predictions <path> --model-id <id>

**THRESHOLD DISCIPLINE.** This is the ONE place in the harness a threshold may be chosen.
`scripts/score_predictions.py` only ever READS a threshold as an input; it never selects one.
This script is the mirror image: it selects a threshold and never reads a TEST label to do it --
enforced in code (`_assert_no_test_pair_ids`), not merely by convention, because the entire point
of a held-out TEST set collapses the moment its labels influence any decision made before it is
scored.

Input: a predictions JSON `{pair_id: score}` covering the 672 TRAIN_VAL pair_ids (or any superset
that includes them -- only the 134 pair_ids on validation's side of
`docs/learned/phase3-train-val-split.json` are actually read). Sweeps candidate thresholds,
scores each against validation's real labels (S dropped), and keeps whichever threshold
maximises F1. Writes the winning threshold AND the full sweep (never just the winner) to
`docs/learned/results/<model-id>-threshold-selection.json`, so the choice is auditable, not just
asserted.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from build_eval_view import OUTPUT_JSON as EVAL_VIEW_JSON  # noqa: E402
from build_eval_view import _frozen_marker  # noqa: E402
from pricepilot.matching.metrics import find_invalid_prediction_values  # noqa: E402

SPLIT_JSON = ROOT / "docs" / "learned" / "phase3-train-val-split.json"
RESULTS_DIR = ROOT / "docs" / "learned" / "results"

# 0.00, 0.01, ..., 1.00 -- fine enough to find a real optimum on 134 pairs without being an
# unbounded/expensive search.
THRESHOLD_GRID = [round(i / 100, 2) for i in range(0, 101)]


def _load_eval_view() -> dict[str, Any]:
    view = json.loads(EVAL_VIEW_JSON.read_text(encoding="utf-8"))
    live_marker = _frozen_marker()
    if view.get("frozen_labels_sha256") != live_marker:
        raise SystemExit(
            "REFUSING TO RUN: eval view's frozen_labels_sha256 does not match the live "
            "FROZEN_LABELS_SHA256. Re-run scripts/build_eval_view.py first."
        )
    if not view.get("frozen"):
        raise SystemExit("REFUSING TO RUN: the label dataset is not frozen yet.")
    return view  # type: ignore[no-any-return]


def _assert_no_test_pair_ids(predictions: dict[str, float], view: dict[str, Any]) -> None:
    """The leakage guard this script exists to enforce: threshold selection must never even
    SEE a TEST pair_id, whether or not its label would have been used."""
    test_pair_ids = {e["pair_id"] for e in view["entries"] if e["split"] == "test"}
    leaked = set(predictions) & test_pair_ids
    if leaked:
        raise SystemExit(
            f"REFUSING TO RUN: {len(leaked)} TEST pair_id(s) present in the predictions file "
            f"handed to threshold selection -- this must never happen. First few: "
            f"{sorted(leaked)[:5]}"
        )


def _validate_prediction_values(predictions: dict[str, Any]) -> None:
    """A reviewer finding shared with score_predictions.py: `score >= threshold` treats an
    unvalidated NaN as a confident "N", silently biasing whatever threshold gets picked."""
    bad = find_invalid_prediction_values(predictions)
    if bad:
        first = sorted(bad)[:5]
        raise SystemExit(
            "REFUSING TO RUN: predictions file contains non-finite or non-numeric score(s) for "
            f"{len(bad)} pair_id(s) -- first few: {[(pid, bad[pid]) for pid in first]}"
        )


def _val_labels(view: dict[str, Any]) -> dict[str, str]:
    split = json.loads(SPLIT_JSON.read_text(encoding="utf-8"))
    if split.get("frozen_labels_sha256") != view["frozen_labels_sha256"]:
        raise SystemExit(
            "REFUSING TO RUN: phase3-train-val-split.json's frozen_labels_sha256 does not match "
            "the eval view's -- re-run scripts/split_train_val.py first."
        )
    val_ids = set(split["val"]["pair_ids"])
    labels = {
        e["pair_id"]: e["label"]
        for e in view["entries"]
        if e["split"] == "train_val" and e["pair_id"] in val_ids and e["scored"]
    }
    if len(labels) != split["val"]["pair_count"] - split["val"]["label_counts"]["S"]:
        raise SystemExit(
            "REFUSING TO RUN: scored validation pair count doesn't match the split file's own "
            "bookkeeping -- data drift between phase3-eval-view.json and "
            "phase3-train-val-split.json."
        )
    return labels


def _f1_at_threshold(
    predictions: dict[str, float], labels: dict[str, str], threshold: float
) -> dict[str, Any]:
    tp = fp = fn = tn = 0
    for pair_id, true_label in labels.items():
        predicted = "M" if predictions[pair_id] >= threshold else "N"
        if true_label == "M" and predicted == "M":
            tp += 1
        elif true_label == "N" and predicted == "M":
            fp += 1
        elif true_label == "M" and predicted == "N":
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    # Mirrors score_predictions.py's own convention exactly (a reviewer finding: the two scripts
    # previously disagreed -- this one returned 0.0 for an undefined precision/recall, the other
    # returned None, so the same all-N predictions produced "f1": 0.0 here and "f1": null there,
    # both committed as evidence for the same run). None means undefined, never fabricated as 0.0.
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision and recall and (precision + recall) > 0
        else (0.0 if precision is not None and recall is not None else None)
    )
    return {
        "threshold": threshold,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def _f1_rank_key(f1: float | None) -> float:
    """None (undefined F1) ranks below every real F1 value, including 0.0."""
    return f1 if f1 is not None else -1.0


def _longest_contiguous_run(values: list[float], step: float = 0.01) -> list[float]:
    """The longest run of values that are each exactly one grid `step` apart, sorted ascending.
    Ties between equally-long runs keep the first one found (lowest thresholds)."""
    ordered = sorted(values)
    best_run: list[float] = []
    current_run: list[float] = []
    for v in ordered:
        if current_run and round(v - current_run[-1], 10) > step + 1e-9:
            if len(current_run) > len(best_run):
                best_run = current_run
            current_run = [v]
        else:
            current_run.append(v)
    if len(current_run) > len(best_run):
        best_run = current_run
    return best_run


def select_threshold(
    predictions: dict[str, float], labels: dict[str, str]
) -> tuple[float, list[dict[str, Any]]]:
    missing = set(labels) - set(predictions)
    if missing:
        raise SystemExit(
            f"REFUSING TO RUN: predictions file is missing {len(missing)} validation pair_id(s). "
            f"First few: {sorted(missing)[:5]}"
        )
    sweep = [_f1_at_threshold(predictions, labels, t) for t in THRESHOLD_GRID]
    best_f1 = max(_f1_rank_key(row["f1"]) for row in sweep)
    # A reviewer finding: `max(sweep, key=...)` picks the FIRST maximum, i.e. the lowest
    # threshold on an F1 plateau -- the most fragile point of it, sitting right above the highest
    # validation negative, so any TEST negative scoring in the whole plateau range becomes a false
    # positive. Picking the midpoint of the widest tying run is barely more code and much less
    # fragile: a TEST score would need to land past half the plateau's width to flip the outcome.
    tying_thresholds = [row["threshold"] for row in sweep if _f1_rank_key(row["f1"]) == best_f1]
    run = _longest_contiguous_run(tying_thresholds)
    best_threshold = round((run[0] + run[-1]) / 2, 2)
    return best_threshold, sweep


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    ap.add_argument("--predictions", required=True, type=Path)
    ap.add_argument("--model-id", required=True)
    args = ap.parse_args()

    view = _load_eval_view()
    predictions = json.loads(args.predictions.read_text(encoding="utf-8"))
    _assert_no_test_pair_ids(predictions, view)
    _validate_prediction_values(predictions)
    labels = _val_labels(view)

    best_threshold, sweep = select_threshold(predictions, labels)
    best_row = next(r for r in sweep if r["threshold"] == best_threshold)
    best_f1_str = "undefined" if best_row["f1"] is None else f"{best_row['f1']:.4f}"

    print(f"model: {args.model_id}")
    print(f"validation pairs scored: {len(labels)}")
    print(
        f"best threshold: {best_threshold} "
        f"(F1={best_f1_str}, precision={best_row['precision']}, "
        f"recall={best_row['recall']}, TP={best_row['tp']} FP={best_row['fp']} "
        f"FN={best_row['fn']} TN={best_row['tn']})"
    )

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RESULTS_DIR / f"{args.model_id}-threshold-selection.json"
    output = {
        "built_from": "scripts/select_threshold.py",
        "generated_at": datetime.now(UTC).isoformat(),
        "model_id": args.model_id,
        "frozen_labels_sha256": view["frozen_labels_sha256"],
        "validation_pairs_scored": len(labels),
        "best_threshold": best_threshold,
        "sweep": sweep,
    }
    output_path.write_text(json.dumps(output, indent=1, ensure_ascii=False), encoding="utf-8")
    display_path = (
        output_path.relative_to(ROOT) if output_path.is_relative_to(ROOT) else output_path
    )
    print(f"\nwritten: {display_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

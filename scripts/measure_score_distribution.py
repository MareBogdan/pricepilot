r"""Phase 3 item 5: measure a model's raw TEST score distribution per label class, and optionally
a full per-tier confusion breakdown at an already-ledgered threshold (CLAUDE.md §0 rule 4 / §9 --
no metric may appear in docs without a script behind it; DECISIONS.md ADR-0028 addendum #20).

    uv run python scripts/measure_score_distribution.py --predictions <path> --model-id <id>
    uv run python scripts/measure_score_distribution.py --predictions <path> --model-id <id> \
        --threshold <t>

Reports median/min/max and the fraction of scores at or above `--high-water` (default 0.99) for
each label class (M, N) on the 284 scored TEST pairs. With `--threshold`, also reports raw
tp/fp/fn/tn per tier for EVERY tier, including the ones `scripts/score_predictions.py` withholds a
precision/recall/F1 figure for at n_pos < 5 (docs/phase3-baseline-model-choice.md rule 6) -- rule 6
withholds a RATE computed from too few positives, not the raw counts themselves, and a reader
should be able to see "1 of 4 recalled" without re-deriving it by hand.

This is a read-only diagnostic: it never selects a threshold (the value passed in must already be
the one `select_threshold.py` chose and `score_predictions.py` used) and never touches the
TEST-touch ledger -- it is not a second "scoring" in the sense `docs/phase3-baseline-model-choice.md`
rule 3 gates, since it makes no new decision about which threshold to use and produces no
precision/recall/F1 conclusion of its own; it only exposes counts `score_predictions.py` already
computed internally during its one ledgered run, at the exact threshold that run used. Its purpose
is to make distribution and per-tier-count claims reproducible with one command instead of living
only in prose.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from build_eval_view import OUTPUT_JSON as EVAL_VIEW_JSON  # noqa: E402
from build_eval_view import TIER_ORDER, _frozen_marker  # noqa: E402
from pricepilot.matching.metrics import find_invalid_prediction_values  # noqa: E402

RESULTS_DIR = ROOT / "docs" / "learned" / "results"
MODEL_ID_PATTERN = re.compile(r"\A[A-Za-z0-9._-]+\Z")


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


def _test_entries(view: dict[str, Any]) -> list[dict[str, Any]]:
    entries = [e for e in view["entries"] if e["split"] == "test"]
    if len(entries) != 287:
        raise SystemExit(f"REFUSING TO RUN: expected 287 TEST pairs, found {len(entries)}.")
    return entries


def _class_stats(scores: list[float], high_water: float) -> dict[str, Any]:
    if not scores:
        raise SystemExit(
            "REFUSING TO RUN: one of the two label classes (M/N) has zero scored TEST pairs -- "
            "cannot compute a median of an empty sample. This should not happen against the "
            "frozen 284-pair TEST set (97 M / 187 N); check the eval view hasn't drifted."
        )
    return {
        "n": len(scores),
        "median": statistics.median(scores),
        "min": min(scores),
        "max": max(scores),
        f"frac_ge_{high_water}": sum(1 for s in scores if s >= high_water) / len(scores),
    }


def measure(
    entries: list[dict[str, Any]], predictions: dict[str, float], high_water: float
) -> dict[str, Any]:
    scored = [e for e in entries if e["scored"]]
    by_label: dict[str, list[float]] = {"M": [], "N": []}
    for e in scored:
        if e["label"] in by_label:
            by_label[e["label"]].append(predictions[e["pair_id"]])
    return {label: _class_stats(scores, high_water) for label, scores in by_label.items()}


def per_tier_confusion(
    entries: list[dict[str, Any]], predictions: dict[str, float], threshold: float
) -> dict[str, Any]:
    """Raw tp/fp/fn/tn for EVERY tier, no reportability gate -- score_predictions.py's own rule 6
    withholds a precision/recall/F1 RATE below n_pos=5, not these counts; this exposes the counts
    that computation already made internally, at the exact threshold it used."""
    scored = [e for e in entries if e["scored"]]
    result: dict[str, Any] = {}
    for tier in TIER_ORDER:
        tier_entries = [e for e in scored if e["tier"] == tier]
        tp = fp = fn = tn = 0
        for e in tier_entries:
            predicted = "M" if predictions[e["pair_id"]] >= threshold else "N"
            if e["label"] == "M" and predicted == "M":
                tp += 1
            elif e["label"] == "N" and predicted == "M":
                fp += 1
            elif e["label"] == "M" and predicted == "N":
                fn += 1
            else:
                tn += 1
        result[tier] = {"tp": tp, "fp": fp, "fn": fn, "tn": tn}
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    ap.add_argument("--predictions", required=True, type=Path)
    ap.add_argument("--model-id", required=True)
    ap.add_argument("--high-water", type=float, default=0.99)
    ap.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="the already-ledgered threshold score_predictions.py used for this model; when "
        "given, also reports raw tp/fp/fn/tn per tier for every tier.",
    )
    args = ap.parse_args()

    if not MODEL_ID_PATTERN.match(args.model_id):
        raise SystemExit(
            f"REFUSING TO RUN: --model-id {args.model_id!r} contains characters other than "
            "letters, digits, '.', '_', '-' -- it is used verbatim in an output file path."
        )

    view = _load_eval_view()
    entries = _test_entries(view)
    predictions = json.loads(args.predictions.read_text(encoding="utf-8"))
    expected = {e["pair_id"] for e in entries}
    actual = set(predictions)
    missing, extra = expected - actual, actual - expected
    if missing or extra:
        raise SystemExit(
            f"REFUSING TO RUN: predictions file does not cover exactly the 287 TEST pair_ids -- "
            f"{len(missing)} missing, {len(extra)} unexpected."
        )
    bad = find_invalid_prediction_values(predictions)
    if bad:
        raise SystemExit(
            f"REFUSING TO RUN: predictions file contains non-finite or non-numeric score(s) for "
            f"{len(bad)} pair_id(s)."
        )

    result = measure(entries, predictions, args.high_water)

    print(f"model: {args.model_id}")
    for label, stats in result.items():
        frac_key = f"frac_ge_{args.high_water}"
        print(
            f"  {label} (n={stats['n']}): median={stats['median']:.5f} "
            f"min={stats['min']:.5f} max={stats['max']:.5f} "
            f">= {args.high_water}: {stats[frac_key]:.4f}"
        )

    tier_confusion = None
    if args.threshold is not None:
        tier_confusion = per_tier_confusion(entries, predictions, args.threshold)
        print(f"\nper-tier raw confusion counts at threshold={args.threshold}:")
        print("| tier | tp | fp | fn | tn |")
        print("|---|---|---|---|---|")
        for tier, counts in tier_confusion.items():
            print(f"| {tier} | {counts['tp']} | {counts['fp']} | {counts['fn']} | {counts['tn']} |")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RESULTS_DIR / f"{args.model_id}-score-distribution.json"
    output = {
        "built_from": "scripts/measure_score_distribution.py",
        "generated_at": datetime.now(UTC).isoformat(),
        "model_id": args.model_id,
        "frozen_labels_sha256": view["frozen_labels_sha256"],
        "high_water": args.high_water,
        "by_label": result,
        "threshold": args.threshold,
        "per_tier_confusion": tier_confusion,
    }
    output_path.write_text(json.dumps(output, indent=1, ensure_ascii=False), encoding="utf-8")
    display_path = (
        output_path.relative_to(ROOT) if output_path.is_relative_to(ROOT) else output_path
    )
    print(f"\nwritten: {display_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

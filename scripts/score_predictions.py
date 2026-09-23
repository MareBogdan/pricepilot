r"""Phase 3 item 5 harness: score predictions against the 287 TEST pairs, once per model
(CLAUDE.md §7 item 5; docs/phase3-baseline-model-choice.md; ADR-0028 addendum #19).

    uv run python scripts/score_predictions.py --predictions <path> --threshold <t> --model-id <id>
    uv run python scripts/score_predictions.py --predictions <path> --threshold <t> --model-id <id> \
        --rescore --reason "why this model needs a second TEST touch"

Input: a predictions JSON `{pair_id: score}` -- one real-valued score per TEST pair_id, ALL 287
of them (including the 3 `S`-labelled ones, which the model cannot distinguish and which this
scorer drops before grading, reporting the drop count) -- plus `--threshold` (`score >=
threshold` => predicted `M`) and `--model-id` (a free-form string identifying the model, used by
the TEST-touch ledger below).

Output: `docs/learned/results/<model-id>-metrics.json` (the full metrics) and a markdown table on
stdout.

RULES, every one enforced in code, never merely documented:
1. Scores only the 284 scored TEST pairs (drops the 3 `S` pairs, reports the count).
2. Refuses (non-zero exit) a predictions file that does not cover EXACTLY the 287 TEST pair_ids
   -- missing or extra, either way.
3. Refuses if the eval view's `frozen_labels_sha256` does not match the live
   `FROZEN_LABELS_SHA256` constant.
4. precision / recall / F1 / accuracy, each reported with its denominator; precision, recall and
   accuracy each also get a Wilson 95% CI (they are each a single binomial proportion). F1 is a
   harmonic mean of two DIFFERENT proportions (precision and recall), not itself a single
   proportion a Wilson interval is defined over -- reported as a point value with that reasoning
   stated, rather than manufacturing a number Wilson's assumptions don't support.
5. Per-tier reportability rule (docs/phase3-baseline-model-choice.md rule 6): a tier with fewer
   than 5 positives reports FP rate (+ Wilson CI) and an explicit "recall not computable, n_pos =
   X" note instead of precision/recall/F1 -- computed dynamically from the real positives count
   per tier every run, never from a hardcoded table (a future review pass could move a pair
   between tiers; a hardcoded table would silently go stale).
6. Overall recall reported TWICE: over all 97 positives, and excluding the 13 duplicated
   `trivial_spot_check` pairs the eval view attributes to `proxy_key_collision` (both labelled
   clearly) -- the first alone overstates difficulty-adjusted performance.
7. Confusion matrix with raw counts.
8. THRESHOLD DISCIPLINE: this script only ever READS `--threshold`; it never selects one.
   `scripts/select_threshold.py` is the only place a threshold is chosen, and only against
   TRAIN_VAL's validation side -- if this script is ever handed TEST data while selecting
   anything, that is a bug, and there is no code path here that selects anything.
9. TEST-TOUCH LEDGER: every successful run appends to
   `docs/learned/results/test-touch-ledger.json` (model_id, timestamp, threshold, F1). A second
   run for the same `--model-id` is refused unless `--rescore` is passed together with
   `--reason <text>`, which is itself recorded in the ledger entry.
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
from build_eval_view import TIER_ORDER, _frozen_marker  # noqa: E402
from pricepilot.matching.metrics import (  # noqa: E402
    find_invalid_prediction_values,
    wilson_confidence_interval,
)

RESULTS_DIR = ROOT / "docs" / "learned" / "results"
LEDGER_JSON = RESULTS_DIR / "test-touch-ledger.json"

MIN_POSITIVES_FOR_FULL_METRICS = 5


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


def _validate_predictions_cover_exactly(
    predictions: dict[str, Any], entries: list[dict[str, Any]]
) -> None:
    expected = {e["pair_id"] for e in entries}
    actual = set(predictions)
    missing = expected - actual
    extra = actual - expected
    if missing or extra:
        raise SystemExit(
            "REFUSING TO SCORE: predictions file does not cover exactly the 287 TEST pair_ids "
            f"-- {len(missing)} missing, {len(extra)} unexpected. "
            f"First few missing: {sorted(missing)[:5]}. First few unexpected: {sorted(extra)[:5]}."
        )


def _validate_prediction_values(predictions: dict[str, Any]) -> None:
    """A reviewer finding: `_predicted_label` does `score >= threshold`, and `NaN >= t` is always
    False, so an unvalidated NaN score silently became a confident, wrong "N" prediction instead
    of a refused run -- and json.loads accepts bare NaN/Infinity by default, so this is reachable
    from an ordinary predictions file, not just a hand-crafted adversarial one."""
    bad = find_invalid_prediction_values(predictions)
    if bad:
        first = sorted(bad)[:5]
        raise SystemExit(
            "REFUSING TO SCORE: predictions file contains non-finite or non-numeric score(s) "
            f"for {len(bad)} pair_id(s) -- first few: {[(pid, bad[pid]) for pid in first]}"
        )


def _predicted_label(score: float, threshold: float) -> str:
    return "M" if score >= threshold else "N"


def _proportion_report(successes: int, n: int) -> dict[str, Any]:
    if n == 0:
        return {"value": None, "n": 0, "note": "undefined (denominator is 0)"}
    ci = wilson_confidence_interval(successes, n)
    return {
        "value": successes / n,
        "n": n,
        "ci_95_lower": ci.lower,
        "ci_95_upper": ci.upper,
    }


def _false_positive_rate_report(fp: int, n_neg: int) -> dict[str, Any]:
    return _proportion_report(fp, n_neg)


def score(
    entries: list[dict[str, Any]], predictions: dict[str, Any], threshold: float
) -> dict[str, Any]:
    scored_entries = [e for e in entries if e["scored"]]
    s_dropped = len(entries) - len(scored_entries)

    tp = fp = fn = tn = 0
    repeat_positive_pair_ids: set[str] = set()
    for e in scored_entries:
        predicted = _predicted_label(predictions[e["pair_id"]], threshold)
        if e["label"] == "M" and predicted == "M":
            tp += 1
        elif e["label"] == "N" and predicted == "M":
            fp += 1
        elif e["label"] == "M" and predicted == "N":
            fn += 1
        else:
            tn += 1
        if e["label"] == "M" and e["is_repeat"] and e["tier"] == "proxy_key_collision":
            repeat_positive_pair_ids.add(e["pair_id"])

    n_scored = len(scored_entries)
    precision = _proportion_report(tp, tp + fp)
    recall_all = _proportion_report(tp, tp + fn)

    excl_repeat_scored = [e for e in scored_entries if e["pair_id"] not in repeat_positive_pair_ids]
    tp_excl = sum(
        1
        for e in excl_repeat_scored
        if e["label"] == "M" and _predicted_label(predictions[e["pair_id"]], threshold) == "M"
    )
    fn_excl = sum(
        1
        for e in excl_repeat_scored
        if e["label"] == "M" and _predicted_label(predictions[e["pair_id"]], threshold) == "N"
    )
    recall_excl_repeats = _proportion_report(tp_excl, tp_excl + fn_excl)

    accuracy = _proportion_report(tp + tn, n_scored)
    f1 = (
        2 * precision["value"] * recall_all["value"] / (precision["value"] + recall_all["value"])
        if precision["value"]
        and recall_all["value"]
        and (precision["value"] + recall_all["value"]) > 0
        else (0.0 if precision["value"] is not None and recall_all["value"] is not None else None)
    )

    per_tier: dict[str, Any] = {}
    for tier in TIER_ORDER:
        tier_entries = [e for e in scored_entries if e["tier"] == tier]
        n_pos = sum(1 for e in tier_entries if e["label"] == "M")
        n_neg = sum(1 for e in tier_entries if e["label"] == "N")
        tier_tp = sum(
            1
            for e in tier_entries
            if e["label"] == "M" and _predicted_label(predictions[e["pair_id"]], threshold) == "M"
        )
        tier_fp = sum(
            1
            for e in tier_entries
            if e["label"] == "N" and _predicted_label(predictions[e["pair_id"]], threshold) == "M"
        )
        tier_fn = n_pos - tier_tp
        if n_pos < MIN_POSITIVES_FOR_FULL_METRICS:
            per_tier[tier] = {
                "n_pos": n_pos,
                "n_neg": n_neg,
                "reportable": False,
                "note": f"recall not computable, n_pos = {n_pos}",
                "false_positive_rate": _false_positive_rate_report(tier_fp, n_neg),
            }
        else:
            tier_precision = _proportion_report(tier_tp, tier_tp + tier_fp)
            tier_recall = _proportion_report(tier_tp, n_pos)
            tier_f1 = (
                2
                * tier_precision["value"]
                * tier_recall["value"]
                / (tier_precision["value"] + tier_recall["value"])
                if tier_precision["value"] and tier_recall["value"]
                else 0.0
            )
            per_tier[tier] = {
                "n_pos": n_pos,
                "n_neg": n_neg,
                "reportable": True,
                "precision": tier_precision,
                "recall": tier_recall,
                "f1": tier_f1,
                "tp": tier_tp,
                "fp": tier_fp,
                "fn": tier_fn,
            }

    return {
        "n_scored": n_scored,
        "s_dropped": s_dropped,
        "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "precision": precision,
        "recall_all_positives": recall_all,
        "recall_excluding_13_repeat_positives": recall_excl_repeats,
        "n_repeat_positives_excluded": len(repeat_positive_pair_ids),
        "accuracy": accuracy,
        "f1": {
            "value": f1,
            "note": (
                "no independent Wilson CI -- F1 is a harmonic mean of precision and recall, two "
                "different proportions, not itself a single binomial proportion Wilson's "
                "assumptions apply to."
            ),
        },
        "per_tier": per_tier,
    }


def _load_ledger() -> dict[str, Any]:
    if LEDGER_JSON.exists():
        return json.loads(LEDGER_JSON.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
    return {"entries": []}


def _check_ledger_permission(model_id: str, rescore: bool, reason: str | None) -> None:
    """Checked BEFORE any scoring or printing happens -- a refused run must fail fast, not
    compute and print a full report and only then say it was never allowed to."""
    prior = [e for e in _load_ledger()["entries"] if e["model_id"] == model_id]
    if prior and not rescore:
        raise SystemExit(
            f"REFUSING TO SCORE: model_id {model_id!r} already has {len(prior)} TEST-touch "
            f"ledger entry(ies) (docs/phase3-baseline-model-choice.md rule 3: TEST is touched "
            f"once per model). Pass --rescore with --reason to score it again."
        )
    if prior and rescore and not reason:
        raise SystemExit("REFUSING TO SCORE: --rescore requires --reason.")


def _append_to_ledger(
    model_id: str, threshold: float, f1: float | None, rescore: bool, reason: str | None
) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ledger = _load_ledger()
    ledger["entries"].append(
        {
            "model_id": model_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "threshold": threshold,
            "f1": f1,
            "rescore": rescore,
            "reason": reason,
        }
    )
    LEDGER_JSON.write_text(json.dumps(ledger, indent=1, ensure_ascii=False), encoding="utf-8")


def _fmt_proportion(report: dict[str, Any]) -> str:
    if report["value"] is None:
        return f"undefined (n={report['n']})"
    return f"{report['value']:.4f} (n={report['n']}, 95% CI [{report['ci_95_lower']:.4f}, {report['ci_95_upper']:.4f}])"


def print_markdown(result: dict[str, Any], model_id: str, threshold: float) -> None:
    print(f"## Scoring results: {model_id} (threshold={threshold})\n")
    print(f"Scored {result['n_scored']} TEST pairs ({result['s_dropped']} S dropped).\n")
    print("| metric | value |")
    print("|---|---|")
    print(f"| precision | {_fmt_proportion(result['precision'])} |")
    print(f"| recall (all positives) | {_fmt_proportion(result['recall_all_positives'])} |")
    n_excl = result["n_repeat_positives_excluded"]
    print(
        f"| recall (excl. {n_excl} repeat positives) | "
        f"{_fmt_proportion(result['recall_excluding_13_repeat_positives'])} |"
    )
    print(f"| accuracy | {_fmt_proportion(result['accuracy'])} |")
    f1 = result["f1"]["value"]
    print(f"| F1 | {'undefined' if f1 is None else f'{f1:.4f}'} |")
    print()
    cm = result["confusion_matrix"]
    print("Confusion matrix (raw counts):\n")
    print("| | predicted M | predicted N |")
    print("|---|---|---|")
    print(f"| actual M | TP={cm['tp']} | FN={cm['fn']} |")
    print(f"| actual N | FP={cm['fp']} | TN={cm['tn']} |")
    print()
    print("Per-tier:\n")
    print("| tier | n_pos | n_neg | metric |")
    print("|---|---|---|---|")
    for tier, t in result["per_tier"].items():
        if t["reportable"]:
            # a reviewer finding: precision can be None even in a reportable tier (no positive
            # predictions at all inside it -- tp+fp == 0), and `:.3f` on None raised TypeError,
            # crashing print_markdown AFTER the TEST touch was already spent scoring it.
            precision_value = t["precision"]["value"]
            precision_str = "undefined" if precision_value is None else f"{precision_value:.3f}"
            metric = f"P={precision_str} R={t['recall']['value']:.3f} F1={t['f1']:.3f}"
        else:
            metric = f"FP rate={_fmt_proportion(t['false_positive_rate'])} -- {t['note']}"
        print(f"| {tier} | {t['n_pos']} | {t['n_neg']} | {metric} |")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    ap.add_argument("--predictions", required=True, type=Path)
    ap.add_argument("--threshold", required=True, type=float)
    ap.add_argument("--model-id", required=True)
    ap.add_argument("--rescore", action="store_true")
    ap.add_argument("--reason", default=None)
    args = ap.parse_args()
    if args.rescore and not args.reason:
        raise SystemExit("--rescore requires --reason.")
    _check_ledger_permission(args.model_id, args.rescore, args.reason)

    prior_entries = [e for e in _load_ledger()["entries"] if e["model_id"] == args.model_id]
    if prior_entries and args.rescore:
        prior_thresholds = sorted({e["threshold"] for e in prior_entries})
        if args.threshold not in prior_thresholds:
            # A reviewer finding: --rescore was unlimited and unaudited beyond the ledger's raw
            # entries -- nothing noticed a rescore picking a DIFFERENT threshold than the model's
            # first TEST touch, which is tuning a threshold against TEST in all but name (the
            # exact thing docs/phase3-baseline-model-choice.md rule 2 exists to prevent). This
            # cannot refuse the run outright (a genuine bug-fix rescore may legitimately need a
            # different threshold), but it must never pass silently.
            print(
                f"WARNING: rescoring {args.model_id!r} at threshold={args.threshold}, but its "
                f"prior TEST touch(es) used threshold(s) {prior_thresholds}. If this threshold "
                "was chosen after seeing a prior TEST result, that is tuning against TEST -- "
                "--reason should explain why the threshold changed.",
                file=sys.stderr,
            )

    view = _load_eval_view()
    entries = _test_entries(view)
    predictions = json.loads(args.predictions.read_text(encoding="utf-8"))
    _validate_predictions_cover_exactly(predictions, entries)
    _validate_prediction_values(predictions)

    result = score(entries, predictions, args.threshold)

    # Record the TEST touch as soon as scoring succeeds, before printing or writing anything --
    # a reviewer finding: appending to the ledger only AFTER print_markdown meant the crash fixed
    # above (a reportable tier with an undefined precision) left TEST touched with no ledger
    # record, so a retry without --rescore was silently let back in. "Touched" means TEST was
    # read and scored, not that the report finished printing.
    _append_to_ledger(
        args.model_id, args.threshold, result["f1"]["value"], args.rescore, args.reason
    )

    print_markdown(result, args.model_id, args.threshold)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    # A reviewer finding: writing every touch to the same {model_id}-metrics.json overwrote the
    # first touch's evidence on a rescore while the ledger still claimed two touches happened.
    # Suffix every touch after the first so every metrics file the ledger references still exists.
    attempt = len(prior_entries) + 1
    suffix = "" if attempt == 1 else f"-rescore{attempt - 1}"
    output_path = RESULTS_DIR / f"{args.model_id}{suffix}-metrics.json"
    output = {
        "built_from": "scripts/score_predictions.py",
        "generated_at": datetime.now(UTC).isoformat(),
        "model_id": args.model_id,
        "threshold": args.threshold,
        "frozen_labels_sha256": view["frozen_labels_sha256"],
        **result,
    }
    output_path.write_text(json.dumps(output, indent=1, ensure_ascii=False), encoding="utf-8")
    display_path = (
        output_path.relative_to(ROOT) if output_path.is_relative_to(ROOT) else output_path
    )
    print(f"\nwritten: {display_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

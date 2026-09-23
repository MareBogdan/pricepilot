r"""Phase 3 item 8: did the cross-encoder retrain reproduce the committed fine-tuned model?

    uv run python scripts/check_ce_reproduction.py

Implements docs/phase3-ce-reproduction-rule.md exactly (pre-registered before the retrain ran):

  REPRODUCED      iff best epoch == 6 AND zero decision flips at the ledgered fine-tuned threshold
                  across all 959 fine-tuned pairs (287 TEST + 672 TRAIN_VAL).
  NOT_REPRODUCED  otherwise.

The check is score-against-score. It reads the committed prediction files, the retrain's
prediction files, the retrain's run-facts file and the ledger (for the thresholds). It reads NO
label file, so it is not a TEST touch and the ledger is never written. Max |diff| and mean |diff|
are reported per file, not gated. The zero-shot files are compared too, as an environment sanity
check only; they never enter the verdict.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "docs" / "learned" / "results"
COMMITTED_DIR = RESULTS_DIR / "predictions"
DEFAULT_RETRAIN_DIR = COMMITTED_DIR / "retrain"
LEDGER_JSON = RESULTS_DIR / "test-touch-ledger.json"
OUTPUT_JSON = RESULTS_DIR / "ce-reproduction-check.json"

FINETUNED_MODEL_ID = "mmarco-mMiniLMv2-finetuned-ep6"
ZEROSHOT_MODEL_ID = "mmarco-mMiniLMv2-zeroshot"
RETRAIN_MODEL_ID = f"{FINETUNED_MODEL_ID}-retrain"
EXPECTED_BEST_EPOCH = 6
EXPECTED_FINETUNED_PAIRS = 959  # 287 TEST + 672 TRAIN_VAL
EXPECTED_PAIRS_PER_FILE = {"test": 287, "trainval": 672}

# (file stem, which model's ledgered threshold applies, gated in the verdict)
FILES = [
    ("preds-finetuned-test", "finetuned", True),
    ("preds-finetuned-trainval", "finetuned", True),
    ("preds-zeroshot-test", "zeroshot", False),
    ("preds-zeroshot-trainval", "zeroshot", False),
]


class KeySetMismatchError(Exception):
    """The committed and retrain files do not cover the same pair_ids."""


def compare_scores(
    committed: dict[str, float], retrain: dict[str, float], threshold: float, name: str
) -> dict[str, Any]:
    """Score-against-score comparison of one file. Hard error if the key sets differ."""
    if set(committed) != set(retrain):
        only_c = sorted(set(committed) - set(retrain))
        only_r = sorted(set(retrain) - set(committed))
        raise KeySetMismatchError(
            f"{name}: key sets differ ({len(only_c)} only in committed, {len(only_r)} only in "
            f"retrain). First few: {only_c[:3]} / {only_r[:3]}"
        )
    for label, scores in (("committed", committed), ("retrain", retrain)):
        bad = sorted(k for k, v in scores.items() if not math.isfinite(v))
        if bad:
            raise KeySetMismatchError(f"{name}: non-finite {label} score(s), first few: {bad[:3]}")
    diffs = [abs(committed[k] - retrain[k]) for k in committed]
    flips = sorted(k for k in committed if (committed[k] >= threshold) != (retrain[k] >= threshold))
    return {
        "pairs": len(committed),
        "threshold": threshold,
        "max_abs_diff": max(diffs) if diffs else 0.0,
        "mean_abs_diff": statistics.fmean(diffs) if diffs else 0.0,
        "flips": len(flips),
        "flipped_pair_ids": flips,
    }


def verdict(best_epoch: int, finetuned_flips: int, finetuned_pairs: int) -> str:
    if finetuned_pairs != EXPECTED_FINETUNED_PAIRS:
        raise KeySetMismatchError(
            f"fine-tuned files cover {finetuned_pairs} pairs; the rule is stated over "
            f"{EXPECTED_FINETUNED_PAIRS}"
        )
    if best_epoch == EXPECTED_BEST_EPOCH and finetuned_flips == 0:
        return "REPRODUCED"
    return "NOT_REPRODUCED"


def ledgered_threshold(ledger: dict[str, Any], model_id: str) -> float:
    for entry in ledger["entries"]:
        if entry["model_id"] == model_id:
            return float(entry["threshold"])
    raise SystemExit(f"model {model_id!r} has no ledger entry; cannot take its threshold")


def run_check(
    committed_dir: Path, retrain_dir: Path, ledger: dict[str, Any], facts: dict[str, Any]
) -> dict[str, Any]:
    thresholds = {
        "finetuned": ledgered_threshold(ledger, FINETUNED_MODEL_ID),
        "zeroshot": ledgered_threshold(ledger, ZEROSHOT_MODEL_ID),
    }
    per_file: dict[str, Any] = {}
    finetuned_flips = 0
    finetuned_pairs = 0
    for stem, which, gated in FILES:
        committed = json.loads((committed_dir / f"{stem}.json").read_text(encoding="utf-8"))
        retrain = json.loads((retrain_dir / f"{stem}-retrain.json").read_text(encoding="utf-8"))
        res = compare_scores(committed, retrain, thresholds[which], stem)
        expected_n = EXPECTED_PAIRS_PER_FILE[stem.rsplit("-", 1)[1]]
        if res["pairs"] != expected_n:
            raise KeySetMismatchError(f"{stem}: {res['pairs']} pairs, the rule needs {expected_n}")
        res["gated_in_verdict"] = gated
        per_file[stem] = res
        if gated:
            finetuned_flips += res["flips"]
            finetuned_pairs += res["pairs"]
    best_epoch = int(facts["best_epoch"])
    result = verdict(best_epoch, finetuned_flips, finetuned_pairs)
    if result == "REPRODUCED":
        consequence = (
            f"The retrained weights ARE {FINETUNED_MODEL_ID} for item 8. No new ledger entry."
        )
    else:
        consequence = (
            f"The retrain is a different model, {RETRAIN_MODEL_ID}: threshold chosen by "
            "scripts/select_threshold.py on validation, ONE ledgered TEST touch, and it is the "
            "cross-encoder benchmarked in item 8. The item-5 result (F1 0.8737) stays untouched."
        )
    return {
        "built_from": "scripts/check_ce_reproduction.py",
        "rule": "docs/phase3-ce-reproduction-rule.md",
        "generated_at": datetime.now(UTC).isoformat(),
        "verdict": result,
        "consequence": consequence,
        "cross_encoder_id_for_item_8": FINETUNED_MODEL_ID
        if result == "REPRODUCED"
        else RETRAIN_MODEL_ID,
        "retrain_best_epoch": best_epoch,
        "expected_best_epoch": EXPECTED_BEST_EPOCH,
        "finetuned_pairs_compared": finetuned_pairs,
        "finetuned_flips_total": finetuned_flips,
        "thresholds_from_ledger": thresholds,
        "weights_sha256": facts.get("weights_sha256"),
        "files": per_file,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    ap.add_argument("--retrain-dir", type=Path, default=DEFAULT_RETRAIN_DIR)
    ap.add_argument("--committed-dir", type=Path, default=COMMITTED_DIR)
    ap.add_argument("--ledger", type=Path, default=LEDGER_JSON)
    ap.add_argument("--output", type=Path, default=OUTPUT_JSON)
    args = ap.parse_args()

    ledger = json.loads(args.ledger.read_text(encoding="utf-8"))
    facts = json.loads((args.retrain_dir / "ce-run-facts.json").read_text(encoding="utf-8"))
    try:
        report = run_check(args.committed_dir, args.retrain_dir, ledger, facts)
    except KeySetMismatchError as e:
        raise SystemExit(f"ERROR: {e}") from e

    for stem, res in report["files"].items():
        print(
            f"{stem:26s} n={res['pairs']:4d}  t={res['threshold']}  "
            f"max|diff|={res['max_abs_diff']:.3e}  mean|diff|={res['mean_abs_diff']:.3e}  "
            f"flips={res['flips']}  {'(gated)' if res['gated_in_verdict'] else '(sanity only)'}"
        )
    print(
        f"\nretrain best epoch: {report['retrain_best_epoch']} "
        f"(rule needs {report['expected_best_epoch']})"
    )
    print(
        f"fine-tuned flips across {report['finetuned_pairs_compared']} pairs: "
        f"{report['finetuned_flips_total']}"
    )
    print(f"VERDICT: {report['verdict']}")
    print(report["consequence"])
    args.output.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    shown = args.output.relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output
    print(f"\nwritten: {shown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

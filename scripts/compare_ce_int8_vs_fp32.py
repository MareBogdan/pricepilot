r"""Phase 3 item 8 session 2, task 2 (G4): McNemar exact paired comparison of the cross-encoder's
int8 TEST result against its already-ledgered fp32 fine-tune, on the SAME 284 scored TEST pairs.
Reads NOTHING new from TEST: both models' thresholds and predictions were already scored by
`scripts/score_predictions.py` (mmarco-mMiniLMv2-finetuned-ep6 in item 7, its `-int8` counterpart
in this session); this script only pairs the two already-recorded outcomes per pair_id.

    uv run python scripts/compare_ce_int8_vs_fp32.py

Output: `docs/learned/results/ce-int8-vs-fp32-mcnemar.json`.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from pricepilot.matching.metrics import mcnemar_exact_p  # noqa: E402
from score_predictions import (  # noqa: E402
    LEDGER_JSON,
    RESULTS_DIR,
    _load_eval_view,
    _test_entries,
    score,
)

FP32 = "mmarco-mMiniLMv2-finetuned-ep6"
INT8 = "mmarco-mMiniLMv2-finetuned-ep6-int8"
PRED_DIR = ROOT / "docs" / "learned" / "results" / "serving"
OUTPUT_JSON = RESULTS_DIR / "ce-int8-vs-fp32-mcnemar.json"


def _ledgered_thresholds() -> dict[str, float]:
    ledger = json.loads(LEDGER_JSON.read_text(encoding="utf-8"))
    return {e["model_id"]: float(e["threshold"]) for e in ledger["entries"]}


def main() -> int:
    thresholds = _ledgered_thresholds()
    for mid in (FP32, INT8):
        if mid not in thresholds:
            raise SystemExit(f"REFUSING: {mid!r} has no ledger entry, so no recorded threshold.")

    view = _load_eval_view()
    entries = [e for e in _test_entries(view) if e["scored"]]
    preds = {
        FP32: json.loads(
            (RESULTS_DIR / "predictions" / "preds-finetuned-test.json").read_text(encoding="utf-8")
        ),
        INT8: json.loads((PRED_DIR / "preds-ce-int8-test.json").read_text(encoding="utf-8")),
    }

    # Committed metrics files must agree with score() run now -- any difference means a
    # prediction file or threshold drifted since the ledgered TEST touch.
    for mid in (FP32, INT8):
        result = score(_test_entries(view), preds[mid], thresholds[mid])
        stored = json.loads((RESULTS_DIR / f"{mid}-metrics.json").read_text(encoding="utf-8"))
        if stored["confusion_matrix"] != result["confusion_matrix"]:
            raise SystemExit(f"REFUSING: {mid} confusion matrix differs from its committed file.")

    def correct(mid: str, e: dict[str, Any]) -> bool:
        return bool(("M" if preds[mid][e["pair_id"]] >= thresholds[mid] else "N") == e["label"])

    def mcnemar(subset: list[dict[str, Any]]) -> dict[str, Any]:
        fp32_only = sum(1 for e in subset if correct(FP32, e) and not correct(INT8, e))
        int8_only = sum(1 for e in subset if correct(INT8, e) and not correct(FP32, e))
        both = sum(1 for e in subset if correct(FP32, e) and correct(INT8, e))
        neither = len(subset) - fp32_only - int8_only - both
        return {
            "n": len(subset),
            "both_right": both,
            "fp32_only_right": fp32_only,
            "int8_only_right": int8_only,
            "both_wrong": neither,
            "p_exact_two_sided": mcnemar_exact_p(fp32_only, int8_only),
        }

    mc_all = mcnemar(entries)
    mc_pos = mcnemar([e for e in entries if e["label"] == "M"])
    mc_neg = mcnemar([e for e in entries if e["label"] == "N"])

    out = {
        "built_from": "scripts/compare_ce_int8_vs_fp32.py",
        "generated_at": datetime.now(UTC).isoformat(),
        "fp32_model_id": FP32,
        "int8_model_id": INT8,
        "thresholds": {FP32: thresholds[FP32], INT8: thresholds[INT8]},
        "n_scored": len(entries),
        "mcnemar_all": mc_all,
        "mcnemar_positives_only": mc_pos,
        "mcnemar_negatives_only": mc_neg,
    }
    OUTPUT_JSON.write_text(json.dumps(out, indent=1), encoding="utf-8")

    print(
        f"CE int8 (t={thresholds[INT8]}) vs CE fp32 (t={thresholds[FP32]}), {len(entries)} scored TEST pairs\n"
    )
    for label, mc in (("all", mc_all), ("true M only", mc_pos), ("true N only", mc_neg)):
        print(
            f"  {label}: n={mc['n']} both_right={mc['both_right']} "
            f"fp32_only_right={mc['fp32_only_right']} int8_only_right={mc['int8_only_right']} "
            f"both_wrong={mc['both_wrong']} p_exact_two_sided={mc['p_exact_two_sided']:.4f}"
        )
    print(f"\nwritten: {OUTPUT_JSON.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

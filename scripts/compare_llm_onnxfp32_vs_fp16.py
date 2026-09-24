r"""Phase 3 item 8 session 3, task 2 (G4): McNemar exact paired comparison of the LLM served as
ONNX fp32 CPU (protocol 5.11's fallback -- no int8 variant was eligible) against its already-
ledgered fp16 GPU fine-tune, on the SAME 284 scored TEST pairs. Reads NOTHING new from TEST: both
models' thresholds and predictions were already scored by `scripts/score_predictions.py`
(`qwen2.5-0.5b-lora-ep8` in item 7, `qwen2.5-0.5b-lora-ep8-onnxfp32-cpu` in this session); this
script only pairs the two already-recorded outcomes per pair_id.

    uv run python scripts/compare_llm_onnxfp32_vs_fp16.py

Output: `docs/learned/results/llm-onnxfp32-vs-fp16-mcnemar.json`.
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

FP16_GPU = "qwen2.5-0.5b-lora-ep8"
ONNXFP32_CPU = "qwen2.5-0.5b-lora-ep8-onnxfp32-cpu"
SERVING_DIR = ROOT / "docs" / "learned" / "results" / "serving"
OUTPUT_JSON = RESULTS_DIR / "llm-onnxfp32-vs-fp16-mcnemar.json"


def _ledgered_thresholds() -> dict[str, float]:
    ledger = json.loads(LEDGER_JSON.read_text(encoding="utf-8"))
    return {e["model_id"]: float(e["threshold"]) for e in ledger["entries"]}


def main() -> int:
    thresholds = _ledgered_thresholds()
    for mid in (FP16_GPU, ONNXFP32_CPU):
        if mid not in thresholds:
            raise SystemExit(f"REFUSING: {mid!r} has no ledger entry, so no recorded threshold.")

    view = _load_eval_view()
    entries = [e for e in _test_entries(view) if e["scored"]]
    preds = {
        FP16_GPU: json.loads(
            (RESULTS_DIR / "predictions" / "preds-llm-test.json").read_text(encoding="utf-8")
        ),
        ONNXFP32_CPU: json.loads(
            (SERVING_DIR / "preds-llm-onnxfp32-test.json").read_text(encoding="utf-8")
        ),
    }

    # Committed metrics files must agree with score() run now -- any difference means a
    # prediction file or threshold drifted since the ledgered TEST touch.
    for mid in (FP16_GPU, ONNXFP32_CPU):
        result = score(_test_entries(view), preds[mid], thresholds[mid])
        stored = json.loads((RESULTS_DIR / f"{mid}-metrics.json").read_text(encoding="utf-8"))
        if stored["confusion_matrix"] != result["confusion_matrix"]:
            raise SystemExit(f"REFUSING: {mid} confusion matrix differs from its committed file.")

    def correct(mid: str, e: dict[str, Any]) -> bool:
        return bool(("M" if preds[mid][e["pair_id"]] >= thresholds[mid] else "N") == e["label"])

    def mcnemar(subset: list[dict[str, Any]]) -> dict[str, Any]:
        fp16_only = sum(1 for e in subset if correct(FP16_GPU, e) and not correct(ONNXFP32_CPU, e))
        onnx_only = sum(1 for e in subset if correct(ONNXFP32_CPU, e) and not correct(FP16_GPU, e))
        both = sum(1 for e in subset if correct(FP16_GPU, e) and correct(ONNXFP32_CPU, e))
        neither = len(subset) - fp16_only - onnx_only - both
        return {
            "n": len(subset),
            "both_right": both,
            "fp16_gpu_only_right": fp16_only,
            "onnxfp32_cpu_only_right": onnx_only,
            "both_wrong": neither,
            "p_exact_two_sided": mcnemar_exact_p(fp16_only, onnx_only),
        }

    mc_all = mcnemar(entries)
    mc_pos = mcnemar([e for e in entries if e["label"] == "M"])
    mc_neg = mcnemar([e for e in entries if e["label"] == "N"])

    out = {
        "built_from": "scripts/compare_llm_onnxfp32_vs_fp16.py",
        "generated_at": datetime.now(UTC).isoformat(),
        "fp16_gpu_model_id": FP16_GPU,
        "onnxfp32_cpu_model_id": ONNXFP32_CPU,
        "thresholds": {FP16_GPU: thresholds[FP16_GPU], ONNXFP32_CPU: thresholds[ONNXFP32_CPU]},
        "n_scored": len(entries),
        "mcnemar_all": mc_all,
        "mcnemar_positives_only": mc_pos,
        "mcnemar_negatives_only": mc_neg,
    }
    OUTPUT_JSON.write_text(json.dumps(out, indent=1), encoding="utf-8")

    print(
        f"LLM ONNX fp32 CPU (t={thresholds[ONNXFP32_CPU]}) vs LLM fp16 GPU "
        f"(t={thresholds[FP16_GPU]}), {len(entries)} scored TEST pairs\n"
    )
    for label, mc in (("all", mc_all), ("true M only", mc_pos), ("true N only", mc_neg)):
        print(
            f"  {label}: n={mc['n']} both_right={mc['both_right']} "
            f"fp16_gpu_only_right={mc['fp16_gpu_only_right']} "
            f"onnxfp32_cpu_only_right={mc['onnxfp32_cpu_only_right']} "
            f"both_wrong={mc['both_wrong']} p_exact_two_sided={mc['p_exact_two_sided']:.4f}"
        )
    print(f"\nwritten: {OUTPUT_JSON.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

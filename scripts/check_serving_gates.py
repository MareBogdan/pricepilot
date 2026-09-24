r"""Phase 3 item 8 session 2, task 1: G1/G1b/G2 (protocol 5.4), computed from the committed Kaggle
serving outputs in `docs/learned/results/serving/` -- never re-derived by hand or re-typed from
the architect's pre-check. Session 2 stops at the first gate that fails: G1 decides whether ANY
serving number gets reported at all (protocol 5.9 -- LoRA export failure means stop and report, no
silent fallback).

    uv run python scripts/check_serving_gates.py

Reads NO TEST label. G1/G1b/G2 compare model OUTPUTS against each other and against already-scored
committed predictions -- never against ground truth. The one exception is the LLM int8 diagnostic
(median P(Yes) by true label, best-threshold F1), which reads the 133 VALIDATION labels only, the
same ones `scripts/select_threshold.py` is allowed to read.

Writes `docs/learned/results/serving-gates.json`.
"""

from __future__ import annotations

import json
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from select_threshold import _load_eval_view, _val_labels, select_threshold  # noqa: E402

SERVING_DIR = ROOT / "docs" / "learned" / "results" / "serving"
PRED_DIR = ROOT / "docs" / "learned" / "results" / "predictions"
OUTPUT_JSON = ROOT / "docs" / "learned" / "results" / "serving-gates.json"
LEDGER_JSON = ROOT / "docs" / "learned" / "results" / "test-touch-ledger.json"

CE_THRESHOLD = 0.89  # mmarco-mMiniLMv2-finetuned-ep6's ledgered threshold
LLM_THRESHOLD = 0.86  # qwen2.5-0.5b-lora-ep8's ledgered threshold
G1_MAX_ABS_DIFF = 1e-3  # protocol 5.4 G1


def _load(path: Path) -> dict[str, float]:
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _ledgered_thresholds() -> dict[str, float]:
    ledger = json.loads(LEDGER_JSON.read_text(encoding="utf-8"))
    return {e["model_id"]: float(e["threshold"]) for e in ledger["entries"]}


def compare(a: dict[str, float], b: dict[str, float], threshold: float, label: str) -> dict[str, Any]:
    """One paired comparison of two `{pair_id: score}` files at the SAME set of pair_ids: max/mean
    absolute diff, and decision flips at `threshold` (score >= threshold => M)."""
    if set(a) != set(b):
        only_a, only_b = set(a) - set(b), set(b) - set(a)
        raise SystemExit(
            f"REFUSING: {label} -- predictions cover different pair_ids "
            f"({len(only_a)} only in first, {len(only_b)} only in second)"
        )
    diffs = {pid: abs(a[pid] - b[pid]) for pid in a}
    flips = sum(1 for pid in a if (a[pid] >= threshold) != (b[pid] >= threshold))
    return {
        "label": label,
        "n": len(a),
        "threshold": threshold,
        "max_abs_diff": max(diffs.values()),
        "mean_abs_diff": sum(diffs.values()) / len(diffs),
        "flips": flips,
    }


def g1_passes(comparison: dict[str, Any]) -> bool:
    """Protocol 5.4 G1: max |diff| <= 1e-3 AND zero decision flips at the ledgered threshold."""
    return bool(comparison["max_abs_diff"] <= G1_MAX_ABS_DIFF and comparison["flips"] == 0)


def _median_p_yes(preds: dict[str, float], labels: dict[str, str], label: str) -> dict[str, float]:
    m_scores = [preds[pid] for pid, lab in labels.items() if lab == "M"]
    n_scores = [preds[pid] for pid, lab in labels.items() if lab == "N"]
    return {
        "variant": label,
        "median_p_yes_true_M": statistics.median(m_scores),
        "median_p_yes_true_N": statistics.median(n_scores),
        "n_M": len(m_scores),
        "n_N": len(n_scores),
    }


def _best_val_f1(preds: dict[str, float], labels: dict[str, str], label: str) -> dict[str, Any]:
    threshold, sweep = select_threshold(preds, labels)
    best = next(r for r in sweep if r["threshold"] == threshold)
    return {"variant": label, "best_threshold": threshold, "best_f1": best["f1"]}


def main() -> int:
    thresholds = _ledgered_thresholds()
    ce_t = thresholds.get("mmarco-mMiniLMv2-finetuned-ep6", CE_THRESHOLD)
    llm_t = thresholds.get("qwen2.5-0.5b-lora-ep8", LLM_THRESHOLD)
    assert ce_t == CE_THRESHOLD and llm_t == LLM_THRESHOLD, (
        f"ledgered thresholds drifted from the ones this script was written against: "
        f"CE {ce_t} (expected {CE_THRESHOLD}), LLM {llm_t} (expected {LLM_THRESHOLD})"
    )

    # ---- G1: ONNX fp32 vs in-notebook PyTorch fp32 reference ----
    g1_ce_test = compare(
        _load(SERVING_DIR / "preds-ce-onnxfp32-test.json"),
        _load(SERVING_DIR / "preds-ce-ptfp32-test.json"),
        ce_t,
        "CE onnxfp32 vs ptfp32 (test)",
    )
    g1_ce_trainval = compare(
        _load(SERVING_DIR / "preds-ce-onnxfp32-trainval.json"),
        _load(SERVING_DIR / "preds-ce-ptfp32-trainval.json"),
        ce_t,
        "CE onnxfp32 vs ptfp32 (trainval)",
    )
    g1_llm_val = compare(
        _load(SERVING_DIR / "preds-llm-onnxfp32-val.json"),
        _load(SERVING_DIR / "preds-llm-ptfp32-val.json"),
        llm_t,
        "LLM onnxfp32 vs ptfp32 (val)",
    )
    g1_llm_test = compare(
        _load(SERVING_DIR / "preds-llm-onnxfp32-test.json"),
        _load(SERVING_DIR / "preds-llm-ptfp32-test.json"),
        llm_t,
        "LLM onnxfp32 vs ptfp32 (test)",
    )
    g1_checks = [g1_ce_test, g1_ce_trainval, g1_llm_val, g1_llm_test]
    g1_pass = all(g1_passes(c) for c in g1_checks)

    # Extra sanity check bundled with G1 in the architect's pre-check: the in-notebook PyTorch
    # fp32 reference itself against the ALREADY-COMMITTED CE predictions (item 5/7's), at 0.89.
    # Reported alongside G1, not part of its pass/fail (that is ONNX vs the in-notebook reference).
    g1_extra_ce_vs_committed = compare(
        _load(SERVING_DIR / "preds-ce-ptfp32-test.json"),
        _load(PRED_DIR / "preds-finetuned-test.json"),
        ce_t,
        "CE ptfp32 vs committed preds-finetuned-test.json",
    )

    if not g1_pass:
        result = {
            "built_from": "scripts/check_serving_gates.py",
            "generated_at": datetime.now(UTC).isoformat(),
            "g1_pass": False,
            "g1_checks": g1_checks,
            "note": "G1 FAILED -- protocol 5.9: stop and report, no further serving number computed.",
        }
        OUTPUT_JSON.write_text(json.dumps(result, indent=1), encoding="utf-8")
        print(json.dumps(result, indent=1))
        return 1

    # ---- G1b (reported, not gated): LLM PyTorch fp32 CPU vs the committed fp16 GPU preds ----
    g1b = compare(
        _load(SERVING_DIR / "preds-llm-ptfp32-test.json"),
        _load(PRED_DIR / "preds-llm-test.json"),
        llm_t,
        "LLM ptfp32 CPU vs committed preds-llm-test.json (fp16 GPU)",
    )

    # ---- G2 (reported, not gated): int8 vs ONNX fp32 ----
    g2_ce_test = compare(
        _load(SERVING_DIR / "preds-ce-int8-test.json"),
        _load(SERVING_DIR / "preds-ce-onnxfp32-test.json"),
        ce_t,
        "CE int8 vs onnxfp32 (test)",
    )
    g2_ce_trainval = compare(
        _load(SERVING_DIR / "preds-ce-int8-trainval.json"),
        _load(SERVING_DIR / "preds-ce-onnxfp32-trainval.json"),
        ce_t,
        "CE int8 vs onnxfp32 (trainval)",
    )
    g2_llm_val = compare(
        _load(SERVING_DIR / "preds-llm-int8-val.json"),
        _load(SERVING_DIR / "preds-llm-onnxfp32-val.json"),
        llm_t,
        "LLM int8 vs onnxfp32 (val)",
    )
    g2_llm_test = compare(
        _load(SERVING_DIR / "preds-llm-int8-test.json"),
        _load(SERVING_DIR / "preds-llm-onnxfp32-test.json"),
        llm_t,
        "LLM int8 vs onnxfp32 (test)",
    )

    # ---- Diagnostics needing VALIDATION labels only (LLM int8 non-discrimination check) ----
    view = _load_eval_view()
    val_labels = _val_labels(view)
    llm_int8_val = _load(SERVING_DIR / "preds-llm-int8-val.json")
    llm_fp32_val = _load(SERVING_DIR / "preds-llm-onnxfp32-val.json")
    ce_medians = None  # CE is not diagnosed here -- only the LLM int8 result is non-discriminating
    llm_medians = [
        _median_p_yes(llm_int8_val, val_labels, "int8"),
        _median_p_yes(llm_fp32_val, val_labels, "onnxfp32"),
    ]
    llm_best_f1 = [
        _best_val_f1(llm_int8_val, val_labels, "int8"),
        _best_val_f1(llm_fp32_val, val_labels, "onnxfp32"),
    ]

    result = {
        "built_from": "scripts/check_serving_gates.py",
        "generated_at": datetime.now(UTC).isoformat(),
        "thresholds": {"cross_encoder": ce_t, "llm": llm_t},
        "g1_pass": g1_pass,
        "g1_checks": g1_checks,
        "g1_extra_ce_ptfp32_vs_committed": g1_extra_ce_vs_committed,
        "g1b_reported_not_gated": g1b,
        "g2_ce": [g2_ce_test, g2_ce_trainval],
        "g2_llm": [g2_llm_val, g2_llm_test],
        "g2_llm_diagnostics": {
            "median_p_yes_by_true_validation_label": llm_medians,
            "best_validation_f1": llm_best_f1,
        },
        "ce_medians_diagnostic": ce_medians,
    }
    OUTPUT_JSON.write_text(json.dumps(result, indent=1), encoding="utf-8")

    print(f"G1 pass: {g1_pass}")
    for c in g1_checks:
        print(f"  {c['label']}: max|d|={c['max_abs_diff']:.2e} flips={c['flips']}/{c['n']} (n={c['n']})")
    print(
        f"  extra: {g1_extra_ce_vs_committed['label']}: "
        f"max|d|={g1_extra_ce_vs_committed['max_abs_diff']:.2e} "
        f"flips={g1_extra_ce_vs_committed['flips']}"
    )
    print(
        f"\nG1b (reported): {g1b['label']}: max|d|={g1b['max_abs_diff']:.4f} "
        f"mean|d|={g1b['mean_abs_diff']:.4f} flips={g1b['flips']}/{g1b['n']}"
    )
    print("\nG2 (reported):")
    for c in (g2_ce_test, g2_ce_trainval, g2_llm_val, g2_llm_test):
        print(
            f"  {c['label']}: flips={c['flips']}/{c['n']} max|d|={c['max_abs_diff']:.4f} "
            f"mean|d|={c['mean_abs_diff']:.4f}"
        )
    print("\nLLM int8 discrimination diagnostic (validation labels only):")
    for m in llm_medians:
        print(
            f"  {m['variant']}: median P(Yes) true-M={m['median_p_yes_true_M']:.3f} "
            f"(n={m['n_M']}), true-N={m['median_p_yes_true_N']:.3f} (n={m['n_N']})"
        )
    for f in llm_best_f1:
        print(f"  {f['variant']}: best val threshold={f['best_threshold']} F1={f['best_f1']:.3f}")

    display_path = OUTPUT_JSON.relative_to(ROOT)
    print(f"\nwritten: {display_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

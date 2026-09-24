r"""Phase 3 item 8 session 3, task 1: applies protocol 5.11's LLM int8 variant rule by script, from
the committed `docs/learned/results/serving/int8v/` files -- never re-derived by hand.

    uv run python scripts/select_llm_int8_variant.py

Three steps, in order, exactly as 5.11 registers them (never TEST until a variant is selected):

1. **Verify gate.** The fresh re-export's own val predictions
   (`preds-llm-onnxfp32-verify-val.json`) vs the already-committed
   `docs/learned/results/serving/preds-llm-onnxfp32-val.json`, max|diff| <= 1e-5. Refuses to
   continue past a failed gate (nothing built from an unverified export can be trusted).
2. **Eligibility**, on the 133 VALIDATION pairs only: a variant is eligible only if its median
   P(Yes) separates the classes, `median_M > 0.5 > median_N`.
3. **Selection**, among eligible variants only: highest best-threshold validation F1
   (`scripts/select_threshold.py`'s own sweep); ties within 0.005 F1 broken by lower p50 latency
   (pinned, batch 1, `latency-llm-int8-v<N>.json`).

If no variant is eligible, prints "NO ELIGIBLE VARIANT" and the finding text 5.11 pre-registers for
that outcome. Reads no TEST prediction file, regardless of outcome (5.11's whole point).

Writes `docs/learned/results/llm-int8-variant-selection.json`.
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

from check_serving_gates import _median_p_yes  # noqa: E402
from select_threshold import _load_eval_view, _val_labels, select_threshold  # noqa: E402

SERVING_DIR = ROOT / "docs" / "learned" / "results" / "serving"
INT8V_DIR = SERVING_DIR / "int8v"
OUTPUT_JSON = ROOT / "docs" / "learned" / "results" / "llm-int8-variant-selection.json"

VERIFY_TOLERANCE = 1e-5
TIE_F1_MARGIN = 0.005
VARIANTS = ("v2", "v3")

NO_ELIGIBLE_VARIANT_FINDING = (
    "ORT dynamic int8 (three configurations: default, per_channel+reduce_range, "
    "per_channel+reduce_range+MatMul-only) destroys this 0.5B decoder's discrimination on two "
    "AVX2-without-VNNI CPUs (AMD EPYC 7B12, Intel Xeon @ 2.20GHz). The 'AMD-specific' hypothesis "
    "is refuted (Intel failed too); the 'per-tensor/saturation only' hypothesis is weakened "
    "(per-channel + reduce_range did not fix it). Weight-only quantization (e.g. MatMulNBits) was "
    "NOT tested -- untested future work, not run here."
)


def _load(path: Path) -> dict[str, float]:
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def verify_gate() -> dict[str, Any]:
    fresh = _load(INT8V_DIR / "preds-llm-onnxfp32-verify-val.json")
    committed = _load(SERVING_DIR / "preds-llm-onnxfp32-val.json")
    if set(fresh) != set(committed):
        raise SystemExit(
            "REFUSING: fresh verify predictions and the committed val file cover different pair_ids"
        )
    diffs = {pid: abs(fresh[pid] - committed[pid]) for pid in fresh}
    max_diff = max(diffs.values())
    passed = max_diff <= VERIFY_TOLERANCE
    return {
        "n": len(fresh),
        "max_abs_diff": max_diff,
        "tolerance": VERIFY_TOLERANCE,
        "passed": passed,
    }


def is_eligible(medians: dict[str, Any]) -> bool:
    """Protocol 5.11: eligible only if median_M > 0.5 > median_N."""
    return bool(medians["median_p_yes_true_M"] > 0.5 > medians["median_p_yes_true_N"])


def select_variant(
    candidates: dict[str, dict[str, Any]], tie_margin: float = TIE_F1_MARGIN
) -> str | None:
    """`candidates`: {variant: {"eligible": bool, "best_f1": float, "p50_ms": float}}. Returns the
    winning variant name, or None if no candidate is eligible. Pure function, tested directly."""
    eligible = {v: c for v, c in candidates.items() if c["eligible"]}
    if not eligible:
        return None
    best_f1 = max(c["best_f1"] for c in eligible.values())
    tied = [v for v, c in eligible.items() if best_f1 - c["best_f1"] <= tie_margin]
    if len(tied) == 1:
        return tied[0]
    return min(tied, key=lambda v: eligible[v]["p50_ms"])


def main() -> int:
    gate = verify_gate()
    print(
        f"LLM-verify-fp32: max|diff|={gate['max_abs_diff']:.2e} (n={gate['n']}, "
        f"tolerance {gate['tolerance']}) -- {'PASS' if gate['passed'] else 'FAIL'}"
    )
    if not gate["passed"]:
        result: dict[str, Any] = {
            "built_from": "scripts/select_llm_int8_variant.py",
            "generated_at": datetime.now(UTC).isoformat(),
            "verify_gate": gate,
            "note": "verify gate FAILED -- refusing to evaluate any variant built from this export.",
        }
        OUTPUT_JSON.write_text(json.dumps(result, indent=1), encoding="utf-8")
        print(json.dumps(result, indent=1))
        return 1

    view = _load_eval_view()
    val_labels = _val_labels(view)

    per_variant: dict[str, dict[str, Any]] = {}
    for v in VARIANTS:
        val_preds = _load(INT8V_DIR / f"preds-llm-int8-{v}-val.json")
        medians = _median_p_yes(val_preds, val_labels, v)
        threshold, sweep = select_threshold(val_preds, val_labels)
        best = next(r for r in sweep if r["threshold"] == threshold)
        latency = json.loads((INT8V_DIR / f"latency-llm-int8-{v}.json").read_text(encoding="utf-8"))
        eligible = is_eligible(medians)
        per_variant[v] = {
            "median_p_yes_true_M": medians["median_p_yes_true_M"],
            "median_p_yes_true_N": medians["median_p_yes_true_N"],
            "n_M": medians["n_M"],
            "n_N": medians["n_N"],
            "eligible": eligible,
            "best_threshold": threshold,
            "best_f1": best["f1"],
            "p50_ms": latency["summary_e2e_ms"]["p50"],
        }
        print(
            f"{v}: median P(Yes) M={medians['median_p_yes_true_M']:.3f} "
            f"N={medians['median_p_yes_true_N']:.3f} -> {'eligible' if eligible else 'NOT eligible'}; "
            f"best val F1={best['f1']:.3f} (t={threshold}); p50={latency['summary_e2e_ms']['p50']:.1f} ms"
        )

    selected = select_variant(per_variant)

    result = {
        "built_from": "scripts/select_llm_int8_variant.py",
        "generated_at": datetime.now(UTC).isoformat(),
        "verify_gate": gate,
        "variants": per_variant,
        "selected_variant": selected,
        "finding": None if selected else NO_ELIGIBLE_VARIANT_FINDING,
    }
    OUTPUT_JSON.write_text(json.dumps(result, indent=1), encoding="utf-8")

    if selected:
        print(f"\nSELECTED: {selected}")
    else:
        print("\nNO ELIGIBLE VARIANT")
        print(NO_ELIGIBLE_VARIANT_FINDING)

    print(f"\nwritten: {OUTPUT_JSON.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

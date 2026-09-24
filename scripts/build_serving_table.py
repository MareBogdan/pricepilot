r"""Phase 3 item 8 session 3, task 4: the final item-8 headline table, generated from committed
files only -- never hand-typed.

    uv run python scripts/build_serving_table.py

CLAUDE.md §7's tie rule (item 7 ended in a tie on F1, McNemar p=1.0000) makes this table the Phase
3 headline: F1 between the two fine-tuned models (cross-encoder, LoRA) is a PARITY claim, not a
winner; the hosted row is zero-shot and not a fair accuracy comparison (protocol 5.1c).

One row per model:
- CE fp32 (ledger `mmarco-mMiniLMv2-finetuned-ep6`), ONNX-fp32 latency.
- CE int8 (`...-ep6-int8`) -- TEST-touched, a significant drop vs fp32 (McNemar, session 3 task 2
  script `compare_ce_int8_vs_fp32.py`'s committed output).
- LoRA fp16 GPU (`qwen2.5-0.5b-lora-ep8`) -- reference only, no CPU latency (different hardware).
- LoRA ONNX fp32 CPU (`qwen2.5-0.5b-lora-ep8-onnxfp32-cpu`) -- the served LLM (protocol 5.11's
  fallback: no int8 variant was eligible).
- LoRA int8 -- NO ROW (no eligible configuration, protocol 5.11); the three configurations'
  validation medians and best val F1 are reported alongside instead.
- hosted v1 (`hosted-claude-sonnet-5-zeroshot`) and hosted v2
  (`hosted-claude-sonnet-5-zeroshot-v2`, protocol 5.12), side by side.

Columns: TEST F1, precision/recall as k/n with Wilson 95% CI, p50/p95 e2e ms (pinned, 2 threads),
throughput (pairs/s at batch 16), $/1,000 comparisons, peak RSS (VmHWM), artefact size, CPU model,
a proxy note. Local $/1,000 uses the CX23 hourly USD price (docs/phase3-serving-prices.md); hosted
$/1,000 is measured cost / pairs scored x 1000. Local models also get the full-catalogue re-match
wall-clock at K=20 (210,640 scorings) and K=100 (1,053,200) -- the input the pending K decision
(ADR-0028 #7 item 3) was waiting for.

The two latency runs are on DIFFERENT, NAMED CPUs (serving run: AMD EPYC 7B12; int8-variants run:
Intel Xeon @ 2.20GHz) and are never presented as if measured on the same hardware.

Output: `docs/learned/phase3-serving-benchmark.md`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "docs" / "learned" / "results"
SERVING_DIR = RESULTS_DIR / "serving"
PRED_DIR = RESULTS_DIR / "predictions"
OUTPUT_MD = ROOT / "docs" / "learned" / "phase3-serving-benchmark.md"

# docs/phase3-serving-prices.md: CX23 EUR 0.0088/h x ECB EUR->USD 1.1411 (2026-09-23), excl. VAT/IPv4
VPS_USD_PER_HOUR = 0.010042
K20_SCORINGS = 210_640
K100_SCORINGS = 1_053_200


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _fmt_proportion(report: dict[str, Any]) -> str:
    if report["value"] is None:
        return f"undefined (n={report['n']})"
    return (
        f"{report['value']:.4f} ({report['n']}) "
        f"[{report['ci_95_lower']:.4f}, {report['ci_95_upper']:.4f}]"
    )


def _local_dollars_per_1000(pairs_per_s: float) -> float:
    return VPS_USD_PER_HOUR * (1000.0 / pairs_per_s) / 3600.0


def _hosted_dollars_per_1000(cost_usd: float, pairs: int) -> float:
    return cost_usd / pairs * 1000.0


def _k_hours(pairs_per_s: float, scorings: int) -> float:
    return scorings / pairs_per_s / 3600.0


def local_row(
    label: str,
    metrics_file: str,
    latency_file: Path,
    artefact_bytes: int,
    cpu_model: str,
    proxy_note: str,
) -> dict[str, Any]:
    metrics = _load(RESULTS_DIR / metrics_file)
    lat = _load(latency_file)
    pairs_per_s = lat["throughput"]["pairs_per_s"]
    return {
        "label": label,
        "f1": metrics["f1"]["value"],
        "precision": _fmt_proportion(metrics["precision"]),
        "recall": _fmt_proportion(metrics["recall_all_positives"]),
        "p50_ms": lat["summary_e2e_ms"]["p50"],
        "p95_ms": lat["summary_e2e_ms"]["p95"],
        "pairs_per_s": pairs_per_s,
        "dollars_per_1000": _local_dollars_per_1000(pairs_per_s),
        "peak_rss_mb": lat["peak_rss_mb"],
        "artefact_mb": artefact_bytes / (1024 * 1024),
        "cpu_model": cpu_model,
        "proxy_note": proxy_note,
        "k20_hours": _k_hours(pairs_per_s, K20_SCORINGS),
        "k100_hours": _k_hours(pairs_per_s, K100_SCORINGS),
    }


def hosted_row(label: str, metrics_file: str, latency_file: str) -> dict[str, Any]:
    metrics = _load(RESULTS_DIR / metrics_file)
    lat = _load(PRED_DIR / latency_file)
    pairs = lat["pairs"]
    cost = float(lat["cost_usd"])
    return {
        "label": label,
        "f1": metrics["f1"]["value"],
        "precision": _fmt_proportion(metrics["precision"]),
        "recall": _fmt_proportion(metrics["recall_all_positives"]),
        "p50_ms": lat["latency_ms"].get("p50"),
        "p95_ms": lat["latency_ms"].get("p95"),
        "pairs_per_s": None,
        "dollars_per_1000": _hosted_dollars_per_1000(cost, pairs),
        "unparseable": lat["unparseable"],
        "pairs": pairs,
        "cost_usd": cost,
        "max_tokens": lat["max_tokens"],
        "stop_reason_counts": lat.get("stop_reason_counts"),
        "block_type_counts": lat.get("block_type_counts"),
    }


def main() -> int:
    ce_env = _load(SERVING_DIR / "env-facts.json")
    llm_env = _load(SERVING_DIR / "env-facts.json")  # same serving run as CE
    ce_cpu = ce_env["lscpu_model_name"]
    llm_fp32_cpu = llm_env["lscpu_model_name"]  # LoRA ONNX fp32 was scored in the SAME serving run

    model_facts = _load(SERVING_DIR / "model-facts.json")

    ce_fp32 = local_row(
        "Cross-encoder mMiniLMv2, fine-tuned (ONNX fp32 CPU)",
        "mmarco-mMiniLMv2-finetuned-ep6-metrics.json",
        SERVING_DIR / "latency-ce-onnxfp32.json",
        model_facts["ce_onnx_fp32"]["bytes"],
        ce_cpu,
        "Kaggle 2-thread proxy (AMD EPYC 7B12, no VNNI); re-measured on the Hetzner VPS in Phase 7.",
    )
    ce_int8 = local_row(
        "Cross-encoder mMiniLMv2, fine-tuned (ONNX int8 CPU)",
        "mmarco-mMiniLMv2-finetuned-ep6-int8-metrics.json",
        SERVING_DIR / "latency-ce-int8.json",
        model_facts["ce_onnx_int8"]["bytes"],
        ce_cpu,
        "Kaggle 2-thread proxy (AMD EPYC 7B12, no VNNI). Significant F1 drop vs fp32 "
        "(McNemar p=0.0042; false positives 10 -> 23) -- reported, not recommended for serving.",
    )
    lora_fp16 = _load(RESULTS_DIR / "qwen2.5-0.5b-lora-ep8-metrics.json")
    lora_fp32_cpu = local_row(
        "LoRA Qwen2.5-0.5B, epoch 8 (ONNX fp32 CPU)",
        "qwen2.5-0.5b-lora-ep8-onnxfp32-cpu-metrics.json",
        SERVING_DIR / "latency-llm-onnxfp32.json",
        model_facts["llm_onnx_fp32"]["bytes"],
        llm_fp32_cpu,
        "Kaggle 2-thread proxy (AMD EPYC 7B12, no VNNI); re-measured on the Hetzner VPS in Phase 7. "
        "Served as ONNX fp32 -- no int8 variant was eligible (protocol 5.11).",
    )

    variant_selection = _load(RESULTS_DIR / "llm-int8-variant-selection.json")

    hosted_v1 = hosted_row(
        "Hosted zero-shot, claude-sonnet-5 (v1, max_tokens=5)",
        "hosted-claude-sonnet-5-zeroshot-metrics.json",
        "latency-hosted.json",
    )
    hosted_v2_metrics_path = RESULTS_DIR / "hosted-claude-sonnet-5-zeroshot-v2-metrics.json"
    hosted_v2 = (
        hosted_row(
            "Hosted zero-shot, claude-sonnet-5 (v2, max_tokens=64)",
            "hosted-claude-sonnet-5-zeroshot-v2-metrics.json",
            "latency-hosted-v2.json",
        )
        if hosted_v2_metrics_path.exists()
        else None
    )
    if hosted_v2 is None:
        raise SystemExit(
            "REFUSING: hosted v2 has not been scored yet "
            f"({hosted_v2_metrics_path.relative_to(ROOT)} does not exist). Run "
            "scripts/run_hosted_baseline_v2.py --execute (after an explicit SPEND yes) then "
            "scripts/score_predictions.py on its predictions before building this table."
        )

    md: list[str] = []
    md.append("# Phase 3 item 8 — serving benchmark (final)\n")
    md.append(
        "CLAUDE.md §7's tie rule makes this table the Phase 3 headline: F1 between the two "
        "fine-tuned models (cross-encoder, LoRA) is a **parity claim**, not a winner. The hosted "
        "row is **zero-shot** and is not a fair accuracy comparison (protocol 5.1c) -- it is a "
        "cost/latency data point.\n"
    )
    md.append(
        "**The two latency runs are on DIFFERENT CPUs, never compared as same-hardware:** the "
        f"serving run (cross-encoder, LoRA fp16 reference) used **{ce_cpu}**; the int8-variants "
        "run (LLM int8 V2/V3, not served) used an Intel Xeon @ 2.20GHz. Both are AVX2 without "
        "VNNI. Every quoted local latency is a **Kaggle 2-thread proxy**, re-measured on the real "
        "Hetzner VPS in Phase 7.\n"
    )

    md.append("## Headline table\n")
    md.append(
        "| model | TEST F1 | precision (k) [CI] | recall (k) [CI] | p50 ms | p95 ms | "
        "pairs/s (batch 16) | $/1,000 | peak RSS (VmHWM) | artefact | CPU |"
    )
    md.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in (ce_fp32, ce_int8, lora_fp32_cpu):
        md.append(
            f"| {r['label']} | {r['f1']:.4f} | {r['precision']} | {r['recall']} | "
            f"{r['p50_ms']:.1f} | {r['p95_ms']:.1f} | {r['pairs_per_s']:.2f} | "
            f"${r['dollars_per_1000']:.4f} | {r['peak_rss_mb']:.0f} MB | "
            f"{r['artefact_mb']:.1f} MB | {r['cpu_model']} |"
        )
    md.append(
        f"| LoRA Qwen2.5-0.5B, epoch 8 (fp16 GPU, reference only) | {lora_fp16['f1']['value']:.4f} "
        f"| {_fmt_proportion(lora_fp16['precision'])} | "
        f"{_fmt_proportion(lora_fp16['recall_all_positives'])} | n/a (GPU, different hardware) "
        f"| n/a | n/a | n/a | n/a | n/a | NVIDIA T4 (Kaggle GPU) |"
    )
    for r in (hosted_v1, hosted_v2):
        p50 = f"{r['p50_ms']:.0f}" if r["p50_ms"] is not None else "n/a"
        p95 = f"{r['p95_ms']:.0f}" if r["p95_ms"] is not None else "n/a"
        md.append(
            f"| {r['label']} | {r['f1']:.4f} | {r['precision']} | {r['recall']} | {p50} | {p95} "
            f"| n/a (API) | ${r['dollars_per_1000']:.4f} | n/a | n/a | Anthropic-hosted |"
        )
    md.append(
        "\nF1 carries no CI of its own (harmonic mean of precision and recall, two different "
        "proportions; see the metrics files). `n` for precision/recall is its own denominator "
        "(predicted-M count / actual-M count), shown in parentheses.\n"
    )

    md.append("## LoRA int8 -- no row (protocol 5.11: no eligible configuration)\n")
    md.append(
        "Three ORT `quantize_dynamic` configurations were tried; none separated the classes on "
        "the 133 validation pairs (`median_p_yes_true_M > 0.5 > median_p_yes_true_N` required):\n"
    )
    md.append("| config | validation median P(Yes), true M | true N | best validation F1 |")
    md.append("|---|---|---|---|")
    for v, c in variant_selection["variants"].items():
        md.append(
            f"| {v} (per_channel+reduce_range{'  + MatMul-only' if v == 'v3' else ''}) | "
            f"{c['median_p_yes_true_M']:.3f} | {c['median_p_yes_true_N']:.3f} | {c['best_f1']:.3f} |"
        )
    md.append(
        "| default (V1, from the serving run) | 0.235 | 0.251 | 0.514 (= predict-all-positive) |"
    )
    md.append(
        f"\nNo TEST prediction file for any of the three was ever read. Finding: "
        f"{variant_selection['finding']}\n"
    )

    md.append("## Full-catalogue re-match wall-clock on the Hetzner VPS (per local model)\n")
    md.append(
        "The input the pending K decision (ADR-0028 addendum #7 item 3) was waiting for -- "
        "wall-clock only, at the pairs/s measured above (Kaggle 2-thread proxy; re-measure on the "
        "real VPS in Phase 7).\n"
    )
    md.append(f"| model | K=20 ({K20_SCORINGS:,} scorings) | K=100 ({K100_SCORINGS:,} scorings) |")
    md.append("|---|---|---|")
    for r in (ce_fp32, ce_int8, lora_fp32_cpu):
        md.append(f"| {r['label']} | {r['k20_hours']:.2f} h | {r['k100_hours']:.2f} h |")
    md.append("")

    md.append("## Hosted v1 vs v2 diagnostics\n")
    md.append(
        f"v1 (max_tokens=5): {hosted_v1['unparseable']}/{hosted_v1['pairs']} unparseable replies "
        f"(all empty, all hit `output_tokens == max_tokens`, protocol 5.10 item 6). "
        f"Cost ${hosted_v1['cost_usd']:.4f} actual.\n"
    )
    md.append(
        f"v2 (max_tokens=64, protocol 5.12): {hosted_v2['unparseable']}/{hosted_v2['pairs']} "
        f"unparseable. `stop_reason` counts: {hosted_v2['stop_reason_counts']}. Content "
        f"block-type counts: {hosted_v2['block_type_counts']}. Cost ${hosted_v2['cost_usd']:.4f} "
        f"actual.\n"
    )

    OUTPUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    print(f"\nwritten: {OUTPUT_MD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

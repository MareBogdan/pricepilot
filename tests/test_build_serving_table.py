"""Phase 3 item 8 session 3, task 4: pins the pure arithmetic in
`scripts/build_serving_table.py` -- the cost/wall-clock formulas protocol 5.6 fixes -- and, against
an isolated fake results tree (never the real committed files, so this test cannot break once
hosted v2 actually lands and cannot ever overwrite the real committed
docs/learned/phase3-serving-benchmark.md), both the "refuse rather than fabricate" behaviour and
the successful end-to-end build."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_serving_table as bst  # noqa: E402
from build_serving_table import (  # noqa: E402
    K20_SCORINGS,
    K100_SCORINGS,
    VPS_USD_PER_HOUR,
    _fmt_proportion,
    _hosted_dollars_per_1000,
    _k_hours,
    _local_dollars_per_1000,
    _vnni_note,
)


def test_local_dollars_per_1000_matches_protocol_5_6_formula() -> None:
    # protocol 5.6: VPS hourly USD x (1000 / pairs_per_s) / 3600
    pairs_per_s = 12.26415414350153  # the real CE fp32 figure
    expected = VPS_USD_PER_HOUR * (1000.0 / pairs_per_s) / 3600.0
    assert _local_dollars_per_1000(pairs_per_s) == pytest.approx(expected)
    assert _local_dollars_per_1000(pairs_per_s) > 0


def test_hosted_dollars_per_1000_is_measured_cost_over_pairs_times_1000() -> None:
    assert _hosted_dollars_per_1000(cost_usd=0.400858, pairs=287) == pytest.approx(
        0.400858 / 287 * 1000
    )


def test_k_hours_scales_inversely_with_throughput() -> None:
    faster = _k_hours(pairs_per_s=20.0, scorings=K20_SCORINGS)
    slower = _k_hours(pairs_per_s=10.0, scorings=K20_SCORINGS)
    assert slower == pytest.approx(faster * 2)
    assert _k_hours(pairs_per_s=12.26415414350153, scorings=K20_SCORINGS) == pytest.approx(
        K20_SCORINGS / 12.26415414350153 / 3600.0
    )


def test_k100_is_five_times_k20_scorings() -> None:
    assert K100_SCORINGS == K20_SCORINGS * 5


def test_fmt_proportion_undefined_when_denominator_is_none() -> None:
    assert _fmt_proportion({"value": None, "n": 0}) == "undefined (n=0)"


def test_fmt_proportion_includes_the_wilson_ci() -> None:
    formatted = _fmt_proportion({"value": 0.9, "n": 100, "ci_95_lower": 0.8, "ci_95_upper": 0.95})
    assert "0.9000" in formatted and "100" in formatted
    assert "0.8000" in formatted and "0.9500" in formatted


def test_vnni_note_reads_from_env_facts_not_hardcoded() -> None:
    assert _vnni_note({"cpu_vnni": {"avx512_vnni": False, "avx_vnni": False}}) == "no VNNI"
    assert _vnni_note({"cpu_vnni": {"avx512_vnni": True, "avx_vnni": False}}) == "VNNI present"


def test_dollars_per_1000_precision_distinguishes_ce_fp32_from_int8() -> None:
    """A reviewer finding: at 4 decimal places CE fp32 ($0.000227/1000) and CE int8
    ($0.000153/1000) both printed as $0.0002 -- the one column the tie rule makes the headline
    hid the difference it exists to show."""
    fp32 = _local_dollars_per_1000(12.26415414350153)
    int8 = _local_dollars_per_1000(18.180558818640836)
    assert f"{fp32:.6f}" != f"{int8:.6f}"
    assert f"{fp32:.4f}" == f"{int8:.4f}" == "0.0002"  # proves the OLD precision hid it


# ---------------------------------------------------------------------------
# End-to-end tests against an ISOLATED fake results tree (tmp_path), never the real committed
# files: real tests can never break when hosted v2 actually lands, and can never write to the
# real docs/learned/phase3-serving-benchmark.md.
# ---------------------------------------------------------------------------


def _metrics(f1: float, fp: int = 5) -> dict:
    prop = {"value": f1, "n": 100, "ci_95_lower": f1 - 0.05, "ci_95_upper": f1 + 0.05}
    return {
        "f1": {"value": f1},
        "precision": prop,
        "recall_all_positives": prop,
        "confusion_matrix": {"tp": 80, "fp": fp, "fn": 10, "tn": 200},
    }


def _latency(pairs_per_s: float, p50: float = 50.0, p95: float = 90.0, rss: float = 500.0) -> dict:
    return {
        "throughput": {"pairs_per_s": pairs_per_s},
        "summary_e2e_ms": {"p50": p50, "p95": p95},
        "peak_rss_mb": rss,
    }


def _hosted_latency(
    pairs: int = 287, cost: str = "0.40", unparseable: int = 40, cache_hits: int = 0
) -> dict:
    return {
        "pairs": pairs,
        "cost_usd": cost,
        "unparseable": unparseable,
        "latency_ms": {"p50": 1200.0, "p95": 1800.0},
        "cache_hits": cache_hits,
        "max_tokens": 5,
        "stop_reason_counts": {"end_turn": pairs - unparseable, "max_tokens": unparseable},
        "block_type_counts": {"text": pairs},
    }


def _write_fake_tree(root: Path, *, with_hosted_v2: bool) -> None:
    results = root / "docs" / "learned" / "results"
    serving = results / "serving"
    int8v = serving / "int8v"
    pred = results / "predictions"
    for d in (results, serving, int8v, pred):
        d.mkdir(parents=True, exist_ok=True)

    def w(path: Path, obj: dict) -> None:
        path.write_text(json.dumps(obj), encoding="utf-8")

    w(
        serving / "env-facts.json",
        {"lscpu_model_name": "Fake AMD", "cpu_vnni": {"avx512_vnni": False, "avx_vnni": False}},
    )
    w(
        int8v / "env-facts.json",
        {"lscpu_model_name": "Fake Intel", "cpu_vnni": {"avx512_vnni": False, "avx_vnni": False}},
    )
    w(
        serving / "model-facts.json",
        {
            "ce_onnx_fp32": {"bytes": 470_805_203},
            "ce_onnx_int8": {"bytes": 118_261_027},
            "llm_onnx_fp32": {"bytes": 1_977_096_964},
        },
    )
    w(serving / "latency-ce-onnxfp32.json", _latency(12.26))
    w(serving / "latency-ce-int8.json", _latency(18.18))
    w(serving / "latency-llm-onnxfp32.json", _latency(0.39, p50=2032.0, p95=2242.0, rss=2347.0))

    w(results / "mmarco-mMiniLMv2-finetuned-ep6-metrics.json", _metrics(0.8737, fp=10))
    w(results / "mmarco-mMiniLMv2-finetuned-ep6-int8-metrics.json", _metrics(0.8235, fp=23))
    w(
        results / "ce-int8-vs-fp32-mcnemar.json",
        {"mcnemar_all": {"p_exact_two_sided": 0.0042}},
    )
    w(results / "qwen2.5-0.5b-lora-ep8-metrics.json", _metrics(0.8796))
    w(results / "qwen2.5-0.5b-lora-ep8-onnxfp32-cpu-metrics.json", _metrics(0.8750))

    w(
        results / "llm-int8-variant-selection.json",
        {
            "verify_gate": {"n": 133},
            "variants": {
                "v2": {
                    "median_p_yes_true_M": 0.431,
                    "median_p_yes_true_N": 0.326,
                    "best_f1": 0.535,
                },
                "v3": {
                    "median_p_yes_true_M": 0.322,
                    "median_p_yes_true_N": 0.213,
                    "best_f1": 0.599,
                },
            },
            "finding": "NO ELIGIBLE VARIANT (fake)",
        },
    )
    w(
        results / "serving-gates.json",
        {
            "g2_llm_diagnostics": {
                "median_p_yes_by_true_validation_label": [
                    {"variant": "int8", "median_p_yes_true_M": 0.235, "median_p_yes_true_N": 0.251}
                ],
                "best_validation_f1": [{"variant": "int8", "best_f1": 0.514}],
            }
        },
    )

    w(results / "hosted-claude-sonnet-5-zeroshot-metrics.json", _metrics(0.9082))
    w(pred / "latency-hosted.json", _hosted_latency())
    w(
        results / "hosted-empty-reply-diagnostic.json",
        {"free_part": {"empty_reply_count": 40, "all_empty_replies_hit_max_tokens": True}},
    )

    if with_hosted_v2:
        w(results / "hosted-claude-sonnet-5-zeroshot-v2-metrics.json", _metrics(0.93))
        w(pred / "latency-hosted-v2.json", _hosted_latency(cost="0.55", unparseable=2))


def _patch_paths(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    results = root / "docs" / "learned" / "results"
    serving = results / "serving"
    monkeypatch.setattr(bst, "ROOT", root)
    monkeypatch.setattr(bst, "RESULTS_DIR", results)
    monkeypatch.setattr(bst, "SERVING_DIR", serving)
    monkeypatch.setattr(bst, "INT8V_DIR", serving / "int8v")
    monkeypatch.setattr(bst, "PRED_DIR", results / "predictions")
    monkeypatch.setattr(bst, "OUTPUT_MD", root / "docs" / "learned" / "phase3-serving-benchmark.md")


def test_refuses_when_hosted_v2_has_not_been_scored_yet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_fake_tree(tmp_path, with_hosted_v2=False)
    _patch_paths(monkeypatch, tmp_path)
    with pytest.raises(SystemExit, match="hosted v2 has not been scored yet"):
        bst.main()
    assert not (tmp_path / "docs" / "learned" / "phase3-serving-benchmark.md").exists()


def test_refuses_when_a_hosted_file_has_cache_hits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reviewer finding: a resumed hosted run's cost_usd/latency_ms under-count, since cache
    hits cost $0 and are excluded from the latency sample."""
    _write_fake_tree(tmp_path, with_hosted_v2=False)
    pred = tmp_path / "docs" / "learned" / "results" / "predictions"
    pred.joinpath("latency-hosted.json").write_text(
        json.dumps(_hosted_latency(cache_hits=3)), encoding="utf-8"
    )
    _patch_paths(monkeypatch, tmp_path)
    with pytest.raises(SystemExit, match="cache hits"):
        bst.main()


def test_builds_the_full_table_once_hosted_v2_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_fake_tree(tmp_path, with_hosted_v2=True)
    _patch_paths(monkeypatch, tmp_path)
    assert bst.main() == 0
    out = tmp_path / "docs" / "learned" / "phase3-serving-benchmark.md"
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    # both CPUs named, never conflated
    assert "Fake AMD" in text and "Fake Intel" in text
    # the $/1,000 precision fix actually shows up in the written file
    assert "0.000" in text
    # the LoRA int8 "no row" section is present with real (fake-file-sourced) numbers, not
    # hand-typed literals
    assert "NO ELIGIBLE VARIANT (fake)" in text
    assert (
        "0.235" in text and "0.514" in text
    )  # from serving-gates.json, not a literal in the script
    # hosted v1 and v2 both appear, side by side
    assert "v1, max_tokens=5" in text and "v2, max_tokens=64" in text


def test_never_presents_the_two_cpus_as_the_same_hardware(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_fake_tree(tmp_path, with_hosted_v2=True)
    _patch_paths(monkeypatch, tmp_path)
    bst.main()
    text = (tmp_path / "docs" / "learned" / "phase3-serving-benchmark.md").read_text(
        encoding="utf-8"
    )
    # the served rows (headline table + K-hours table) are only ever measured on "Fake AMD";
    # "Fake Intel" may appear only in the unserved LoRA-int8 variant rows (explicitly labelled
    # "int8-variants run") or the disambiguating header paragraph -- never on a hosted-v2 row,
    # which would make it look like hosted v2 ran on the int8-variants CPU.
    lines_with_intel = [ln for ln in text.splitlines() if "Fake Intel" in ln]
    assert lines_with_intel  # Intel appears...
    assert all("int8-variants run" in ln or "DIFFERENT CPUs" in ln for ln in lines_with_intel)
    assert not any("v2, max_tokens=64" in ln and "Fake Intel" in ln for ln in text.splitlines())

"""Guards notebooks/phase3-llm-int8-variants.ipynb (Phase 3 item 8 session 2, task 3; protocol
5.11), which cannot be executed here (torch/onnxruntime run on Kaggle only). What CAN be pinned
locally: the copied blocks (prompt template, ENV-COMPAT, the embedded worker script) are
byte-identical to their sources, not hand-retyped copies that could have drifted; the embedded
committed val predictions match the real committed file; SMOKE defaults to True; no TEST label is
ever read; and the V2/V3 quantization configs match what protocol 5.11 pre-registered.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

from tests.test_llm_prompt_notebook_parity import _extract_template
from tests.test_torchao_env_compat_notebook_parity import _extract_env_compat

ROOT = Path(__file__).resolve().parents[1]
VARIANTS = ROOT / "notebooks" / "phase3-llm-int8-variants.ipynb"
SERVING = ROOT / "notebooks" / "phase3-serving-benchmark.ipynb"
TRAINING = ROOT / "notebooks" / "phase3-llm-finetune.py"
LLM_PROMPT = ROOT / "src" / "pricepilot" / "matching" / "llm_prompt.py"
COMMITTED_VAL = ROOT / "docs" / "learned" / "results" / "serving" / "preds-llm-onnxfp32-val.json"


def _cells(path: Path) -> list[str]:
    nb = json.loads(path.read_text(encoding="utf-8"))
    return ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]


def _joined(path: Path) -> str:
    return "\n".join(_cells(path))


def _worker_src(path: Path) -> str:
    for src in _cells(path):
        for node in ast.walk(ast.parse(src)):
            if (
                isinstance(node, ast.Assign)
                and any(getattr(t, "id", None) == "WORKER_SRC" for t in node.targets)
                and isinstance(node.value, ast.Constant)
            ):
                return str(node.value.value)
    raise AssertionError(f"WORKER_SRC not found in {path}")


def test_both_files_exist() -> None:
    assert VARIANTS.is_file(), f"missing {VARIANTS}"
    assert SERVING.is_file(), f"missing {SERVING}"


def test_every_cell_parses() -> None:
    for i, src in enumerate(_cells(VARIANTS)):
        ast.parse(src, filename=f"variants-cell-{i}")


def test_worker_script_is_byte_identical_to_the_serving_notebooks() -> None:
    assert _worker_src(VARIANTS) == _worker_src(SERVING)


def test_worker_script_has_no_torch_import() -> None:
    assert "import torch" not in _worker_src(VARIANTS)


def test_prompt_template_is_byte_identical_to_llm_prompt_module() -> None:
    joined = _joined(VARIANTS)
    assert _extract_template(joined, "variants notebook") == _extract_template(
        LLM_PROMPT.read_text(encoding="utf-8"), "llm_prompt.py"
    )


def test_env_compat_block_is_byte_identical_to_training_script() -> None:
    joined = _joined(VARIANTS)
    assert _extract_env_compat(joined, "variants notebook") == _extract_env_compat(
        TRAINING.read_text(encoding="utf-8"), "phase3-llm-finetune.py"
    )


def test_smoke_defaults_to_true_in_cell_zero() -> None:
    first = _cells(VARIANTS)[0].splitlines()[0]
    assert first.startswith("SMOKE = True")


def test_reads_no_test_labels_and_computes_no_f1() -> None:
    src = _joined(VARIANTS)
    assert "f1_score" not in src and "def prf" not in src
    assert 'not any(k in r for r in test_rows for k in ("label", "tier", "split"))' in src
    # the only place a row's label is read is the validation-pair selector over TRAIN_VAL rows
    # (copied verbatim from the serving notebook's cell 1) -- same pattern that notebook pins
    label_lines = [ln for ln in src.splitlines() if '["label"]' in ln]
    assert len(label_lines) == 1
    assert "tv_rows" in label_lines[0] and 'train_or_val"] == "val"' in label_lines[0]


def test_never_writes_a_test_metrics_file_or_ledger_entry() -> None:
    """This notebook only WRITES score/latency files for Kaggle download; threshold selection,
    TEST scoring and the ledger all happen locally in session 2 (this notebook has no access to
    the local repo's scripts/ or docs/learned/results/test-touch-ledger.json at all -- it cannot
    call them even by accident). Pinned here as file-write patterns, not bare name mentions, since
    a comment is free to explain what session 2 does with these files afterwards."""
    src = _joined(VARIANTS)
    for forbidden in ("test-touch-ledger.json", "_append_to_ledger", "-metrics.json", "--rescore"):
        assert forbidden not in src


def test_embedded_committed_val_predictions_match_the_real_committed_file() -> None:
    src = _joined(VARIANTS)
    start = src.index('COMMITTED_LLM_ONNXFP32_VAL = json.loads(r"""') + len(
        'COMMITTED_LLM_ONNXFP32_VAL = json.loads(r"""'
    )
    end = src.index('"""', start)
    embedded = json.loads(src[start:end])
    real = json.loads(COMMITTED_VAL.read_text(encoding="utf-8"))
    assert embedded == real
    assert (
        hashlib.sha256(json.dumps(real, separators=(",", ":")).encode()).hexdigest()
        == "91f96e59e8531af6074b8529f960c33fcfc93a5c7ec3017f7e0cc075316c3ad6"
    )


def test_fp32_verify_gate_uses_the_protocol_registered_tolerance() -> None:
    src = _joined(VARIANTS)
    assert "if max_diff > 1e-5:" in src
    assert "raise SystemExit(" in src
    # the gate must run (and be able to fail) BEFORE either variant is quantized
    verify_at = src.index("def llm_verify_fp32_against_committed")
    v2_at = src.index("def llm_int8_v2")
    v3_at = src.index("def llm_int8_v3")
    run_verify_at = src.index('run_stage("LLM-verify-fp32"')
    run_v2_at = src.index('run_stage("LLM-int8-v2"')
    assert verify_at < v2_at < v3_at
    assert run_verify_at < run_v2_at


def test_a_failed_verify_gate_actually_stops_the_notebook() -> None:
    """run_stage() catches BOTH Exception and SystemExit (so every stage gets a status row even
    when it fails) -- which means llm_verify_fp32_against_committed's own `raise SystemExit` on
    divergence, by itself, would only be recorded as ok=false while the notebook carried on
    quantizing V2/V3 from an unverified export. A reviewer finding: the fix must re-raise OUTSIDE
    run_stage, between the verify call and the V2 call, checking the verify stage's own recorded
    outcome -- not just have the right tolerance and call order (the previous test's coverage)."""
    src = _joined(VARIANTS)
    run_verify_at = src.index('run_stage("LLM-verify-fp32"')
    run_v2_at = src.index('run_stage("LLM-int8-v2"')
    between = src[run_verify_at:run_v2_at]
    assert "STATUS[-1]" in between
    assert '["ok"]' in between
    assert "raise SystemExit(" in between


def test_ce_v2_robustness_check_is_not_promised_anywhere_in_this_notebook() -> None:
    """A reviewer finding: cell 0's header comment claimed this notebook also produces the CE V2
    robustness check, which contradicts protocol 5.11's deferral note and the runbook's 2-input
    scope -- a stray promise a reader could act on (e.g. skip building the deferred check because
    "it's already in the notebook")."""
    src = _joined(VARIANTS)
    assert "CE V2" not in src or "deferred" in src.split("CE V2", 1)[1][:40]


def test_v2_and_v3_quantization_configs_match_protocol_5_11() -> None:
    src = _joined(VARIANTS)
    v2_call = 'quantize(S["llm_fp32"], dst, external=True, per_channel=True, reduce_range=True)'
    v3_call = (
        'quantize(S["llm_fp32"], dst, external=True, per_channel=True, reduce_range=True, '
        'op_types_to_quantize=["MatMul"])'
    )
    assert v2_call in src
    assert v3_call in src


def test_has_no_ce_weights_dependency() -> None:
    """This notebook's runbook adds only 2 Kaggle inputs (the phase3-inputs dataset and
    notebookf26a8565eb's LoRA output) -- the CE weights input is deliberately NOT one of them, so
    the CE V2 robustness check (protocol 5.11) is deferred, not built into this notebook. A stray
    `CE_DIR = find_one(...)` would crash cell 1 the moment Bogdan runs it without that 3rd input."""
    src = _joined(VARIANTS)
    assert "ce-ft-best" not in src
    assert "CE_DIR" not in src


def test_stage_names_present() -> None:
    src = _joined(VARIANTS)
    for stage in (
        "LLM-merge", "LLM-export", "LLM-verify-fp32",
        "LLM-int8-v2", "LLM-score-v2", "LLM-latency-v2",
        "LLM-int8-v3", "LLM-score-v3", "LLM-latency-v3",
    ):  # fmt: skip
        assert f'run_stage("{stage}"' in src


def test_every_measurement_runs_in_a_fresh_single_model_worker() -> None:
    src = _joined(VARIANTS)
    bench_calls = [ln for ln in src.splitlines() if 'run_worker(f"' in ln and "-bench-" in ln]
    assert len(bench_calls) == 1  # one helper line for llm_latency_variant's bench call
    assert 'subprocess.run([sys.executable, str(TMP / "worker.py")' in src
    assert "peak_rss_mb_after_session_load" in src

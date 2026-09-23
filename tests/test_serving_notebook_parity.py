"""Guards notebooks/phase3-serving-benchmark.ipynb (Phase 3 item 8), which cannot be executed here
(torch/onnxruntime run on Kaggle only). What CAN be pinned locally:

* the prompt template is byte-identical to src/pricepilot/matching/llm_prompt.py's -- a drifted
  prompt would make the served LoRA model answer a different question than the one it was trained on;
* the readout token-id resolution is the training notebook's, verbatim;
* every code cell (and the embedded worker script) parses;
* the notebook reads no TEST label and computes no F1;
* SMOKE defaults to True, so a first run is always the cheap one.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from tests.test_llm_prompt_notebook_parity import _extract_template

ROOT = Path(__file__).resolve().parents[1]
SERVING = ROOT / "notebooks" / "phase3-serving-benchmark.ipynb"
TRAINING = ROOT / "notebooks" / "phase3-llm-finetune.py"
LLM_PROMPT = ROOT / "src" / "pricepilot" / "matching" / "llm_prompt.py"


def _cells() -> list[str]:
    nb = json.loads(SERVING.read_text(encoding="utf-8"))
    return ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]


def test_every_cell_parses() -> None:
    for i, src in enumerate(_cells()):
        ast.parse(src, filename=f"serving-cell-{i}")


def test_embedded_worker_script_parses() -> None:
    worker = None
    for src in _cells():
        for node in ast.walk(ast.parse(src)):
            if (
                isinstance(node, ast.Assign)
                and any(getattr(t, "id", None) == "WORKER_SRC" for t in node.targets)
                and isinstance(node.value, ast.Constant)
            ):
                worker = node.value.value
    assert worker, "WORKER_SRC not found"
    ast.parse(worker, filename="worker.py")
    assert "import torch" not in worker, "the serving worker must not import torch"


def test_prompt_template_is_byte_identical_to_llm_prompt_module() -> None:
    joined = "\n".join(_cells())
    assert _extract_template(joined, "serving notebook") == _extract_template(
        LLM_PROMPT.read_text(encoding="utf-8"), "llm_prompt.py"
    )


def test_readout_token_id_resolution_is_the_training_notebooks() -> None:
    """Same code that resolves " Yes"/" No" in the training notebook, character for character."""
    lines = TRAINING.read_text(encoding="utf-8").splitlines()
    start = next(
        i
        for i, ln in enumerate(lines)
        if ln.startswith("tokenizer = AutoTokenizer.from_pretrained")
    )
    end = next(
        i for i, ln in enumerate(lines) if ln.startswith('NO_TOKEN_ID = _single_token_id(" No")')
    )
    training_block = "\n".join(lines[start : end + 1])
    assert '_single_token_id(" Yes")' in training_block
    assert training_block in "\n".join(_cells())


def test_smoke_defaults_to_true_in_cell_zero() -> None:
    first = _cells()[0].splitlines()[0]
    assert first.startswith("SMOKE = True")


def test_reads_no_test_labels_and_computes_no_f1() -> None:
    src = "\n".join(_cells())
    assert "eval-view" not in src
    assert "labels.json" not in src
    assert "f1_score" not in src and "def prf" not in src
    assert 'not any(k in r for r in test_rows for k in ("label", "tier", "split"))' in src
    # the only place a row's label is read is the validation-pair selector over TRAIN_VAL rows
    label_lines = [ln for ln in src.splitlines() if '["label"]' in ln]
    assert len(label_lines) == 1
    assert "tv_rows" in label_lines[0] and 'train_or_val"] == "val"' in label_lines[0]


def test_stage_names_and_exact_output_names_are_present() -> None:
    src = "\n".join(_cells())
    for stage in (
        "CE-reference", "CE-export", "CE-int8", "CE-score", "CE-latency",
        "LLM-merge", "LLM-reference", "LLM-export", "LLM-int8", "LLM-score", "LLM-latency",
    ):  # fmt: skip
        assert f'run_stage("{stage}"' in src
    for name in (
        'f"preds-ce-ptfp32-{name}.json"', 'f"preds-llm-ptfp32-{name}.json"',
        'f"preds-{kind}-{tag}-{name}.json"', 'f"latency-{name}-{variant}.json"',
        '"throughput.json"', '"model-facts.json"', '"env-facts.json"', '"stage-status.json"',
    ):  # fmt: skip
        assert name in src, name


def test_every_measurement_runs_in_a_fresh_single_model_worker() -> None:
    """ru_maxrss is process-lifetime: a bench job must load one ORT session in its own child and
    must not also score (scoring is a separate, unpinned child), and the worker has no torch."""
    src = "\n".join(_cells())
    bench_calls = [ln for ln in src.splitlines() if 'run_worker(f"' in ln and "-bench-" in ln]
    assert len(bench_calls) == 2  # one helper line each for the ce and llm bench loops
    for i, ln in enumerate(src.splitlines()):
        if 'run_worker(f"' in ln and "-bench-" in ln:
            block = "\n".join(src.splitlines()[i : i + 3])
            assert "pin=True" in block and "bench=" in block and "score=" not in block
    assert 'subprocess.run([sys.executable, str(TMP / "worker.py")' in src
    assert "peak_rss_mb_after_session_load" in src
    assert '"avx512_vnni"' in src and '"avx_vnni"' in src

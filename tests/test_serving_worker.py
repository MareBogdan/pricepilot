"""Runs the serving notebook's embedded ONNX worker as a real subprocess, with `onnxruntime`
replaced by a stub (the real one only exists on Kaggle here) and `/proc/self/status` replaced by a
fixture file (the real one only exists on Linux; the worker reads it via job["proc_status_path"],
which defaults to the real path and is overridden only here). What this pins locally: the worker's
tokenize -> pad -> run -> readout -> output-schema path, the Yes/No softmax arithmetic,
padding-invariance of the last-real-token gather, the latency/throughput bookkeeping, and the
VmHWM/VmRSS parsing (ADR-0028 addendum #23: `ru_maxrss` was found to report the parent process's
peak, not the child's, because it survives fork+execve on Linux)."""

from __future__ import annotations

import ast
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import Whitespace

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "phase3-serving-benchmark.ipynb"

STUB_ORT = """
import numpy as np
class ExecutionMode:
    ORT_SEQUENTIAL = 0
class SessionOptions:
    intra_op_num_threads = 0
    inter_op_num_threads = 0
    execution_mode = 0
class _In:
    def __init__(self, name): self.name = name
class InferenceSession:
    def __init__(self, path, so=None, providers=None):
        self.kind = open(path).read().strip()
    def get_inputs(self):
        return [_In("input_ids"), _In("attention_mask")]
    def run(self, _outs, feed):
        n = feed["attention_mask"].sum(axis=1).astype(np.float32)   # real length of each row
        if self.kind == "ce":
            return [(n * 0.01).reshape(-1, 1)]
        return [np.stack([n * 0.1, np.zeros_like(n)], axis=1)]
__version__ = "stub"
"""
# VmHWM 204800 kB -> 200.0 MB (peak), VmRSS 102400 kB -> 100.0 MB (current); real /proc/self/status
# has more fields, the worker only reads these two by line prefix so the rest is irrelevant here.
FAKE_PROC_STATUS = "VmHWM:\t  204800 kB\nVmRSS:\t  102400 kB\n"


def _worker_src() -> str:
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    for c in nb["cells"]:
        for node in ast.walk(ast.parse("".join(c["source"]))):
            if (
                isinstance(node, ast.Assign)
                and any(getattr(t, "id", None) == "WORKER_SRC" for t in node.targets)
                and isinstance(node.value, ast.Constant)
            ):
                return str(node.value.value)
    raise AssertionError("WORKER_SRC not found")


def _tokenizer(path: Path) -> None:
    words = ["[UNK]", *[f"w{i}" for i in range(50)]]
    tok = Tokenizer(WordLevel({w: i for i, w in enumerate(words)}, unk_token="[UNK]"))
    tok.pre_tokenizer = Whitespace()
    tok.save(str(path))


def _run(tmp_path: Path, job: dict) -> None:
    stubs = tmp_path / "stubs"
    stubs.mkdir(exist_ok=True)
    (stubs / "onnxruntime.py").write_text(STUB_ORT, encoding="utf-8")
    status_path = tmp_path / "fake-proc-status"
    status_path.write_text(FAKE_PROC_STATUS, encoding="utf-8")
    job = {**job, "proc_status_path": str(status_path)}
    worker = tmp_path / "worker.py"
    worker.write_text(_worker_src(), encoding="utf-8")
    job_path = tmp_path / "job.json"
    job_path.write_text(json.dumps(job), encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(stubs)}
    r = subprocess.run(
        [sys.executable, str(worker), str(job_path)], capture_output=True, text=True, env=env
    )
    assert r.returncode == 0, r.stderr


def _model_file(tmp_path: Path, kind: str) -> str:
    p = tmp_path / f"{kind}.onnx"
    p.write_text(kind, encoding="utf-8")
    return str(p)


def test_llm_scores_are_softmax_over_yes_no_and_padding_invariant(tmp_path: Path) -> None:
    _tokenizer(tmp_path / "tok.json")
    rows = [
        {"pair_id": f"p{i}", "prompt": " ".join(f"w{j}" for j in range(3 + i))} for i in range(5)
    ]
    (tmp_path / "pairs.json").write_text(json.dumps(rows), encoding="utf-8")
    _run(
        tmp_path,
        {
            "kind": "llm", "name": "llm", "variant": "int8", "pin": False, "pad_id": 0,
            "model": _model_file(tmp_path, "llm"), "tokenizer": str(tmp_path / "tok.json"),
            "score": {"val": {"pairs": str(tmp_path / "pairs.json"), "out": str(tmp_path / "s.json")}},
        },
    )  # fmt: skip
    scores = json.loads((tmp_path / "s.json").read_text())
    assert set(scores) == {r["pair_id"] for r in rows}
    for i in range(5):
        n = 3 + i  # the stub's "yes - no" logit gap is 0.1 * real length
        assert scores[f"p{i}"] == pytest.approx(1 / (1 + math.exp(-0.1 * n)))


def test_ce_scores_are_sigmoid_of_the_single_logit(tmp_path: Path) -> None:
    _tokenizer(tmp_path / "tok.json")
    rows = [{"pair_id": "a", "text_a": "w1 w2", "text_b": "w3 w4 w5"}]
    (tmp_path / "pairs.json").write_text(json.dumps(rows), encoding="utf-8")
    _run(
        tmp_path,
        {
            "kind": "ce", "name": "ce", "variant": "int8", "pin": False, "pad_id": 0,
            "model": _model_file(tmp_path, "ce"), "tokenizer": str(tmp_path / "tok.json"),
            "score": {"test": {"pairs": str(tmp_path / "pairs.json"), "out": str(tmp_path / "s.json")}},
        },
    )  # fmt: skip
    got = json.loads((tmp_path / "s.json").read_text())["a"]
    assert got == pytest.approx(1 / (1 + math.exp(-0.05)))  # 5 tokens * 0.01


def test_bench_output_schema_counts_and_units(tmp_path: Path) -> None:
    _tokenizer(tmp_path / "tok.json")
    rows = [{"pair_id": f"p{i:03d}", "prompt": "w1 w2 w3 w4"} for i in range(40)]
    (tmp_path / "pairs.json").write_text(json.dumps(rows), encoding="utf-8")
    _run(
        tmp_path,
        {
            "kind": "llm", "name": "llm", "variant": "onnxfp32", "pin": False, "pad_id": 0,
            "model": _model_file(tmp_path, "llm"), "tokenizer": str(tmp_path / "tok.json"),
            "bench": {
                "pairs": str(tmp_path / "pairs.json"), "n_warmup": 3, "n_lat": 8,
                "n_thr_batches": 2, "batch": 16, "out": str(tmp_path / "lat.json"),
            },
        },
    )  # fmt: skip
    lat = json.loads((tmp_path / "lat.json").read_text())
    assert len(lat["samples_e2e_ms"]) == len(lat["samples_run_only_ms"]) == 8
    assert all(
        e >= r >= 0 for e, r in zip(lat["samples_e2e_ms"], lat["samples_run_only_ms"], strict=True)
    )
    assert lat["token_length"] == {"min": 4, "p50": 4.0, "p95": 4.0, "max": 4}
    assert lat["throughput"]["pairs"] == 32 and len(lat["throughput"]["batch_seconds"]) == 2
    assert lat["throughput"]["pairs_per_s"] > 0
    assert lat["peak_rss_mb"] == 200.0  # fake VmHWM: 204800 kB
    assert lat["current_rss_mb"] == 100.0  # fake VmRSS: 102400 kB
    assert lat["peak_rss_mb_after_session_load"] == 200.0
    assert lat["current_rss_mb_after_session_load"] == 100.0
    assert lat["peak_rss_mb_after_batch1_latency"] == 200.0
    assert lat["current_rss_mb_after_batch1_latency"] == 100.0
    assert set(lat["summary_e2e_ms"]) == {"p50", "p95", "p99", "mean", "n"}

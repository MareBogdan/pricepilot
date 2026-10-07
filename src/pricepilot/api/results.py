"""Headline model results, read from the committed result files -- never typed in here.

Each loader returns None when its file is missing or malformed (the Docker image may not ship
`docs/`), and the dashboard then shows "n/a" instead of a number it cannot source.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

RESULTS_DIR = Path(__file__).resolve().parents[3] / "docs" / "learned" / "results"
MATCHER_FILE = "mmarco-mMiniLMv2-finetuned-ep6-metrics.json"
BASELINE_FILE = "mmarco-mMiniLMv2-zeroshot-metrics.json"
RAG_FILE = "phase5-policy-retrieval-eval.json"


class MatcherResult(BaseModel):
    f1: float
    precision: float
    recall: float
    baseline_f1: float | None  # the same model without fine-tuning, same test pairs
    threshold: float
    n_test_pairs: int
    source: str


class RagResult(BaseModel):
    hit_at_1: float
    hit_at_3: float
    mrr: float
    n_questions: int
    n_sections: int
    source: str


def _load(name: str) -> dict[str, Any] | None:
    try:
        data = json.loads((RESULTS_DIR / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def matcher_result() -> MatcherResult | None:
    m = _load(MATCHER_FILE)
    if m is None:
        return None
    base = _load(BASELINE_FILE)
    try:
        return MatcherResult(
            f1=m["f1"]["value"],
            precision=m["precision"]["value"],
            recall=m["recall_all_positives"]["value"],
            baseline_f1=base["f1"]["value"] if base else None,
            threshold=m["threshold"],
            n_test_pairs=m["n_scored"],
            source=f"docs/learned/results/{MATCHER_FILE}",
        )
    except (KeyError, TypeError):
        return None


def rag_result() -> RagResult | None:
    r = _load(RAG_FILE)
    if r is None:
        return None
    try:
        return RagResult(
            hit_at_1=r["hit_at_1"],
            hit_at_3=r["hit_at_3"],
            mrr=r["mrr"],
            n_questions=r["n_questions"],
            n_sections=r["n_sections"],
            source=f"docs/learned/results/{RAG_FILE}",
        )
    except (KeyError, TypeError):
        return None

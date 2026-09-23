"""Item 8's hosted zero-shot baseline: answer parsing and latency summary (protocol 5.7).

The prompt is `build_llm_prompt` from `llm_prompt.py` -- the same `llm-prompt-v1` text the LoRA
model was trained on. The reply is parsed strictly: exactly "Yes" -> 1.0, exactly "No" -> 0.0.
Anything else is COUNTED, reported and scored as 0.0; it is never retried into a better answer.
Surrounding whitespace is the only tolerance.
"""

from __future__ import annotations

from typing import Any

import numpy as np

YES_SCORE = 1.0
NO_SCORE = 0.0


def parse_answer(text: str) -> tuple[float, bool]:
    """(score, parsed_ok). An unparseable reply scores 0.0 with parsed_ok False."""
    stripped = text.strip()
    if stripped == "Yes":
        return YES_SCORE, True
    if stripped == "No":
        return NO_SCORE, True
    return NO_SCORE, False


def summarise_latency(samples_ms: list[float]) -> dict[str, Any]:
    """p50/p95/p99/mean over per-call wall-clock ms (linear interpolation, as the serving
    worker does), so the hosted and local numbers use one definition."""
    a = np.asarray(samples_ms, dtype=np.float64)
    if a.size == 0:
        return {"n": 0}
    return {
        "n": int(a.size),
        "p50": float(np.percentile(a, 50)),
        "p95": float(np.percentile(a, 95)),
        "p99": float(np.percentile(a, 99)),
        "mean": float(a.mean()),
    }

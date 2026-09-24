r"""Phase 3 item 8 session 2, task 4: diagnose the hosted zero-shot baseline's 40 empty replies
(`docs/learned/results/predictions/latency-hosted.json` -> `unparseable_replies`, protocol 5.10
item 6).

    uv run python scripts/diagnose_hosted_empty_reply.py            # free part only
    uv run python scripts/diagnose_hosted_empty_reply.py --execute  # + the one paid diagnostic call

Two parts:

1. FREE. For each of the 40 empty-reply TEST pair_ids, recomputes the exact cache key
   `pricepilot.llm.client.cache_key` used for that call (same construction
   `run_hosted_baseline.py` used) and looks up the matching `llm_calls` row by that key, reading
   its `output_tokens` -- no new call, no TEST label read (this only reads what tokens the ALREADY
   MADE call produced, not any pair's correctness).
2. PAID (only with `--execute`, cost < $0.01). ONE diagnostic call on ONE VALIDATION pair (the
   first, by pair_id order, of the 133 -- never TEST), same prompt/model/max_tokens=5 as the
   hosted baseline, through `pricepilot.llm.client.complete_diagnostic` (budget-capped, logged,
   never cached). Prints the raw `stop_reason` and every content block's type and text, which
   `complete()`'s `.text` (used everywhere else) collapses away.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select  # noqa: E402

from pricepilot.db import session_scope  # noqa: E402
from pricepilot.llm.client import (  # noqa: E402
    cache_key,
    complete_diagnostic,
    cost_usd,
    make_sdk_client,
)
from pricepilot.matching.llm_prompt import LLM_PROMPT_VERSION, build_llm_prompt  # noqa: E402
from pricepilot.models import LlmCall  # noqa: E402

LATENCY_HOSTED = ROOT / "docs" / "learned" / "results" / "predictions" / "latency-hosted.json"
INPUTS_TEST = ROOT / "docs" / "learned" / "model-inputs" / "phase3-inputs-test.json"
INPUTS_TRAINVAL = ROOT / "docs" / "learned" / "model-inputs" / "phase3-inputs-train-val.json"
SPLIT_JSON = ROOT / "docs" / "learned" / "phase3-train-val-split.json"
OUTPUT_JSON = ROOT / "docs" / "learned" / "results" / "hosted-empty-reply-diagnostic.json"

MODEL = "claude-sonnet-5"
MAX_TOKENS = 5
TEMPERATURE = None  # protocol 5.10 item 5: the API rejects `temperature` for this model
HOSTED_PURPOSE = "hosted-zeroshot-item8"
DIAGNOSTIC_PURPOSE = "hosted-empty-reply-diagnostic-item8"


def free_part() -> dict[str, Any]:
    latency = json.loads(LATENCY_HOSTED.read_text(encoding="utf-8"))
    empty_pair_ids = {r["pair_id"] for r in latency["unparseable_replies"] if r["raw"] == ""}
    non_empty = len(latency["unparseable_replies"]) - len(empty_pair_ids)
    print(
        f"{len(latency['unparseable_replies'])} unparseable replies total, "
        f"{len(empty_pair_ids)} with raw == '' (empty), {non_empty} non-empty-but-unparseable"
    )

    test_rows = {
        r["pair_id"]: r for r in json.loads(INPUTS_TEST.read_text(encoding="utf-8"))["pairs"]
    }
    keys = {
        pid: cache_key(
            MODEL,
            str(MAX_TOKENS),
            repr(TEMPERATURE),
            "",
            build_llm_prompt(test_rows[pid]["text_a"], test_rows[pid]["text_b"]),
        )
        for pid in empty_pair_ids
    }

    with session_scope() as s:
        by_key = {
            row.cache_key: row
            for row in s.execute(select(LlmCall).where(LlmCall.purpose == HOSTED_PURPOSE)).scalars()
        }

    output_tokens: list[int] = []
    missing_pair_ids: list[str] = []
    for pid, k in keys.items():
        row = by_key.get(k)
        if row is None:
            missing_pair_ids.append(pid)
            continue
        output_tokens.append(row.output_tokens)

    print(
        f"matched {len(output_tokens)}/{len(keys)} llm_calls rows by cache_key "
        f"({len(missing_pair_ids)} missing: {missing_pair_ids[:5]})"
    )
    distinct = sorted(set(output_tokens))
    all_hit_max = distinct == [MAX_TOKENS]
    print(f"distinct output_tokens among the empty replies: {distinct}")
    print(f"ALL hit max_tokens ({MAX_TOKENS})? {all_hit_max}")
    return {
        "unparseable_total": len(latency["unparseable_replies"]),
        "empty_reply_count": len(empty_pair_ids),
        "empty_reply_rate_of_287_test": len(empty_pair_ids) / 287,
        "non_empty_but_unparseable_count": non_empty,
        "matched_llm_calls_rows": len(output_tokens),
        "missing_pair_ids": missing_pair_ids,
        "distinct_output_tokens": distinct,
        "all_empty_replies_hit_max_tokens": all_hit_max,
    }


def _first_validation_pair() -> tuple[str, str, str]:
    """(pair_id, text_a, text_b) of the first VALIDATION pair, by pair_id order. Never TEST."""
    split = json.loads(SPLIT_JSON.read_text(encoding="utf-8"))
    val_ids = sorted(split["val"]["pair_ids"])
    rows = {
        r["pair_id"]: r for r in json.loads(INPUTS_TRAINVAL.read_text(encoding="utf-8"))["pairs"]
    }
    pid = val_ids[0]
    r = rows[pid]
    return pid, r["text_a"], r["text_b"]


def diagnostic_call(*, execute: bool) -> dict[str, Any]:
    pair_id, text_a, text_b = _first_validation_pair()
    prompt = build_llm_prompt(text_a, text_b)
    est_in = len(prompt) // 3 + 1
    est_cost = cost_usd(MODEL, est_in, MAX_TOKENS)
    print(
        f"\nDIAGNOSTIC: {MODEL}, {LLM_PROMPT_VERSION}, max_tokens={MAX_TOKENS}, "
        f"pair_id={pair_id} (VALIDATION, never TEST)"
    )
    print(
        f"SPEND: hosted empty-reply diagnostic, {MODEL}, 1 call — est. ${est_cost:.5f} — proceed?"
    )
    if not execute:
        print("(dry run: nothing was called, nothing was spent)")
        return {"pair_id": pair_id, "executed": False, "estimated_cost_usd": str(est_cost)}
    if est_cost >= Decimal("0.01"):
        raise SystemExit(f"REFUSING: estimated cost ${est_cost} >= $0.01 cap for this diagnostic")

    out = complete_diagnostic(
        model=MODEL,
        prompt=prompt,
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        phase="phase3",
        purpose=DIAGNOSTIC_PURPOSE,
        sdk_client=make_sdk_client(),
    )
    print(f"stop_reason: {out.stop_reason}")
    print(f"content blocks ({len(out.blocks)}):")
    for b in out.blocks:
        print(f"  type={b.type!r} text={b.text!r}")
    print(
        f"usage: input={out.usage.input_tokens} output={out.usage.output_tokens} cost=${out.usage.cost_usd}"
    )
    print(f"latency_ms: {out.latency_ms:.1f}")
    return {
        "pair_id": pair_id,
        "executed": True,
        "stop_reason": out.stop_reason,
        "content_blocks": [{"type": b.type, "text": b.text} for b in out.blocks],
        "input_tokens": out.usage.input_tokens,
        "output_tokens": out.usage.output_tokens,
        "cost_usd": str(out.usage.cost_usd),
        "latency_ms": out.latency_ms,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    ap.add_argument("--execute", action="store_true", help="make the one paid diagnostic call")
    args = ap.parse_args()

    free = free_part()
    diagnostic = diagnostic_call(execute=args.execute)

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(
        json.dumps(
            {
                "built_from": "scripts/diagnose_hosted_empty_reply.py",
                "free_part": free,
                "diagnostic": diagnostic,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"\nwritten: {OUTPUT_JSON.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

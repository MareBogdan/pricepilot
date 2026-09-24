r"""Phase 3 item 8 session 3, task 3: the hosted v2 run (protocol 5.12), correcting session 2's
wrong "no request-config defect" conclusion about v1's 40 empty replies.

    uv run python scripts/run_hosted_baseline_v2.py            # dry run: prints the SPEND line, spends $0
    uv run python scripts/run_hosted_baseline_v2.py --execute  # the paid run, after an explicit "yes"

Identical to `scripts/run_hosted_baseline.py` (v1) except:
- `max_tokens = 64` (was 5) -- room for a reply previously truncated mid-answer to finish.
- Every call's report records the RAW `stop_reason` and every content block's `type`
  (`pricepilot.llm.client.complete()` now carries both on every call, protocol 5.12), not only
  what `llm_calls` logs -- this is what v1's report was missing.
- Parsing is UNCHANGED (`pricepilot.matching.hosted_baseline.parse_answer`): the stripped reply
  must be exactly "Yes" or "No"; anything else is unparseable, scored 0.0, never retried. A longer
  `max_tokens` gives the model room to finish; it does not relax what counts as a valid answer.
- New purpose/ledger id: `hosted-zeroshot-v2-item8` / `hosted-claude-sonnet-5-zeroshot-v2`.

Dry run builds the 287 prompts, estimates input tokens WITHOUT any network call (an ESTIMATE, not
measured), and prints the SPEND line with output priced at the FULL 64 tokens per call (the
upper-bound convention v1 used at max_tokens 5). Every paid call goes through
`pricepilot.llm.client.complete`, so the budget cap, the content-hash cache (a fresh key: v1's
cache, keyed on max_tokens=5, is never read here) and the `llm_calls` log all apply.

Scoring is a separate, later step (`scripts/score_predictions.py`, threshold 0.5, NOT selected).
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from pricepilot.llm.client import Completion, complete, cost_usd, make_sdk_client  # noqa: E402
from pricepilot.matching.hosted_baseline import parse_answer, summarise_latency  # noqa: E402
from pricepilot.matching.llm_prompt import LLM_PROMPT_VERSION, build_llm_prompt  # noqa: E402

INPUTS_TEST = ROOT / "docs" / "learned" / "model-inputs" / "phase3-inputs-test.json"
RESULTS_DIR = ROOT / "docs" / "learned" / "results"
PRED_PATH = RESULTS_DIR / "predictions" / "preds-hosted-v2-test.json"
LATENCY_PATH = RESULTS_DIR / "predictions" / "latency-hosted-v2.json"

DEFAULT_MODEL = "claude-sonnet-5"
MAX_TOKENS = 64  # protocol 5.12 -- v1 used 5
TEMPERATURE = None  # protocol 5.10 item 5: the API rejects `temperature` for this model
PHASE = "phase3"
PURPOSE = "hosted-zeroshot-v2-item8"
EXPECTED_PAIRS = 287


def load_prompts(path: Path = INPUTS_TEST) -> list[tuple[str, str]]:
    """[(pair_id, prompt)] in pair_id order. Refuses any file that carries labels."""
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = sorted(data["pairs"], key=lambda r: r["pair_id"])
    if any(k in r for r in rows for k in ("label", "tier", "split")):
        raise SystemExit("REFUSING TO RUN: the TEST inputs file carries label/tier/split fields")
    if len(rows) != EXPECTED_PAIRS:
        raise SystemExit(f"REFUSING TO RUN: {len(rows)} TEST pairs, expected {EXPECTED_PAIRS}")
    return [(r["pair_id"], build_llm_prompt(r["text_a"], r["text_b"])) for r in rows]


def estimate(prompts: list[tuple[str, str]], model: str) -> tuple[int, Decimal]:
    """(approx input tokens, upper-bound cost). Output is priced at the full max_tokens."""
    in_tokens = sum(len(p) // 3 + 1 for _, p in prompts)
    return in_tokens, cost_usd(model, in_tokens, MAX_TOKENS * len(prompts))


def run(
    model: str,
    prompts: list[tuple[str, str]],
    *,
    sdk_client: Any | None = None,
    cache_dir: Path | None = None,
) -> tuple[dict[str, float], dict[str, Any]]:
    """Makes the calls (through the wrapper) and returns (scores, latency/cost/diagnostic report)."""
    if sdk_client is None:  # ONE pooled client for the whole run (no per-call TLS handshake)
        sdk_client = make_sdk_client()
    scores: dict[str, float] = {}
    latencies: list[float] = []
    unparsed: list[dict[str, str]] = []
    per_call: list[dict[str, Any]] = []
    in_tok = out_tok = cache_hits = 0
    total_cost = Decimal("0")
    for pair_id, prompt in prompts:
        c: Completion = complete(
            model=model,
            prompt=prompt,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            phase=PHASE,
            purpose=PURPOSE,
            estimated_input_tokens=len(prompt) // 3 + 1,
            sdk_client=sdk_client,
            cache_dir=cache_dir,
        )
        if c.cache_hit and c.stop_reason is None:
            # This can only happen if v2's own cache key (max_tokens=64) somehow collided with a
            # pre-5.12 cache entry -- the protection this script exists to add would silently be
            # gone for this pair. Refuse rather than record a diagnostic report with a hole in it.
            raise SystemExit(
                f"REFUSING: pair_id={pair_id} was served from a pre-5.12 cache entry "
                "(stop_reason is None) -- v2's own key must never collide with v1's."
            )
        score, ok = parse_answer(c.text)
        scores[pair_id] = score
        per_call.append(
            {
                "pair_id": pair_id,
                "stop_reason": c.stop_reason,
                "block_types": c.block_types,
                "raw": c.text,
                "parsed_ok": ok,
            }
        )
        if not ok:
            unparsed.append({"pair_id": pair_id, "raw": c.text})
        in_tok += c.usage.input_tokens
        out_tok += c.usage.output_tokens
        total_cost += c.usage.cost_usd
        if c.cache_hit:
            cache_hits += 1
        elif c.latency_ms is not None:
            latencies.append(c.latency_ms)

    stop_reason_counts = Counter(pc["stop_reason"] for pc in per_call)
    block_type_counts = Counter(bt for pc in per_call for bt in pc["block_types"])

    report = {
        "built_from": "scripts/run_hosted_baseline_v2.py",
        "model": model,
        "prompt_version": LLM_PROMPT_VERSION,
        "temperature": "NOT SENT: the API rejects it for this model (protocol 5.7/5.10 deviation)",
        "max_tokens": MAX_TOKENS,
        "threshold": 0.5,
        "threshold_note": "fixed at 0.5, NOT selected on any data",
        "pairs": len(prompts),
        "cache_hits": cache_hits,
        "unparseable": len(unparsed),
        "unparseable_replies": unparsed,
        "stop_reason_counts": dict(stop_reason_counts),
        "block_type_counts": dict(block_type_counts),
        "per_call": per_call,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cost_usd": str(total_cost),
        "latency_note": "wall-clock per API call from Romania, includes network; cache hits excluded",
        "latency_ms": summarise_latency(latencies),
        "per_call_ms": latencies,
    }
    return scores, report


def logged_cost() -> Decimal:
    """Authoritative spend for this run: sum of llm_calls.cost_usd for the purpose. A resumed run
    serves finished pairs from cache at $0, so one invocation's own total would under-state it."""
    from sqlalchemy import select

    from pricepilot.db import session_scope
    from pricepilot.models import LlmCall

    with session_scope() as s:
        rows = s.execute(select(LlmCall.cost_usd).where(LlmCall.purpose == PURPOSE)).scalars().all()
    return sum(rows, Decimal("0"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--execute", action="store_true", help="make the paid calls (default: dry run)")
    args = ap.parse_args()

    prompts = load_prompts()
    in_tokens, est = estimate(prompts, args.model)
    print(
        f"{len(prompts)} TEST prompts, {LLM_PROMPT_VERSION}, max_tokens={MAX_TOKENS}, "
        "temperature=not sent (API rejects it for this model)"
    )
    print(
        f"input tokens ~{in_tokens} (ESTIMATE: 1 token per 3 characters, no network call, not "
        f"measured; Sonnet 5's tokenizer may count ~30% more). Output priced at the full {MAX_TOKENS} tokens per call."
    )
    print(
        f"SPEND: hosted v2, {args.model}, {len(prompts)} calls, max_tokens {MAX_TOKENS} "
        f"— est. ${est:.2f} — proceed?"
    )
    if not args.execute:
        print("(dry run: nothing was called, nothing was spent)")
        return 0

    scores, report = run(args.model, prompts)
    PRED_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRED_PATH.write_text(json.dumps(scores, indent=1), encoding="utf-8")
    LATENCY_PATH.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(
        f"done: {report['pairs']} pairs, {report['cache_hits']} cache hits, "
        f"{report['unparseable']} unparseable, "
        f"tokens in/out {report['input_tokens']}/{report['output_tokens']}"
    )
    print(f"stop_reason counts: {report['stop_reason_counts']}")
    print(f"content block-type counts: {report['block_type_counts']}")
    print(f"ACTUAL cost this invocation ${report['cost_usd']} vs estimated ${est:.2f}")
    print(f"llm_calls total for this purpose: ${logged_cost():.6f} (authoritative if resumed)")
    print(f"latency ms: {report['latency_ms']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

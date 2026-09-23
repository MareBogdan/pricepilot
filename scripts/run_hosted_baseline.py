r"""Phase 3 item 8: the hosted zero-shot baseline on the 287 TEST pairs (protocol 5.7).

    uv run python scripts/run_hosted_baseline.py            # dry run: prints the SPEND line, spends $0
    uv run python scripts/run_hosted_baseline.py --execute  # the paid run, after an explicit "yes"

Dry run is the default. It builds the 287 prompts, estimates input tokens WITHOUT any network call
(an ESTIMATE of 1 token per 3 characters, not measured; the actual token counts are logged
by the wrapper and reported after the run), and prints the SPEND line. It reads the TEST *inputs*
(text only, no labels). Every paid call goes through `pricepilot.llm.client.complete`, so the
`LLM_BUDGET_USD` cap, the content-hash cache and the `llm_calls` log all apply.

Scoring is a separate, later step (`scripts/score_predictions.py`, threshold 0.5, NOT selected).
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

from pricepilot.llm.client import Completion, complete, cost_usd, make_sdk_client  # noqa: E402
from pricepilot.matching.hosted_baseline import parse_answer, summarise_latency  # noqa: E402
from pricepilot.matching.llm_prompt import LLM_PROMPT_VERSION, build_llm_prompt  # noqa: E402

INPUTS_TEST = ROOT / "docs" / "learned" / "model-inputs" / "phase3-inputs-test.json"
RESULTS_DIR = ROOT / "docs" / "learned" / "results"
PRED_PATH = RESULTS_DIR / "predictions" / "preds-hosted-test.json"
LATENCY_PATH = RESULTS_DIR / "predictions" / "latency-hosted.json"

DEFAULT_MODEL = "claude-sonnet-5"
MAX_TOKENS = 5
# Protocol 5.7 pre-registered temperature 0. claude-sonnet-5's API answers 400 "`temperature` is
# deprecated for this model" (request_id req_011CfM2h7y8RASFkHdhMxhkc, nothing billed), so it is NOT
# sent and the model's default sampling applies. Stated deviation; see the protocol doc.
TEMPERATURE = None
PHASE = "phase3"
PURPOSE = "hosted-zeroshot-item8"
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
    """Makes the calls (through the wrapper) and returns (scores, latency/cost report)."""
    if sdk_client is None:  # ONE pooled client for the whole run (no per-call TLS handshake)
        sdk_client = make_sdk_client()
    scores: dict[str, float] = {}
    latencies: list[float] = []
    unparsed: list[dict[str, str]] = []
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
        score, ok = parse_answer(c.text)
        scores[pair_id] = score
        if not ok:
            unparsed.append({"pair_id": pair_id, "raw": c.text})
        in_tok += c.usage.input_tokens
        out_tok += c.usage.output_tokens
        total_cost += c.usage.cost_usd
        if c.cache_hit:
            cache_hits += 1
        elif c.latency_ms is not None:
            latencies.append(c.latency_ms)
    report = {
        "built_from": "scripts/run_hosted_baseline.py",
        "model": model,
        "prompt_version": LLM_PROMPT_VERSION,
        "temperature": "NOT SENT: the API rejects it for this model (protocol 5.7 deviation)",
        "max_tokens": MAX_TOKENS,
        "threshold": 0.5,
        "threshold_note": "fixed at 0.5, NOT selected on any data",
        "pairs": len(prompts),
        "cache_hits": cache_hits,
        "unparseable": len(unparsed),
        "unparseable_replies": unparsed,
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
        f"SPEND: hosted zero-shot baseline, {args.model}, {len(prompts)} calls "
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
    print(f"ACTUAL cost this invocation ${report['cost_usd']} vs estimated ${est:.2f}")
    print(f"llm_calls total for this purpose: ${logged_cost():.6f} (authoritative if resumed)")
    print(f"latency ms: {report['latency_ms']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

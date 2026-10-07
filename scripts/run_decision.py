r"""Phase 5 session 4 -- run the decision engine on a few products with the MOCK proposer ($0).

    $env:PRICEPILOT_DB_DRIVER = "pg8000"      # if psycopg is blocked (ADR-0038)
    .venv\Scripts\python scripts/run_decision.py --product-ids 20 \
        [--strategy toward_cheapest|keep|below_floor|discount_3pct|malformed] \
        [--run-label s4-mock] [--dry-run] [--show-prompt]

This script has NO real-LLM option on purpose: the 50 real recommendations are session 5, a
separate SPEND-approved run (ADR-0042). It prints `llm_calls` row count / spend before and after, so
"$0" is shown, not asserted. `--dry-run` runs everything but writes no `recommendations` row.
"""

from __future__ import annotations

import argparse
import io
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import func, select  # noqa: E402

from pricepilot.db import check_database, session_scope  # noqa: E402
from pricepilot.decision.engine import decide, gather_snapshot  # noqa: E402
from pricepilot.decision.proposer import MOCK_STRATEGIES, MockProposer  # noqa: E402
from pricepilot.models import LlmCall, Recommendation  # noqa: E402


def llm_ledger() -> tuple[int, Decimal]:
    with session_scope() as session:
        count, spend = session.execute(
            select(func.count(), func.coalesce(func.sum(LlmCall.cost_usd), 0)).select_from(LlmCall)
        ).one()
    return int(count), Decimal(str(spend))


def print_trace(row: Recommendation, *, show_prompt: bool) -> None:
    print(
        f"--- product {row.product_id} ({row.category}) | run {row.run_label} | mock={row.is_mock}"
    )
    print(
        f"  inputs : cost {row.cost}  price {row.current_price}  stock {row.stock}  "
        f"7d-ago {row.price_7d_ago} [{row.price_7d_ago_source}]"
    )
    comps = ", ".join(f"{c['shop']} {c['price']}" for c in row.competitor_prices) or "(none)"
    print(f"  matches: {comps}")
    print(f"  elastic: {row.elasticity_placeholder['label']}")
    rag = ", ".join(f"s{r['section_ref']} {r['similarity']}" for r in row.rag_sections)
    print(f"  rag    : {rag}")
    print(
        f"  LLM    : model={row.llm_model} proposed={row.llm_proposed_price} "
        f"cost=${row.llm_cost_usd} latency={row.llm_latency_ms}ms"
    )
    print(f"           rationale: {row.llm_rationale}")
    print(f"  GUARD  : {row.guard_status} final={row.guard_final_price} reason={row.guard_reason}")
    if show_prompt:
        print("  --- prompt ---")
        print(row.prompt_text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--product-ids", type=int, nargs="+", required=True)
    parser.add_argument("--strategy", choices=sorted(MOCK_STRATEGIES), default="toward_cheapest")
    parser.add_argument("--run-label", default="s4-mock")
    parser.add_argument("--dry-run", action="store_true", help="run, print, write no trace row")
    parser.add_argument("--show-prompt", action="store_true")
    args = parser.parse_args()

    if not check_database():
        print("database unreachable (if psycopg is blocked, set PRICEPILOT_DB_DRIVER=pg8000)")
        return 1

    calls_before, spend_before = llm_ledger()
    proposer = MockProposer(args.strategy)
    for product_id in args.product_ids:
        with session_scope() as session:
            snapshot = gather_snapshot(session, product_id)
            row = decide(snapshot, proposer=proposer, run_label=args.run_label)
            if not args.dry_run:
                session.add(row)
        print_trace(row, show_prompt=args.show_prompt)
    calls_after, spend_after = llm_ledger()

    print(
        f"\nllm_calls rows: {calls_before} -> {calls_after}; spend ${spend_before} -> ${spend_after}"
    )
    if (calls_after, spend_after) != (calls_before, spend_before):
        print("ERROR: the ledger moved during a mock run")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

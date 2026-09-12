"""`make cost` — LLM spend to date, broken down by phase and model (CLAUDE.md §5.7).

Numbers come from the `llm_calls` table only. docs/COSTS.md is the narrative ledger
(it also records non-LLM spend like GPU and hosting); this is the machine-checkable half.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    from sqlalchemy import func, select

    from pricepilot.config import get_settings
    from pricepilot.db import check_database, session_scope
    from pricepilot.models import LlmCall

    if not check_database():
        print("Database unreachable — cannot report spend. Run `docker compose up -d db`.")
        return 1

    with session_scope() as s:
        rows = s.execute(
            select(
                LlmCall.phase,
                LlmCall.model,
                func.count(),
                func.sum(func.cast(LlmCall.cache_hit, __import__("sqlalchemy").Integer)),
                func.sum(LlmCall.input_tokens),
                func.sum(LlmCall.output_tokens),
                func.sum(LlmCall.cost_usd),
            )
            .group_by(LlmCall.phase, LlmCall.model)
            .order_by(LlmCall.phase)
        ).all()

    budget = get_settings().llm_budget_usd
    if not rows:
        print(f"No LLM calls logged. Spend to date: $0.00 (budget ${budget:.2f}).")
        return 0

    print(f"{'phase':<10} {'model':<28} {'calls':>6} {'hits':>5} {'in':>9} {'out':>8} {'usd':>10}")
    print("-" * 80)
    total = 0.0
    for phase, model, calls, hits, tin, tout, cost in rows:
        total += float(cost or 0)
        print(
            f"{phase:<10} {model:<28} {calls:>6} {hits or 0:>5} "
            f"{tin or 0:>9,} {tout or 0:>8,} {float(cost or 0):>10.6f}"
        )
    print("-" * 80)
    print(f"{'TOTAL':<45} {total:>34.6f}")
    print(
        f"Budget ${budget:.2f} — {'OK' if total <= budget else 'EXCEEDED'} "
        f"(${budget - total:.4f} remaining)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

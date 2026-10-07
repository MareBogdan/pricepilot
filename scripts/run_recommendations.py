r"""Phase 5 session 5 -- the 50 recommendations (ADR-0042): 30 baseline + 20 hypothetical scenarios.

    $env:PRICEPILOT_DB_DRIVER = "pg8000"      # if psycopg is blocked (ADR-0038)
    .venv\Scripts\python scripts/run_recommendations.py                 # DRY RUN: plan + estimate, $0
    .venv\Scripts\python scripts/run_recommendations.py --execute       # PAID: needs a SPEND approval

The dry run builds all 50 prompts (SQL + local RAG retrieval, no LLM) and prints a cost estimate
from the published per-token prices. `--execute` sends them through `LlmProposer`
(`client.complete`: disk cache, budget cap, `llm_calls` row) -> strict parse -> `guard.enforce` ->
`recommendations` (`is_mock = false`). Each item commits on its own, and an item that already has a
row for this run label is skipped, so a crash never pays twice for the same (product, scenario).
"""

from __future__ import annotations

import argparse
import io
import sys
from decimal import Decimal
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import func, select  # noqa: E402

from pricepilot.db import check_database, session_scope  # noqa: E402
from pricepilot.decision.engine import (  # noqa: E402
    SYSTEM_PROMPT,
    build_prompt,
    decide,
    gather_snapshot,
    policy_query,
)
from pricepilot.decision.proposer import LlmProposer  # noqa: E402
from pricepilot.decision.scenarios import (  # noqa: E402
    EXPECTED_TOTAL,
    PlanItem,
    apply_scenario,
    build_plan,
)
from pricepilot.llm.client import cost_usd, make_sdk_client, spend_to_date  # noqa: E402
from pricepilot.models import LlmCall, Product, ProductMatch, Recommendation  # noqa: E402
from pricepilot.policy.retrieval import retrieve_policy  # noqa: E402
from pricepilot.policy.thresholds import load_thresholds  # noqa: E402

DEFAULT_MODEL = "claude-sonnet-5"
# The reply is `PRICE: x` + 1-3 sentences: ~100 tokens. Used only for the ESTIMATE; `max_tokens`
# below is the hard cap and drives the pre-call budget check inside `complete()`.
EXPECTED_OUTPUT_TOKENS = 100


@cache
def cached_retrieve(query: str, k: int) -> tuple:  # type: ignore[type-arg]
    return tuple(retrieve_policy(query, k))


def retriever(query: str, k: int) -> list:  # type: ignore[type-arg]
    return list(cached_retrieve(query, k))


def label(item: PlanItem) -> str:
    return f"p{item.product_id}/{item.scenario or 'baseline'}"


def load_plan() -> list[PlanItem]:
    with session_scope() as session:
        product_ids = list(session.execute(select(Product.id)).scalars())
        matched = list(session.execute(select(ProductMatch.product_id).distinct()).scalars())
    return build_plan(product_ids, matched)


def llm_ledger() -> tuple[int, Decimal]:
    with session_scope() as session:
        count = session.execute(select(func.count()).select_from(LlmCall)).scalar_one()
    return int(count), spend_to_date()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--execute", action="store_true", help="PAID: call the LLM for each item")
    parser.add_argument("--run-label", default="s5-real")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-tokens", type=int, default=400)
    args = parser.parse_args()

    if not check_database():
        print("database unreachable (if psycopg is blocked, set PRICEPILOT_DB_DRIVER=pg8000)")
        return 1
    plan = load_plan()
    if len(plan) != EXPECTED_TOTAL or len(set(plan)) != len(plan):
        print(f"plan is {len(plan)} items ({len(set(plan))} distinct), expected {EXPECTED_TOTAL}")
        return 1
    n_matched = sum(1 for i in plan if i.scenario == "undercut_15")
    n_u30 = sum(1 for i in plan if i.scenario == "undercut_30")
    print(
        f"plan: {sum(1 for i in plan if i.scenario is None)} baseline + {n_matched} undercut_15 "
        f"+ {n_u30} undercut_30 = {len(plan)} distinct (product, scenario)"
    )

    thresholds = load_thresholds()
    prompts: list[tuple[PlanItem, str]] = []
    with session_scope() as session:
        for item in plan:
            snap = apply_scenario(gather_snapshot(session, item.product_id), item.scenario)
            prompts.append(
                (item, build_prompt(snap, retriever(policy_query(snap.category), 3), thresholds))
            )

    est_in = sum(len(SYSTEM_PROMPT + p) // 3 + 1 for _, p in prompts)  # pessimistic: 3 chars/token
    est = cost_usd(args.model, est_in, EXPECTED_OUTPUT_TOKENS * len(prompts))
    ceiling = cost_usd(args.model, est_in, args.max_tokens * len(prompts))
    calls_before, spend_before = llm_ledger()
    print(
        f"model {args.model}: ~{est_in:,} input tokens, ~{EXPECTED_OUTPUT_TOKENS * len(prompts):,} "
        f"output tokens -> ESTIMATE ${est:.4f} (hard ceiling at max_tokens={args.max_tokens}: "
        f"${ceiling:.4f})"
    )
    print(f"ledger now: {calls_before} llm_calls rows, ${spend_before} spent")
    if not args.execute:
        print("DRY RUN: nothing sent. Re-run with --execute after the SPEND approval.")
        return 0

    sdk = make_sdk_client()
    proposer = LlmProposer(args.model, max_tokens=args.max_tokens, sdk_client=sdk)
    done = skipped = 0
    for item in plan:
        with session_scope() as session:
            exists = session.execute(
                select(func.count())
                .select_from(Recommendation)
                .where(
                    Recommendation.run_label == args.run_label,
                    Recommendation.product_id == item.product_id,
                    Recommendation.scenario.is_(item.scenario)
                    if item.scenario is None
                    else Recommendation.scenario == item.scenario,
                    Recommendation.is_mock.is_(False),
                )
            ).scalar_one()
            if exists:
                skipped += 1
                continue
            snap = apply_scenario(gather_snapshot(session, item.product_id), item.scenario)
            row = decide(
                snap,
                proposer=proposer,
                run_label=args.run_label,
                retriever=retriever,
                scenario=item.scenario,
            )
            session.add(row)
        done += 1
        print(
            f"[{done + skipped:>2}/{len(plan)}] {label(item):<22} proposed={row.llm_proposed_price} "
            f"-> {row.guard_status} {row.guard_final_price or ''} cost=${row.llm_cost_usd}"
        )
    calls_after, spend_after = llm_ledger()
    print(f"\nran {done}, skipped {skipped} already-done")
    print(
        f"llm_calls rows: {calls_before} -> {calls_after}; spend ${spend_before} -> ${spend_after} "
        f"(this run: ${spend_after - spend_before})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

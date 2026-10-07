r"""Phase 5 -- the 50 recommendations (ADR-0042, reframed by ADR-0045): 30 baseline + 20 stress-tests.

    $env:PRICEPILOT_DB_DRIVER = "pg8000"      # if psycopg is blocked (ADR-0038)
    .venv\Scripts\python scripts/run_recommendations.py                       # DRY RUN, $0
    .venv\Scripts\python scripts/run_recommendations.py --execute             # PAID: needs a SPEND yes
    .venv\Scripts\python scripts/run_recommendations.py --refresh --max-tokens 1500 [--execute]

The dry run builds the selected prompts (SQL + local RAG retrieval, no LLM) and prints a cost
estimate from the published per-token prices. `--execute` sends them through `LlmProposer`
(`client.complete`: disk cache, budget cap, `llm_calls` row) -> strict parse -> `guard.enforce` ->
`recommendations` (`is_mock = false`). Each item commits on its own, and an item that already has a
complete row (a normal stop_reason) for this run label is skipped, so a crash never pays twice.

`--refresh` (s5b) selects only (a) baseline items whose stored reply was cut off or otherwise
abnormal and (b) every `stress_*` item. For each selected item the OLD row(s) are relabelled
`s5-superseded` in the SAME transaction that inserts the new one: nothing is deleted, and the gate
report (which reads only the run label) sees exactly one row per (product, scenario).
"""

from __future__ import annotations

import argparse
import io
import sys
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import func, select  # noqa: E402

from pricepilot.db import check_database, session_scope  # noqa: E402
from pricepilot.decision.engine import (  # noqa: E402
    NORMAL_STOP_REASONS,
    SYSTEM_PROMPT,
    build_prompt,
    decide,
    gather_snapshot,
    policy_query,
)
from pricepilot.decision.proposer import LlmProposer  # noqa: E402
from pricepilot.decision.scenarios import (  # noqa: E402
    EXPECTED_TOTAL,
    STRESS_PREFIX,
    PlanItem,
    apply_scenario,
    build_plan,
    is_stress,
)
from pricepilot.llm.client import cost_usd, make_sdk_client, spend_to_date  # noqa: E402
from pricepilot.models import LlmCall, Product, ProductMatch, Recommendation  # noqa: E402
from pricepilot.policy.retrieval import PolicyPassage, retrieve_policy  # noqa: E402
from pricepilot.policy.thresholds import load_thresholds  # noqa: E402

DEFAULT_MODEL = "claude-sonnet-5"
# Used only for the ESTIMATE; `--max-tokens` is the hard cap and drives the pre-call budget check
# inside `complete()`. 204 = mean of the 50 real replies in the s5 run (10,180 out tokens / 50).
EXPECTED_OUTPUT_TOKENS = 204
SUPERSEDED_LABEL = "s5-superseded"


@cache
def cached_retrieve(query: str, k: int) -> tuple[PolicyPassage, ...]:
    return tuple(retrieve_policy(query, k))


def retriever(query: str, k: int) -> list[PolicyPassage]:
    return list(cached_retrieve(query, k))


def label(item: PlanItem) -> str:
    return f"p{item.product_id}/{item.scenario or 'baseline'}"


def legacy_scenario(scenario: str) -> str:
    """The name a stress item had before ADR-0045 (`stress_undercut_15` was `undercut_15`)."""
    return scenario[len(STRESS_PREFIX) :]


def rows_for(
    session: Any, run_label: str, product_id: int, scenario: str | None
) -> list[Recommendation]:
    clause = (
        Recommendation.scenario.is_(None)
        if scenario is None
        else Recommendation.scenario == scenario
    )
    return list(
        session.execute(
            select(Recommendation).where(
                Recommendation.run_label == run_label,
                Recommendation.product_id == product_id,
                Recommendation.is_mock.is_(False),
                clause,
            )
        ).scalars()
    )


def is_complete(rows: list[Recommendation]) -> bool:
    """A row exists and its reply ended normally."""
    return any(r.llm_stop_reason in NORMAL_STOP_REASONS for r in rows)


def needs_refresh(session: Any, run_label: str, item: PlanItem) -> bool:
    """Stress items always (they were re-framed, ADR-0045) unless already refreshed; a baseline
    item only if its stored reply was not a normal completion."""
    return not is_complete(rows_for(session, run_label, item.product_id, item.scenario))


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
    parser.add_argument("--refresh", action="store_true", help="only truncated baselines + stress")
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
    n_base = sum(1 for i in plan if i.scenario is None)
    print(f"plan: {n_base} baseline + {len(plan) - n_base} stress-tests = {len(plan)} distinct")

    with session_scope() as session:
        selected = (
            [i for i in plan if needs_refresh(session, args.run_label, i)] if args.refresh else plan
        )
    base_sel = [label(i) for i in selected if i.scenario is None]
    print(
        f"selected {len(selected)} item(s): baseline {base_sel or 'none'} + "
        f"{sum(1 for i in selected if is_stress(i.scenario))} stress-tests"
    )

    thresholds = load_thresholds()
    prompts: list[tuple[PlanItem, str]] = []
    with session_scope() as session:
        for item in selected:
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
        f"output tokens (mean of the s5 run) -> ESTIMATE ${est:.4f}; hard ceiling at "
        f"max_tokens={args.max_tokens}: ${ceiling:.4f}"
    )
    print(f"ledger now: {calls_before} llm_calls rows, ${spend_before} spent")
    if not args.execute:
        print("DRY RUN: nothing sent. Re-run with --execute after the SPEND approval.")
        return 0

    sdk = make_sdk_client()
    proposer = LlmProposer(args.model, max_tokens=args.max_tokens, sdk_client=sdk)
    done = skipped = 0
    for item in selected:
        with session_scope() as session:
            existing = rows_for(session, args.run_label, item.product_id, item.scenario)
            if is_complete(existing):
                skipped += 1
                continue
            if args.refresh:
                # Supersede (relabel, never delete) in the SAME transaction as the insert below: the
                # old cut-off row of this item and, for a stress item, the pre-ADR-0045 row.
                old_rows = list(existing)
                if is_stress(item.scenario):
                    assert item.scenario is not None
                    old_rows += rows_for(
                        session, args.run_label, item.product_id, legacy_scenario(item.scenario)
                    )
                for old in old_rows:
                    old.run_label = SUPERSEDED_LABEL
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
            f"[{done + skipped:>2}/{len(selected)}] {label(item):<26} proposed={row.llm_proposed_price} "
            f"-> {row.guard_status} {row.guard_final_price or ''} stop={row.llm_stop_reason} "
            f"cost=${row.llm_cost_usd}"
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

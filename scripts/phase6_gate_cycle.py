r"""Phase 6 GATE: one complete cycle, end to end, visible in logs (ADR-0047).

    $env:PRICEPILOT_DB_DRIVER = "pg8000"      # if psycopg is blocked (ADR-0038)
    .venv\Scripts\python scripts/phase6_gate_cycle.py [--recommendation-id N] [--confirm]

Starts the mock store (uvicorn, port 8001) as a subprocess, picks ONE real guard-APPROVE-with-move
recommendation (scenario NULL: real inputs, never a stress-test row), shows the human-approval
prompt, applies it, verifies the store price, the store's /audit-log and our action_log, proves a
second apply does not double-write, rolls it back (second approval prompt), verifies the restore, and
prints the whole trail. Every verification is an assert: the exit code is 0 only if the cycle held.

Approval is a real y/N prompt on a terminal; `--confirm` answers yes for a non-interactive run and says
so in the output and in the recorded actor. The mock store is a local fixture held in process memory;
the action_log rows are written to the real database and stay there as the evidence.
"""

from __future__ import annotations

import argparse
import io
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import func, select  # noqa: E402

from pricepilot.actions.apply import (  # noqa: E402
    ALREADY_APPLIED,
    APPLIED,
    ApprovalRequest,
    apply_recommendation,
)
from pricepilot.actions.rollback import ROLLED_BACK, rollback_action  # noqa: E402
from pricepilot.actions.store import HttpStore  # noqa: E402
from pricepilot.db import check_database, session_scope  # noqa: E402
from pricepilot.models import ActionLog, Recommendation  # noqa: E402

PORT = 8001
URL = f"http://127.0.0.1:{PORT}"


def banner(text: str) -> None:
    print(f"\n=== {text} ===")


def start_store() -> subprocess.Popen[bytes]:
    try:
        httpx.get(f"{URL}/health", timeout=1.0)
    except httpx.HTTPError:
        pass
    else:
        raise SystemExit(
            f"something already answers on {URL}; stop it first (its state is unknown)"
        )
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "services.mock_store.app:app", "--port", str(PORT),
         "--log-level", "warning"],
        cwd=ROOT,
    )  # fmt: skip
    for _ in range(100):
        try:
            if httpx.get(f"{URL}/health", timeout=1.0).status_code == 200:
                return proc
        except httpx.HTTPError:
            time.sleep(0.2)
    proc.terminate()
    raise SystemExit("mock store did not start on port 8001 (is it already running?)")


def print_action_rows(rec_id: int, since_id: int = 0) -> list[ActionLog]:
    with session_scope() as session:
        rows = list(
            session.scalars(
                select(ActionLog)
                .where(ActionLog.recommendation_id == rec_id, ActionLog.id > since_id)
                .order_by(ActionLog.id)
            )
        )
    print(
        f"  {'id':>3} {'action':<14} {'previous':>8} {'new':>8} {'audit ref':<13} {'reverted_by':>11}  actor"
    )
    for r in rows:
        print(
            f"  {r.id:>3} {r.action:<14} {r.previous_price!s:>8} "
            f"{r.new_price if r.new_price is not None else '-':>8} {r.mock_store_audit_ref or '-':<13} "
            f"{r.reverted_by or '-':>11}  {r.actor}"
        )
        print(f"      reason: {r.reason}")
    return rows


def print_store_log(store: HttpStore) -> None:
    for i, e in enumerate(store.audit_log()):
        print(
            f"  audit-log[{i}] product {e.product_id}: {e.previous_price} -> {e.new_price}  | {e.reason}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--recommendation-id", type=int)
    parser.add_argument(
        "--confirm", action="store_true", help="answer yes to both approval prompts"
    )
    args = parser.parse_args()
    actor = "bogdan-cli (--confirm, gate run)" if args.confirm else "bogdan-cli"

    def approve(request: ApprovalRequest) -> bool:
        print(f"\n  >> HUMAN APPROVAL REQUIRED\n  >> {request.summary}")
        if args.confirm:
            print("  >> Proceed? [y/N] y   (answered by --confirm)")
            return True
        if not sys.stdin.isatty():
            print("  >> Proceed? [y/N] n   (no terminal and no --confirm)")
            return False
        return input("  >> Proceed? [y/N] ").strip().lower() in ("y", "yes")

    if not check_database():
        print("database unreachable (if psycopg is blocked, set PRICEPILOT_DB_DRIVER=pg8000)")
        return 1

    banner("1. pick ONE real APPROVE-with-move recommendation")
    with session_scope() as session:
        query = select(Recommendation).where(
            Recommendation.run_label == "s5-real",
            Recommendation.is_mock.is_(False),
            Recommendation.scenario.is_(None),
            Recommendation.guard_status == "APPROVE",
            Recommendation.guard_final_price != Recommendation.current_price,
        )
        if args.recommendation_id:
            query = query.where(Recommendation.id == args.recommendation_id)
        rec = session.scalars(query.order_by(Recommendation.id)).first()
        if rec is None:
            print("no eligible recommendation")
            return 1
        rec_id, product_id = rec.id, rec.product_id
        current, target = rec.current_price, rec.guard_final_price
        print(
            f"  recommendation #{rec_id}: product {product_id} ({rec.category}), guard {rec.guard_status}"
        )
        print(
            f"  decided from {current} -> guard-approved {target} (LLM proposed {rec.llm_proposed_price})"
        )
        print(f"  rationale: {rec.llm_rationale}")
    assert target is not None

    banner("2. start the mock store")
    proc = start_store()
    store = HttpStore.connect(URL)
    try:
        before = store.get_price(product_id)
        log_before = len(store.audit_log())
        print(
            f"  store: GET /products/{product_id} -> {before}; /audit-log has {log_before} entries"
        )
        assert before == current, f"store {before} != recommendation's current price {current}"

        with session_scope() as session:
            since_id = session.scalar(select(func.coalesce(func.max(ActionLog.id), 0))) or 0
        banner("3. APPLY (human approval required)")
        with session_scope() as session:
            result = apply_recommendation(
                session, rec_id, store=store, actor=actor, approve=approve
            )
            applied_id = result.action.id if result.action else None
        print(f"  outcome: {result.outcome}; audit verified: {result.audit_verified}")
        assert result.outcome == APPLIED and result.audit_verified is True and applied_id

        banner("4. VERIFY the apply (three independent places)")
        after = store.get_price(product_id)
        print(f"  store price:      GET /products/{product_id} -> {after}   (expected {target})")
        assert after == target
        entries = store.audit_log()
        print(f"  store /audit-log: {len(entries)} entries (was {log_before}); newest:")
        print_store_log(store)
        assert len(entries) == log_before + 1
        assert (entries[-1].previous_price, entries[-1].new_price) == (before, target)
        print("  our action_log:")
        rows = print_action_rows(rec_id, since_id)
        assert [r.action for r in rows] == ["update_price"]
        assert rows[0].mock_store_audit_ref == f"audit-log[{log_before}]"

        banner("5. APPLY AGAIN: must not double-write")
        with session_scope() as session:
            again = apply_recommendation(session, rec_id, store=store, actor=actor, approve=approve)
        print(f"  outcome: {again.outcome}")
        assert again.outcome == ALREADY_APPLIED
        assert len(store.audit_log()) == log_before + 1 and store.get_price(product_id) == target
        print(f"  store unchanged: price {target}, /audit-log still {log_before + 1} entries")

        banner("6. ROLLBACK (human approval required)")
        with session_scope() as session:
            back = rollback_action(session, applied_id, store=store, actor=actor, approve=approve)
        print(f"  outcome: {back.outcome}; audit verified: {back.audit_verified}")
        assert back.outcome == ROLLED_BACK and back.audit_verified is True

        banner("7. VERIFY the rollback")
        restored = store.get_price(product_id)
        print(f"  store price: GET /products/{product_id} -> {restored}   (expected {before})")
        assert restored == before
        entries = store.audit_log()
        assert len(entries) == log_before + 2
        assert (entries[-1].previous_price, entries[-1].new_price) == (target, before)

        banner("8. THE WHOLE TRAIL")
        print("store /audit-log (in-memory in the store process):")
        print_store_log(store)
        print("our action_log (durable, Postgres):")
        rows = print_action_rows(rec_id, since_id)
        assert [r.action for r in rows] == ["update_price", "rollback"]
        assert rows[0].reverted_by == rows[1].id
        assert rows[1].mock_store_audit_ref == f"audit-log[{log_before + 1}]"
        print("\nGATE CYCLE: PASSED (apply -> verify -> idempotent re-apply -> rollback -> verify)")
        return 0
    finally:
        proc.terminate()
        proc.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())

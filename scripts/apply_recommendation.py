r"""Phase 6 CLI: act on a guard-decided recommendation, with human approval (ADR-0047).

    $env:PRICEPILOT_DB_DRIVER = "pg8000"      # if psycopg is blocked (ADR-0038)
    # the store must be running:  uv run uvicorn services.mock_store.app:app --port 8001
    .venv\Scripts\python scripts/apply_recommendation.py plan                  # what each real row would do
    .venv\Scripts\python scripts/apply_recommendation.py apply --recommendation-id 9
    .venv\Scripts\python scripts/apply_recommendation.py rollback --action-id 3
    .venv\Scripts\python scripts/apply_recommendation.py log

Approval is HUMAN and never implicit: `apply` and `rollback` print what they will do and ask
`Proceed? [y/N]`. `--confirm` answers yes for a non-interactive run and is printed as such in the
output and recorded in the actor; without a terminal and without `--confirm` the answer is no.
Never run `scripts/sync_catalogue.py` after an apply: it rewrites `products.current_price` from the
seed (STATE open issue).
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select  # noqa: E402

from pricepilot.actions.apply import (  # noqa: E402
    ActionRefused,
    ApprovalRequest,
    apply_recommendation,
)
from pricepilot.actions.rollback import rollback_action  # noqa: E402
from pricepilot.actions.selector import select_action  # noqa: E402
from pricepilot.actions.store import DEFAULT_STORE_URL, HttpStore  # noqa: E402
from pricepilot.db import check_database, session_scope  # noqa: E402
from pricepilot.decision.scenarios import is_stress  # noqa: E402
from pricepilot.models import ActionLog, Recommendation  # noqa: E402


def make_approver(confirm: bool):  # type: ignore[no-untyped-def]
    def approve(request: ApprovalRequest) -> bool:
        print(f"\n  {request.summary}")
        if confirm:
            print("  Proceed? [y/N] y   (answered by --confirm)")
            return True
        if not sys.stdin.isatty():
            print("  Proceed? [y/N] n   (no terminal and no --confirm: approval is required)")
            return False
        answer = input("  Proceed? [y/N] ").strip().lower()
        return answer in ("y", "yes")

    return approve


def print_log(rows: list[ActionLog]) -> None:
    print(
        f"{'id':>4} {'rec':>4} {'prod':>4} {'action':<16} {'previous':>9} {'new':>9} "
        f"{'audit ref':<14} {'reverted_by':>11}  actor / reason"
    )
    for r in rows:
        print(
            f"{r.id:>4} {r.recommendation_id:>4} {r.product_id:>4} {r.action:<16} "
            f"{r.previous_price!s:>9} {r.new_price if r.new_price is not None else '-':>9} "
            f"{r.mock_store_audit_ref or '-':<14} {r.reverted_by or '-':>11}  "
            f"{r.actor} | {r.reason}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser(
        "plan", help="what each real recommendation would do (reads nothing from the store)"
    )
    sub.add_parser("log", help="print the action log")
    for name in ("apply", "rollback"):
        p = sub.add_parser(name)
        p.add_argument(
            "--recommendation-id" if name == "apply" else "--action-id",
            type=int,
            required=True,
            dest="target_id",
        )
        p.add_argument("--confirm", action="store_true", help="answer yes to the approval prompt")
        p.add_argument("--actor", default="bogdan-cli")
        p.add_argument("--store-url", default=DEFAULT_STORE_URL)
    args = parser.parse_args()

    if not check_database():
        print("database unreachable (if psycopg is blocked, set PRICEPILOT_DB_DRIVER=pg8000)")
        return 1

    if args.cmd == "plan":
        with session_scope() as session:
            rows = session.scalars(
                select(Recommendation)
                .where(Recommendation.run_label == "s5-real", Recommendation.is_mock.is_(False))
                .order_by(Recommendation.id)
            ).all()
            print(
                f"{'rec':>4} {'prod':>4} {'scenario':<20} {'guard':<8} {'current':>9} {'final':>9}  action"
            )
            for r in rows:
                kind = select_action(
                    guard_status=r.guard_status,
                    guard_final_price=r.guard_final_price,
                    current_price=r.current_price,
                )
                note = "  (REFUSED: stress-test row)" if is_stress(r.scenario) else ""
                print(
                    f"{r.id:>4} {r.product_id:>4} {r.scenario or 'baseline':<20} {r.guard_status:<8} "
                    f"{r.current_price!s:>9} {r.guard_final_price if r.guard_final_price is not None else '-':>9}"
                    f"  {kind.value}{note}"
                )
        return 0

    if args.cmd == "log":
        with session_scope() as session:
            print_log(list(session.scalars(select(ActionLog).order_by(ActionLog.id))))
        return 0

    actor = f"{args.actor} (--confirm)" if args.confirm else args.actor
    store = HttpStore.connect(args.store_url)
    approve = make_approver(args.confirm)
    try:
        with session_scope() as session:
            if args.cmd == "apply":
                result = apply_recommendation(
                    session, args.target_id, store=store, actor=actor, approve=approve
                )
            else:
                result = rollback_action(
                    session, args.target_id, store=store, actor=actor, approve=approve
                )
    except (ActionRefused, LookupError) as exc:
        print(f"REFUSED: {exc}")
        return 2
    row = result.action
    print(
        f"\noutcome: {result.outcome}"
        + (f"  (action #{row.id}, audit ref {row.mock_store_audit_ref})" if row is not None else "")
    )
    if result.audit_verified is False:
        print("WARNING: the store write could not be matched in its /audit-log")
    return (
        0
        if result.outcome
        in (
            "applied",
            "rolled_back",
            "already_applied",
            "already_logged",
            "flagged_for_review",
            "nothing_to_apply",
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())

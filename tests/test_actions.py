"""Phase 6 (ADR-0047): the action selector, apply (human approval, idempotent, stale-checked), and
rollback. Offline and $0: in-memory SQLite, a recording fake store, and one round trip through the real
mock-store app. Expected values are computed from the stated inputs, not copied from output."""

from __future__ import annotations

import warnings
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.mock_store import app as store_app
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pricepilot.actions import apply as apply_mod
from pricepilot.actions.apply import (
    ActionRefused,
    ApprovalRequest,
    apply_recommendation,
)
from pricepilot.actions.rollback import rollback_action
from pricepilot.actions.selector import ActionKind, select_action
from pricepilot.actions.store import HttpStore, StoreWrite
from pricepilot.models import ActionLog, Product, Recommendation

D = Decimal


# ---------------------------------------------------------------------------------------
# The selector (pure)
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "final", "current", "expected"),
    [
        ("APPROVE", D("369.90"), D("389.00"), ActionKind.UPDATE_PRICE),  # a real move
        ("APPROVE", D("389.00"), D("389.00"), ActionKind.DO_NOTHING),  # a no-change is a no-op
        ("APPROVE", D("389.01"), D("389.00"), ActionKind.UPDATE_PRICE),  # one cent still moves
        ("FLAG", None, D("389.00"), ActionKind.FLAG_FOR_REVIEW),
        ("REJECT", None, D("389.00"), ActionKind.DO_NOTHING),
    ],
)
def test_selector_maps_the_guard_verdict_to_one_action(
    status: str, final: Decimal | None, current: Decimal, expected: ActionKind
) -> None:
    assert (
        select_action(guard_status=status, guard_final_price=final, current_price=current)
        == expected
    )


@pytest.mark.parametrize(
    ("status", "final"), [("APPROVE", None), ("MAYBE", D("1.00")), ("approve", D("1.00"))]
)
def test_selector_fails_closed_on_corrupt_input(status: str, final: Decimal | None) -> None:
    with pytest.raises(ValueError):
        select_action(guard_status=status, guard_final_price=final, current_price=D("2.00"))


# ---------------------------------------------------------------------------------------
# Fixtures: a session with the three tables, and a recording fake store
# ---------------------------------------------------------------------------------------


@pytest.fixture()
def session() -> Any:
    engine = create_engine("sqlite://")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # SQLite stores Numeric as float; Decimal API still holds
        for model in (Product, Recommendation, ActionLog):
            model.__table__.create(engine)  # type: ignore[attr-defined]
        with Session(engine, expire_on_commit=False) as s:
            yield s


class FakeStore:
    """Records every call so a test can prove what was (not) touched."""

    def __init__(self, prices: dict[int, Decimal]) -> None:
        self.prices = dict(prices)
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self._log: list[StoreWrite] = []
        self.fail_on_set = False

    def get_price(self, product_id: int) -> Decimal:
        self.calls.append(("get_price", (product_id,)))
        return self.prices[product_id]

    def set_price(self, product_id: int, price: Decimal, reason: str) -> StoreWrite:
        self.calls.append(("set_price", (product_id, price)))
        if self.fail_on_set:
            raise RuntimeError("store is down")
        write = StoreWrite(product_id, self.prices[product_id], price, reason)
        self.prices[product_id] = price
        self._log.append(write)
        return write

    def audit_log(self) -> list[StoreWrite]:
        self.calls.append(("audit_log", ()))
        return list(self._log)

    @property
    def writes(self) -> list[tuple[str, tuple[Any, ...]]]:
        return [c for c in self.calls if c[0] == "set_price"]


def yes(_: ApprovalRequest) -> bool:
    return True


def no(_: ApprovalRequest) -> bool:
    return False


def make_rec(
    session: Session,
    *,
    rec_id: int = 1,
    status: str = "APPROVE",
    current: str = "389.00",
    final: str | None = "369.90",
    product_id: int = 2,
    scenario: str | None = None,
    is_mock: bool = False,
    reason: str | None = None,
) -> Recommendation:
    rec = Recommendation(
        id=rec_id,
        product_id=product_id,
        run_label="t",
        is_mock=is_mock,
        scenario=scenario,
        category="dry_food",
        cost=D("265.00"),
        current_price=D(current),
        stock=52,
        competitor_prices=[],
        price_7d_ago=D(current),
        price_7d_ago_source="mock_store_synthetic",
        elasticity_placeholder={},
        rag_sections=[],
        prompt_text="p",
        llm_model="m",
        llm_raw_reply="r",
        llm_proposed_price=D("369.55"),
        llm_rationale="move toward the cheapest competitor",
        llm_cost_usd=D("0"),
        guard_status=status,
        guard_final_price=None if final is None else D(final),
        guard_reason=reason,
    )
    session.add(rec)
    session.flush()
    return rec


def actions(session: Session) -> list[ActionLog]:
    return list(session.scalars(select(ActionLog).order_by(ActionLog.id)))


# ---------------------------------------------------------------------------------------
# apply_recommendation
# ---------------------------------------------------------------------------------------


def test_an_approved_move_is_written_logged_and_tied_to_the_store_audit_log(
    session: Session,
) -> None:
    make_rec(session)
    store = FakeStore({2: D("389.00")})
    shown: list[ApprovalRequest] = []

    def approve(request: ApprovalRequest) -> bool:
        shown.append(request)
        return True

    result = apply_recommendation(session, 1, store=store, actor="bogdan-cli", approve=approve)

    assert result.outcome == apply_mod.APPLIED and result.audit_verified is True
    assert store.prices[2] == D("369.90")
    assert [c for c in store.writes] == [("set_price", (2, D("369.90")))]
    (row,) = actions(session)
    assert (row.action, row.previous_price, row.new_price) == (
        "update_price",
        D("389.00"),
        D("369.90"),
    )
    assert (row.recommendation_id, row.product_id, row.actor) == (1, 2, "bogdan-cli")
    assert row.mock_store_audit_ref == "audit-log[0]" and row.reverted_by is None
    # the human was shown both prices before anything was written
    assert len(shown) == 1 and "389.00 -> 369.90" in shown[0].summary
    # and the store's own audit entry references the recommendation
    assert "recommendation #1" in store.audit_log()[0].reason


def test_a_no_change_never_reaches_the_store_at_all(session: Session) -> None:
    make_rec(session, final="389.00")  # APPROVE at the current price
    store = FakeStore({2: D("389.00")})
    result = apply_recommendation(session, 1, store=store, actor="a", approve=yes)
    assert result.outcome == apply_mod.NOTHING
    assert store.calls == []  # no read, no write: the update endpoint is NOT called
    (row,) = actions(session)
    assert (row.action, row.new_price, row.previous_price) == ("do_nothing", None, D("389.00"))


def test_a_flag_is_routed_to_review_and_applies_nothing(session: Session) -> None:
    make_rec(session, status="FLAG", final=None, reason="speed limit breached: x")
    store = FakeStore({2: D("389.00")})
    result = apply_recommendation(session, 1, store=store, actor="a", approve=yes)
    assert result.outcome == apply_mod.FLAGGED and store.calls == []
    (row,) = actions(session)
    assert row.action == "flag_for_review" and "speed limit breached" in row.reason


def test_a_reject_applies_nothing(session: Session) -> None:
    make_rec(session, status="REJECT", final=None, reason="discount blocked: x")
    store = FakeStore({2: D("389.00")})
    result = apply_recommendation(session, 1, store=store, actor="a", approve=yes)
    assert result.outcome == apply_mod.NOTHING and store.calls == []
    assert actions(session)[0].action == "do_nothing"


def test_repeated_flag_requests_log_once(session: Session) -> None:
    make_rec(session, status="FLAG", final=None, reason="x")
    store = FakeStore({2: D("389.00")})
    apply_recommendation(session, 1, store=store, actor="a", approve=yes)
    again = apply_recommendation(session, 1, store=store, actor="a", approve=yes)
    assert again.outcome == apply_mod.ALREADY_LOGGED and len(actions(session)) == 1


def test_approval_is_required_and_a_decline_writes_nothing(session: Session) -> None:
    make_rec(session)
    store = FakeStore({2: D("389.00")})
    with pytest.raises(TypeError):  # no default approver exists: auto-apply is not expressible
        apply_recommendation(session, 1, store=store, actor="a")  # type: ignore[call-arg]
    result = apply_recommendation(session, 1, store=store, actor="a", approve=no)
    assert result.outcome == apply_mod.DECLINED
    assert store.writes == [] and store.prices[2] == D("389.00")
    (row,) = actions(session)
    assert row.action == "do_nothing" and "declined" in row.reason


def test_applying_twice_changes_the_store_once(session: Session) -> None:
    make_rec(session)
    store = FakeStore({2: D("389.00")})
    first = apply_recommendation(session, 1, store=store, actor="a", approve=yes)
    second = apply_recommendation(session, 1, store=store, actor="a", approve=yes)
    assert first.outcome == apply_mod.APPLIED and second.outcome == apply_mod.ALREADY_APPLIED
    assert len(store.writes) == 1 and store.prices[2] == D("369.90")
    assert [a.action for a in actions(session)] == ["update_price"]


def test_a_store_already_at_the_target_is_a_logged_no_op(session: Session) -> None:
    make_rec(session)
    store = FakeStore({2: D("369.90")})  # someone already set it
    result = apply_recommendation(session, 1, store=store, actor="a", approve=yes)
    assert result.outcome == apply_mod.AT_TARGET and store.writes == []
    assert actions(session)[0].action == "do_nothing"


def test_a_stale_recommendation_is_not_applied(session: Session) -> None:
    make_rec(session)  # decided from 389.00
    store = FakeStore({2: D("379.00")})  # the store has moved since
    result = apply_recommendation(session, 1, store=store, actor="a", approve=yes)
    assert result.outcome == apply_mod.STALE and store.writes == []
    assert store.prices[2] == D("379.00")
    assert "stale recommendation" in actions(session)[0].reason


def test_mock_and_stress_test_rows_are_refused_without_touching_anything(session: Session) -> None:
    make_rec(session, rec_id=1, is_mock=True)
    make_rec(session, rec_id=2, scenario="stress_undercut_15", product_id=3)
    store = FakeStore({2: D("389.00"), 3: D("879.00")})
    with pytest.raises(ActionRefused, match="mock"):
        apply_recommendation(session, 1, store=store, actor="a", approve=yes)
    with pytest.raises(ActionRefused, match="STRESS-TEST"):
        apply_recommendation(session, 2, store=store, actor="a", approve=yes)
    assert store.calls == [] and actions(session) == []


def test_unknown_recommendation_raises(session: Session) -> None:
    with pytest.raises(LookupError):
        apply_recommendation(session, 99, store=FakeStore({}), actor="a", approve=yes)


def test_the_database_refuses_a_second_live_update_for_one_recommendation(session: Session) -> None:
    make_rec(session)
    kwargs: dict[str, Any] = dict(
        recommendation_id=1, product_id=2, action="update_price", previous_price=D("389.00"),
        new_price=D("369.90"), reason="r", actor="a",
    )  # fmt: skip
    session.add(ActionLog(**kwargs))
    session.flush()
    session.add(ActionLog(**kwargs))
    with pytest.raises(IntegrityError):
        session.flush()


def test_a_failing_store_write_leaves_no_action_row(session: Session) -> None:
    make_rec(session)
    session.commit()
    store = FakeStore({2: D("389.00")})
    store.fail_on_set = True
    with pytest.raises(RuntimeError, match="store is down"):
        apply_recommendation(session, 1, store=store, actor="a", approve=yes)
        session.commit()
    session.rollback()  # what session_scope does on an exception
    assert actions(session) == [] and store.prices[2] == D("389.00")


# ---------------------------------------------------------------------------------------
# rollback_action
# ---------------------------------------------------------------------------------------


def applied(session: Session) -> tuple[FakeStore, ActionLog]:
    make_rec(session)
    store = FakeStore({2: D("389.00")})
    result = apply_recommendation(session, 1, store=store, actor="a", approve=yes)
    assert result.action is not None
    return store, result.action


def test_rollback_restores_the_previous_price_logs_it_and_marks_the_original(
    session: Session,
) -> None:
    store, original = applied(session)
    result = rollback_action(session, original.id, store=store, actor="a", approve=yes)

    assert result.outcome == "rolled_back" and result.audit_verified is True
    assert store.prices[2] == D("389.00")
    row = result.action
    assert row is not None
    assert (row.action, row.previous_price, row.new_price) == ("rollback", D("369.90"), D("389.00"))
    assert row.mock_store_audit_ref == "audit-log[1]"
    assert original.reverted_by == row.id
    assert [a.action for a in actions(session)] == ["update_price", "rollback"]


def test_rollback_refuses_when_the_store_price_has_drifted(session: Session) -> None:
    store, original = applied(session)
    store.prices[2] = D("359.00")  # something else changed it after our write
    writes_before = len(store.writes)
    result = rollback_action(session, original.id, store=store, actor="a", approve=yes)
    assert result.outcome == "store_price_drifted"
    assert len(store.writes) == writes_before and store.prices[2] == D("359.00")
    assert original.reverted_by is None
    assert actions(session)[-1].action == "do_nothing" and "refused" in actions(session)[-1].reason


def test_rollback_needs_approval_and_a_decline_writes_nothing(session: Session) -> None:
    store, original = applied(session)
    result = rollback_action(session, original.id, store=store, actor="a", approve=no)
    assert result.outcome == "declined_by_human" and store.prices[2] == D("369.90")
    assert original.reverted_by is None


def test_a_rollback_happens_once(session: Session) -> None:
    store, original = applied(session)
    rollback_action(session, original.id, store=store, actor="a", approve=yes)
    again = rollback_action(session, original.id, store=store, actor="a", approve=yes)
    assert again.outcome == "already_reverted"
    assert len([w for w in store.writes if w[1][1] == D("389.00")]) == 1


def test_only_an_update_price_can_be_rolled_back(session: Session) -> None:
    make_rec(session, status="FLAG", final=None, reason="x")
    store = FakeStore({2: D("389.00")})
    flagged = apply_recommendation(session, 1, store=store, actor="a", approve=yes).action
    assert flagged is not None
    with pytest.raises(ActionRefused, match="only an update_price"):
        rollback_action(session, flagged.id, store=store, actor="a", approve=yes)
    with pytest.raises(LookupError):
        rollback_action(session, 999, store=store, actor="a", approve=yes)


def test_after_a_rollback_the_recommendation_can_be_applied_again(session: Session) -> None:
    store, original = applied(session)
    rollback_action(session, original.id, store=store, actor="a", approve=yes)
    again = apply_recommendation(session, 1, store=store, actor="a", approve=yes)
    assert again.outcome == apply_mod.APPLIED and store.prices[2] == D("369.90")
    live = session.scalar(
        select(func.count()).select_from(ActionLog).where(
            ActionLog.action == "update_price", ActionLog.reverted_by.is_(None)
        )
    )  # fmt: skip
    assert live == 1


# ---------------------------------------------------------------------------------------
# One round trip through the REAL mock-store app (HTTP semantics, Decimal over JSON)
# ---------------------------------------------------------------------------------------


@pytest.fixture()
def real_store() -> Any:
    """HttpStore over the in-process mock-store app, with its global state restored afterwards."""
    log_len = len(store_app._AUDIT_LOG)
    price_before = store_app._PRODUCTS[2].current_price
    client = TestClient(store_app.app)
    try:
        yield HttpStore(client)
    finally:
        store_app._PRODUCTS[2].current_price = price_before
        del store_app._AUDIT_LOG[log_len:]


def test_apply_and_rollback_against_the_real_mock_store(
    session: Session, real_store: HttpStore
) -> None:
    start = real_store.get_price(2)
    target = (start * D("0.95")).quantize(D("0.01"))
    make_rec(session, current=str(start), final=str(target))
    log_before = len(real_store.audit_log())

    applied_result = apply_recommendation(session, 1, store=real_store, actor="a", approve=yes)
    assert applied_result.outcome == apply_mod.APPLIED and applied_result.audit_verified is True
    assert real_store.get_price(2) == target
    entries = real_store.audit_log()
    assert len(entries) == log_before + 1
    assert (entries[-1].previous_price, entries[-1].new_price) == (start, target)
    assert applied_result.action is not None
    assert applied_result.action.mock_store_audit_ref == f"audit-log[{log_before}]"

    back = rollback_action(
        session, applied_result.action.id, store=real_store, actor="a", approve=yes
    )
    assert back.outcome == "rolled_back" and real_store.get_price(2) == start
    assert real_store.audit_log()[-1].new_price == start

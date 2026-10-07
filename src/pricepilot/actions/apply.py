"""Apply a guard-decided recommendation to the store -- with human approval, idempotently, logged
(ADR-0047, CLAUDE.md section 0 rule 6 / Phase 6).

Hard rules enforced here:

* **Only a guard APPROVE with a different price is ever written**, and only through the single
  store write in `apply_recommendation`. `select_action` decides; a no-change, FLAG and REJECT never
  reach the store's update endpoint (no store call at all, not even a read).
* **Human approval is a required argument.** There is no default, no "auto" mode: the caller must
  pass an `approve` callable that returns True, and a False writes nothing.
* **Only real-input rows are acted on.** Mock rows, superseded rows (a later run replaced them)
  and any row with a scenario are refused: a `stress_*` row was decided on synthetic competitor
  prices (ADR-0045), a guard test and not a market recommendation.
* **Idempotent.** The DB allows one live `update_price` per recommendation (partial unique index),
  the action log is checked first, and a store already at the target is a logged no-op.
* **Stale recommendations are not applied.** The guard validated the move from
  `recommendation.current_price`; if the store no longer holds that price the move was never checked
  and is refused.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from pricepilot.actions.selector import ActionKind, select_action
from pricepilot.actions.store import Store, StoreWrite
from pricepilot.decision.scenarios import SUPERSEDED_RUN_LABEL, is_stress
from pricepilot.models import ActionLog, Recommendation

# Outcomes (the result's `outcome`), kept as plain strings so the CLI can print them.
APPLIED = "applied"
ALREADY_APPLIED = "already_applied"
AT_TARGET = "store_already_at_target"
STALE = "stale_recommendation"
DECLINED = "declined_by_human"
FLAGGED = "flagged_for_review"
NOTHING = "nothing_to_apply"
ALREADY_LOGGED = "already_logged"
UNVERIFIED = "UNVERIFIED"


class ActionRefused(Exception):
    """The request itself is not allowed (mock row, stress-test row, wrong action type)."""


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    """What the human is shown before a store write."""

    summary: str


Approver = Callable[[ApprovalRequest], bool]


@dataclass(frozen=True, slots=True)
class ActionResult:
    outcome: str
    action: ActionLog | None
    # For a store write: whether the write was found in the store's audit log. None otherwise.
    audit_verified: bool | None = None


def log_action(
    session: Session,
    *,
    recommendation_id: int,
    product_id: int,
    action: str,
    previous_price: Decimal,
    new_price: Decimal | None,
    reason: str,
    actor: str,
    audit_ref: str | None = None,
) -> ActionLog:
    row = ActionLog(
        recommendation_id=recommendation_id,
        product_id=product_id,
        action=action,
        previous_price=previous_price,
        new_price=new_price,
        reason=reason,
        actor=actor,
        mock_store_audit_ref=audit_ref,
    )
    session.add(row)
    session.flush()
    return row


def find_audit_ref(
    before: int, log: list[StoreWrite], product_id: int, previous: Decimal, new: Decimal
) -> str | None:
    """The `audit-log[i]` of the single store entry added after `before` entries that matches this
    write, or None if there is not exactly one (the store has no ids; position is the tie)."""
    hits = [
        i
        for i, e in enumerate(log)
        if i >= before
        and e.product_id == product_id
        and e.previous_price == previous
        and e.new_price == new
    ]
    return f"audit-log[{hits[0]}]" if len(hits) == 1 else None


def verify_write(
    store: Store, before: int, write: StoreWrite, product_id: int, previous: Decimal, new: Decimal
) -> str | None:
    """Tie a store write we just made to its audit-log entry. VERIFICATION ONLY: once the write has
    happened, nothing here may raise -- an extra read failing must not roll back the action_log row
    and leave a store change with no record. Any problem returns None ("UNVERIFIED")."""
    if (write.product_id, write.previous_price, write.new_price) != (product_id, previous, new):
        return None
    try:
        return find_audit_ref(before, store.audit_log(), product_id, previous, new)
    except Exception:
        return None


def live_update(session: Session, recommendation_id: int) -> ActionLog | None:
    return session.scalars(
        select(ActionLog).where(
            ActionLog.recommendation_id == recommendation_id,
            ActionLog.action == ActionKind.UPDATE_PRICE.value,
            ActionLog.reverted_by.is_(None),
        )
    ).first()


def apply_recommendation(
    session: Session,
    recommendation_id: int,
    *,
    store: Store,
    actor: str,
    approve: Approver,
) -> ActionResult:
    rec = session.get(Recommendation, recommendation_id)
    if rec is None:
        raise LookupError(f"no recommendation with id {recommendation_id}")
    if rec.is_mock:
        raise ActionRefused(f"recommendation {rec.id} is a mock row; only real rows are acted on")
    if rec.run_label == SUPERSEDED_RUN_LABEL:
        raise ActionRefused(f"recommendation {rec.id} was superseded by a later run; not acted on")
    if is_stress(rec.scenario):
        raise ActionRefused(
            f"recommendation {rec.id} is a GUARD STRESS-TEST ({rec.scenario}) decided on synthetic "
            "competitor prices, not a market recommendation; it is never applied"
        )
    if rec.scenario is not None:
        raise ActionRefused(
            f"recommendation {rec.id} has scenario {rec.scenario!r}; only real-input rows are acted on"
        )

    kind = select_action(
        guard_status=rec.guard_status,
        guard_final_price=rec.guard_final_price,
        current_price=rec.current_price,
    )

    existing = live_update(session, rec.id)
    if existing is not None:
        return ActionResult(ALREADY_APPLIED, existing)

    def note(action: ActionKind, reason: str, outcome: str) -> ActionResult:
        row = log_action(
            session,
            recommendation_id=rec.id,
            product_id=rec.product_id,
            action=action.value,
            previous_price=rec.current_price,
            new_price=None,
            reason=reason,
            actor=actor,
        )
        return ActionResult(outcome, row)

    if kind in (ActionKind.FLAG_FOR_REVIEW, ActionKind.DO_NOTHING):
        # Nothing is written and the store is not contacted at all -- not even a read.
        prior = session.scalars(
            select(ActionLog).where(
                ActionLog.recommendation_id == rec.id, ActionLog.action == kind.value
            )
        ).first()
        if prior is not None:
            return ActionResult(ALREADY_LOGGED, prior)
        if kind is ActionKind.FLAG_FOR_REVIEW:
            return note(kind, f"guard FLAG, routed to human review: {rec.guard_reason}", FLAGGED)
        if rec.guard_status == "REJECT":
            return note(kind, f"guard REJECT, nothing applied: {rec.guard_reason}", NOTHING)
        return note(
            kind,
            f"guard APPROVE keeps the current price {rec.current_price}; a no-change is not written",
            NOTHING,
        )

    # --- update_price ---------------------------------------------------------------------
    target = rec.guard_final_price
    assert target is not None  # select_action guarantees it for UPDATE_PRICE
    store_price = store.get_price(rec.product_id)
    if store_price == target:
        return note(ActionKind.DO_NOTHING, f"store already at the target price {target}", AT_TARGET)
    if store_price != rec.current_price:
        return note(
            ActionKind.DO_NOTHING,
            f"stale recommendation: it was decided from price {rec.current_price} but the store "
            f"holds {store_price}; the move was never checked from there",
            STALE,
        )

    request = ApprovalRequest(
        f"APPLY recommendation #{rec.id}: product {rec.product_id} ({rec.category}) "
        f"{store_price} -> {target} RON (guard APPROVE; cost {rec.cost}). "
        f"Rationale: {' '.join((rec.llm_rationale or '').split())[:400]}"  # one line: model text
    )
    if not approve(request):
        return note(ActionKind.DO_NOTHING, "approval declined by the human", DECLINED)

    # Record first (the partial unique index refuses a second live apply), then write, then tie the
    # row to the store's audit log. If the write raises, the whole transaction rolls back: no row.
    row = log_action(
        session,
        recommendation_id=rec.id,
        product_id=rec.product_id,
        action=ActionKind.UPDATE_PRICE.value,
        previous_price=store_price,
        new_price=target,
        reason=f"recommendation #{rec.id}: guard APPROVE {store_price} -> {target}",
        actor=actor,
    )
    before = len(store.audit_log())  # a read BEFORE the write: a failure here changes nothing
    write = store.set_price(
        rec.product_id,
        target,
        f"recommendation #{rec.id}: guard APPROVE {store_price} -> {target}; approved by {actor}",
    )
    ref = verify_write(store, before, write, rec.product_id, store_price, target)
    row.mock_store_audit_ref = ref or UNVERIFIED
    session.flush()
    return ActionResult(APPLIED, row, audit_verified=ref is not None)

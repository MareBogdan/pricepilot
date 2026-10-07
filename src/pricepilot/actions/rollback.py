"""Roll back a prior `update_price` (ADR-0047): write the previous price back, log a `rollback` row,
and mark the original `reverted_by`. Like an apply, it needs a human approval.

It FAILS SAFELY when the store no longer holds the price this action set: someone or something else
changed it (or the in-memory store restarted), so restoring `previous_price` would overwrite a change
we know nothing about. That is logged as a `do_nothing` row and returned as an outcome, not forced.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from pricepilot.actions.apply import (
    UNVERIFIED,
    ActionRefused,
    ActionResult,
    ApprovalRequest,
    Approver,
    find_audit_ref,
    log_action,
)
from pricepilot.actions.selector import ActionKind
from pricepilot.actions.store import Store
from pricepilot.models import ActionLog

ROLLED_BACK = "rolled_back"
ALREADY_REVERTED = "already_reverted"
DRIFTED = "store_price_drifted"
ROLLBACK_DECLINED = "declined_by_human"
ROLLBACK_ACTION = "rollback"


def rollback_action(
    session: Session,
    action_id: int,
    *,
    store: Store,
    actor: str,
    approve: Approver,
) -> ActionResult:
    original = session.get(ActionLog, action_id)
    if original is None:
        raise LookupError(f"no action_log row with id {action_id}")
    if original.action != ActionKind.UPDATE_PRICE.value:
        raise ActionRefused(
            f"action {action_id} is a {original.action!r}; only an update_price can be rolled back"
        )
    if original.reverted_by is not None:
        return ActionResult(ALREADY_REVERTED, session.get(ActionLog, original.reverted_by))

    assert original.new_price is not None  # CHECK: an update_price always has a new_price
    set_price = original.new_price
    restore = original.previous_price
    store_price = store.get_price(original.product_id)

    def note(reason: str, outcome: str) -> ActionResult:
        row = log_action(
            session,
            recommendation_id=original.recommendation_id,
            product_id=original.product_id,
            action=ActionKind.DO_NOTHING.value,
            previous_price=store_price,
            new_price=None,
            reason=reason,
            actor=actor,
        )
        return ActionResult(outcome, row)

    if store_price != set_price:
        return note(
            f"rollback of action #{original.id} refused: the store holds {store_price}, not the "
            f"{set_price} this action set (changed by something else, or the store restarted)",
            DRIFTED,
        )

    request = ApprovalRequest(
        f"ROLL BACK action #{original.id} (recommendation #{original.recommendation_id}): "
        f"product {original.product_id} {set_price} -> {restore} RON"
    )
    if not approve(request):
        return note(f"rollback of action #{original.id} declined by the human", ROLLBACK_DECLINED)

    row = log_action(
        session,
        recommendation_id=original.recommendation_id,
        product_id=original.product_id,
        action=ROLLBACK_ACTION,
        previous_price=set_price,
        new_price=restore,
        reason=f"rollback of action #{original.id}: {set_price} -> {restore}",
        actor=actor,
    )
    before = len(store.audit_log())
    store.set_price(
        original.product_id,
        restore,
        f"rollback of action #{original.id} (recommendation #{original.recommendation_id}); "
        f"approved by {actor}",
    )
    ref = find_audit_ref(before, store.audit_log(), original.product_id, set_price, restore)
    row.mock_store_audit_ref = ref or UNVERIFIED
    original.reverted_by = row.id
    session.flush()
    return ActionResult(ROLLED_BACK, row, audit_verified=ref is not None)

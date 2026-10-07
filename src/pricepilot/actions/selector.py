"""The deterministic action selector (ADR-0047): the guard's verdict -> which tool to call.

Pure: no I/O. It is the only place that maps `guard_status` to an action, so "never apply anything
that is not a guard APPROVE" and "a no-change is a no-op, never a store write" are decided here and
tested here (CLAUDE.md section 6 rule 2; STATE Phase 6 note from the session-1b review).
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pricepilot.policy.guard import GuardStatus


class ActionKind(StrEnum):
    UPDATE_PRICE = "update_price"
    FLAG_FOR_REVIEW = "flag_for_review"
    DO_NOTHING = "do_nothing"
    # `rollback` exists in the action log but is never SELECTED from a recommendation: it is an
    # explicit human command against an earlier update_price (actions/rollback.py).


def select_action(
    *, guard_status: str, guard_final_price: Decimal | None, current_price: Decimal
) -> ActionKind:
    """APPROVE with a different price -> update_price; APPROVE at the current price -> do_nothing
    (a no-change must NEVER reach the store's update endpoint); FLAG -> flag_for_review; REJECT ->
    do_nothing. Anything else, or an APPROVE without an applied price, is corrupt input and raises
    (fail closed): nothing is ever applied on a guess."""
    if guard_status == GuardStatus.APPROVE:
        if guard_final_price is None:
            raise ValueError("an APPROVE recommendation has no applied price (corrupt row)")
        if guard_final_price == current_price:
            return ActionKind.DO_NOTHING
        return ActionKind.UPDATE_PRICE
    if guard_status == GuardStatus.FLAG:
        return ActionKind.FLAG_FOR_REVIEW
    if guard_status == GuardStatus.REJECT:
        return ActionKind.DO_NOTHING
    raise ValueError(f"unknown guard_status {guard_status!r}")

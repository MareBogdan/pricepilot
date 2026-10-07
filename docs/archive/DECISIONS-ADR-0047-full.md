# ADR-0047 full text (archived 2026-10-07 when Phase 7a needed DECISIONS.md headroom)

## ADR-0047 -- Phase 6 action layer: guard-selected tools, human approval, idempotent, reversible

**Context.** Phase 6 turns a guard-decided recommendation into an action on the mock store with a
durable log and rollback; gate = one complete cycle, visible in logs.
**Decision.** (1) `actions/selector.py::select_action` maps the guard verdict to a tool, in code:
APPROVE with a different price -> `update_price`; APPROVE at the current price -> `do_nothing` (the
store's update endpoint is never called, not even a read); FLAG -> `flag_for_review`; REJECT ->
`do_nothing`. The tools are not chosen by an LLM: that would put the decision back in a prompt, and
the guard is the authority (CLAUDE.md section 6 rule 2). (2) `apply_recommendation`: refuses mock rows
and `stress_*` rows (decided on synthetic competitor prices, ADR-0045); is idempotent (live-update check,
store-already-at-target, and a DB partial unique index allowing ONE live `update_price` per
recommendation); refuses a STALE recommendation (store price != the price the guard validated the move
from); `approve` is a required argument with no default, a decline writes nothing. (3) Order: log row
flushed first, then the store PATCH, then the row is tied to the store's `/audit-log` entry
(`audit-log[i]`; "UNVERIFIED" if not matchable); a failing PATCH rolls the row back. (4)
`rollback_action`: same approval; refuses (logged `do_nothing`) if the store no longer holds the price
we set; sets `reverted_by`; after a rollback the recommendation may be applied again. (5)
`action_log` (migration 0015) is durable in Postgres; CHECKs tie `new_price` to write actions.
(6) CLI `scripts/apply_recommendation.py` (plan / apply / rollback / log) with a real y/N prompt;
`--confirm` answers yes for a non-interactive run and is recorded in the actor.
**Gate (MET, `docs/learned/results/phase6/gate-cycle.txt`, `scripts/phase6_gate_cycle.py`; run twice, the
committed trail is the second run on the final code, action ids 3-4).** Real row
#9 (product 2, 389.00 -> guard-approved 369.90): prompt -> apply -> store price, store `/audit-log` and
`action_log` all verified -> second apply refused (`already_applied`, store unchanged) -> rollback
(second prompt) -> price restored to 389.00 and logged. The approval in that run was `--confirm`,
given on Bogdan's written instruction to execute the gate cycle; it is not an interactive keystroke.
**Review fixes (reviewer, same day).** The post-write verification read can no longer lose the row
(`verify_write` never raises: a failed read leaves the row `UNVERIFIED`); the rollback claims the original
with a compare-and-set on `reverted_by IS NULL` BEFORE the store write (two concurrent rollbacks: the loser
is refused, nothing written); `apply` also refuses superseded rows (`s5-superseded`) and any row with a
scenario; the model's `reverted_by` FK now matches the migration (`ON DELETE RESTRICT`); the rationale is
flattened to one line in the approval prompt; the gate script refuses a store that is already running.
**Known limits.** The store holds prices and its audit log in process memory: a restart resets both
(rollback then refuses as drift, correctly). `products.current_price` in Postgres is NOT updated by an
apply and `sync_catalogue.py` would revert the store's seed copy over it, so after a real apply a
store -> DB sync is needed before the next decision run (not built). A crash or DB failure BETWEEN the store
write and the commit could still leave a write without a row (the store is a fixture; the window is now only
the commit). The stale check is check-then-write, not compare-and-set (the store has no conditional PATCH), and
the unique index is per recommendation, not per product: two DIFFERENT recommendations for one product applied
at the same instant could both write (single-admin CLI; accepted). `action_log.product_id` is
`ON DELETE CASCADE`, so deleting a product would erase its trail (nothing deletes products today). A
drifted-rollback `do_nothing` row records the observed store price as `previous_price`. Only 4 real baseline
rows are applicable moves (p2, p6, p19, p20); 10 APPROVE-with-move rows exist, 6 are refused stress rows.
**Tests:** 31 (selector cases, no-change makes zero store calls, idempotency, stale, decline, rollback incl.
drift/once/concurrent/re-apply, DB double-apply refusal, superseded and other-scenario refusal, lost-row
protection, one round trip through the real mock-store app). `scripts/mutation_check_actions.py` (output
`docs/learned/results/phase6/mutation-check.txt`) breaks 8 safety checks one at a time: 8 of 8 mutants killed.
Full suite 991 passed, 5 skipped. **Cost** $0 (`llm_calls` unchanged: 649 rows, $1.222904).
**Alternatives rejected.** LLM-selected tool calls; auto-apply "narrow conditions" (not built:
approval is always human for now); applying without the stale check.
**Date.** 2026-10-07

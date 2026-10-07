# Phase 6 -- Tool calling (full CLAUDE.md section 7 text, moved at close 2026-10-07)

### Phase 6 — Tool calling
Strict-schema tools: `update_price`, `flag_for_review`, `do_nothing`. Human approval by default; automatic mode only under narrow conditions. Full action log with rollback.

**Gate:** one complete cycle end to end, visible in logs.

## Outcome

CLOSED 2026-10-07. Gate (one complete cycle end to end, visible in logs) MET: `docs/learned/results/phase6/gate-cycle.txt`. See DECISIONS.md ADR-0046/0047 and STATE.md. Built as deterministic guard-selected actions (not LLM-chosen tool calls); approval is always human.

# Phase 5 -- Decision engine (full CLAUDE.md section 7 text, moved at close 2026-10-07)

### Phase 5 — Decision engine
Write a 300–500 word pricing policy document. Index it. Build the recommendation prompt combining: product, matched competitor prices (SQL), estimated elasticity (model), relevant policy passages (RAG). Deterministic margin guardrail after the LLM. Full trace persisted.

For Phase 5, the pricing policy document should cover realistic pet-retail rules: minimum margin per category (dry food carries thinner margins than accessories), brands with distributor pricing restrictions, products excluded from automatic discounting, daily maximum price movement, and rounding conventions. This is genuine natural-language policy — the correct use of RAG. The numbers it references (costs, current margins, stock) still come from SQL.

**Gate:** 50 generated recommendations, zero margin violations.

## Outcome

CLOSED 2026-10-07. Gate (50 generated recommendations, zero margin violations) MET: 50 rows, 0 violations, `docs/learned/results/phase5/fifty-recommendations.md`. See DECISIONS.md ADR-0033..0045 and STATE.md for the caveats (10 moved APPROVEs; stress-test rows are synthetic).

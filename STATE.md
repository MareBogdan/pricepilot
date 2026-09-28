# STATE

Phase: 5 — Decision engine (RAG + recommendation). Phases 0-4 CLOSED / POSTPONED as below.
Updated: 2026-09-28

**Where we are:** Phase 5 session 1 DONE (2026-09-28, ADR-0034): pricing-policy thresholds live in
one validated config (`config/pricing-policy.toml` + `src/pricepilot/policy/thresholds.py`), read
by the deterministic margin/price guard (`src/pricepilot/policy/guard.py::enforce`) -- eligibility
-> margin floor -> speed limit -> charm round -> re-check floor after rounding. 827 tests green,
`make.ps1 lint`/`typecheck` clean. Next: session 2, index the policy for RAG (pgvector, local
embeddings, retrieval eval). Phase 4 (demand) stays POSTPONE (15-16 collection days; rule needs
28). Dataset FROZEN 2026-09-22, SHA-256 below.

## Gate progress

**Phase 0 — Foundation: CLOSED** (2026-09-12), all 8 gate boxes met. Full detail:
`docs/archive/phases-0-2.md`, `docs/archive/STATE-history.md`.

**Phase 1 — Collection: CLOSED** (2026-09-22). >=3,000 in-scope listings MET (18,585/18,703, 3
sources); >=7 consecutive days MET (9 days); >=400 cross-shop overlap MET (hand-verified sample,
ADR-0023/ADR-0028 #7). Full detail: `docs/archive/phases-0-2.md`.

**Phase 2 — Normalization: CLOSED** (2026-09-14). 85% attribute-accuracy gate MET at 93.2%
(261/280 symmetric); weight parsing 100% (82/82). Full detail: `docs/archive/phases-0-2.md`,
DECISIONS.md ADR-0027.

**Phase 3 — Matching: CLOSED** (2026-09-25, ADR-0030). TIE on F1 (LoRA 0.8796 vs CE 0.8737,
McNemar p=1.0000); served CE ONNX fp32 CPU, threshold 0.89, incremental batch, K=100. Full detail:
`docs/archive/phases-3.md`, `docs/audits/phase3-audit.md`.

**Phase 4 — Demand: POSTPONE** (v1 2026-09-26, v2 2026-09-27). v1 and v2 rules both FAIL R1-R3;
re-measure both times `NEEDS ARCHITECT: movement too rare` (15-16 days too short for the 28-day
history rule). `docs/learned/phase4-data-sufficiency.md`, ADR-0031/ADR-0032.

**Phase 5 — Decision engine: IN PROGRESS** (started 2026-09-27). Gate: 50 generated
recommendations, zero margin violations. Sessions: (1) policy thresholds as structured config,
read by the Python margin guard [DONE 2026-09-28, ADR-0034]; (2) index the policy for RAG
(pgvector, local embeddings) + retrieval eval [NEXT]; (3) decision engine (SQL prices + labelled
elasticity placeholder + RAG policy -> LLM -> code guard -> full trace); (4) the 50
recommendations, SPEND-approved, zero-violation report. LLM transport already done (`client.py`);
only §5.3 prompt caching on the system prompt is an optional gap.

**Dataset FROZEN 2026-09-22.** SHA-256 (`docs/learned/phase3-labels.json`, LF-normalised):
`540a4fd6ccfc52525014ac770caadbf544243dccc5a85d3fcb279fd7d052eed4` -- pinned identically in
`tests/test_labels_frozen.py`. No label may change without a reason recorded here first.

## Last done

1. **Phase 5 session 1: policy thresholds config + margin/price guard (2026-09-28, ADR-0034):**
   `config/pricing-policy.toml` + validated Pydantic loader (`policy/thresholds.py`) + deterministic
   guard (`policy/guard.py::enforce`) composing eligibility/margin/speed/charm-rounding; 44 new
   tests with computed expected values (boundary cases, a post-rounding floor breach that must be
   corrected, missing-reference FLAG, unknown-category raise); full suite 827 green.
2. **Pricing-policy APPROVED v0.2 + margin basis decided (2026-09-27, ADR-0033):** Bogdan approved
   the Phase 5 RAG corpus; margin defined on the gross shelf price to match `Product.margin_pct`
   and the VAT-less mock-store data; §1 wording and the number-source line corrected; trimmed to
   the §7 300-500 word budget (500).
3. **Stale note corrected (2026-09-27):** "LLM transport not implemented (ADR-0006)" was wrong --
   `client.py` implements the transport, budget cap, `llm_calls` logging and cache, and was used
   for the Phase 3 hosted baseline. Phase 5 does not rebuild it.
4. **Storage fix shipped (2026-09-27, ADR-0032):** migration 0009 (`raw_payload_sha256`) applied
   and pushed; a review-found BLOCKING bug fixed (`b211a1c`) before any real loss; post-push cron
   run verified (NULL-payload share shows >0 from the day after the first hash).
5. **Phase 4 rule v2 (2026-09-27):** pre-registered (`f40769e`) before any v2 number; measured
   (`f44a704`) -- verdict unchanged, POSTPONE.
6. **Phase 3 closed (2026-09-25):** audit committed; CLAUDE.md/README/COSTS/ADR-0030 updated.

## Open issues

- **Guard scope gaps, all deferred because the mock store has no field for them yet (ADR-0034)**
  -- not stubbed or faked: MAP-restricted brands (policy §2, no MAP field on `Product`); new-product
  age < 14 days (§3, no `listed_at`); manual price lock (§3, no lock field); promotion
  duration/competitor-hold/match-score filters (§4-5, need the decision engine + SQL, sessions 3-4).
- **Neon Free storage (0.5 GB) projected to fill ~2026-12-03** (ESTIMATE, ADR-0032) -- re-run
  `scripts/measure_storage_backfill.py` for a fresh estimate; needs a decision before then. A
  one-off backfill (21.4 MB potential) is identified but not run -- destructive, needs a local
  export first.
- **LLM prompt caching (§5.3) not implemented** -- `client.py` has a disk response cache but no
  provider-side prompt caching on the system prompt. Optional for 50 recommendations; revisit if
  the decision-engine token cost warrants it.
- **Rule v2's decorative-promo suppression cannot reveal a real masked price change by
  construction** -- documented, a v3 decision if Phase 4 reopens.
- **`get_payload()`-routed callers have no end-to-end test against a real Postgres** (only pure
  logic + in-memory SQLite). Low priority.
- **`pytest`'s console-script `.exe` is blocked** by Windows Application Control -- use
  `.venv\Scripts\python -m pytest`.
- **`select_threshold.py` and `score_predictions.py` duplicate `_load_eval_view`** -- extract into
  `src/pricepilot/matching/` before a third caller. ADR-0028 #19.
- **`species` field disagrees with its title on 53/10,532 rows (0.50%)** -- Phase 2 closed, not
  fixed. ADR-0028 #13.
- **Brand extraction has no title-only fallback** -- 3/10,503 rows (petmax), low priority.
- **pentruanimale.ro's regulated-product exposure is "not measured", not "clean".**
- **`make` not installed** on this machine; use `.\make.ps1 <target>` (ADR-0003).
- **Precision at K=100 on real candidates unmeasured** (ADR-0030) -- hand-verified sample at Phase 7.

## Blocked on Bogdan

Phase 5: SPEND approval before the 50-recommendation run (est. ~$2, ADR-0030) -- at session 4.
Phase 4/storage: the one-off payload backfill decision (21.4 MB potential, ADR-0032) -- not urgent.
Phase 7: hosting shortfall ~$4-6 (ADR-0030) -- decide then (host 2 months, or raise "available" by ~$5).

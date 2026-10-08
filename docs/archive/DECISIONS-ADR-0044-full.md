# ADR-0044 full text (archived 2026-10-08 when Phase 7b needed DECISIONS.md headroom)

## ADR-0044 -- Phase 5 gate run: result, and a truncation fault found in the harness

**Context.** Session 5 ran the 50 recommendations (ADR-0042 scheme) on the real LLM, `claude-sonnet-5`
via `LlmProposer`, `max_tokens=400`, approved at est. $0.17. Gate: 50 recommendations, zero margin
violations. Report: `docs/learned/results/phase5/fifty-recommendations.md` (`scripts/report_recommendations.py`).
**Result (all produced by that script).** 50 rows, 50 distinct (product, scenario). **0 margin
violations** among 45 APPROVE rows (each re-checked from stored cost / applied price / category against
the TOML, independent of the guard); 0 direction contradictions; 0 REJECT; 5 FLAG. **Actual spend
$0.240276** (est. $0.1724, ceiling $0.3224; the estimate undercounted output because the model thinks
before answering). Mean latency 2.9 s. Ledger: $0.818442 -> $1.058718, 575 -> 625 `llm_calls` rows.
**How strong the evidence is.** Of the 45 APPROVEs, 42 keep the current price and 3 move it
(p2 369.90, p6 98.99, p19 3.99). None of the 20 scenario rows moved the price, but NOT because the model is robust: all 20 rationales
say the competitor price was labelled hypothetical, i.e. my own prompt note told the model to ignore it
(see the correction below). A no-change keeps today's margin, so this run is weak evidence for the
floor; the floor's protection is shown by the guard's unit tests, the 400k-call review sweep and the catalogue x
strategy sweep with a deliberately below-floor mock proposer (tests/test_decision_engine.py).
**Harness fault found.** Sonnet 5 emits a thinking block by default; at `max_tokens=400` four replies
were cut off (`stop_reason=max_tokens`): three had no text (-> "unparseable" FLAG, p4/p5/p14) and one
(p20 baseline) had text ending mid-sentence, which the parser accepted and the guard APPROVEd at the
UNCHANGED price 12.50. Neither is margin-related, but 3 FLAGs are harness faults, not model decisions.
**Decision.** (1) `RawReply.stop_reason` -> `recommendations.llm_stop_reason` (migration 0014); a
`max_tokens` reply is FLAGged whatever it parses to (a cut-off "12.50" can parse as "12.5"). (2) The
50 rows were backfilled from the response cache by recomputing each row's cache key from its stored
prompt, matching the stored reply text before writing (`scripts/backfill_stop_reason.py`, $0). (3) The
report counts truncated replies (APPROVE included), splits APPROVEs into moved vs unchanged, and
labels FLAG causes: truncated x3, rounding-over-cap x2, synthetic-reference x0. (4) The rows were NOT
re-run or edited; re-running 4 items with a larger cap (est. $0.05-0.07) is a separate SPEND decision
for Bogdan.
**Also found: rounding can breach the daily cap.** p3 (879.00 -> proposed 835.05, exactly -5.0%) and p21
(11.00 -> 10.45, -5.0%) were FLAGged because the nearest charm value (834.90; 9.99) lies outside the 5%
cap. The LLM respected the cap; rounding did not. Guard change (round within the cap) is for the
architect; it cannot create a margin violation.
**Matcher precision, recorded honestly** in `gate-s3b.md`: pre-guard 0.786 (22/28, blind); post-guard
0.9565 (22/23 labelled; 2 newly surfaced links unlabelled, so 0.88-0.96), NOT independent of the errors
the guard was built from, labels Claude-written pending Bogdan's review. The brief's "~0.88-0.92" was an
ESTIMATE and is replaced by the script's bounds.
**Correction after review (same day).** (a) The 20 scenario rows could not stress the floor: the prompt
announced the prices as hypothetical and every rationale cites that as the reason to ignore them. The
real test of this run is the 13 matched baseline rows: 3 moved the price, 5 kept it, 5 were FLAGged
(3 truncated, 2 rounding-over-cap). (b) 17 of the 30 baseline rows had no competitor data, so no move
was ever prompted there; the report said "real inputs" for all 30 and now says 13. (c) The cost
overrun ($0.068) is $0.016 input (69,238 tokens vs ~61.2k estimated) and the rest output (mean 204
tokens vs 100 assumed). (d) The report prose is now computed from the rows, not hard-coded; the
backfill is all-or-nothing (a mismatch raises and rolls back); any provider `stop_reason` other than
`end_turn` / `stop_sequence` / none is distrusted, not just `max_tokens`. **Option not taken:** re-run
the 20 scenarios without announcing the what-if in the prompt (the trace would still label them) to
make them real floor tests, est. ~$0.10 -- a separate SPEND decision.
**Alternatives rejected.** Silently re-running the 4 items (spend beyond the approved line, and it would
overwrite the evidence of the fault); editing the stored verdicts after the fact; dropping the
truncated rows from the denominator.
**Date.** 2026-10-07

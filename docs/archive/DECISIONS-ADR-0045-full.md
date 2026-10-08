# ADR-0045 full text (archived 2026-10-08 to give DECISIONS.md headroom)

## ADR-0045 -- Make the Phase 5 gate meaningful: scenarios become guard stress-tests

**Context.** ADR-0044 found the 50-row gate weak: 42 of 45 APPROVEs were no-change; all 20 scenario
rows self-neutralised because my prompt announced the competitor prices as hypothetical (20 of 20
rationales cite it); 17 baseline rows had no competitor data; 4 replies were cut off at
`max_tokens=400`. Bogdan authorised an explicit adversarial re-run.
**Decision.** (1) The 20 scenario rows are re-framed as GUARD STRESS-TESTS (scenario names
`stress_undercut_15` / `stress_undercut_30`): the competitor prices (observed x 0.85 / x 0.70) are
presented in the prompt as ordinary pricing input, and the model is not told they are synthetic. The
deception is of the model under test only, and is disclosed wherever a human reads the result: the
row's `scenario` starts with `stress_`, the competitor JSON keeps `observed_price`, the report labels
the rows "GUARD STRESS-TEST -- synthetic competitor prices, not a market recommendation". (2) The 4
truncated baselines (p4, p5, p14, p20) and the 20 stress rows were re-run with `max_tokens=1500`
(`run_recommendations.py --refresh`); old rows are relabelled `s5-superseded` in the same transaction
as each new insert (nothing deleted; the old s5 spend stays in `llm_calls` and COSTS). (3) The report
gains a `MoveSummary` table: per group, the model's proposals BEFORE the guard (moves, over the daily
cap, below the floor) and what the guard let through.
**Result (refreshed 50, `scripts/report_recommendations.py`).** 50 rows, **0 margin violations**, 0
direction contradictions, 0 truncated replies; **38 APPROVE / 0 REJECT / 12 FLAG**. The model proposed
a move on 22 rows (14 of 20 stress-tests, 8 of 13 matched baselines); **10 APPROVEs move the price**
(6 stress-test, 4 matched baseline), 28 keep it (17 of those had no competitor data). The 12 FLAGs
are ALL one cause: the model proposed exactly the daily-cap move (-5%), charm rounding to the nearest
charm value overshot the cap, and the guard FLAGged. Refresh run cost **$0.164186** (est. $0.1073,
ceiling $0.4183); the stress rationales no longer cite "hypothetical" (0 of 20).
**What this does and does not show.** Zero model proposals were over the daily cap and zero were below
a floor: a live model that is told the limits obeys them, and the 5% cap keeps one step far from
every floor here (margins 28-56% vs floors 12-30%). So the margin floor was never the binding
constraint in live data; the guard's real live work was the rounding-over-cap FLAGs. The floor's
protection is shown by the guard's unit tests, the 400k-call reviewer sweep and the catalogue x
strategy sweep with a deliberately below-floor mock proposer -- not by these 50 rows. Gate as written
(50 recommendations, zero margin violations): MET, with this stated plainly.
**Defect surfaced, not fixed here.** Charm rounding can push an in-cap move over the cap; it turned
12 of 22 proposed moves into FLAGs: 11 are -5% cuts that nearest-charm rounding overshot, and 1 (p18,
`stress_undercut_15`) is a +5% rise (5.20 -> 5.46) that the ADR-0043 direction rule rounded UP to 5.99,
+15.2%, because the in-cap nearest value (4.99) is on the wrong side. Below ~20 RON the 1-RON charm step
is bigger than the 5% cap, so many moves cannot be expressed either way; a within-cap rule must handle
both directions (a guard change, ADR-0034/0043, for Bogdan to decide). **Review also found** that 3 of
the 20 stress rationales (p-rows 62/65/78 in the report) decline to react for reasons other than the
label (a single observation; a doubtful match), that 7 of 13 matched products carry a real competitor
price below our own cost, and that the earlier 'every FLAG is a cut' wording was wrong for p18.
**Alternatives rejected.** Telling the model the prices are hypothetical again (it ignores them);
forcing a below-floor proposal by instructing the model to ignore the limits (tests the prompt, not
the guard -- the mock-proposer sweep already does the adversarial version without spend).
**Date.** 2026-10-07

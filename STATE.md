# STATE

Phase: 3 — Matching (Phases 0-2 CLOSED)
Updated: 2026-09-25

**Where we are:** Phase 3 items 1-8 are all DONE, item 8 (and the phase's own work) CLOSED
2026-09-24. Headline serving-benchmark table built and reviewer-passed: local CPU serving is
roughly 6,000-9,000x cheaper per 1,000 comparisons than the hosted API. Verdict on the
pre-registered LoRA-vs-cross-encoder rule: a **TIE on F1** (0.8796 vs 0.8737, McNemar p=1.0000) —
the serving benchmark is therefore the result, per CLAUDE.md §7. This session (2026-09-25) ran a
context diet on CLAUDE.md/STATE.md/DECISIONS.md — no code, numbers or labels changed. Dataset
FROZEN 2026-09-22, SHA-256 below. **Next: the architect's phase audit, before Phase 4 (Demand)
starts.**

## Gate progress

**Phase 0 — Foundation: CLOSED** (2026-09-12), all 8 gate boxes met (Docker compose up, migration
applied, pgvector live, `/health` ok, mock-store seeded, `make test`/`make lint` clean, $0 spent).
Full detail: `docs/archive/phases-0-2.md`, `docs/archive/STATE-history.md`.

**Phase 1 — Collection: CLOSED** (2026-09-22). ≥3,000 in-scope listings — MET (18,585/18,703, 3
sources, petmax non-Shopify); ≥7 consecutive days — MET (9 days, 2026-09-13→2026-09-21, strict
definition); ≥400 cross-shop overlap — MET (hand-verified sample, point 1,214–1,342 across two
independent passes, ADR-0023/ADR-0028 addendum #7). Full detail: `docs/archive/phases-0-2.md`.

**Phase 2 — Normalization: CLOSED** (2026-09-14). 85% attribute-accuracy gate MET at 93.2%
(261/280 symmetric, brand excluded; 95.6% kept alongside as the recall figure); weight parsing
100% (82/82); cache proof shown. Full detail: `docs/archive/phases-0-2.md`, DECISIONS.md ADR-0027.

**Phase 3 — Matching: CLOSED 2026-09-24** (opened 2026-09-15). CLAUDE.md §7's 8 items, all DONE:

[x] 1. Candidate retrieval — recall@20 = 88.0% (44/50), Wilson 95% CI [76.2%, 94.4%]. A
    measurement-power finding (the >=90% target sits inside the CI), not a pass or a fail —
    closing it would need ~1,000 verified positive pairs, out of reach. ADR-0028 addendum #8.
[x] 2. Annotation tool — `tools/annotate.html`, keyboard-driven (M/N/S), assisted TRAIN_VAL
    suggestions with blind TEST enforced three independent ways. ADR-0028 addenda #9-#11.
[x] 3. 997/997 pairs labelled by Bogdan — M 354 / N 634 / S 9, one annotator, hand-labelled, not
    generated. ADR-0028 addenda #15, #17, #18.
[x] 4. Product-level split — TEST 287 distinct pairs (300 rows) / TRAIN_VAL 672 distinct pairs
    (697 rows), 0 listing overlap, TEST blind (no rules-engine suggestion ever shown).
    ADR-0028 addenda #10, #16.
[x] 5. Baseline: cross-encoder `mmarco-mMiniLMv2-L12-H384-v1` — **TEST F1 0.8737**, P 0.8925
    (n=93), R 0.8557 (n=97). `docs/learned/phase3-baseline-results.md`, ADR-0028 addenda #19-#20.
[x] 6. Fine-tune: LoRA Qwen2.5-0.5B-Instruct, r=16, epoch 8 — **TEST F1 0.8796**, P 0.8936 (n=94),
    R 0.8660 (n=97). ADR-0028 addenda #21-#22.
[x] 7. Comparison + failure analysis of 10 cases — **verdict: TIE on F1** (0.8796 vs 0.8737,
    McNemar exact p=1.0000). `docs/learned/phase3-model-comparison.md`,
    `docs/learned/phase3-failure-analysis.md`. ADR-0028 addendum #22.
[x] 8. Quantize + CPU benchmark vs. cross-encoder vs. hosted API — CE int8 F1 0.8235 (significant
    drop, McNemar p=0.0042); LoRA int8 non-eligible on two CPUs (AMD + Intel), served as ONNX fp32
    instead (F1 0.8750, parity with the fp16-GPU reference, p=1.0000); hosted v1 F1 0.9082 / v2
    (corrected) F1 0.9036. `docs/learned/phase3-serving-benchmark.md`. ADR-0028 addenda #23-#25.

**Dataset FROZEN 2026-09-22.** SHA-256 (`docs/learned/phase3-labels.json`, LF-normalised):
`540a4fd6ccfc52525014ac770caadbf544243dccc5a85d3fcb279fd7d052eed4` — pinned identically in
`tests/test_labels_frozen.py`. No label may change without a reason recorded here first.

## Last done

1. **Phase 3 item 8 CLOSED, session 3 (2026-09-24)**: LLM int8 variants (V2/V3) both non-eligible
   on Kaggle's Intel CPU — refutes "AMD-specific", weakens "per-tensor/saturation only". Served
   LoRA as ONNX fp32 CPU instead (F1 0.8750, one new TEST touch, McNemar vs. the fp16-GPU reference
   p=1.0000, a parity result). Retracted session 2's wrong hosted empty-reply diagnosis; a
   corrected v2 hosted run (max_tokens=64, $0.42 spent after an explicit yes) cut unparseable
   replies 40/287 -> 11/287, confirming truncation via `thinking` content blocks. Built the final
   headline table (`scripts/build_serving_table.py`, reviewer-passed after two rounds that caught
   real bugs). Ledger: 7 entries. DECISIONS.md ADR-0028 addendum #25.
2. **Full verification green throughout**: `uv run python -m pytest` passed; `ruff check`/`ruff
   format --check` clean; `uv run mypy` clean.
3. **This session (2026-09-25): context diet on CLAUDE.md/STATE.md/DECISIONS.md** — closed-phase
   history moved to `docs/archive/` (nothing deleted), live files condensed to fit the new
   `tests/test_context_budget.py` line limits, `scripts/check_archive_integrity.py` added and
   passing. New ADR-0029. No code, number, or label changed.
4. Prior session: built the Phase 3 item 5/6 scoring harness — pair-text builder, product-level
   train/val split inside TRAIN_VAL, leakage-checked hosted-notebook export, threshold discipline
   (validation only), TEST-touch ledger. DECISIONS.md ADR-0028 addendum #19.
5. Prior session: ran the cross-encoder baseline and the LoRA fine-tune on TEST, once each, per
   the ledger. DECISIONS.md ADR-0028 addenda #20, #22.

## Open issues

- **`pytest`'s console-script `.exe` is blocked** by this machine's Windows Application Control
  policy — `uv run python -m pytest` is the standing workaround, low friction.
- **`scripts/select_threshold.py` and `scripts/score_predictions.py` duplicate `_load_eval_view`**
  byte-for-byte, plus their own separate confusion-matrix logic — worth extracting into
  `src/pricepilot/matching/` before a third caller (e.g. Phase 4/5) needs the same logic; already
  caused one real drift (an F1-convention mismatch, fixed). DECISIONS.md ADR-0028 addendum #19.
- **`species` field disagrees with its own title on 53/10,532 `norm_listings` rows (0.50%)** — a
  `normalize/species.py` extraction defect (animax `product_type` / petmax URL segment vs. title
  text). Not fixed (Phase 2 is closed); matters for Phase 3 rule 1 (species-differs) if the field
  is leaned on again. `docs/learned/phase3-species-field-mismatch-20260921.md`, ADR-0028
  addendum #13.
- **Brand extraction has no title-only fallback.** `canonicalize_brand()` returns `None` when the
  shop's own structured brand field is empty — 3/10,503 rows (all petmax), low priority.
- **pentruanimale.ro's regulated-product exposure is "not measured", not "clean".** VTEX
  `categories`/`categoryId` captured going-forward only (ADR-0025), cannot backfill onto rows
  already collected; the title-text-only diagnostic found 0 hits, the weaker of the two signals.
- **LLM transport not implemented** (ADR-0006) — blocks Phase 5's decision engine.
- **`make` not installed** on this machine; use `.\make.ps1 <target>` (ADR-0003).

## Blocked on Bogdan

Nothing blocking. The Phase 7 hosting reserve must be re-checked at Phase 7 (CX22 no longer sold;
CX23 EUR 5.49/mo, currently listed as unavailable to order) — deferred to Phase 7, not blocking
now.

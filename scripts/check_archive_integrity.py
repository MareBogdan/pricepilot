"""Verify the 2026-09-25 context diet lost nothing.

Reads every pre-diet snapshot under docs/archive/_pre-diet/*.md and checks that every
non-empty, stripped line appears verbatim in the union of {the new CLAUDE.md, STATE.md,
DECISIONS.md} and {every docs/archive/**/*.md file except _pre-diet itself}. A pre-diet
line that was deliberately reworded (condensed, or a small in-place edit) instead of
moved verbatim is not a defect -- but it must be named on REWRITTEN_LINES below, so the
rewording is a reviewed decision, not a silent loss.

Usage: uv run python scripts/check_archive_integrity.py
Exit code 0 iff MISSING == 0.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PRE_DIET_DIR = REPO_ROOT / "docs" / "archive" / "_pre-diet"
ARCHIVE_DIR = REPO_ROOT / "docs" / "archive"
LIVE_FILES = ["CLAUDE.md", "STATE.md", "DECISIONS.md"]

# Every pre-diet line below was deliberately reworded (condensed prose, a path fix, a
# renamed/removed table row) rather than moved verbatim into a live file or an archive
# file. Each was reviewed at diet time; this list is what makes that review durable.
REWRITTEN_LINES: list[str] = [
    # --- CLAUDE.md: Sub-agents table edited (scraper-engineer row removed, retired
    # instead; "Phase 0 creates exactly these three" no longer true with two agents) ---
    "**The main session is the orchestrator and does most of the implementation itself.** Sub-agents fragment context and cost more tokens; they earn their keep only on genuinely isolated, repetitive or high-volume work. Phase 0 creates exactly these three in `.claude/agents/`:",
    "| `scraper-engineer` | One source adapter at a time, against saved fixtures | Repetitive, self-contained, produces a lot of throwaway parsing detail |",
    # --- CLAUDE.md: stale wrapper-module path fixed in section 5 and section 9 ---
    "4. Every LLM call goes through **one wrapper module** (`src/llm/client.py`) which logs model, input tokens, output tokens and computed cost to a `llm_calls` table. No direct SDK calls anywhere else in the codebase.",
    "- An LLM call outside `src/llm/client.py`",
    # --- CLAUDE.md: section 11's illustrative STATE.md example block replaced with the
    # new (section-2-of-the-diet-plan) structure ---
    "Phase: 3 — Matching",
    "Updated: 2026-09-20",
    "[x] candidate retrieval, recall@20 = 0.93",
    "[x] annotation tool built",
    "[ ] 1000 pairs annotated — 340 done",
    "[ ] baseline trained",
    "[ ] fine-tune trained",
    "[ ] serving benchmark",
    "- <anything known-broken or deferred, with why>",
    # --- STATE.md: the short "Gate progress" summary paragraphs for Phases 0-3 were
    # rewritten into new, differently line-wrapped condensed summaries (the detailed
    # "Gate progress detail" narrative deeper in History is preserved verbatim instead;
    # these are the short top-of-file summary lines, not that narrative) ---
    "Phase: 3 — Matching (Phases 0-2 CLOSED)",
    "Updated: 2026-09-24",
    "**Where we are (2026-09-24): Phase 3 items 1-8 are all DONE.** Item 8 closed this session",
    "(session 3): the int8-variants Kaggle run confirmed protocol 5.11's fallback applies — LoRA int8",
    "is non-eligible on BOTH an AMD EPYC 7B12 and an Intel Xeon CPU (V2 median M=0.431/N=0.326, V3",
    'M=0.322/N=0.213, both fail `median_M > 0.5 > median_N`), refuting "AMD-specific" and weakening',
    '"per-tensor/saturation only". LoRA is served/reported as ONNX fp32 CPU instead (F1 0.8750, one new',
    "TEST touch, McNemar vs the fp16-GPU reference p=1.0000 — a parity result). Session 2's hosted",
    'empty-reply diagnosis (commit eb72250, "no request-config defect") was **wrong and retracted**: a',
    "corrected v2 hosted run at max_tokens=64 (protocol 5.12, $0.42 spent after an explicit yes) cut",
    "unparseable replies from 40/287 to 11/287, and 40 of the 287 calls used a `thinking` content block",
    '— exactly matching v1\'s empty-reply count, confirming those were truncated, not settled "no"',
    "answers. Final headline table: `docs/learned/phase3-serving-benchmark.md`",
    "(`scripts/build_serving_table.py`, reviewer-passed after two rounds that caught real bugs). Ledger:",
    "7 entries. Details: DECISIONS.md ADR-0028 addendum #25.",
    "**Next: a context diet, then the architect's phase audit** before Phase 4 (Demand) starts.",
    "## Gate progress",
    "**Phase 0 — Foundation: CLOSED** (2026-09-12). All 8 gate boxes met (Docker compose up, migration",
    "applied, pgvector live, `/health` ok, mock-store seeded, `make test`/`make lint` clean, $0 spent).",
    'Full detail: History → "Gate progress detail — Phase 0 & Phase 1".',
    "**Phase 1 — Collection: CLOSED** (2026-09-22). `docs/SOURCES.md` complete; all 3 adapters",
    "(petmax/pentruanimale/animax) built and tested offline; daily cron running for all 3;",
    "**≥3,000 in-scope listings — MET (18,585 in-scope / 18,703 stored, 3 sources)**; **≥7 consecutive",
    "days — MET (9 days, 2026-09-13→2026-09-21, strict definition)**; **≥400 cross-shop overlap —",
    "MET (hand-verified sample, point 1,214–1,342 across two independent passes, 95% CI clears 400 on",  # noqa: RUF001
    'both — ADR-0023/ADR-0028 addendum #7)**. Full detail: History → "Gate progress detail — Phase 0 &',
    'Phase 1".',
    "**Phase 2 — Normalization: CLOSED** (2026-09-14). **85% attribute-accuracy gate MET: 93.2%",
    "(261/280 symmetric — labelled cells + false positives, brand excluded) — the gate figure; 95.6%",
    "(261/273, labelled-cells-only) kept alongside as the recall figure; weight parsing 100% (82/82).**",
    "Cache proof shown (0 new extractions on a second pass). Four gate-derived fixes approved and",
    "implemented, each measured by population coverage, never by re-scoring the frozen gate sample.",
    'Full detail: History → "Phase 2 — Normalization: CLOSED 2026-09-14 (detail)", DECISIONS.md',
    "ADR-0027.",
    "**Phase 3 — Matching: OPEN since 2026-09-15.** CLAUDE.md §7's 8 items:",
    "[x] 1. Candidate retrieval via embeddings — **recall@20 = 88.0% (44/50), Wilson 95% CI [76.2%,",
    "    94.4%].** CLOSED as a measurement-power finding, not a pass or a fail: at n=50, 88% and the",
    "    >=90% target are not statistically distinguishable (the target sits inside the CI). Closing",
    "    that question would need ~1,000 verified positive pairs (~27,000 draws at this project's",
    "    observed rate) — out of reach; not pursued further. DECISIONS.md ADR-0028 addendum #8.",
    "[x] 2. Annotation tool — `tools/annotate.html`. Keyboard-driven (M/N/S), token-level title diff,",
    "    attribute table, pilot stop, assisted TRAIN_VAL suggestions with blind TEST enforced three",
    "    independent ways, review mode (bug-fixed this session — see Last done).",
    "[x] 3. 800-1,000 pairs labelled by Bogdan — **997/997, M 354 / N 634 / S 9.** Hand-labelled, one",
    "    annotator, not generated. Includes: 4 `trivial_spot_check` occurrences the mechanical checker",
    "    still flags on tier-definition grounds alone, recorded as deliberate annotator",
    "    acknowledgements (`docs/learned/phase3-freeze-acknowledgements.json`) — the checker never",
    "    overrides the annotator; and 1 TEST occurrence (`3f574dad8b6e_b52acad20816_0`) recorded as a",
    "    stated, never-reviewed limitation — its label rests on a 2026-09-21 revision ADR-0028",
    "    addendum #15 judged invalid, and the annotator deliberately let it stand on 2026-09-22 rather",
    "    than reopen it.",
    "[x] 4. Product-level split — **TEST 287 distinct pairs (300 rows) / TRAIN_VAL 672 distinct pairs",
    "    (697 rows)**, 0 listing overlap between splits. TEST is BLIND (no rules-engine suggestion ever",
    "    shown). Post-freeze eval-view numbers (`docs/learned/phase3-eval-view.json`): TEST 97 M / 187 N",
    "    / 3 S (284 scored), TRAIN_VAL 222 M / 444 N / 6 S (666 scored).",
    "[x] 5. Baseline: classical cross-encoder, precision/recall/F1 — **DONE, 2026-09-23.**",
    "    `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`, run on a hosted Kaggle notebook (CPU, seed",
    "    20260923, 8 epochs), scored once on TEST via the item-5 harness (thresholds picked on",
    "    TRAIN_VAL's validation side only, never on TEST). **TEST F1 = 0.8737** — precision 0.8925",
    "    (n=93, Wilson 95% CI [0.8133, 0.9405]), recall 0.8557 (n=97, CI [0.7722, 0.9120]), accuracy",
    "    0.9155 (n=284, CI [0.8773, 0.9426]). F1 itself carries no independent Wilson CI by this",
    "    project's own convention — it is a harmonic mean of two different proportions, not a single",
    "    binomial proportion Wilson's assumptions apply to (its two input CIs are given instead). A",
    "    zero-shot run of the same model was also scored as a comparison point: F1 0.5028, and its",
    "    score distribution shows it is not weakly discriminating but not discriminating at all",
    "    (median ~1.0000 on both M and N labels) — the fine-tuned run is the real baseline, not the",
    "    zero-shot one. Full numbers, per-tier breakdown and named failure tiers:",
    "    `docs/learned/phase3-baseline-results.md`; run facts and limitations (selection-maximum",
    "    caveat, epoch tie-break, discarded under-trained run, device dependency):",
    "    DECISIONS.md ADR-0028 addendum #20. **Next concrete step: item 6 — LoRA/QLoRA fine-tune of a",
    "    0.5B-1.5B instruct model on the same TRAIN_VAL/TEST split, setup session on Opus** (this is",
    "    core ML/architecture work per CLAUDE.md §4's sub-agent rule, staying in the main session).",
    "[x] 6. Fine-tune with LoRA, same TEST set — **DONE, 2026-09-23.** Qwen2.5-0.5B-Instruct, r=16,",
    "    epoch 8 (a tie-break among statistically indistinguishable epochs), val-selected threshold",
    "    0.86 (validation F1 0.8941, a selection maximum). **TEST F1 0.8796**, P 0.8936 (84/94, CI",
    "    [0.815, 0.941]), R 0.8660 (84/97, CI [0.784, 0.920]), accuracy 0.9190 (261/284, CI [0.881,",
    "    0.945]). ADR-0028 addenda #21, #22.",
    "[x] 7. Comparison table + error analysis of 10 representative failures — **DONE, 2026-09-23.**",
    "    Verdict vs the pre-registered rule: **TIE on F1** (0.8796 vs 0.8737; CIs overlap on every",
    "    metric; McNemar exact 8 vs 9 discordant, p = 1.0000). `docs/learned/phase3-model-comparison.md`,",
    "    `docs/learned/phase3-failure-analysis.md` (10 cases chosen by a deterministic rule; 4 look like",
    "    label noise). Reproduce: `uv run python scripts/compare_models.py`,",
    "    `uv run python scripts/select_failure_cases.py`.",
    "[x] 8. Quantize the fine-tune + CPU benchmark (accuracy, p50/p95, $/1,000) vs. cross-encoder vs.",
    "    hosted API — **DONE, 2026-09-24.** CE int8 TEST-touched (F1 0.8235, significant drop vs fp32,",
    "    McNemar p=0.0042). LoRA int8 (three configs: default, V2, V3) NON-ELIGIBLE on both an AMD and",
    "    an Intel CPU (protocol 5.11) — served as ONNX fp32 CPU instead (F1 0.8750, one new TEST touch).",
    "    Hosted v1 (F1 0.9082, 40/287 empty) corrected by a v2 rerun at max_tokens=64 (F1 0.9036,",
    "    11/287 empty — confirms the empty replies were a request-config truncation, not model",
    "    behaviour). Headline table: `docs/learned/phase3-serving-benchmark.md`. Ledger: 7 entries.",
    "    Reproduce: `uv run python scripts/build_serving_table.py`.",
    "**Dataset FROZEN 2026-09-22.** SHA-256 (of `docs/learned/phase3-labels.json`, LF-normalised)",
    "`540a4fd6ccfc52525014ac770caadbf544243dccc5a85d3fcb279fd7d052eed4` — recorded identically in",
    "`tests/test_labels_frozen.py` and this file's marker line below. No label may change without a",
    "reason recorded here first; `test_frozen_labels_hash_unchanged` enforces it and now runs (not",
    "skipped).",
    "Frozen labels SHA-256: `540a4fd6ccfc52525014ac770caadbf544243dccc5a85d3fcb279fd7d052eed4`",
    "## Last done",
    "1. **Ran the Phase 3 item 5 baseline and scored it on TEST, once** (ADR-0028 addendum #20):",
    "   `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`, hosted Kaggle notebook, CPU, seed 20260923.",
    "   Committed the four hosted-notebook prediction files unchanged (SHA-256 in the commit message,",
    "   independently re-verified — id sets, no NaN, no TEST leakage into TRAINVAL — before commit,",
    "   not just taken on trust); selected thresholds on TRAIN_VAL's validation side only (zero-shot",
    "   0.86, fine-tuned 0.89); scored both models on TEST exactly once each. **Fine-tuned TEST: F1",
    "   0.8737, P 0.8925 (CI [0.8133, 0.9405]), R 0.8557 (CI [0.7722, 0.9120]).** Four commits, one per",
    "   task (predictions / thresholds / scoring / analysis) — see item 3 below: the first three ran",
    "   without the required `reviewer` pass, caught and corrected before the fourth.",
    "2. **Wrote the honest analysis** (`docs/learned/phase3-baseline-results.md`): both recall",
    "   readings side by side (all 97 positives vs. excluding 13 duplicated `trivial_spot_check`",
    "   positives), per-tier P/R/F1 and raw tp/fp/fn/tn for every tier, and the zero-shot model's score",
    "   distribution showing it is not weakly discriminating but not discriminating at all (median",
    "   ~1.0000 on both M and N) — built a new script, `scripts/measure_score_distribution.py`, so",
    "   every number in the doc has a script behind it (CLAUDE.md §9).",
    "3. **Three reviewer rounds on this doc/script, not one** — the first found the median-score claim",
    "   had no script behind it (fixed by writing the script above); the second, after that fix, found",
    "   the script's new per-tier confusion output had been read out by hand rather than run, plus a",
    '   factual error (a 1-positive tier mislabelled "zero-positive") and a misleading "second-highest',
    '   FP rate" claim that ignored two actually-higher reportable-tier rates; the third confirmed all',
    "   fixes and found only small non-blocking wording/staleness issues, also fixed. **This session",
    "   also caught its own process lapse**: the first three commits (predictions, thresholds, scoring)",
    "   were made without the required `reviewer` pass — caught immediately after, and every commit",
    "   from that point on went through review first.",
    "4. **Full verification suite green throughout**: `uv run python -m pytest` — 605 passed; `ruff",
    "   check .` / `ruff format --check .` — clean; `uv run mypy` — success, 58 source files (was 57",
    "   before `measure_score_distribution.py`).",
    "5. Prior session (2026-09-22/23): built the Phase 3 item 5 scoring harness itself",
    "   (`split_train_val.py`, `export_model_inputs.py`, `select_threshold.py`,",
    "   `score_predictions.py`) — full account in DECISIONS.md ADR-0028 addendum #19, not duplicated",
    "   into this file's History section.",
    "## Open issues",
    # --- STATE.md: still-OPEN items condensed to <=3 lines each in the live file; full
    # original multi-line wording kept only here, not archived (only RESOLVED items were
    # moved to docs/archive/STATE-history.md) ---
    "- **Flagged 2026-09-23: `pytest` (the console-script `.exe`) is blocked by this machine's Windows",
    "  Application Control policy** — `uv run python -m pytest` works and was used throughout this",
    "  session instead; a low-friction workaround, not a blocker. `mypy` and `selectolax` (used by the",
    "  scraper adapters) were also transiently blocked earlier in this same session and resolved",
    "  themselves mid-session without any code or config change — consistent with the policy's known",
    "  scan-then-allow behaviour on first use of a given binary/DLL, not a regression.",
    "- **Flagged 2026-09-23 (deferred, not fixed): `scripts/select_threshold.py` and",
    "  `scripts/score_predictions.py` duplicate `_load_eval_view` byte-for-byte**, and each has its own",
    "  confusion-matrix/precision/recall computation (`_f1_at_threshold` vs `score()`). A reviewer",
    "  finding during this session's own work — the two scripts already disagreed on the undefined-F1",
    "  convention as a direct result of this duplication (fixed this session), which is exactly the",
    "  drift risk of having the same logic in two places. Worth extracting into",
    "  `src/pricepilot/matching/` alongside `metrics.py` and `pair_text.py` before Phase 3 item 6",
    "  (fine-tune) adds a third caller of the same logic — not urgent enough to justify a larger",
    "  refactor under this session's own time budget.",
    "- **Flagged 2026-09-21 (ADR-0028 addendum #13, TASK 5): `species` field disagrees with its own",
    "  title on 53/10,532 `norm_listings` rows (0.50%)** — 46 `animax_ro`, 7 `petmax_ro`, 0",
    "  `pentruanimale_ro` (structurally impossible there — see below). A `normalize/species.py`",
    "  extraction defect, found by `scripts/check_label_rule_consistency.py`'s class (e) on the 300-row",
    "  TEST label set (1 instance, `3f574dad8b6e...`) and then measured over the whole population by",
    "  `scripts/measure_species_field_mismatch.py`. Every mismatch is a case where `animax_ro`'s",
    '  `raw_payload["product_type"]` or `petmax_ro`\'s URL path segment (the STRUCTURED per-source',
    "  signal `classify_species()` trusts ahead of the title) disagreed with what the title itself",
    "  says; `pentruanimale_ro` has no structured signal at all, so its stored field IS the title",
    "  keyword test and can never disagree with it by construction. **Not fixed this session — Phase 2",
    "  is closed, this is a recorded finding, not a reopening.** Full detail, methodology and examples:",
    "  `docs/learned/phase3-species-field-mismatch-20260921.md`. Matters most for Phase 3's rule 1",
    "  (species-differs): a wrong `species` field can silently suppress a real cross-species `N` the",
    "  annotator would have caught reading the actual title, and worth reconsidering before Phase 3",
    "  fine-tuning leans on the field again — but no evidence yet that it changed any of the 300 TEST",
    "  labels themselves (the one overlapping instance was already correctly labelled `M` by the",
    "  annotator, reading the real title, not the wrong field).",
    "- **Brand extraction has no title-only fallback.** `canonicalize_brand()` returns `None` when the",
    "  shop's own structured brand field is empty — only 3 of 10,503 rows today (all petmax), so low",
    "  priority, but the function's `title` parameter is already reserved for this if it ever becomes",
    "  worth building.",
    '- **pentruanimale.ro\'s regulated-product exposure is "not measured", not "clean".** Its 0-hits',
    "  result from the 2026-09-13/14 title-text diagnostic is real but incomplete: the source also",
    "  carries VTEX `categories`/`categoryId` (confirmed live) that could in principle reveal a",
    "  veterinary-diet branch, but that field was never captured before ADR-0025 started capturing it",
    "  **going forward only** — it cannot be backfilled onto rows already collected. Do not read",
    "  pentruanimale's 0-Tier-A-hits as evidence it has no leak; it means only that title text alone",
    "  found nothing, which is the weaker of the two signals everywhere else it was checked.",
    "- **LLM transport not implemented.** ADR-0006.",
    "- **`make` not installed.** `.\\make.ps1 <target>` is the Windows path. ADR-0003.",
    "## Blocked on Bogdan",
    "**Nothing on item 8 — it is closed.** The int8-variants Kaggle run (session 2's blocking item)",
    "completed and session 3 scored it; see the header above.",
    "Still open: the Phase 7 hosting reserve must be re-checked (CX22 no longer sold; CX23 EUR",
    "5.49/mo and unavailable to order today) — deferred to Phase 7, not blocking now.",
    '(The prior "run the Kaggle serving benchmark" item here is done — session 1\'s serving run',
    "completed and session 2 part 1 scored it; see the header above.)",
    "Dropped, resolved:",
    '- *"`3f574dad8b6e_b52acad20816_0` needs a real, confirmed re-decision"* — resolved 2026-09-22: the',
    "  annotator explicitly decided to let its N label stand, recorded as a stated, never-reviewed",
    "  limitation rather than reopened.",
    '- *"The 4 class-d occurrences need a decision"* — resolved 2026-09-22: recorded as deliberate',
    "  annotator acknowledgements; the checker never overrides the annotator.",
    '- *"After both are resolved: re-run the checker, then `scripts/freeze_labels.py --freeze`"* — done:',
    "  dataset frozen 2026-09-22, hash above.",
    '- *"Every Phase 1 gate box is met except 7 consecutive days of history"* — resolved: Phase 1 is',
    "  CLOSED (9 consecutive days measured, 2026-09-13→2026-09-21).",
    '- *"Bogdan needs to review [retrieval closed / queue frozen / split+assisted flow built / pilot',
    '  stop] before labelling begins"* — resolved: labelling is long since complete (997/997, reviewed,',
    "  frozen); the review checklist that preceded it is historical.",
    "Phase 3 item 5 (baseline) is the next action and is self-directed — no decision from Bogdan is",
    "needed to start it.",
]

REWRITTEN_SET = {line.strip() for line in REWRITTEN_LINES}


def non_empty_stripped_lines(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [line.strip() for line in text.splitlines() if line.strip()]


def main() -> int:
    pre_diet_files = sorted(PRE_DIET_DIR.glob("*.md"))
    if not pre_diet_files:
        print(f"ERROR: no pre-diet files found under {PRE_DIET_DIR}")
        return 1

    found_lines: set[str] = set()
    for name in LIVE_FILES:
        found_lines.update(non_empty_stripped_lines(REPO_ROOT / name))
    for path in ARCHIVE_DIR.rglob("*.md"):
        if PRE_DIET_DIR in path.parents:
            continue
        found_lines.update(non_empty_stripped_lines(path))

    total = 0
    found = 0
    on_rewritten_list = 0
    missing: list[tuple[str, str]] = []

    for pre_diet_path in pre_diet_files:
        for line in non_empty_stripped_lines(pre_diet_path):
            total += 1
            if line in found_lines:
                found += 1
            elif line in REWRITTEN_SET:
                on_rewritten_list += 1
            else:
                missing.append((pre_diet_path.name, line))

    print(f"Total lines checked: {total}")
    print(f"Found verbatim:      {found}")
    print(f"On REWRITTEN list:   {on_rewritten_list}")
    print(f"MISSING:             {len(missing)}")

    if missing:
        print("\nMISSING lines (not found verbatim, not on the REWRITTEN list):")
        for source, line in missing:
            print(f"  [{source}] {line}")
        return 1

    print("\nOK: every pre-diet line is accounted for.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

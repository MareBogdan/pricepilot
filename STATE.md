# STATE

Phase: 4 — Demand (data-sufficiency measurement first; Phases 0-3 CLOSED)
Updated: 2026-09-25

**Where we are:** Phase 3 closed by the architect's audit (`docs/audits/phase3-audit.md`, ADR-0030):
every number recomputed and reproduced, gate MET as a **TIE on F1** (LoRA 0.8796 vs cross-encoder
0.8737, McNemar p=1.0000). Served model: cross-encoder ONNX fp32 on CPU, incremental batch, K=100.
Dataset FROZEN 2026-09-22, SHA-256 below. **Next: the Phase 4 measurement session (no model):**
is there enough real price history, and how many new `content_hash` values arrive per day?

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

**Phase 3 — Matching: CLOSED** (2026-09-25, audit + ADR-0030). Gate MET as a TIE on F1 (LoRA 0.8796
vs CE 0.8737, McNemar p=1.0000); served model CE ONNX fp32 CPU, threshold 0.89, incremental batch,
K=100; CE int8 reported not served; LoRA int8 non-eligible (fp32 fallback F1 0.8750). Full detail:
`docs/archive/phases-3.md`, `docs/archive/STATE-history.md`, `docs/audits/phase3-audit.md`.

**Dataset FROZEN 2026-09-22.** SHA-256 (`docs/learned/phase3-labels.json`, LF-normalised):
`540a4fd6ccfc52525014ac770caadbf544243dccc5a85d3fcb279fd7d052eed4` — pinned identically in
`tests/test_labels_frozen.py`. No label may change without a reason recorded here first.

## Last done

1. **Phase 3 closed (2026-09-25)**: audit committed; CLAUDE.md, README, COSTS, ADR-0030 and the
   two stale Phase 3 sentences updated; Phase 3 text archived verbatim. No number, label or
   results file changed.
2. Context diet on CLAUDE.md/STATE.md/DECISIONS.md (ADR-0029, 2026-09-25).
3. Phase 3 item 8 closed (2026-09-24): LoRA int8 non-eligible, ONNX fp32 fallback; hosted v2 run.

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
- **Precision at K=100 on real candidates unmeasured** (ADR-0030) — hand-verified sample of produced links at Phase 7.

## Blocked on Bogdan

Phase 7: hosting shortfall ~$4-6 (ADR-0030) — decide then (host 2 months, or raise "available" by ~$5).

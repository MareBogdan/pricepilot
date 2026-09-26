# Phase 3 — Matching (verbatim from CLAUDE.md section 7, archived 2026-09-25)

### Phase 3 — Matching ⭐ core of the project
1. Candidate retrieval via embeddings, measured by recall@20 (target ≥90%)
2. A local annotation tool — single HTML page, keyboard-driven (`M`/`N`/`S`), so 200 pairs/hour is realistic
3. **The user annotates 800–1,000 pairs manually.** At least 40% hard cases: same model different capacity, single unit vs multipack, consecutive generations, same title different brand. This dataset is the most valuable artefact in the repo — it is not generated, it is labelled.
4. Product-level train/val/test split
5. Baseline: classical cross-encoder. Record precision/recall/F1.
6. Fine-tune a 0.5B–1.5B instruct model with LoRA/QLoRA. Same test set.
7. Comparison table + error analysis of 10 representative failures

8. Quantize the fine-tuned model and benchmark it running on CPU: accuracy, p50/p95 latency, cost per 1,000 comparisons — against both the classical baseline and a large hosted API model

**Gate:** documented baseline vs fine-tuned comparison on a held-out product-level test set, broken down by category as well as overall, plus the three-way serving benchmark above.

> If fine-tuning does not beat the baseline, write that down honestly and analyse why. A correctly reported negative result is stronger evidence of competence than an unexplained good number.

**Fine-tune versus cross-encoder is an uncertain bet, and that is accepted going in.** The fine-tune
may not beat the classical cross-encoder on F1. That does not make the phase a failure, and it does
not license quietly reframing the goal afterwards:

- If the fine-tune **wins on F1** — report the margin, broken down by category, with error analysis.
- If the two **tie on F1** — the serving benchmark is the result. A local quantized model matching a
  cross-encoder at some cost per 1,000 comparisons and some p95 latency is a real, reportable finding,
  and it is the engineering question a hiring manager actually cares about. Report cost and latency
  as the headline, F1 as the parity claim it is.
- If the fine-tune **loses** — say so, in the README results table, and analyse why.

Whichever happens, report what actually happened. The decision rule is written down here, before the
numbers exist, precisely so the numbers cannot choose the framing.

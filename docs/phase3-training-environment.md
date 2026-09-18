# Phase 3 training environment

## 1. What can run where

**DLL-blocking claim: VERIFIED**, not asserted fresh — two dated incidents in `DECISIONS.md`.

| Library | Status | Evidence |
|---|---|---|
| `psycopg` | Blocked; worked around with `pg8000` | ADR-0028 addendum #5, ~L1945 |
| `sentence-transformers` | Blocked — `DLL load failed ... _argkmin: Application Control policy` | ADR-0028 addendum #6, ~L2019 |
| `torch`, `transformers` | Import cleanly | STATE.md ~L850 |
| `peft` | Not yet checked | STATE.md ~L854 |

Per STATE.md ~L850-856, LoRA/QLoRA **training** needs the full optimizer/scheduler/mixed-precision
chain through the same blocked extensions — no `pg8000`-style workaround exists. The repo already
plans a hosted GPU notebook for the fine-tune; this doc verifies that and prices the options.

| Phase 3 step | Runs locally? |
|---|---|
| Baseline (cross-encoder, `sentence-transformers`) | **No** — same blocked import |
| LoRA/QLoRA fine-tune | **No** — confirmed above |
| Evaluation (score predictions vs. TEST labels) | **Yes** — plain JSON arithmetic, no blocked import |

## 2. Hosted GPU options

| Option | Price/hr | Limit | JSON in | Adapter out |
|---|---|---|---|---|
| **Colab free (T4)** | $0 | ~12h/session, ~15-30 GPU-hr/wk ESTIMATE, ~90min idle disconnect | Upload / Drive | Download / Drive |
| **Kaggle free (T4/P100)** | $0 | 12h/session, 30 GPU-hr/wk (stated) | "Add Data" upload | Save "Output" |
| **RunPod Community (RTX 4090)** | **$0.34/hr** | No cap, per-second billing | scp / web terminal | scp before stop |

Sources: runpod.io/gpu-models/rtx-4090 (Sept 2026); research.google.com/colaboratory/faq.html
(Google doesn't publish weekly hours — ESTIMATE); kaggle.com/docs/efficient-gpu-usage (stated).

CLAUDE.md §5's smoke run (~200 examples, minutes) fits Colab/Kaggle free — **$0**. A real run
(separate approval) likely still fits one free session for a 0.5B-1.5B model on a few hundred
pairs. RunPod is the fallback, against $15 reserved for VPS hosting first (§5 priority order).

## 3. Same-TEST-set evaluation, no leakage

TEST = **287 distinct pair_ids** (`phase3-annotation-split.json`, `test_distinct_pair_ids: 287`,
ADR-0028 addendum #11 stratified split).

| Step | Where | Leakage guard |
|---|---|---|
| Baseline scoring | Colab/Kaggle (blocked locally, §1) | Sees listing text only, never TEST labels |
| Fine-tune training | Colab/Kaggle/RunPod, TRAIN_VAL only (697 rows / 802 listings) | Zero content_hash overlap TEST/TRAIN_VAL (STATE.md ~L437) |
| Predictions on TEST | Same session, inference only | No TEST label is a training input |
| Scoring | **Local**, arithmetic on two JSON files | Same script/TEST file, both models |

Both models' predictions return as KB-sized JSON, scored locally — the comparison needs no GPU.

## 4. Recommendation

**Kaggle Notebooks free tier for both baseline and fine-tune (smoke, then real if approved);
score locally. Cost: $0.** Kaggle states its 30 GPU-hr/week quota directly, unlike Colab's
undisclosed limit, and uploading one JSON file is simpler than Drive mounting.

**What would change this:** repeated Kaggle/Colab preemption — then move the *real* run (not the
smoke run) to RunPod at $0.34/hr (~$0.68-$1.02 for 2-3h), trivial against the ~$20 remaining.

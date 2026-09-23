# Phase 3 item 8 — serving benchmark protocol (pre-registered)

Written 2026-09-23, BEFORE any benchmark code, notebook, hosted call or serving number exists.
It is the item-8 counterpart of the decision rule in `docs/phase3-baseline-model-choice.md`. The
numbers cannot choose the framing; this file does. Prices come only from
`docs/phase3-serving-prices.md` (which records that CX22 is no longer listed; its 2 vCPU / 4 GB
successor CX23 is the VPS priced here, and it is currently unavailable to order -- a Phase 7 issue).

Context: item 7 ended in a tie on F1 (LoRA 0.8796 vs fine-tuned cross-encoder 0.8737, McNemar
p = 1.0000). Under CLAUDE.md §7's tie rule the serving benchmark is the headline of the phase.

## 5.1 Decisions already taken (not reopened)

a) **ONNX Runtime with dynamic int8 quantization, for BOTH local models.** Not GGUF/llama.cpp: the
   LoRA model's two-token readout (" Yes"/" No" logits after "Answer:") would become a logprob
   hack there, and llama.cpp would put a C++ runtime into the CX22-class Docker image. ONNX returns
   logits directly, `optimum` does the export, and one runtime serves both models — so latency
   compares models, not runtimes.
b) **Kaggle CPU (Accelerator = None) is a PROXY for the Hetzner VPS (2 vCPU / 4 GB class).** Latency
   runs are pinned to 2 threads: ORT `intra_op_num_threads=2`, `inter_op_num_threads=1`, sequential
   execution, `OMP_NUM_THREADS=2`, `os.sched_setaffinity` on 2 cores. Unpinned, Kaggle's 4 vCPUs
   give a falsely optimistic number. Every quoted latency is labelled "Kaggle 2-thread proxy" and is
   re-measured on the real VPS in Phase 7. Parity/accuracy scoring is NOT pinned (it measures
   correctness, not speed).
c) **The hosted API model is zero-shot.** It is NOT a fair accuracy comparison. It is a
   cost/latency comparison and shows what a large model gets off the shelf.

## 5.2 Models and ids

Cross-encoder: the retrain's weights, under the id the reproduction verdict assigns
(`docs/learned/results/ce-reproduction-check.json`). Local, per model: PyTorch fp32 CPU (reference
only), ONNX fp32 (export validity, latency), ONNX int8 (the served candidate). New ledger ids:
`<cross-encoder id>-int8` and `qwen2.5-0.5b-lora-ep8-int8` — NEW entries, never `--rescore`.

LoRA: the adapter is merged into the base (`merge_and_unload`, fp32) before export. The exported
graph outputs ONLY the two readout logits (" Yes", " No") at the last prompt position. No KV-cache,
one forward pass. Exporting full-vocab logits at every position would make latency measure work
the decision never uses. The readout (token ids resolved as in the training notebook, softmax over
the two logits) must match the training notebook's.

## 5.3 Scoring sets

Cross-encoder: all 959 pairs. LoRA: the 133 scored validation pairs plus the 287 TEST pairs = 420.
The 533 train pairs play no part in item 8.

## 5.4 Gates, in order — session 2 stops at the first that fails

- **G1 export validity.** ONNX fp32 vs the in-notebook PyTorch fp32 CPU reference on the model's
  scoring set: max |diff| <= 1e-3 AND zero decision flips at the ledgered threshold. (Not against
  the committed LoRA preds: those are fp16 on a T4 GPU.)
- **G1b, reported not gated.** LoRA PyTorch fp32 CPU vs the committed fp16 GPU preds: max/mean
  |diff| and flips at 0.86.
- **G2, reported not gated.** int8 vs ONNX fp32 on validation: flips and max/mean |diff|.
- **G3.** The int8 threshold is chosen by `scripts/select_threshold.py` on the 133 validation pairs
  only. The fp32 thresholds are NOT reused, because int8 moves the scores.
- **G4.** TEST is touched once per int8 model via `scripts/score_predictions.py`. int8 is reported
  against its fp32/ledgered counterpart with McNemar exact (paired). Any drop is reported as it is.

## 5.5 Latency protocol

Batch 1, pinned as in 5.1b. Discard 10 warm-up pairs, then the 287 TEST pairs in `pair_id` order,
one pass: 287 samples per model variant, timed with `time.perf_counter_ns`. Report p50, p95, p99
and mean, both end-to-end (tokenize + run + readout) and run-only. Report the input-token-length
distribution (min/p50/p95/max) per model. Throughput: the first 160 TEST pairs in `pair_id` order,
as 10 batches of 16, in pairs/s. Also report peak RSS per model, ONNX file size for fp32 and int8,
the exact parameter count, and `lscpu` model name + CPU count.

## 5.6 Cost formula, fixed now

Local $/1,000 comparisons = VPS hourly USD x (1000 / batch-16 throughput in pairs/s) / 3600, with
the hourly price from `docs/phase3-serving-prices.md`. The VPS is flat-fee, so the real marginal
cost of one more comparison is ~0; the figure only normalises CPU time against a per-token API.
Also give the wall-clock hours on the VPS for a full re-match of the current population at K=20
(210,640 scorings) and K=100 (1,053,200) — the input the pending K decision (ADR-0028 #7 item 3)
was waiting for. Hosted $/1,000 = measured tokens x published price.

## 5.7 Hosted API

Provider Anthropic (the only one the wrapper allows). Model: the current Sonnet-class model from
the prices doc, id pinned in the SPEND line. The SAME `llm-prompt-v1` text from
`src/pricepilot/matching/llm_prompt.py`, temperature 0, max_tokens 5. Parse "Yes" -> 1.0 (M),
"No" -> 0.0 (N). Anything else is counted, reported and scored as 0.0, and is never retried into
a better answer. Fixed threshold 0.5, stated as NOT selected. The 287 TEST pairs only; no
validation run, since there is no threshold to pick. One ledgered TEST touch as
`hosted-<model-id>-zeroshot`. Every call goes through `src/pricepilot/llm/client.py` with the
`LLM_BUDGET_USD` cap and the content-hash cache. Latency includes the network from Romania and is
labelled that way.

## 5.8 Headline table shape (filled in session 2)

model | TEST F1 with P and R (k/n, Wilson CIs) | p50 / p95 ms | throughput | $/1,000 | peak RSS |
artefact size | proxy note.

## 5.9 If G1 fails for the LoRA export

Stop and report. No silent fallback to PyTorch-on-CPU latency.

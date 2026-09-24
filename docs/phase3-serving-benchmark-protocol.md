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

## 5.10 Stated deviations (added 2026-09-23, after the protocol commit; sections above unchanged)

Recorded here, in the open, so no number is quoted without them.

1. **int8 uses ORT's default `reduce_range`** (`quantize_dynamic`, QInt8 weights, per-tensor). On
   CPUs without VNNI this can saturate; `env-facts.json` records `avx512_vnni` / `avx_vnni` so the
   result can be read against the actual CPU. If G2 flips look odd, that is the first suspect.
2. **The 10 warm-up pairs are also among the 287 measured pairs** (the first 10 in `pair_id`
   order). ONNX Runtime has no cross-call result cache, so no bias is expected.
3. **Export is `torch.onnx.export` with a two-logit wrapper, not `optimum`** (5.1a's wording):
   `optimum` exports standard heads only, and 5.2 requires a graph that outputs just the two readout
   logits. One runtime (ONNX Runtime) still serves both models.
4. **Peak RSS** is measured in a fresh child process per ONNX variant that loads only that one
   session, read from `/proc/self/status` (`VmHWM` = peak, `VmRSS` = current) rather than
   `ru_maxrss`: `ru_maxrss` is preserved across fork+execve on Linux, so a child started by
   `subprocess.run` from the parent notebook process was reporting the *parent's* peak, not its
   own (caught in the 2026-09-24 Kaggle smoke run: `latency-ce-onnxfp32.json` and
   `latency-ce-int8.json` both reported `peak_rss_mb = 3341.918`, identical to the parent).
   `VmHWM`/`VmRSS` belong to the `mm` this process got at exec, so they are this child's own.
   Two figures per variant: after batch-1 latency, and after the batch-16 throughput pass; plus
   the peak so far right after session load (so it includes the runtime imports). Current RSS
   (`VmRSS`) is recorded alongside each peak reading, not just the peak.
5. **Hosted temperature (5.7) could NOT be 0.** `claude-sonnet-5`'s API rejected the parameter:
   `400 invalid_request_error: "temperature is deprecated for this model"` (request
   `req_011CfM2h7y8RASFkHdhMxhkc`; a rejected request, nothing billed). The hosted run sends no
   temperature, so the model's default sampling applies. Everything else in 5.7 is as registered.
6. **Hosted result caveat, observed:** 40 of 287 replies came back empty within `max_tokens=5`. Per
   5.7 they are counted, scored 0.0 and NOT retried; the hosted recall is therefore understated by
   an unknown amount. The hosted F1 stays a zero-shot cost/latency data point, not a fair accuracy
   comparison (5.1c).
7. **VPS price basis:** CX22 is no longer listed; CX23 (same specs) at EUR 0.0088/h is used, and it
   is currently unavailable to order (`docs/phase3-serving-prices.md`).

## 5.11 LLM int8 is non-discriminating with the default config -- pre-registered variant rule
(added 2026-09-24, session 2, BEFORE any code in `notebooks/phase3-llm-int8-variants.ipynb` exists)

**Finding, from the committed serving run** (`scripts/check_serving_gates.py`'s G2 diagnostic,
validation labels only): the default dynamic int8 quantization (`quantize_dynamic`, QInt8
weights, per_channel=False, reduce_range=False -- protocol 5.10 item 1) destroys the LoRA model's
discrimination. On the 133 validation pairs, median P(Yes) is 0.235 for true M and 0.251 for true
N (fp32 on the same pairs: 0.995 / 0.000) -- the two classes are no longer separated by score at
all. Best validation F1 is 0.514, achieved only by predicting M for everything. **No TEST touch
follows for this configuration**: scoring a non-discriminating model against TEST would add a
meaningless ledger row (protocol 5.4 G4 exists to report a real result, not to burn a TEST touch
on a broken one).

**Probable cause (hypothesis, to be tested by the variants below, not asserted as a finding):**
the Kaggle CPU is an AMD EPYC 7B12, AVX2 WITHOUT VNNI (`env-facts.json`). ORT's dynamic U8S8 path
on AVX2-without-VNNI can saturate in int16 accumulation with `reduce_range=False`; Qwen's
activation outliers make per-tensor weight quantization fragile on top of that. The cross-encoder,
scored with the SAME default config, degrades (G4: F1 0.8235 vs fp32's 0.8737, McNemar
p=0.0042) but does not stop discriminating -- consistent with the LLM's decoder being the more
fragile of the two under this config, not with the CPU being universally unusable for int8.

**Candidate configurations, all ORT `quantize_dynamic`, QInt8 weights:**
- **V1** = current default (`per_channel=False`, `reduce_range=False`) -- already measured above,
  broken. Not re-run.
- **V2** = `per_channel=True`, `reduce_range=True`.
- **V3** = V2 + `op_types_to_quantize=["MatMul"]` only (the embedding `Gather` and everything else
  stays fp32; only the matrix multiplies are quantized).

**Selection rule**, applied on the 133 VALIDATION pairs only (never TEST):
1. A variant is **eligible** only if its validation M/N median P(Yes) are separated:
   `median_M > 0.5 > median_N`. A variant that fails this is not a candidate for TEST at all,
   regardless of its F1 (V1 itself fails this test, which is exactly why it never reached TEST).
2. Among eligible variants, the winner is the one with the **highest best-threshold F1** on the
   133 validation pairs (found the same way `scripts/select_threshold.py` finds it).
3. **Ties within 0.005 F1** are broken by the **lower p50 latency** (pinned, batch 1, as in 5.5).
4. **If NO variant is eligible**, the finding is stated exactly as: "dynamic int8 destroys this
   0.5B decoder on AVX2-without-VNNI." In that case the LLM is served and reported as **ONNX
   fp32**, with one new TEST touch for `qwen2.5-0.5b-lora-ep8-onnxfp32-cpu` (`score_predictions.py`,
   threshold re-selected on validation from the fp32 scores already committed), and **no int8 LLM
   row exists** in the headline table.
5. Only the SELECTED variant's TEST predictions are ever read, and only once, via
   `scripts/score_predictions.py`, as `qwen2.5-0.5b-lora-ep8-int8-<v>` (`<v>` = `v2` or `v3`). The
   other non-selected eligible variant's TEST predictions, if any were produced, are never scored
   against TEST -- computing but not reading them is fine; reading them is the thing this rule
   exists to prevent.

**Cross-encoder robustness check, deferred (not a second CE TEST touch, and not part of this
notebook):** V2 is also intended for the cross-encoder, scored on validation and reported as a
validation-only drift check next to the already-recorded CE int8 TEST result (task 2 of this
session). `notebooks/phase3-llm-int8-variants.ipynb` (below) needs only the two inputs its runbook
lists -- the CE weights input (`ce-ft-best/`, from `notebook87be682cf2`) is deliberately NOT one of
them, so this check is not built into that notebook and has not been run as of this addendum. It
is picked up as a small additional cell in `phase3-serving-benchmark.ipynb` (which already has the
CE weights input) whenever that notebook is next run, or as its own tiny notebook -- whichever
comes first. Whichever runs it, the rule is fixed now: the CE int8 TEST result stays
`mmarco-mMiniLMv2-finetuned-ep6-int8` at threshold 0.83, F1 0.8235, unchanged by this check,
whatever it shows.

**Notebook** (`notebooks/phase3-llm-int8-variants.ipynb`, CPU accelerator, internet on): re-merges
the LoRA adapter from `notebookf26a8565eb`'s output exactly as `phase3-serving-benchmark.ipynb`
does (same `ENV-COMPAT-BEGIN`/`END` block, same `LLMWrap` export, same worker script, verbatim --
`notebookf26a8565eb`'s output is used again rather than depending on `notebook79d89ab24c`, which is
not needed here). Stages: merge; export fp32 (gated -- refuses to continue if
`max|diff|` against the already-committed `docs/learned/results/serving/preds-llm-onnxfp32-val.json`
exceeds `1e-5`, since this is a fresh re-merge/re-export and must reproduce the committed fp32
reference before any new int8 variant is trusted); quantize V2 and V3; score val+test for each
(unpinned); latency+RSS for each (pinned, fresh worker per variant, `VmHWM`/`VmRSS` as fixed in
this session's task 0). `SMOKE` flag defaults to `True`, as in the serving notebook.

# Phase 3 item 8 session 2 — LLM int8 variants: Kaggle runbook

For Bogdan. Follow it literally. Protocol: `docs/phase3-serving-benchmark-protocol.md` section
5.11 (pre-registered before this notebook was written).
Notebook: `notebooks/phase3-llm-int8-variants.ipynb` (CPU only, no GPU).

## A. Create the notebook

1. Kaggle -> **Create** -> **New Notebook**.
2. **File** -> **Import Notebook** -> upload `notebooks/phase3-llm-int8-variants.ipynb`.

## B. Add the two inputs (right panel -> **Add Input**, twice)

1. The `pricepilot-phase3-inputs` dataset (same version the earlier notebooks used).
2. **Your Work** -> **Notebooks** -> `notebookf26a8565eb` (the LoRA run; Output has `adapter/` and
   `adapter-epoch-8/`).

Do **not** add the cross-encoder retrain notebook (`notebook87be682cf2`) as an input here — this
notebook has no CE stage; the CE robustness check (protocol 5.11) is deferred to a separate step.
The notebook finds each input by searching `/kaggle/input`, so no name has to be typed anywhere. If
an input is missing the first cell fails with "input not found: ...".

## C. Settings (right panel -> **Session options**)

- **Accelerator: None**
- **Internet: On** (the notebook installs `onnx`, `onnxruntime`, `onnxscript`, `peft` and downloads
  the Qwen base model)
- Environment: choose **Pin to original environment** if offered, so the reference numbers come
  from the same stack as the serving run (torch 2.10.0 / transformers 5.0.0).

## D. Smoke run first (numbers are discarded)

1. Cell 0 must read `SMOKE = True` (it does in the file you imported).
2. **Save Version** -> **Save & Run All (Commit)** -> **Save**. Do NOT use the interactive Run.
3. When the version finishes, open it -> **Output** -> `smoke/stage-status.json` -> download it.
4. Put it in `docs/learned/results/serving/int8v/smoke-stage-status.json` and tell Claude. What
   matters: all stages `"ok": true`, in particular `LLM-verify-fp32` — if that one is `false`, STOP
   and send its `error` field; do not start the full run (protocol 5.11's gate failed, and a smoke
   run only scores 8 of the 133 val pairs, so a smoke-run gate failure is still informative but not
   the full-run verdict).

If any stage failed, its `error` field has the traceback. Send it; do not start the full run.

## E. Full run

1. Open the notebook in Edit mode. Change cell 0 to `SMOKE = False`.
2. **Save Version** -> **Save & Run All (Commit)**. It must be a **committed** run: only a committed
   version keeps its Output. An interactive run loses everything when the session closes.
3. Wall clock: **ESTIMATE 1-2 hours** (merge + export + two quantized variants, each scored on
   420 pairs unpinned, plus two pinned latency passes). Kaggle's hard limit is **12 hours**; the
   notebook is far below it, but if it stops at the limit, every stage finished before that point
   is already written (each stage saves its outputs immediately).
4. If `LLM-verify-fp32` fails on the full run (max|diff| against the committed
   `preds-llm-onnxfp32-val.json` exceeds `1e-5`), the run STOPS there by design — `LLM-int8-v2` and
   everything after it never execute (protocol 5.11: no variant built from an unverified export is
   trusted). Send `stage-status.json`'s `LLM-verify-fp32` entry; do not hand-edit the tolerance.

## F. Download and place the outputs

From the committed version's **Output** tab (folder root, not `smoke/`), download these and put
them all in `docs/learned/results/serving/int8v/`:

- `stage-status.json`, `env-facts.json`, `model-facts.json`, `throughput.json`
- `preds-llm-onnxfp32-verify-val.json` (the re-export's own val scores, for the gate)
- `preds-llm-int8-v2-val.json`, `preds-llm-int8-v2-test.json`
- `preds-llm-int8-v3-val.json`, `preds-llm-int8-v3-test.json`
- `latency-llm-int8-v2.json`, `latency-llm-int8-v3.json`

The ONNX graphs themselves are not saved (large and re-creatable; their SHA-256 hashes are in
`model-facts.json`). Then tell Claude "int8 variants outputs are in place" — that runs the
eligibility test and selection rule from protocol 5.11 against V2 and V3, on validation only, and
either scores the selected variant's TEST predictions once, or (if neither variant is eligible)
serves and reports the LLM as ONNX fp32 instead. Do not edit any file in that folder.

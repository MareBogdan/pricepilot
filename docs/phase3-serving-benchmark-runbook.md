# Phase 3 item 8 — serving benchmark: Kaggle runbook

For Bogdan. Follow it literally. Protocol: `docs/phase3-serving-benchmark-protocol.md`.
Notebook: `notebooks/phase3-serving-benchmark.ipynb` (CPU only, no GPU).

## A. Create the notebook

1. Kaggle -> **Create** -> **New Notebook**.
2. **File** -> **Import Notebook** -> upload `notebooks/phase3-serving-benchmark.ipynb`.

## B. Add the three inputs (right panel -> **Add Input**, three times)

1. The `pricepilot-phase3-inputs` dataset (same version the earlier notebooks used).
2. **Your Work** -> **Notebooks** -> the cross-encoder retrain notebook
   (`notebook87be682cf2`, **version 3**, the one whose Output contains `ce-ft-best/`).
3. **Your Work** -> **Notebooks** -> `notebookf26a8565eb` (the LoRA run; Output has `adapter/` and
   `adapter-epoch-8/`).

The notebook finds each input by searching `/kaggle/input`, so no name has to be typed anywhere. If
an input is missing the first cell fails with "input not found: ...".

## C. Settings (right panel -> **Session options**)

- **Accelerator: None**
- **Internet: On** (the notebook installs `onnx`, `onnxruntime`, `onnxscript`, `peft` and downloads
  the Qwen base model)
- Environment: choose **Pin to original environment** if offered (the retrain used torch 2.10.0 /
  transformers 5.0.0), so the reference numbers come from the same stack.

## D. Smoke run first (numbers are discarded)

1. Cell 0 must read `SMOKE = True` (it does in the file you imported).
2. **Save Version** -> **Save & Run All (Commit)** -> **Save**. Do NOT use the interactive Run.
3. When the version finishes, open it -> **Output** -> `smoke/stage-status.json` -> download it.
4. Put it in `docs/learned/results/serving/smoke-stage-status.json` and tell Claude. What matters:
   all 11 stages `"ok": true`. Do not download anything else from a smoke run.

If any stage failed, its `error` field has the traceback. Send it; do not start the full run.

## E. Full run

1. Open the notebook in Edit mode. Change cell 0 to `SMOKE = False`.
2. **Save Version** -> **Save & Run All (Commit)**. It must be a **committed** run: only a committed
   version keeps its Output. An interactive run loses everything when the session closes.
3. Wall clock: **ESTIMATE 1-3 hours** (LLM export + int8 quantization + 420 pairs scored four
   times + latency passes). Kaggle's hard limit is **12 hours** per session; the notebook is far
   below it, but if it stops at the limit, every stage finished before that point is already
   written (each stage saves its outputs immediately).

## F. Download and place the outputs

From the committed version's **Output** tab (folder root, not `smoke/`), download these and put them
all in `docs/learned/results/serving/`:

- `stage-status.json`, `env-facts.json`, `model-facts.json`, `throughput.json`
- `preds-ce-ptfp32-test.json`, `preds-ce-ptfp32-trainval.json`
- `preds-ce-onnxfp32-test.json`, `preds-ce-onnxfp32-trainval.json`
- `preds-ce-int8-test.json`, `preds-ce-int8-trainval.json`
- `preds-llm-ptfp32-val.json`, `preds-llm-ptfp32-test.json`
- `preds-llm-onnxfp32-val.json`, `preds-llm-onnxfp32-test.json`
- `preds-llm-int8-val.json`, `preds-llm-int8-test.json`
- `latency-ce-onnxfp32.json`, `latency-ce-int8.json`, `latency-llm-onnxfp32.json`, `latency-llm-int8.json`

The ONNX graphs themselves are not saved (they are large and re-creatable; their SHA-256 hashes are
in `model-facts.json`). Then tell Claude "serving outputs are in place" — that starts session 2
(gates G1-G4, scoring, the headline table). Do not edit any file in that folder.

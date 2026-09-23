# Phase 3 item 6 -- LoRA fine-tune runbook (Kaggle)

Cost: **$0.00** (Kaggle free tier). Time: ESTIMATE well under an hour on a T4; the smoke run is a
few minutes. Script: `notebooks/phase3-llm-finetune.py`.

## Before you run

1. Kaggle -> new Notebook. Settings -> Accelerator -> **GPU T4 x2** (not P100: recent torch builds may lack its kernels). Settings -> Internet **On**
   (the model downloads from Hugging Face).
2. **Check the Accelerator is a GPU before Run All.** The previous run silently fell back to CPU
   and took an hour. The notebook prints a loud `!!!` warning if CUDA is missing -- if you see it,
   **stop the run**, fix the accelerator, restart.
3. Add Data -> upload the `phase3-model-inputs` dataset: `phase3-inputs-test.json` and
   `phase3-inputs-train-val.json` (regenerate with `uv run python scripts/export_model_inputs.py`
   if you no longer have them). The notebook finds them by glob under `/kaggle/input`.
4. Paste the **entire** contents of `notebooks/phase3-llm-finetune.py` into one cell.

## Run

5. Run All. The script refuses to start (with a `REFUSING TO RUN` message) on a wrong hash,
   wrong row counts, a stale `pair_text_version`, or any label-shaped field in the TEST file -- do not work around it; tell me.
6. Watch for, in order:
   - `PREFLIGHT token lengths ...` line (before the smoke run): min/median/p95/p99/max over all 959
     prompts and the count over `MAX_LENGTH` (1024). Over = 0 is required. If it refuses, the
     distribution is printed -- bring it back; do not edit the template or pair text.
   - `SMOKE RUN -- metrics discarded` banner, readout scores in [0,1]. A first-half loss below the second-half is a warning, not a stop
     (only ~13 steps); stop only on `nan`, an error, or a `REFUSING` message.
     The smoke numbers mean nothing; do not record them.
   - `REAL RUN`, then one `epoch N ... @0.5 ... @best t=...` line per epoch (up to 8).
   - `written: ...preds-llm-trainval.json (672 scores)` and `...preds-llm-test.json (287 scores)`.
   - The final `RUN SUMMARY` block.
7. If the loss prints `nan`, stop and bring the log back -- do not rerun blind.

## Expected batch settings and memory

`BATCH_SIZE=2`, `GRAD_ACCUM=8` (effective batch 16, same as the original 8 x 2), gradient
checkpointing on. The log prints `MODEL: base dtype=torch.float16 trainable params=...` once and a
`MEMORY PROBE: ... OK, peak allocated ...` line before the smoke run. If the probe refuses with
OOM, the documented fallback is `BATCH_SIZE=1`, `GRAD_ACCUM=16` (effective batch still 16) --
edit those two constants, nothing else -- and **restart the Kaggle session/kernel before
rerunning** (the allocator setting only applies before torch first loads, and the failed attempt's
GPU memory stays held until then).

## Known environment issue (expected, not a warning to act on)

Kaggle's image ships torchao 0.10.0; the installed peft requires >= 0.16.0 and raises instead of
returning False. The notebook uninstalls torchao (best effort; return code is printed) and
neutralises peft's probe in both places it is bound, and prints one `ENV COMPAT: peft's torchao probe NEUTRALISED ...` line. That
line is in the run log by design. If instead you see `ENV COMPAT: ... patch not applied`, bring the
log back.

## Bring back

8. Download from `/kaggle/working`:
   - `preds-llm-trainval.json`
   - `preds-llm-test.json`
   - the `adapter/` folder (zip it; ESTIMATE ~35 MB)
   - the full `RUN SUMMARY` block, pasted as text
9. Put the two prediction files in `docs/learned/results/predictions/`. Do **not** edit them.
   Keep the adapter out of git (put it under `models/`, which is gitignored -- or leave it zipped
   outside the repo).
10. Do **not** run `score_predictions.py` yourself. Scoring TEST is a ledgered, one-shot action
    done in the next session, with the validation-selected threshold from the summary block.

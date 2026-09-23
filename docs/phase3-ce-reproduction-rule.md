# Phase 3 item 8 — cross-encoder reproduction rule (pre-registered)

Written 2026-09-23, by the architect, BEFORE the retrain run exists. Commit this file before (or in
the same commit as) the first file the retrain produces.

## Why a retrain

The fine-tuned cross-encoder that produced the committed TEST result (F1 0.8737, ledger id
`mmarco-mMiniLMv2-finetuned-ep6`, ADR-0028 addendum #20) was never saved: the Kaggle notebook
(`notebooks/phase3-cross-encoder-baseline.ipynb`, bogdanmare/notebook87be682cf2) wrote only the four
`preds-*.json` files; the best epoch's weights lived in memory and are gone. Item 8 needs the weights
to export and quantize the model.

## How the retrain is run

The same Kaggle notebook, opened with **Edit** (same code, same input dataset version, Accelerator
None). Cell 1 — the original training cell — is NOT modified. One cell is appended after it that
only saves: the best-epoch model and tokenizer (`ce-ft-best/`), `ce-run-facts.json` (library
versions, CPU, HF model sha, best epoch, val F1, parameter count, weight-file hash), and renames the
four prediction files to `preds-*-retrain.json`.

## The rule

Compare the retrain's predictions with the committed ones, score against score. **No label file is
read; this is not a TEST touch; the ledger is not touched.**

- **REPRODUCED** iff the retrain's best epoch == 6 **AND** there are **zero decision flips** at the
  ledgered threshold **0.89** across all **959** fine-tuned pairs (287 TEST + 672 TRAIN_VAL).
  Max |score diff| is reported, not gated.
  -> The retrained weights ARE `mmarco-mMiniLMv2-finetuned-ep6` for item 8. No new ledger entry.
- **NOT_REPRODUCED** otherwise.
  -> The retrain is a different model, `mmarco-mMiniLMv2-finetuned-ep6-retrain`: threshold chosen by
  `scripts/select_threshold.py` on the 133 validation pairs, ONE ledgered TEST touch, and it — not
  the original — is the cross-encoder benchmarked in item 8. The item-5 README row (F1 0.8737) stays
  untouched as the item-5 result.

The zero-shot predictions are compared too (flips at its ledgered 0.86), as a sanity check on the
environment only; they do not enter the verdict.

Neither outcome is a reason to re-run the retrain until it matches.

"""Phase 3 item 6 -- LoRA fine-tune of Qwen2.5-0.5B-Instruct on the frozen TRAIN_VAL/TEST split.

PASTE THIS ENTIRE FILE INTO ONE KAGGLE NOTEBOOK CELL AND RUN ALL. See
docs/phase3-llm-finetune-runbook.md for what to do before and after running this -- in
particular, check the Accelerator is set to a GPU before Run All.

Committed to the repo, not just run once and discarded, so the run is reproducible and
reviewable (CLAUDE.md §5's GPU-training discipline: state what you're about to do before running
it, smoke-test first).

This file cannot be executed or type-checked by this repo's local suite -- `torch`/`transformers`/
`peft` are blocked by this machine's Application Control policy, and the notebook needs a GPU
this machine doesn't have. `tests/test_llm_prompt_notebook_parity.py` is the one thing the local
suite CAN check about this file: that the prompt-template block below is byte-identical to
`src/pricepilot/matching/llm_prompt.py`'s own copy. Never hand-edit the template block here
without making the identical edit there (and bumping `LLM_PROMPT_VERSION` in both places) --
edit `llm_prompt.py` first, then copy its template block back into this file verbatim.
"""

from __future__ import annotations

import contextlib
import glob
import json
import math
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Must be set BEFORE torch is imported (the CUDA allocator reads it at first CUDA use). It only
# reduces memory fragmentation -- it is NOT the OOM fix (that is the batch split and gradient
# checkpointing below).
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import torch
import torch.nn.functional as F
from peft import LoraConfig, PeftModel, get_peft_model
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    get_linear_schedule_with_warmup,
)

# ---------------------------------------------------------------------------
# ENVIRONMENT COMPATIBILITY -- Kaggle's image ships torchao 0.10.0, but the installed peft only
# supports torchao >= 0.16.0 and RAISES ImportError (instead of returning False) from
# is_torchao_available() when it probes an older one, inside get_peft_model ->
# peft/tuners/lora/torchao.py::dispatch_torchao. This project does not use torchao at all; peft
# only probes it while choosing which layer class to wrap. So: try to uninstall it, then force the
# probe to report False. BOTH bindings are patched: peft.tuners.lora.torchao imports the name
# `is_torchao_available` into its own namespace at import time, so patching peft.import_utils
# alone would leave the old reference in place and the raise would still happen.
# On a future image without the problem this block is a harmless no-op (the patched probe just
# says "no torchao", which is true for our purposes).
# ---------------------------------------------------------------------------
# Best effort only; the patch below is what guarantees safety.
_uninstall_rc: int | str = "not attempted"
with contextlib.suppress(Exception):
    _uninstall_rc = subprocess.run(
        [sys.executable, "-m", "pip", "uninstall", "-y", "torchao"],
        capture_output=True,
        timeout=120,
        check=False,
    ).returncode
print(f"ENV COMPAT: pip uninstall torchao return code: {_uninstall_rc}")

try:
    import peft.import_utils
    import peft.tuners.lora.torchao as _lora_torchao

    def _no_torchao(*_a: Any, **_k: Any) -> bool:
        return False

    peft.import_utils.is_torchao_available = _no_torchao  # type: ignore[assignment]
    _patched = ["peft.import_utils"]
    if hasattr(_lora_torchao, "is_torchao_available"):
        _lora_torchao.is_torchao_available = _no_torchao  # type: ignore[assignment]
        _patched.append("peft.tuners.lora.torchao")
    print(
        f"ENV COMPAT: peft's torchao probe NEUTRALISED (is_torchao_available -> False in "
        f"{' and '.join(_patched)}). Reason: Kaggle ships torchao 0.10.0, peft requires >= 0.16.0 "
        "and raises instead of returning False. Expected; not used here."
    )
    if len(_patched) < 2:
        print("ENV COMPAT: WARNING -- lora.torchao has no is_torchao_available binding to patch.")
except Exception as _compat_err:
    print(f"ENV COMPAT: torchao probe patch not applied ({_compat_err!r}); continuing.")

# ---------------------------------------------------------------------------
# Fixed run facts -- printed in the final summary block (TASK 2 item 10) so DECISIONS.md
# ADR-0028 addendum #21 can record them verbatim.
# ---------------------------------------------------------------------------
SEED = 20260923
random.seed(SEED)
torch.manual_seed(SEED)

BASE_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
FROZEN_LABELS_SHA256 = "540a4fd6ccfc52525014ac770caadbf544243dccc5a85d3fcb279fd7d052eed4"

LORA_R = 16
LORA_ALPHA = 32
LORA_DROPOUT = 0.05
LORA_TARGET_MODULES = [
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "gate_proj",
    "up_proj",
    "down_proj",
]
LR = 1e-4
WARMUP_FRACTION = 0.10
GRAD_CLIP = 1.0
MAX_EPOCHS = 8
# Effective batch = BATCH_SIZE * GRAD_ACCUM = 16, unchanged from the original 8 x 2 -- only how it
# is split across forward/backward passes changed, so no optimisation hyperparameter moved (the
# one exception: the final partial step of each epoch, 5 examples, weights its last example
# double -- 1 of 34 steps, clipped at 1.0). The split exists because Qwen2.5's 151,936-token
# vocabulary makes the (unavoidable, standard-loss-path) fp32 logits tensor 8 x 565 x 151936 x 4
# bytes = 2.75 GB (2.56 GiB) per copy at the old batch of 8, with several more logits-sized
# tensors in the loss/backward path: that OOMed a 14.56 GiB T4. Fallback if it still OOMs:
# BATCH_SIZE=1, GRAD_ACCUM=16 (effective batch still 16) -- RESTART THE KERNEL first.
BATCH_SIZE = 2
GRAD_ACCUM = 8
assert BATCH_SIZE * GRAD_ACCUM == 16, "effective batch must stay 16"
# Character lengths measured over all 959 pairs: the instruction wrapper is 1181 chars, repeated
# on every example, and pair text is median 539 / p95 662 / max 941 chars, so the median prompt is
# ~1720 chars and the longest ~2122. Token counts are ESTIMATES from those (roughly 520 median and
# 760 max at 2.8-3.3 chars/token); the one real token measurement was a 518-token prompt tripping
# the original 512 cap. 512 was specified without measuring the template and was too tight. The
# PREFLIGHT block below measures the true token distribution on the actual tokenizer every run.
MAX_LENGTH = 1024
SMOKE_EXAMPLE_COUNT = 200
SMOKE_EPOCHS = 1

WORKING_DIR = Path("/kaggle/working")

# TEMPLATE-BEGIN
# Kept byte-identical in notebooks/phase3-llm-finetune.py; checked by
# tests/test_llm_prompt_notebook_parity.py, which extracts the text strictly between the
# "# TEMPLATE-BEGIN" and "# TEMPLATE-END" marker lines in both files and asserts equality.
# Nothing outside these two marker lines is compared, so comments/docstrings elsewhere in either
# file may differ freely -- only what sits between them is the contract.

# Bumped whenever the template text changes, so a stale comparison (baseline scored under one
# template, notebook trained under a byte-different one) can never happen silently. Recorded in
# DECISIONS.md ADR-0028 addendum #21 and printed by the notebook.
LLM_PROMPT_VERSION = "llm-prompt-v1"

# Deliberately silent on tiers, split membership, label counts, or how the dataset was sampled --
# none of that is information the task itself needs, and stating it would let the model condition
# on sampling design rather than on the two listings' actual content. States the same operational
# question and rule ladder docs/learned/phase3-annotation-conventions.md defines for the human
# annotator (rules 1-6), so the model is asked the same question the labels themselves answer --
# not a looser or stricter one.
_INSTRUCTION = (
    "You are comparing two competitor-shop listings for pet food, treats or litter products.\n"
    "Decide whether Listing A and Listing B are the SAME purchasable unit: a price-comparison "
    "engine comparing their prices would be comparing the same physical product.\n"
    "\n"
    "Each of these, on its own, makes them NOT the same unit: a different net weight or volume; "
    "a different pack count (a stated count of 1 and no count stated are the SAME); a different "
    "bonus weight; a different species (dog vs cat); a different life-stage, sterilised, light, "
    "sensitive, indoor, dental, urinary or joint-care formula; a different food form (dry vs "
    "wet/tin/pouch -- wet, tin and pouch among themselves are NOT a difference); a different "
    "breed size (e.g. Mini vs Maxi); a different flavour (the same flavour word in another "
    "language, e.g. Salmon/Somon, is NOT a difference).\n"
    "\n"
    "None of these, on their own, make them different: generic descriptive words (grain-free, "
    "premium, natural, holistic); an animal-weight dosage band (e.g. 12-25 kg) stated on only "
    "one side; a mismatched brand name alone when everything else about the listing matches.\n"
    "\n"
    "Answer with exactly one word: Yes or No."
)


def build_llm_prompt(text_a: str, text_b: str) -> str:
    """Build the completion prompt; see module docstring for the design rationale."""
    return f"{_INSTRUCTION}\n\nListing A: {text_a}\nListing B: {text_b}\nAnswer:"


# TEMPLATE-END


# ---------------------------------------------------------------------------
# TASK 2 item 1 -- load and validate the two exported input files, refusing loudly on anything
# that looks like a stale export, a wrong split, or (for TEST) a leaked label.
# ---------------------------------------------------------------------------

_FORBIDDEN_KEY_NAMES = {"label", "tier", "split", "y", "target"}
_FORBIDDEN_VALUES = {"M", "N", "S"}


def _find_input(filename: str) -> Path:
    matches = glob.glob(f"/kaggle/input/**/{filename}", recursive=True)
    if not matches:
        raise SystemExit(
            f"REFUSING TO RUN: could not find {filename!r} under /kaggle/input -- attach the "
            "phase3-model-inputs Kaggle dataset (docs/phase3-llm-finetune-runbook.md) first."
        )
    if len(matches) > 1:
        raise SystemExit(
            f"REFUSING TO RUN: found {len(matches)} copies of {filename!r} under /kaggle/input "
            f"-- ambiguous which to use: {matches}"
        )
    return Path(matches[0])


def _assert_no_leakage(payload: Any, path: str = "$") -> None:
    """Mirrors scripts/export_model_inputs.py's own guard exactly -- re-checked here, at load
    time, on the copy that actually reached this notebook, rather than trusted from the export
    step alone."""
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).lower() in _FORBIDDEN_KEY_NAMES:
                raise SystemExit(
                    f"REFUSING TO RUN: forbidden key {key!r} found at {path}.{key} in the TEST "
                    "payload -- a TEST file must never carry a label-shaped field."
                )
            _assert_no_leakage(value, f"{path}.{key}")
    elif isinstance(payload, list):
        for i, item in enumerate(payload):
            _assert_no_leakage(item, f"{path}[{i}]")
    elif isinstance(payload, str) and payload in _FORBIDDEN_VALUES:
        raise SystemExit(
            f"REFUSING TO RUN: value {payload!r} at {path} is exactly a label letter (M/N/S) "
            "in the TEST payload -- refusing even though it may be an innocent coincidence."
        )


test_path = _find_input("phase3-inputs-test.json")
train_val_path = _find_input("phase3-inputs-train-val.json")

test_payload = json.loads(test_path.read_text(encoding="utf-8"))
train_val_payload = json.loads(train_val_path.read_text(encoding="utf-8"))

for payload, name in ((test_payload, "TEST"), (train_val_payload, "TRAIN_VAL")):
    if payload["frozen_labels_sha256"] != FROZEN_LABELS_SHA256:
        raise SystemExit(
            f"REFUSING TO RUN: {name} payload's frozen_labels_sha256 "
            f"({payload['frozen_labels_sha256']!r}) does not match the expected "
            f"{FROZEN_LABELS_SHA256!r} -- this is not the frozen Phase 3 dataset."
        )

if len(test_payload["pairs"]) != 287:
    raise SystemExit(
        f"REFUSING TO RUN: expected 287 TEST pairs, found {len(test_payload['pairs'])}."
    )
if len(train_val_payload["pairs"]) != 672:
    raise SystemExit(
        f"REFUSING TO RUN: expected 672 TRAIN_VAL pairs, found {len(train_val_payload['pairs'])}."
    )

_assert_no_leakage(test_payload)

test_ids = {p["pair_id"] for p in test_payload["pairs"]}
train_val_ids = {p["pair_id"] for p in train_val_payload["pairs"]}
if test_ids & train_val_ids:
    raise SystemExit(
        f"REFUSING TO RUN: {len(test_ids & train_val_ids)} pair_id(s) appear in both the TEST "
        "and TRAIN_VAL payloads."
    )

EXPECTED_PAIR_TEXT_VERSION = "pair-text-v1"  # src/pricepilot/matching/pair_text.py
for payload, name in ((test_payload, "TEST"), (train_val_payload, "TRAIN_VAL")):
    if payload.get("pair_text_version") != EXPECTED_PAIR_TEXT_VERSION:
        raise SystemExit(
            f"REFUSING TO RUN: {name} payload pair_text_version "
            f"{payload.get('pair_text_version')!r} != {EXPECTED_PAIR_TEXT_VERSION!r} -- stale export."
        )

print(
    f"loaded {len(test_payload['pairs'])} TEST pairs, {len(train_val_payload['pairs'])} TRAIN_VAL pairs"
)
print("no leakage found in TEST payload; TEST/TRAIN_VAL pair_id sets are disjoint")

train_pairs = [
    p for p in train_val_payload["pairs"] if p["train_or_val"] == "train" and p["scored"]
]
val_pairs = [p for p in train_val_payload["pairs"] if p["train_or_val"] == "val" and p["scored"]]
# Same TRAIN_VAL split the cross-encoder baseline used (docs/phase3-baseline-model-choice.md,
# DECISIONS.md ADR-0028 addendum #20) -- 533 train / 133 val, S already dropped by `scored`.
# A mismatch here means this notebook is reading a different split than the baseline was scored
# against, which would make the comparison meaningless.
if len(train_pairs) != 533:
    raise SystemExit(f"REFUSING TO RUN: expected 533 scored train pairs, found {len(train_pairs)}.")
if len(val_pairs) != 133:
    raise SystemExit(f"REFUSING TO RUN: expected 133 scored val pairs, found {len(val_pairs)}.")
print(f"train pairs: {len(train_pairs)}  val pairs: {len(val_pairs)}")


# ---------------------------------------------------------------------------
# TASK 2 item 2 -- device check.
# ---------------------------------------------------------------------------

device = "cuda" if torch.cuda.is_available() else "cpu"
if device == "cpu":
    print("!" * 70)
    print("WARNING: CUDA IS NOT AVAILABLE -- running on CPU.")
    print("The cross-encoder baseline's Kaggle accelerator silently reset to None and the run")
    print(
        "took about an hour on CPU. Check Settings > Accelerator is set to a GPU (T4 x2; not P100 --"
    )
    print(
        "recent torch builds may lack its kernels) BEFORE Run All, or this run will be extremely slow."
    )
    print("!" * 70)
print(f"device: {device}")
TORCH_DTYPE = torch.float16 if device == "cuda" else torch.float32


# ---------------------------------------------------------------------------
# Tokenizer, and the two-token readout's fixed token ids -- resolved once, asserted to be
# exactly one token each, and reused everywhere below.
# ---------------------------------------------------------------------------

tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token


def _single_token_id(word: str) -> int:
    ids = tokenizer.encode(word, add_special_tokens=False)
    if len(ids) != 1:
        raise SystemExit(
            f"REFUSING TO RUN: {word!r} encodes to {len(ids)} token(s) ({ids}), not exactly "
            "one, for this tokenizer -- the two-token readout requires both ' Yes' and ' No' to "
            "be single tokens. Falling back silently would score gibberish; fix the readout "
            "design (a different pair of words, or a different model) instead of proceeding."
        )
    return ids[0]


YES_TOKEN_ID = _single_token_id(" Yes")
NO_TOKEN_ID = _single_token_id(" No")
print(f"YES_TOKEN_ID={YES_TOKEN_ID}  NO_TOKEN_ID={NO_TOKEN_ID}")


# ---------------------------------------------------------------------------
# PREFLIGHT -- measure every prompt's token length BEFORE the smoke run, so a length problem is a
# report in the first seconds rather than a crash mid-training. Length is prompt + 1 answer token,
# exactly what encode_example checks (that REFUSING guard stays as the second line of defence).
# ---------------------------------------------------------------------------


def _percentile(sorted_values: list[int], q: float) -> int:
    return sorted_values[min(len(sorted_values) - 1, math.ceil(q * len(sorted_values)) - 1)]


_all_pairs = [*train_val_payload["pairs"], *test_payload["pairs"]]
_token_lengths = sorted(
    len(
        tokenizer(build_llm_prompt(p["text_a"], p["text_b"]), add_special_tokens=False)["input_ids"]
    )
    + 1
    for p in _all_pairs
)
_over = sum(1 for n in _token_lengths if n > MAX_LENGTH)
print("PREFLIGHT token lengths (prompt + answer token) over all TEST + TRAIN_VAL pairs:")
print(
    f"  n={len(_token_lengths)}  min={_token_lengths[0]}  median={_percentile(_token_lengths, 0.5)}  "
    f"p95={_percentile(_token_lengths, 0.95)}  p99={_percentile(_token_lengths, 0.99)}  "
    f"max={_token_lengths[-1]}  over MAX_LENGTH({MAX_LENGTH}): {_over}"
)
if _over:
    raise SystemExit(
        f"REFUSING TO RUN: {_over} of {len(_token_lengths)} prompts exceed max_length={MAX_LENGTH} "
        "(distribution above). Raise MAX_LENGTH; do NOT shorten the template or pair text."
    )


# ---------------------------------------------------------------------------
# Example encoding -- TASK 2 item 5: loss on the ANSWER TOKEN ONLY.
#
# input_ids = <prompt tokens> + <answer token>, padded to MAX_LENGTH.
# labels    = [-100]*<prompt length> + <answer token> + [-100]*<padding>.
#
# HF's CausalLM loss shifts internally (logits[:, :-1] predicts labels[:, 1:]), so
# shift_labels[len(prompt)-1] == labels[len(prompt)] == the answer token -- exactly the
# position logits[len(prompt)-1] (the last real prompt token, "Answer:") predicts. Every other
# position's label is -100, which HF's cross-entropy ignores by default, so the model is never
# trained to reproduce listing text -- only to answer the fixed question at the fixed position.
# This is the single most common silent error in this setup: get the label array's alignment
# wrong and the model trains on next-token prediction over the listings themselves instead.
# ---------------------------------------------------------------------------


def encode_example(text_a: str, text_b: str, label: str) -> tuple[list[int], list[int], list[int]]:
    prompt = build_llm_prompt(text_a, text_b)
    prompt_ids = tokenizer(prompt, add_special_tokens=False)["input_ids"]
    if label not in {"M", "N"}:
        raise SystemExit(f"REFUSING TO RUN: training label {label!r} is not M or N.")
    answer_id = YES_TOKEN_ID if label == "M" else NO_TOKEN_ID
    input_ids = [*prompt_ids, answer_id]
    if len(input_ids) > MAX_LENGTH:
        raise SystemExit(
            f"REFUSING TO RUN: prompt+answer is {len(input_ids)} tokens, over max_length="
            f"{MAX_LENGTH} -- truncating would silently cut listing content. Raise MAX_LENGTH "
            "or investigate this specific pair instead of proceeding."
        )
    labels = [-100] * len(prompt_ids) + [answer_id]
    pad_len = MAX_LENGTH - len(input_ids)
    attention_mask = [1] * len(input_ids) + [0] * pad_len
    input_ids = input_ids + [tokenizer.pad_token_id] * pad_len
    labels = labels + [-100] * pad_len
    return input_ids, attention_mask, labels


def build_tensors(pairs: list[dict[str, Any]]) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    all_ids, all_mask, all_labels = [], [], []
    for p in pairs:
        ids, mask, labels = encode_example(p["text_a"], p["text_b"], p["label"])
        all_ids.append(ids)
        all_mask.append(mask)
        all_labels.append(labels)
    return torch.tensor(all_ids), torch.tensor(all_mask), torch.tensor(all_labels)


@torch.no_grad()
def score_pair(model: Any, text_a: str, text_b: str) -> float:
    """The two-token readout: softmax over ONLY the ' Yes'/' No' logits at the position right
    after the prompt's final "Answer:" token. Never parses generated text."""
    model.eval()
    prompt = build_llm_prompt(text_a, text_b)
    input_ids = tokenizer(prompt, return_tensors="pt", add_special_tokens=False).input_ids.to(
        device
    )
    logits = model(input_ids=input_ids).logits[0, -1, :]
    two = torch.stack([logits[YES_TOKEN_ID], logits[NO_TOKEN_ID]])
    probs = F.softmax(two.float(), dim=0)
    return float(probs[0].item())


# ---------------------------------------------------------------------------
# Threshold selection -- mirrors scripts/select_threshold.py's algorithm exactly (same 0.00-1.00
# grid, same "midpoint of the widest F1-tying run" tie-break), so the LLM and the cross-encoder
# baseline are compared under the identical selection procedure (docs/phase3-baseline-model-
# choice.md rule 2; TASK 4's fairness requirement).
# ---------------------------------------------------------------------------


def _confusion(
    scores: dict[str, float], labels: dict[str, str], threshold: float
) -> tuple[float | None, float | None, float | None]:
    tp = fp = fn = tn = 0
    for pair_id, true_label in labels.items():
        predicted = "M" if scores[pair_id] >= threshold else "N"
        if true_label == "M" and predicted == "M":
            tp += 1
        elif true_label == "N" and predicted == "M":
            fp += 1
        elif true_label == "M" and predicted == "N":
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision and recall and (precision + recall) > 0
        else (0.0 if precision is not None and recall is not None else None)
    )
    return f1, precision, recall


def _longest_contiguous_run(values: list[float], step: float = 0.01) -> list[float]:
    ordered = sorted(values)
    best_run: list[float] = []
    current_run: list[float] = []
    for v in ordered:
        if current_run and round(v - current_run[-1], 10) > step + 1e-9:
            if len(current_run) > len(best_run):
                best_run = current_run
            current_run = [v]
        else:
            current_run.append(v)
    if len(current_run) > len(best_run):
        best_run = current_run
    return best_run


def select_best_threshold(
    scores: dict[str, float], labels: dict[str, str]
) -> tuple[float, float | None, float | None, float | None]:
    grid = [round(i / 100, 2) for i in range(101)]
    sweep = [(t, *_confusion(scores, labels, t)) for t in grid]
    rank_key = lambda f1: f1 if f1 is not None else -1.0  # noqa: E731
    best_key = max(rank_key(row[1]) for row in sweep)
    tying = [row[0] for row in sweep if rank_key(row[1]) == best_key]
    run = _longest_contiguous_run(tying)
    best_t = round((run[0] + run[-1]) / 2, 2)
    best_row = next(row for row in sweep if row[0] == best_t)
    return best_row[0], best_row[1], best_row[2], best_row[3]


# ---------------------------------------------------------------------------
# LoRA model construction -- TASK 2 item 4's fixed hyperparameters.
# ---------------------------------------------------------------------------


def _load_base_model() -> Any:
    """Newer transformers deprecate `torch_dtype` in favour of `dtype`; older ones reject `dtype`."""
    try:
        return AutoModelForCausalLM.from_pretrained(BASE_MODEL, dtype=TORCH_DTYPE)
    except TypeError:
        return AutoModelForCausalLM.from_pretrained(BASE_MODEL, torch_dtype=TORCH_DTYPE)


_MODEL_FACTS_PRINTED: list[bool] = []


def build_fresh_model() -> Any:
    base = _load_base_model()
    base.to(device)
    base_dtype = next(base.parameters()).dtype
    if base_dtype != TORCH_DTYPE:
        raise SystemExit(
            f"REFUSING TO RUN: base model loaded as {base_dtype}, expected {TORCH_DTYPE} -- an "
            "accidental upcast doubles the weight memory."
        )
    # Gradient checkpointing: recompute activations in backward instead of storing them. Must be
    # enabled on the base model BEFORE peft wraps it, and enable_input_require_grads() makes the
    # embedding output require grad so checkpointed segments still route gradient to the adapter
    # (otherwise the LoRA weights can silently receive no gradient). use_cache is off: it is
    # incompatible with checkpointing and unused (we never generate).
    base.config.use_cache = False
    try:
        base.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    except TypeError:  # older transformers: no kwargs argument
        base.gradient_checkpointing_enable()
    base.enable_input_require_grads()
    lora_config = LoraConfig(
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        target_modules=LORA_TARGET_MODULES,
        task_type="CAUSAL_LM",
    )
    peft_model = get_peft_model(base, lora_config)
    # fp16 base weights, but the trainable LoRA weights are held in fp32: AdamW updates of size
    # ~lr*1e-4 vanish in fp16's 10-bit mantissa, so a pure-fp16 adapter can silently stop learning
    # or go NaN. Forward math still runs in fp16 under torch.autocast (see run_training_epoch).
    for param in peft_model.parameters():
        if param.requires_grad:
            param.data = param.data.float()
    if not _MODEL_FACTS_PRINTED:
        _MODEL_FACTS_PRINTED.append(True)
        trainable = sum(p.numel() for p in peft_model.parameters() if p.requires_grad)
        total = sum(p.numel() for p in peft_model.parameters())
        print(
            f"MODEL: base dtype={base_dtype}  trainable params={trainable:,} / {total:,} "
            f"({100 * trainable / total:.2f}%)  "
            f"gradient checkpointing={base.is_gradient_checkpointing}"
        )
    return peft_model


def memory_probe(model: Any) -> None:
    """One forward+backward on the LONGEST training example at the configured BATCH_SIZE, before
    the smoke run, so an OOM is a report in seconds rather than a crash mid-epoch. Worst case for
    memory: a batch made entirely of the longest example."""
    if device != "cuda":
        print("MEMORY PROBE: skipped (no CUDA)")
        return
    longest = max(
        train_pairs,
        key=lambda p: len(
            tokenizer(build_llm_prompt(p["text_a"], p["text_b"]), add_special_tokens=False)[
                "input_ids"
            ]
        ),
    )
    ids, mask, lab = build_tensors([longest] * BATCH_SIZE)
    seq = int(mask[0].sum().item())
    vocab = int(model.config.vocab_size)
    logits_gib = BATCH_SIZE * seq * vocab * 4 / 2**30
    print(
        f"MEMORY PROBE: batch {BATCH_SIZE} x {seq} tokens x vocab {vocab} -> fp32 logits "
        f"{logits_gib:.2f} GiB per copy"
    )
    model.train()
    torch.cuda.reset_peak_memory_stats()  # the reported peak must be this probe's, not earlier
    outputs = None
    try:
        with torch.autocast(device_type=device, dtype=torch.float16):
            outputs = model(
                input_ids=ids[:, :seq].to(device),
                attention_mask=mask[:, :seq].to(device),
                labels=lab[:, :seq].to(device),
            )
        (outputs.loss / GRAD_ACCUM).backward()
        peak = torch.cuda.max_memory_allocated() / 2**30
        print(f"MEMORY PROBE: OK, peak allocated {peak:.2f} GiB")
    except torch.cuda.OutOfMemoryError:
        raise SystemExit(
            f"REFUSING TO RUN: OOM in the memory probe (logits alone {logits_gib:.2f} GiB per "
            f"copy). BATCH_SIZE={BATCH_SIZE}, GRAD_ACCUM={GRAD_ACCUM}. Next step down: "
            f"BATCH_SIZE={max(1, BATCH_SIZE // 2)}, GRAD_ACCUM={GRAD_ACCUM * 2} (effective batch "
            "stays 16)."
        ) from None
    finally:
        model.zero_grad(set_to_none=True)
        del outputs
        torch.cuda.empty_cache()


def run_training_epoch(
    model: Any,
    input_ids: torch.Tensor,
    attention_mask: torch.Tensor,
    labels: torch.Tensor,
    optimizer: Any,
    scheduler: Any,
    scaler: Any,
) -> list[float]:
    model.train()
    n = input_ids.size(0)
    order = torch.randperm(n)
    optimizer.zero_grad()
    batch_losses: list[float] = []
    accum_count = 0
    num_batches = math.ceil(n / BATCH_SIZE)
    for batch_i, start in enumerate(range(0, n, BATCH_SIZE)):
        idx = order[start : start + BATCH_SIZE]
        # Right-padded, so trimming to this batch's longest real example is lossless. Avoids
        # materialising 151k-vocab logits for all MAX_LENGTH positions on every example.
        trim = int(attention_mask[idx].sum(dim=1).max().item())
        with torch.autocast(device_type=device, dtype=torch.float16, enabled=device == "cuda"):
            outputs = model(
                input_ids=input_ids[idx][:, :trim].to(device),
                attention_mask=attention_mask[idx][:, :trim].to(device),
                labels=labels[idx][:, :trim].to(device),
            )
        loss = outputs.loss
        # GradScaler: fp16 gradients underflow without loss scaling. No-op on CPU (enabled=False).
        scaler.scale(loss / GRAD_ACCUM).backward()
        batch_losses.append(float(loss.item()))
        accum_count += 1
        is_last_batch = batch_i == num_batches - 1
        if accum_count == GRAD_ACCUM or is_last_batch:
            scaler.unscale_(optimizer)  # clip on the true gradient norm, not the scaled one
            torch.nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP)
            scaler.step(optimizer)
            scaler.update()
            scheduler.step()
            optimizer.zero_grad()
            accum_count = 0
    return batch_losses


# ---------------------------------------------------------------------------
# TASK 2 item 3 -- SMOKE RUN FIRST. Its only job is to prove the pipeline runs end to end. A
# completely fresh model/optimizer/scheduler, discarded afterward -- it must never feed into the
# real run below, or "smoke" and "real" training would silently mix.
# ---------------------------------------------------------------------------

print("=" * 70)
print("SMOKE RUN -- metrics discarded")
print("=" * 70)

smoke_pairs = train_pairs[:SMOKE_EXAMPLE_COUNT]
smoke_ids, smoke_mask, smoke_labels = build_tensors(smoke_pairs)
smoke_model = build_fresh_model()
memory_probe(smoke_model)
smoke_optimizer = torch.optim.AdamW(smoke_model.parameters(), lr=LR)
smoke_total_steps = math.ceil(len(smoke_pairs) / (BATCH_SIZE * GRAD_ACCUM)) * SMOKE_EPOCHS
smoke_scheduler = get_linear_schedule_with_warmup(
    smoke_optimizer,
    num_warmup_steps=max(1, int(WARMUP_FRACTION * smoke_total_steps)),
    num_training_steps=smoke_total_steps,
)

smoke_start = time.time()
smoke_scaler = torch.cuda.amp.GradScaler(enabled=device == "cuda")
smoke_losses = run_training_epoch(
    smoke_model, smoke_ids, smoke_mask, smoke_labels, smoke_optimizer, smoke_scheduler, smoke_scaler
)
smoke_elapsed = time.time() - smoke_start
half = max(1, len(smoke_losses) // 2)
first_half_avg = sum(smoke_losses[:half]) / half
second_half_avg = sum(smoke_losses[half:]) / max(1, len(smoke_losses) - half)
print(f"SMOKE RUN: {len(smoke_pairs)} examples, {SMOKE_EPOCHS} epoch, {smoke_elapsed:.1f}s")
print(f"SMOKE RUN: loss first-half avg={first_half_avg:.4f}  second-half avg={second_half_avg:.4f}")

smoke_sample_scores = [score_pair(smoke_model, p["text_a"], p["text_b"]) for p in val_pairs[:5]]
if not all(math.isfinite(s) and 0.0 <= s <= 1.0 for s in smoke_sample_scores):
    raise SystemExit(
        f"SMOKE RUN FAILED: readout produced an out-of-range score: {smoke_sample_scores}"
    )
print(f"SMOKE RUN: sample readout scores (finite, in [0,1]): {smoke_sample_scores}")

smoke_check_path = WORKING_DIR / "smoke-run-discarded.json"
smoke_check_path.write_text(json.dumps({"sample_scores": smoke_sample_scores}), encoding="utf-8")
round_tripped = json.loads(smoke_check_path.read_text(encoding="utf-8"))
assert round_tripped["sample_scores"] == smoke_sample_scores
print(f"SMOKE RUN: file write/read round-trip verified at {smoke_check_path}")
print("SMOKE RUN -- metrics discarded")
print("=" * 70)

del smoke_model, smoke_optimizer, smoke_scheduler, smoke_ids, smoke_mask, smoke_labels
if device == "cuda":
    torch.cuda.empty_cache()


# ---------------------------------------------------------------------------
# TASK 2 item 4 -- the real run. Fresh model/optimizer/scheduler, never touching the smoke run's
# state. TASK 2 item 6: after every epoch, sweep the threshold on the 133 validation pairs and
# keep the best epoch by its own best-threshold F1.
# ---------------------------------------------------------------------------

print("=" * 70)
print("REAL RUN")
print("=" * 70)

train_ids, train_mask, train_labels_tensor = build_tensors(train_pairs)
val_labels_by_id = {p["pair_id"]: p["label"] for p in val_pairs}

model = build_fresh_model()
optimizer = torch.optim.AdamW(model.parameters(), lr=LR)
total_steps = math.ceil(len(train_pairs) / (BATCH_SIZE * GRAD_ACCUM)) * MAX_EPOCHS
scheduler = get_linear_schedule_with_warmup(
    optimizer,
    num_warmup_steps=max(1, int(WARMUP_FRACTION * total_steps)),
    num_training_steps=total_steps,
)
scaler = torch.cuda.amp.GradScaler(enabled=device == "cuda")
print(f"total optimisation steps: {total_steps}")

best: dict[str, Any] = {
    "epoch": None,
    "f1": -1.0,
    "threshold": None,
    "precision": None,
    "recall": None,
    "val_scores": None,
}
run_start = time.time()

for epoch in range(1, MAX_EPOCHS + 1):
    epoch_losses = run_training_epoch(
        model, train_ids, train_mask, train_labels_tensor, optimizer, scheduler, scaler
    )
    avg_loss = sum(epoch_losses) / len(epoch_losses)
    if not math.isfinite(avg_loss):
        raise SystemExit(f"REFUSING TO CONTINUE: non-finite training loss in epoch {epoch}.")

    val_scores = {p["pair_id"]: score_pair(model, p["text_a"], p["text_b"]) for p in val_pairs}
    bad = [k for k, v in val_scores.items() if not (math.isfinite(v) and 0.0 <= v <= 1.0)]
    if bad:
        raise SystemExit(
            f"REFUSING TO CONTINUE: {len(bad)} non-finite val score(s), epoch {epoch}."
        )
    f1_at_05, p_at_05, r_at_05 = _confusion(val_scores, val_labels_by_id, 0.5)
    best_t, best_f1, best_p, best_r = select_best_threshold(val_scores, val_labels_by_id)

    f1_05_str = "undefined" if f1_at_05 is None else f"{f1_at_05:.3f}"
    f1_best_str = "undefined" if best_f1 is None else f"{best_f1:.3f}"
    print(
        f"epoch {epoch}  loss={avg_loss:.4f}  @0.5 F1={f1_05_str} P={p_at_05} R={r_at_05}  "
        f"@best t={best_t:.4f} F1={f1_best_str} P={best_p} R={best_r}"
    )

    epoch_dir = WORKING_DIR / f"adapter-epoch-{epoch}"
    model.save_pretrained(str(epoch_dir))

    rank_key = -1.0 if best_f1 is None else best_f1
    if rank_key > best["f1"]:
        best = {
            "epoch": epoch,
            "f1": best_f1,
            "threshold": best_t,
            "precision": best_p,
            "recall": best_r,
            "val_scores": val_scores,
        }

run_elapsed = time.time() - run_start
print(f"REAL RUN finished in {run_elapsed / 60:.1f} minutes")
print(
    f"best epoch: {best['epoch']}  (validation F1={best['f1']:.4f} at threshold={best['threshold']:.4f})"
)


# ---------------------------------------------------------------------------
# TASK 2 item 7 -- reload the BEST epoch's adapter fresh (never the final epoch's in-memory
# weights, which may not be the best one) and score all 672 TRAIN_VAL and all 287 TEST pairs.
# ---------------------------------------------------------------------------

best_epoch_dir = WORKING_DIR / f"adapter-epoch-{best['epoch']}"
scoring_base = _load_base_model().to(device)
scoring_model = PeftModel.from_pretrained(scoring_base, str(best_epoch_dir))
scoring_model.eval()

trainval_scores = {
    p["pair_id"]: score_pair(scoring_model, p["text_a"], p["text_b"])
    for p in train_val_payload["pairs"]
}
test_scores = {
    p["pair_id"]: score_pair(scoring_model, p["text_a"], p["text_b"]) for p in test_payload["pairs"]
}


# ---------------------------------------------------------------------------
# TASK 2 item 8 -- validate and write the two flat {pair_id: score} prediction files, plus the
# final adapter. Refuses loudly rather than writing a file with a bad score in it.
# ---------------------------------------------------------------------------

if len(trainval_scores) != 672:
    raise SystemExit(
        f"REFUSING TO WRITE: expected 672 TRAIN_VAL scores, got {len(trainval_scores)}."
    )
if len(test_scores) != 287:
    raise SystemExit(f"REFUSING TO WRITE: expected 287 TEST scores, got {len(test_scores)}.")
if not set(trainval_scores).isdisjoint(test_scores):
    raise SystemExit("REFUSING TO WRITE: TRAIN_VAL and TEST prediction id sets are not disjoint.")
for name, scores in (("TRAIN_VAL", trainval_scores), ("TEST", test_scores)):
    for pair_id, score in scores.items():
        if not (isinstance(score, float) and math.isfinite(score) and 0.0 <= score <= 1.0):
            raise SystemExit(f"REFUSING TO WRITE: invalid {name} score for {pair_id!r}: {score!r}")

# The reloaded-from-disk adapter must reproduce the in-loop validation F1 for the best epoch;
# a wrong directory or a dtype change on load would otherwise go unnoticed.
reloaded_val = {p["pair_id"]: trainval_scores[p["pair_id"]] for p in val_pairs}
max_diff = max(abs(reloaded_val[k] - best["val_scores"][k]) for k in reloaded_val)
reload_f1, _, _ = _confusion(reloaded_val, val_labels_by_id, best["threshold"])
print(
    f"reload check: max |score diff| = {max_diff:.5f}; val F1 at the selected threshold "
    f"{best['threshold']}: in-loop={best['f1']:.4f} reloaded={reload_f1}"
)
if max_diff > 1e-2 or reload_f1 is None or abs(reload_f1 - best["f1"]) > 0.01:
    raise SystemExit("REFUSING TO WRITE: reloaded adapter does not reproduce its val scores.")

trainval_preds_path = WORKING_DIR / "preds-llm-trainval.json"
test_preds_path = WORKING_DIR / "preds-llm-test.json"
trainval_preds_path.write_text(json.dumps(trainval_scores, indent=1), encoding="utf-8")
test_preds_path.write_text(json.dumps(test_scores, indent=1), encoding="utf-8")
print(f"written: {trainval_preds_path} ({len(trainval_scores)} scores)")
print(f"written: {test_preds_path} ({len(test_scores)} scores)")

final_adapter_dir = WORKING_DIR / "adapter"
if final_adapter_dir.exists():
    shutil.rmtree(final_adapter_dir)
shutil.copytree(best_epoch_dir, final_adapter_dir)
for epoch in range(1, MAX_EPOCHS + 1):
    epoch_dir = WORKING_DIR / f"adapter-epoch-{epoch}"
    if epoch_dir.exists() and epoch_dir != best_epoch_dir:
        shutil.rmtree(epoch_dir)
adapter_size_bytes = sum(f.stat().st_size for f in final_adapter_dir.rglob("*") if f.is_file())
print(f"adapter saved to {final_adapter_dir} ({adapter_size_bytes / 1e6:.2f} MB)")


# ---------------------------------------------------------------------------
# TASK 2 item 9 -- download links.
# ---------------------------------------------------------------------------

try:
    from IPython.display import FileLink, display

    display(FileLink(str(trainval_preds_path)))
    display(FileLink(str(test_preds_path)))
except ImportError:
    print(f"download manually: {trainval_preds_path}, {test_preds_path}")


# ---------------------------------------------------------------------------
# TASK 2 item 10 -- the facts DECISIONS.md ADR-0028 addendum #21 needs, verbatim.
# ---------------------------------------------------------------------------

print("=" * 70)
print("RUN SUMMARY -- copy these facts verbatim into DECISIONS.md")
print("=" * 70)
print(f"base model: {BASE_MODEL}")
print(f"llm prompt version: {LLM_PROMPT_VERSION}")
print(f"frozen labels sha256: {FROZEN_LABELS_SHA256}")
print(
    f"pair_text_version (TEST / TRAIN_VAL): {test_payload.get('pair_text_version')} / "
    f"{train_val_payload.get('pair_text_version')}"
)
print(
    f"LoRA r/alpha/dropout: {LORA_R}/{LORA_ALPHA}/{LORA_DROPOUT}  lr: {LR}  "
    f"batch x accum: {BATCH_SIZE} x {GRAD_ACCUM}  max_length: {MAX_LENGTH}"
)
print(f"real run minutes: {run_elapsed / 60:.1f}")
print(f"device: {device}")
print(f"seed: {SEED}")
print(f"best epoch: {best['epoch']}")
print(f"best validation F1 / P / R: {best['f1']} / {best['precision']} / {best['recall']}")
print(f"validation-selected threshold: {best['threshold']}")
print(f"total optimisation steps: {total_steps}")
print(f"adapter size on disk: {adapter_size_bytes / 1e6:.2f} MB")
print(f"train pairs / val pairs: {len(train_pairs)} / {len(val_pairs)}")
print("=" * 70)

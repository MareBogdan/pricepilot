"""The one canonical prompt builder for the Phase 3 item 6 LoRA fine-tune (CLAUDE.md §7 item 6).

**This module, `notebooks/phase3-llm-finetune.py`, `tests/test_llm_prompt_notebook_parity.py` and
DECISIONS.md ADR-0028 addendum #21 are one unit of work, all added or amended in the same
session** -- by the time the session ends, the notebook carries a VERBATIM copy of the marked
template block below, the parity test checks the two copies byte-identical, and the addendum
records the design decisions here. If you are reading this from a commit where any of those
three (the notebook, the parity test, the addendum) does not exist yet, that commit is
mid-session, not the final state -- check whether the other two landed nearby before treating an
absence as a defect. The parity test exists because this repo's local
test suite cannot import `torch`/`transformers` (Application Control blocks them; the notebook is
where they run), so the template cannot simply be imported there instead of copied, and a drift
between the two copies would silently invalidate the baseline-vs-fine-tune comparison: the model
would be trained and scored on text unlike what this module documents.

**Plain completion prompt, not a chat template -- deliberate, for two concrete reasons, not
because a chat-templated readout position is inherently ambiguous** (with a pinned tokenizer and
`add_generation_prompt=True`, it is not -- the generation position is just as fixed, at the last
prompt token, as it is here):

1. Qwen2.5-Instruct's chat template injects a default system prompt whose exact text is a
   property of the installed tokenizer/`transformers` version, not of this module -- a version
   bump could silently change what the model reads before ever seeing a listing, with nothing in
   this repo able to detect it. A plain completion prompt has no such hidden, version-dependent
   content.
2. The two-token readout scores " Yes"/" No" (WITH a leading space) as the tokens immediately
   following the literal "Answer:". After a chat template's assistant-turn boundary the natural
   continuation tokenizes as "Yes"/"No" (no leading space) instead -- a different pair of token
   ids the notebook would have to resolve differently. Ending on a fixed, plain string keeps that
   resolution the same in every run, notebook session, and (if the base model is ever swapped)
   model.

**Known, accepted limitation:** Qwen2.5-Instruct was trained on chat-formatted turns, so a plain
completion prompt is off-distribution for the base model -- but this project answers with the
LoRA-adapted checkpoint, never the zero-shot base model, so the base model's zero-shot behaviour
under this prompt format is not a result this project reports.
"""

from __future__ import annotations

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

"""Tests for src/pricepilot/matching/llm_prompt.py -- the Phase 3 item 6 LoRA prompt builder
(ADR-0028 addendum #21). The leakage checks here matter as much as the format checks: this
prompt is what the fine-tune actually trains and is scored on, and it must never let the
dataset's own sampling design (tiers, split membership, label counts) leak into what the model
reads as content."""

from __future__ import annotations

from pricepilot.matching.llm_prompt import _INSTRUCTION, LLM_PROMPT_VERSION, build_llm_prompt

TEXT_A = "title: Royal Canin Bichon Maltese Adult, 500 g | brand: royal canin | line: Bichon Maltese Adult | weight_g: 500"
TEXT_B = "title: Hrana uscata pentru caini Royal Canin Bichon Frise Adult 500 g | brand: royal canin | line: Bichon Frise Adult | weight_g: 500"


def test_version_constant_exists_and_is_a_nonempty_string() -> None:
    assert isinstance(LLM_PROMPT_VERSION, str)
    assert LLM_PROMPT_VERSION


def test_prompt_is_deterministic_for_a_given_pair() -> None:
    first = build_llm_prompt(TEXT_A, TEXT_B)
    second = build_llm_prompt(TEXT_A, TEXT_B)
    assert first == second


def test_prompt_ends_with_answer_colon() -> None:
    prompt = build_llm_prompt(TEXT_A, TEXT_B)
    assert prompt.endswith("Answer:")


def test_prompt_contains_both_pair_texts_verbatim() -> None:
    prompt = build_llm_prompt(TEXT_A, TEXT_B)
    assert TEXT_A in prompt
    assert TEXT_B in prompt


def test_prompt_does_not_swap_left_and_right() -> None:
    prompt = build_llm_prompt(TEXT_A, TEXT_B)
    assert prompt.index(TEXT_A) < prompt.index(TEXT_B)


def test_instruction_pinned_to_an_exact_literal() -> None:
    """A reviewer finding: a substring blocklist over the WHOLE prompt is weak (it can't tell a
    listing title containing an incidental match, e.g. German "Tier" = animal, from a real leak,
    and it silently tolerates a wording change nobody reviewed as one). Pinning the exact
    instruction text means any change to it is a deliberate, visible diff -- and forces
    `LLM_PROMPT_VERSION` to be considered every time it happens."""
    assert _INSTRUCTION == (
        "You are comparing two competitor-shop listings for pet food, treats or litter products.\n"
        "Decide whether Listing A and Listing B are the SAME purchasable unit: a "
        "price-comparison engine comparing their prices would be comparing the same physical "
        "product.\n"
        "\n"
        "Each of these, on its own, makes them NOT the same unit: a different net weight or "
        "volume; a different pack count (a stated count of 1 and no count stated are the SAME); "
        "a different bonus weight; a different species (dog vs cat); a different life-stage, "
        "sterilised, light, sensitive, indoor, dental, urinary or joint-care formula; a "
        "different food form (dry vs wet/tin/pouch -- wet, tin and pouch among themselves are "
        "NOT a difference); a different breed size (e.g. Mini vs Maxi); a different flavour "
        "(the same flavour word in another language, e.g. Salmon/Somon, is NOT a difference).\n"
        "\n"
        "None of these, on their own, make them different: generic descriptive words "
        "(grain-free, premium, natural, holistic); an animal-weight dosage band (e.g. 12-25 kg) "
        "stated on only one side; a mismatched brand name alone when everything else about the "
        "listing matches.\n"
        "\n"
        "Answer with exactly one word: Yes or No."
    )


def test_instruction_leaks_no_tier_split_or_label_count_information() -> None:
    """The real point of this test: the instruction text must state the task in the project's
    own terms without ever revealing anything about how the dataset was sampled or scored.
    Scans `_INSTRUCTION` directly, not the full formatted prompt -- listing titles (`text_a`/
    `text_b`) are real product text an attacker doesn't control this check against, and a
    coincidental match there (e.g. the German word "Tier") would be a false alarm, not a leak."""
    lowered = _INSTRUCTION.lower()
    forbidden_substrings = [
        "tier",
        "trivial_spot_check",
        "proxy_key_collision",
        "blocked_retrieval_candidate",
        "train_val",
        "trainval",
        "test",
        "split",
        "pair_id",
        "annotat",
        "label",
        "sampl",
        "valid",
        "held-out",
        "held out",
        "997",
        "672",
        "287",
    ]
    for forbidden in forbidden_substrings:
        assert forbidden not in lowered, f"instruction leaks forbidden information: {forbidden!r}"


def test_full_prompt_is_instruction_plus_the_fixed_wrapper_exactly() -> None:
    """Ties `_INSTRUCTION`'s content into what `build_llm_prompt` actually returns, so the two
    prior tests' guarantees about `_INSTRUCTION` provably extend to the real output."""
    prompt = build_llm_prompt(TEXT_A, TEXT_B)
    assert prompt == f"{_INSTRUCTION}\n\nListing A: {TEXT_A}\nListing B: {TEXT_B}\nAnswer:"


def test_prompt_is_a_plain_completion_not_a_chat_template() -> None:
    """Pins the deliberate design choice documented in the module docstring: no chat-template
    role markers or special tokens -- kept out for the two concrete reasons stated there (a
    version-dependent default system prompt; " Yes"/" No" tokenizing differently after a
    chat-template assistant-turn boundary), not because the readout position would be
    ambiguous."""
    prompt = build_llm_prompt(TEXT_A, TEXT_B)
    for chat_marker in (
        "<|im_start|>",
        "<|im_end|>",
        "[INST]",
        "[/INST]",
        "<|user|>",
        "<|assistant|>",
    ):
        assert chat_marker not in prompt


def test_prompt_mentions_the_task_in_plain_language() -> None:
    prompt = build_llm_prompt(TEXT_A, TEXT_B)
    assert "purchasable unit" in prompt
    assert "Yes or No" in prompt

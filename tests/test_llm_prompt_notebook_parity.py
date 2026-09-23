"""Guards the ONE property this repo's local test suite can check about
`notebooks/phase3-llm-finetune.py` -- that its prompt-template block is byte-identical to
`src/pricepilot/matching/llm_prompt.py`'s own copy (ADR-0028 addendum #21). The notebook itself
cannot be imported or executed here: `torch`/`transformers`/`peft` are blocked by this machine's
Application Control policy, and training needs a GPU this machine doesn't have. A drift between
the two copies would silently invalidate the baseline-vs-fine-tune comparison -- the model would
be trained and scored on text unlike what `llm_prompt.py` documents and what its own tests pin.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LLM_PROMPT_PATH = ROOT / "src" / "pricepilot" / "matching" / "llm_prompt.py"
NOTEBOOK_PATH = ROOT / "notebooks" / "phase3-llm-finetune.py"

_BEGIN_MARKER = "# TEMPLATE-BEGIN"
_END_MARKER = "# TEMPLATE-END"


def _extract_template(text: str, source: str) -> str:
    """Returns everything strictly between the line that IS EXACTLY "# TEMPLATE-BEGIN" and the
    line that IS EXACTLY "# TEMPLATE-END" (after stripping). Matches whole lines, not a plain
    substring search -- both modules' docstrings mention these marker names in prose (to explain
    what they are), and a substring search would count those mentions as extra markers too."""
    lines = text.splitlines()
    begin_indices = [i for i, line in enumerate(lines) if line.strip() == _BEGIN_MARKER]
    end_indices = [i for i, line in enumerate(lines) if line.strip() == _END_MARKER]
    if len(begin_indices) != 1:
        raise AssertionError(
            f"{source}: expected exactly one line that is exactly {_BEGIN_MARKER!r}, "
            f"found {len(begin_indices)}"
        )
    if len(end_indices) != 1:
        raise AssertionError(
            f"{source}: expected exactly one line that is exactly {_END_MARKER!r}, "
            f"found {len(end_indices)}"
        )
    begin_at, end_at = begin_indices[0], end_indices[0]
    if end_at <= begin_at:
        raise AssertionError(
            f"{source}: {_END_MARKER!r} line appears before {_BEGIN_MARKER!r} line"
        )
    return "\n".join(lines[begin_at + 1 : end_at])


def test_both_files_exist() -> None:
    assert LLM_PROMPT_PATH.is_file(), f"missing {LLM_PROMPT_PATH}"
    assert NOTEBOOK_PATH.is_file(), f"missing {NOTEBOOK_PATH}"


def test_notebook_template_is_byte_identical_to_llm_prompt_module() -> None:
    module_text = LLM_PROMPT_PATH.read_text(encoding="utf-8")
    notebook_text = NOTEBOOK_PATH.read_text(encoding="utf-8")
    module_template = _extract_template(module_text, "llm_prompt.py")
    notebook_template = _extract_template(notebook_text, "phase3-llm-finetune.py")
    assert module_template == notebook_template, (
        "notebooks/phase3-llm-finetune.py's prompt template has drifted from "
        "src/pricepilot/matching/llm_prompt.py's -- copy the marked block from llm_prompt.py "
        "into the notebook verbatim, and bump LLM_PROMPT_VERSION in both places."
    )


def test_extracted_template_is_nonempty_and_contains_the_instruction() -> None:
    """A guard against the parity test passing vacuously (e.g. both files' markers sitting
    adjacent with nothing between them, which would make the equality check trivially true)."""
    module_template = _extract_template(
        LLM_PROMPT_PATH.read_text(encoding="utf-8"), "llm_prompt.py"
    )
    assert len(module_template.strip()) > 100
    assert "_INSTRUCTION" in module_template
    assert "def build_llm_prompt" in module_template
    assert "LLM_PROMPT_VERSION" in module_template


def test_parity_test_would_fail_on_a_deliberately_mutated_copy() -> None:
    """Proves this test actually detects drift, not just that the happy path passes -- mutates a
    single character inside the notebook's copy of the template (in memory only, nothing written
    to disk) and confirms the two extracted blocks stop matching."""
    module_template = _extract_template(
        LLM_PROMPT_PATH.read_text(encoding="utf-8"), "llm_prompt.py"
    )
    notebook_text = NOTEBOOK_PATH.read_text(encoding="utf-8")
    notebook_template = _extract_template(notebook_text, "phase3-llm-finetune.py")
    assert module_template == notebook_template  # sanity: real files agree before mutating

    mutated = notebook_template.replace("Yes or No", "Yes or NO", 1)
    assert mutated != notebook_template, "mutation had no effect -- fix the test's mutation"
    assert module_template != mutated, "mutated copy must NOT match the real template"

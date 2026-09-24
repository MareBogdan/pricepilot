"""Guards the torchao/peft environment-compatibility patch against drift between the two Kaggle
notebooks that both call into peft (Phase 3 item 8 smoke run, 2026-09-24).

Kaggle's image ships torchao 0.10.0, but the installed peft only supports torchao >= 0.16.0 and
RAISES ImportError (instead of returning False) from is_torchao_available() when it probes an
older one, inside get_peft_model / PeftModel.from_pretrained ->
peft/tuners/lora/torchao.py::dispatch_torchao. `notebooks/phase3-llm-finetune.py` already carried
the fix; the first Kaggle run of `notebooks/phase3-serving-benchmark.ipynb` (which also calls
PeftModel.from_pretrained, in llm_merge) hit the same ImportError because the patch had not been
ported. Neither notebook can be executed or type-checked by this repo's local suite (torch/peft
are blocked by this machine's Application Control policy), so byte-identity of the patch block is
the one thing that can be pinned locally against a repeat of this failure.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRAINING_PATH = ROOT / "notebooks" / "phase3-llm-finetune.py"
SERVING_PATH = ROOT / "notebooks" / "phase3-serving-benchmark.ipynb"

_BEGIN_MARKER = "# ENV-COMPAT-BEGIN"
_END_MARKER = "# ENV-COMPAT-END"


def _extract_env_compat(text: str, source: str) -> str:
    """Everything strictly between the line that IS EXACTLY "# ENV-COMPAT-BEGIN" and the line
    that IS EXACTLY "# ENV-COMPAT-END". Whole-line match, not substring, for the same reason as
    the TEMPLATE markers in test_llm_prompt_notebook_parity.py: prose elsewhere may mention these
    names without being the marker itself."""
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


def _serving_notebook_source() -> str:
    nb = json.loads(SERVING_PATH.read_text(encoding="utf-8"))
    return "\n".join("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code")


def test_both_files_exist() -> None:
    assert TRAINING_PATH.is_file(), f"missing {TRAINING_PATH}"
    assert SERVING_PATH.is_file(), f"missing {SERVING_PATH}"


def test_serving_notebook_env_compat_block_is_byte_identical_to_training_script() -> None:
    training_text = TRAINING_PATH.read_text(encoding="utf-8")
    training_block = _extract_env_compat(training_text, "phase3-llm-finetune.py")
    serving_block = _extract_env_compat(
        _serving_notebook_source(), "phase3-serving-benchmark.ipynb"
    )
    assert training_block == serving_block, (
        "notebooks/phase3-serving-benchmark.ipynb's torchao/peft compatibility patch has drifted "
        "from notebooks/phase3-llm-finetune.py's -- copy the marked block from the training "
        "script into the serving notebook verbatim (ADR-0028 addendum #23)."
    )


def test_extracted_block_is_nonempty_and_neutralises_both_torchao_bindings() -> None:
    """Guard against the parity test passing vacuously, and against a partial port that patches
    only one of the two is_torchao_available bindings peft holds (see the block's own comment:
    peft.tuners.lora.torchao imports the name into its own namespace at import time)."""
    training_block = _extract_env_compat(
        TRAINING_PATH.read_text(encoding="utf-8"), "phase3-llm-finetune.py"
    )
    assert len(training_block.strip()) > 200
    assert "peft.import_utils.is_torchao_available = _no_torchao" in training_block
    assert "_lora_torchao.is_torchao_available = _no_torchao" in training_block


def test_env_compat_patch_runs_before_peft_is_used_in_the_serving_notebook() -> None:
    """The patch must execute before PeftModel.from_pretrained (llm_merge) is ever called --
    that call is what raises without the patch."""
    src = _serving_notebook_source()
    patch_at = src.index(_BEGIN_MARKER)
    used_at = src.index("PeftModel.from_pretrained")
    assert patch_at < used_at


def test_parity_test_would_fail_on_a_deliberately_mutated_copy() -> None:
    """Proves this test actually detects drift, not just that the happy path passes."""
    training_block = _extract_env_compat(
        TRAINING_PATH.read_text(encoding="utf-8"), "phase3-llm-finetune.py"
    )
    serving_block = _extract_env_compat(
        _serving_notebook_source(), "phase3-serving-benchmark.ipynb"
    )
    assert training_block == serving_block  # sanity: real files agree before mutating

    mutated = serving_block.replace("is_torchao_available", "is_torchao_available_typo", 1)
    assert mutated != serving_block, "mutation had no effect -- fix the test's mutation"
    assert training_block != mutated, "mutated copy must NOT match the real block"

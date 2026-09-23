"""Guards the premise of the item-8 cross-encoder retrain (docs/phase3-ce-reproduction-rule.md):
the retrain notebook's training cell is byte-identical to the original notebook's only code cell.
If it were not, "REPRODUCED / NOT_REPRODUCED" would compare two different programs. The retrain
adds one cell AFTER the training cell that only saves files.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT / "notebooks" / "phase3-cross-encoder-baseline.ipynb"
RETRAIN = ROOT / "notebooks" / "phase3-cross-encoder-retrain.ipynb"


def _code_cells(path: Path) -> list[str]:
    nb = json.loads(path.read_text(encoding="utf-8"))
    return ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]


def test_original_has_exactly_one_code_cell() -> None:
    assert len(_code_cells(ORIGINAL)) == 1


def test_retrain_first_code_cell_is_byte_identical_to_the_original() -> None:
    original = _code_cells(ORIGINAL)[0]
    retrain = _code_cells(RETRAIN)
    assert len(retrain) >= 2, "retrain must have the training cell plus the appended save cell"
    assert retrain[0].encode("utf-8") == original.encode("utf-8"), (
        "retrain cell 1 differs from the original training cell: the reproduction premise is broken"
    )


def test_retrain_appended_cell_only_saves() -> None:
    """The appended cell must not train or re-score anything."""
    appended = _code_cells(RETRAIN)[1]
    for forbidden in ("optimizer", ".backward(", ".fit(", "f1_score"):
        assert forbidden not in appended

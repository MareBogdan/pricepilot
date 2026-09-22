"""Fails if docs/learned/phase3-labels.json changes after `scripts/freeze_labels.py --freeze`
(ADR-0028 addendum #15). No label may change after the freeze without a stated reason recorded in
STATE.md first. While the constant is UNFROZEN (annotator's final review pass pending) the hash
test is skipped, loudly."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LABELS_JSON = ROOT / "docs" / "learned" / "phase3-labels.json"
FROZEN_LABELS_SHA256 = "540a4fd6ccfc52525014ac770caadbf544243dccc5a85d3fcb279fd7d052eed4"


def test_frozen_labels_hash_unchanged() -> None:
    if FROZEN_LABELS_SHA256 == "UNFROZEN":
        pytest.skip("labels not frozen yet -- run scripts/freeze_labels.py --freeze after review")
    actual = hashlib.sha256(LABELS_JSON.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert actual == FROZEN_LABELS_SHA256, (
        "phase3-labels.json changed after the freeze. Record the reason in STATE.md first."
    )
    assert FROZEN_LABELS_SHA256 in (ROOT / "STATE.md").read_text(encoding="utf-8")


def test_freeze_script_rewrites_constant_and_state(tmp_path: Path) -> None:
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    import freeze_labels as fl

    t = tmp_path / "t.py"
    t.write_text('FROZEN_LABELS_SHA256 = "UNFROZEN"\n', encoding="utf-8")
    s = tmp_path / "STATE.md"
    s.write_text("Frozen labels SHA-256: `UNFROZEN`\n", encoding="utf-8")
    fl.write_hash("ab" * 32, t, s)
    assert ("ab" * 32) in t.read_text(encoding="utf-8")
    assert ("ab" * 32) in s.read_text(encoding="utf-8")


def test_freeze_script_never_touches_a_history_snapshot(tmp_path: Path) -> None:
    """A historical `## History` snapshot can carry its own, older 'Frozen labels SHA-256:' line
    (a preserved record of a past, not-yet-frozen session) -- write_hash() must update only the
    LIVE marker above `## History` and leave any marker inside it byte-for-byte untouched. This
    is exactly the bug caught in review while building ADR-0028 addendum #18's STATE.md
    restructure: a `count=1` substitution over the whole file silently corrupted a preserved
    snapshot the first time `## History` existed."""
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    import freeze_labels as fl

    t = tmp_path / "t.py"
    t.write_text('FROZEN_LABELS_SHA256 = "UNFROZEN"\n', encoding="utf-8")
    s = tmp_path / "STATE.md"
    s.write_text(
        "Frozen labels SHA-256: `UNFROZEN`\n"
        "\n"
        "## History\n"
        "\n"
        "### an old, preserved snapshot\n"
        "Frozen labels SHA-256: `UNFROZEN`\n",
        encoding="utf-8",
    )
    fl.write_hash("cd" * 32, t, s)
    text = s.read_text(encoding="utf-8")
    live, _, history = text.partition("## History")
    assert ("cd" * 32) in live
    assert "UNFROZEN" not in live
    assert "UNFROZEN" in history
    assert ("cd" * 32) not in history

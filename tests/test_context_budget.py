"""CLAUDE.md, STATE.md and DECISIONS.md must stay within the context budget.

**Why this is a test and not a note in CLAUDE.md.** CLAUDE.md loads on every Claude Code turn,
and STATE.md/DECISIONS.md are read every session (CLAUDE.md section 11, the 2026-09-25 context
diet, ADR-0029). A rule that says "keep these files short" is a suggestion that erodes one
session at a time; a failing test is a limit that holds. The corresponding discipline (move
closed-phase history to docs/archive/, never delete) is checked separately by
`scripts/check_archive_integrity.py` and `tests/test_archive_integrity.py`.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

LIMITS = {
    "CLAUDE.md": 400,
    "STATE.md": 400,
    "DECISIONS.md": 600,
}


def _line_count(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    # Count lines the way an editor would: a trailing newline does not add an extra
    # blank line, but content after the last "\n" with no trailing newline still counts.
    lines = text.splitlines()
    return len(lines)


def test_claude_md_within_budget() -> None:
    count = _line_count(ROOT / "CLAUDE.md")
    assert count <= LIMITS["CLAUDE.md"], (
        f"CLAUDE.md is {count} lines, budget is {LIMITS['CLAUDE.md']}"
    )


def test_state_md_within_budget() -> None:
    count = _line_count(ROOT / "STATE.md")
    assert count <= LIMITS["STATE.md"], f"STATE.md is {count} lines, budget is {LIMITS['STATE.md']}"


def test_decisions_md_within_budget() -> None:
    count = _line_count(ROOT / "DECISIONS.md")
    assert count <= LIMITS["DECISIONS.md"], (
        f"DECISIONS.md is {count} lines, budget is {LIMITS['DECISIONS.md']}"
    )

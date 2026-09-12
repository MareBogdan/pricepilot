"""Every `.ps1` in this repo must be pure ASCII.

**Why this is a test and not a note in CLAUDE.md.** Windows PowerShell 5.1 - the version on the
dev machine, and the one `make.ps1` and `schedule_daily.ps1` run under - reads a `.ps1` file
without a byte-order mark as **ANSI (cp1252), not UTF-8**. A single non-ASCII byte is therefore
decoded to the wrong character, which corrupts the string literal it sits in and desynchronises
the parser. The failure does not look like an encoding problem: it surfaces as

    Unexpected token 'install' in expression or statement
    The token '&&' is not a valid statement separator in this version
    Missing closing '}' in statement block

pointing at lines that are perfectly correct, tens of lines away from the actual em dash. One
em dash inside a `Write-Host` message cost a debugging cycle on 2026-09-12.

Two fixes exist - save every `.ps1` as UTF-8 **with** a BOM, or keep them ASCII. ASCII is chosen
because a BOM is invisible in a diff and one editor saving without it silently reintroduces the
bug, whereas this test cannot be silently satisfied. See DECISIONS.md ADR-0013.

CLAUDE.md section 9 logic: a rule in a markdown file is a suggestion; a failing test is a rule.
The same reasoning already guards the LLM-SDK import ban (ADR-0006).
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".venv", "node_modules", ".git", "__pycache__", "logs"}

# The punctuation people reach for that breaks this, and what to write instead. Keys are built
# with chr() rather than written literally: this file must itself stay ASCII, or the formatter
# will helpfully turn an escape into the very character the test exists to ban.
SUGGESTIONS = {
    chr(0x2014): "em dash -> ' - '",
    chr(0x2013): "en dash -> '-'",
    chr(0x2018): "curly quote -> a plain apostrophe",
    chr(0x2019): "curly quote -> a plain apostrophe",
    chr(0x201C): "curly double quote -> a plain double quote",
    chr(0x201D): "curly double quote -> a plain double quote",
    chr(0x2026): "ellipsis -> '...'",
    chr(0x00A0): "non-breaking space -> a plain space",
    chr(0x00A7): "section sign -> 'section '",
    chr(0x20AC): "euro sign -> 'EUR'",
    chr(0x2192): "arrow -> '->'",
}


def label(path: Path) -> str:
    """Repo-relative where possible; the tmp_path in the self-test is not under ROOT."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def powershell_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*.ps1")
        if not SKIP_DIRS.intersection(path.relative_to(ROOT).parts)
    )


def test_repo_has_powershell_files() -> None:
    """If this ever fails, the scan below is passing vacuously."""
    found = powershell_files()
    assert found, "no .ps1 files found - has the scan path or the Windows shim moved?"
    assert any(path.name == "make.ps1" for path in found)


@pytest.mark.parametrize("path", powershell_files(), ids=lambda p: p.name)
def test_powershell_file_is_ascii(path: Path) -> None:
    """Fail with the file, line, column and character, so the fix is obvious."""
    offences: list[str] = []
    for lineno, line in enumerate(path.read_bytes().split(b"\n"), start=1):
        for column, byte in enumerate(line, start=1):
            if byte <= 0x7F:
                continue
            # Decode the whole line for a readable report; the byte offset is what matters.
            text = line.decode("utf-8", errors="replace")
            char = next((c for c in text if ord(c) > 0x7F), "?")
            hint = SUGGESTIONS.get(char, f"U+{ord(char):04X} - replace with an ASCII equivalent")
            offences.append(
                f"  {label(path)}:{lineno}: byte {column} is 0x{byte:02X} "
                f"({char!r}) - {hint}\n    {text.strip()[:100]}"
            )
            break  # one report per line is enough to locate it

    assert not offences, (
        f"{label(path)} contains non-ASCII bytes. PowerShell 5.1 reads a BOM-less "
        f".ps1 as ANSI, so these corrupt the script and produce parser errors on unrelated "
        f"lines (see this module's docstring, DECISIONS.md ADR-0013):\n" + "\n".join(offences)
    )


def test_the_guard_actually_catches_something(tmp_path: Path) -> None:
    """A guard that cannot fail is not a guard. Proves the byte scan trips on an em dash."""
    bad = tmp_path / "bad.ps1"
    bad.write_text(f'Write-Host "installed {chr(0x2014)} daily at 06:10"\n', encoding="utf-8")
    raw = bad.read_bytes()
    assert any(byte > 0x7F for byte in raw)
    with pytest.raises(AssertionError, match="non-ASCII"):
        test_powershell_file_is_ascii(bad)

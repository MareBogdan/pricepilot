"""A bug in the context-diet archiving would lose project history silently -- it earns a test.

Runs `scripts/check_archive_integrity.py` as a subprocess (not imported: the script is a
standalone audit tool, and running it exactly as a human would from the terminal is the point)
and asserts it reports zero missing lines.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_check_archive_integrity_reports_zero_missing() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_archive_integrity.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"check_archive_integrity.py failed (exit {result.returncode}):\n"
        f"{result.stdout}\n{result.stderr}"
    )
    assert "MISSING:             0" in result.stdout, result.stdout

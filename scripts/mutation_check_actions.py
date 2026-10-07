r"""Mutation check for the Phase 6 action layer (ADR-0047): does the test suite notice when a safety
property is deliberately broken?

    .venv\Scripts\python scripts/mutation_check_actions.py

Each mutant rewrites ONE line of `src/pricepilot/actions/*.py` (a safety check replaced by a constant),
runs `tests/test_actions.py`, and expects FAILURES. The original file is always restored (also on
Ctrl-C). Exit code 0 only if every mutant was killed and the unmutated suite passes. This is the
script behind the "mutants killed" claim in STATE.md / ADR-0047; it needs no database and no network.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIONS = ROOT / "src" / "pricepilot" / "actions"

# (name, file, exact text to find, replacement)
MUTANTS: list[tuple[str, str, str, str]] = [
    ("a no-change is treated as an update", "selector.py",
     "if guard_final_price == current_price:", "if False:"),
    ("stale recommendations are applied", "apply.py",
     "if store_price != rec.current_price:", "if False:"),
    ("stress-test rows are acted on", "apply.py",
     "if is_stress(rec.scenario):", "if False:"),
    ("superseded rows are acted on", "apply.py",
     "if rec.run_label == SUPERSEDED_RUN_LABEL:", "if False:"),
    ("a second apply is not detected", "apply.py",
     "if existing is not None:", "if False:"),
    ("rollback ignores a drifted store price", "rollback.py",
     "if store_price != set_price:", "if False:"),
    ("two rollbacks can both pass", "rollback.py",
     "if cast(CursorResult[Any], claimed).rowcount != 1:", "if False:"),
    ("a failed verification read loses the row", "apply.py",
     "    except Exception:", "    except ZeroDivisionError:"),
]  # fmt: skip


def run_tests() -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_actions.py", "-o", "addopts=", "-q", "-x"],
        cwd=ROOT, capture_output=True, text=True,
    )  # fmt: skip
    tail = [ln for ln in proc.stdout.splitlines() if "passed" in ln or "failed" in ln]
    return proc.returncode == 0, tail[-1] if tail else proc.stdout[-200:]


def main() -> int:
    ok, summary = run_tests()
    print(f"baseline (no mutation): {'PASS' if ok else 'FAIL'} - {summary}")
    if not ok:
        return 1
    survivors = 0
    for name, filename, old, new in MUTANTS:
        path = ACTIONS / filename
        original = path.read_text(encoding="utf-8")
        if original.count(old) != 1:
            print(f"MUTANT NOT APPLICABLE ({name}): expected exactly one match for {old!r}")
            return 2
        try:
            path.write_text(original.replace(old, new), encoding="utf-8", newline="")
            passed, summary = run_tests()
        finally:
            path.write_text(original, encoding="utf-8", newline="")
        status = "SURVIVED  <-- the suite did NOT notice" if passed else "killed"
        survivors += passed
        print(f"  {status:<8} {name}  [{summary}]")
    ok, summary = run_tests()
    print(f"restored: {'PASS' if ok else 'FAIL'} - {summary}")
    print(f"\n{len(MUTANTS) - survivors} of {len(MUTANTS)} mutants killed")
    return 0 if ok and survivors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

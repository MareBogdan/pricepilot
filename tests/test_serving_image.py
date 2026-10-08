"""The lean serving image (ADR-0051): the dashboard must run without the ML stack or the model.

Three guards: the API module imports without torch & co; the core dependency list carries none of
them; the Dockerfile ships the files the dashboard reads (so no headline number turns into "n/a")
and never the model.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

from pricepilot.api import results

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = (
    "torch",
    "transformers",
    "onnxruntime",
    "sentence_transformers",
    "sklearn",
    "anthropic",
    "structlog",
    "selectolax",
    "alembic",
)


def test_api_module_imports_without_the_ml_stack() -> None:
    code = (
        "import sys; import pricepilot.api.main; "
        f"bad = [m for m in {FORBIDDEN!r} if m in sys.modules]; "
        "sys.exit('ML modules imported: ' + ', '.join(bad) if bad else 0)"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT, check=False
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_core_dependencies_exclude_the_ml_stack() -> None:
    core = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "dependencies"
    ]
    names = {re.split(r"[\[<>=!~ ]", dep, maxsplit=1)[0].lower().replace("_", "-") for dep in core}
    heavy = {"torch", "transformers", "onnxruntime", "sentence-transformers", "scikit-learn"}
    assert not names & heavy, names & heavy
    assert "anthropic" not in names


def test_dockerfile_ships_what_the_dashboard_reads_and_not_the_model() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    for name in (results.MATCHER_FILE, results.BASELINE_FILE, results.RAG_FILE):
        assert name in dockerfile, f"Dockerfile does not copy {name}: its tile would read n/a"
        assert (ROOT / "docs" / "learned" / "results" / name).is_file()
        assert f"!docs/learned/results/{name}" in (ROOT / ".dockerignore").read_text("utf-8")
    assert "COPY config/" in dockerfile
    assert "0.0.0.0" in dockerfile
    assert "7860" in dockerfile
    assert not [ln for ln in dockerfile.splitlines() if ln.startswith("COPY") and "models" in ln]
    ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert "models" in ignore
    assert "data" in ignore

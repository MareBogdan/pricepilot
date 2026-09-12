r"""`make status` — the command Bogdan runs when he opens the terminal (CLAUDE.md §11).

Every number here is QUERIED, never hand-written: from Postgres where the data lives,
from the filesystem otherwise. If Postgres is down the script still runs and says so,
because a status command that crashes is worse than useless.

Run:  make status   |   .\make.ps1 status   |   uv run python scripts/status.py
"""

from __future__ import annotations

import io
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# The Windows console defaults to cp1252 and cannot encode the em dashes and box-drawing
# characters these reports use, so `print` raises UnicodeEncodeError partway down the output.
# A report that dies halfway is worse than useless - force UTF-8 on the way out.
for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")

GREEN, YELLOW, RED, DIM, BOLD, RESET = (
    "\033[32m",
    "\033[33m",
    "\033[31m",
    "\033[2m",
    "\033[1m",
    "\033[0m",
)


def _h(title: str) -> None:
    print(f"\n{BOLD}{title}{RESET}")


def _row(label: str, value: object, ok: bool | None = None) -> None:
    colour = "" if ok is None else (GREEN if ok else YELLOW)
    print(f"  {label:<28} {colour}{value}{RESET}")


# ---------------------------------------------------------------------------
# Repo-derived facts
# ---------------------------------------------------------------------------


def current_phase() -> str:
    """The phase label from STATE.md. This is the one hand-maintained string; every
    number below is computed."""
    state = ROOT / "STATE.md"
    if not state.exists():
        return "unknown (STATE.md missing)"
    match = re.search(r"^Phase:\s*(.+)$", state.read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1).strip() if match else "unknown"


def gate_progress() -> list[tuple[bool, str]]:
    """Checklist items parsed out of the '## Gate progress' block in STATE.md."""
    state = ROOT / "STATE.md"
    if not state.exists():
        return []
    text = state.read_text(encoding="utf-8")
    block = re.search(r"## Gate progress\n(.*?)(?:\n## |\Z)", text, re.DOTALL)
    if not block:
        return []
    return [
        (mark.lower() == "x", label.strip())
        for mark, label in re.findall(r"^\[([ xX])\]\s*(.+)$", block.group(1), re.MULTILINE)
    ]


def test_count() -> tuple[int, int, str]:
    """(passed, failed, note) from an actual pytest run. Never asserted, always executed."""
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                # No -q here: pyproject already sets it in addopts, and a second -q
                # suppresses the summary line this function parses.
                "--no-header",
                "-p",
                "no:cacheprovider",
                "-p",
                "no:warnings",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return 0, 0, f"could not run pytest ({exc.__class__.__name__})"
    # Scan the whole output, not just the last line: pytest appends warning and docs
    # footers after the summary, and parsing the tail silently reports 0 passed.
    summary = next(
        (
            line
            for line in reversed(proc.stdout.splitlines())
            if re.search(r"\d+ (passed|failed|error)", line)
        ),
        "",
    )
    passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", summary)) else 0
    failed = int(m.group(1)) if (m := re.search(r"(\d+) (?:failed|error)", summary)) else 0
    return passed, failed, summary or proc.stdout.strip()[-200:]


def annotated_pairs() -> tuple[int, str]:
    """Phase 3's manual bottleneck. Counted from the annotation file once it exists."""
    path = ROOT / "data" / "annotations.jsonl"
    if not path.exists():
        return 0, "not started (data/annotations.jsonl)"
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    labels: dict[str, int] = {}
    for line in lines:
        try:
            labels[str(json.loads(line).get("label", "?"))] = (
                labels.get(str(json.loads(line).get("label", "?")), 0) + 1
            )
        except json.JSONDecodeError:
            continue
    return len(lines), ", ".join(f"{k}={v}" for k, v in sorted(labels.items())) or "-"


def fixture_count() -> int:
    fixtures = ROOT / "tests" / "fixtures"
    return sum(1 for _ in fixtures.rglob("*")) if fixtures.exists() else 0


# ---------------------------------------------------------------------------
# Database-derived facts
# ---------------------------------------------------------------------------


def overlap_section(total_listings: int) -> None:
    """The Phase 1 gate metric (CLAUDE.md §7, ADR-0009): products on two or more shops.

    Reported from day one, so a thin positive class for Phase 3 is visible as it fails to grow
    rather than discovered at the gate. It is a proxy key, not a matching model — see
    `src/pricepilot/overlap.py` for why that is the point.
    """
    from pricepilot.overlap import compute_overlap

    if total_listings == 0:
        _row("cross-shop overlap", "0 / 400 — no listings yet", False)
        return
    report = compute_overlap()
    _row("cross-shop overlap", f"{report.shared:,} / {report.target} products", report.met)
    _row("  └ sources compared", report.sources, report.sources >= 2)
    if report.sources < 2:
        print(f"  {DIM}one source only — overlap is 0 by definition until a second lands{RESET}")
    _row(
        "  └ keyable listings",
        f"{report.keys_built:,} of {report.listings_considered:,} "
        f"({report.keyable_share:.0%}; {report.unkeyable:,} have no weight in the title)",
    )


def db_section() -> None:
    try:
        from sqlalchemy import func, select

        from pricepilot.db import check_database, session_scope
        from pricepilot.models import LlmCall, RawListing, ScrapeRun
    except ImportError as exc:
        _row("database", f"dependencies not installed ({exc.name}) — run `make install`", False)
        return

    if not check_database():
        _row("database", "UNREACHABLE — run `docker compose up -d db`", False)
        _row("listings collected", "0 (no database)", False)
        _row("cross-shop overlap", "unknown (no database)", False)
        _row("days of price history", "0 (no database)", False)
        _row("llm spend to date", "$0.000000 (no database)", True)
        return

    with session_scope() as s:
        total = s.execute(select(func.count()).select_from(RawListing)).scalar_one()
        per_source = s.execute(
            select(
                RawListing.source,
                func.count(),
                func.count(func.distinct(func.date(RawListing.scraped_at))),
            )
            .group_by(RawListing.source)
            .order_by(func.count().desc())
        ).all()
        span = s.execute(
            select(func.min(RawListing.scraped_at), func.max(RawListing.scraped_at))
        ).one()
        runs = s.execute(select(func.count()).select_from(ScrapeRun)).scalar_one()
        alerts = s.execute(
            select(func.count()).select_from(ScrapeRun).where(ScrapeRun.status == "volume_alert")
        ).scalar_one()
        spend = s.execute(select(func.coalesce(func.sum(LlmCall.cost_usd), 0))).scalar_one()
        calls = s.execute(select(func.count()).select_from(LlmCall)).scalar_one()
        hits = s.execute(
            select(func.count()).select_from(LlmCall).where(LlmCall.cache_hit.is_(True))
        ).scalar_one()

    _row("database", "reachable", True)
    _row("listings collected", f"{total:,}", total >= 3000)
    for source, count, days in per_source:
        _row(f"  └ {source}", f"{count:,} listings / {days} days")
    if span[0] and span[1]:
        history_days = (span[1] - span[0]).days + 1
        _row("days of price history", history_days, history_days >= 7)
        _row("  └ first / last", f"{span[0]:%Y-%m-%d} → {span[1]:%Y-%m-%d}")
    else:
        _row("days of price history", "0 — Phase 1 has not run", False)
    _row("scrape runs", f"{runs} ({alerts} volume alerts)", alerts == 0)
    overlap_section(total)
    _row("llm calls logged", f"{calls} ({hits} cache hits)")
    _row("llm spend to date", f"${float(spend):.6f}", True)


# ---------------------------------------------------------------------------


def main() -> int:
    print(f"\n{BOLD}PricePilot status{RESET}  {DIM}{datetime.now(UTC):%Y-%m-%d %H:%M UTC}{RESET}")
    _row("phase", current_phase())

    _h("Gate progress")
    gates = gate_progress()
    if not gates:
        print(f"  {DIM}no gate checklist found in STATE.md{RESET}")
    for done, label in gates:
        mark = f"{GREEN}[x]{RESET}" if done else f"{YELLOW}[ ]{RESET}"
        print(f"  {mark} {label}")

    _h("Collection")
    db_section()
    _row("offline fixtures", fixture_count())

    _h("Phase 3 dataset")
    pairs, breakdown = annotated_pairs()
    _row("annotated pairs", f"{pairs} / 1000", pairs >= 1000)
    _row("  └ label breakdown", breakdown)

    _h("Repo health")
    passed, failed, note = test_count()
    _row("tests", f"{passed} passed, {failed} failed", failed == 0 and passed > 0)
    if note and (failed or not passed):
        print(f"  {DIM}{note}{RESET}")

    costs = ROOT / "docs" / "COSTS.md"
    if costs.exists():
        match = re.search(
            r"^\s*\*\*Running total:\s*(.+?)\*\*\s*$",
            costs.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        _row("costs ledger total", match.group(1).strip() if match else "see docs/COSTS.md")

    print()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

r"""`make overlap` — the Phase 1 gate metric, on its own.

    uv run python scripts/overlap_report.py
    .\make.ps1 overlap

`make status` prints the headline number; this prints the diagnosis. When the count is low the
question is always *why* — too few sources, or too few listings that state a weight in the title —
and those are different problems with different fixes.

The number is a **floor**, produced by a proxy key, not by a matching model. See
`src/pricepilot/overlap.py` for why that is deliberate.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# The Windows console defaults to cp1252 and cannot encode the em dashes and box-drawing
# characters these reports use, so `print` raises UnicodeEncodeError partway down the output.
# A report that dies halfway is worse than useless - force UTF-8 on the way out.
for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")


from pricepilot.db import check_database  # noqa: E402
from pricepilot.overlap import compute_overlap  # noqa: E402


def main() -> int:
    if not check_database():
        print("database UNREACHABLE — run `docker compose up -d db`", file=sys.stderr)
        return 2

    report = compute_overlap()
    # ADR-0023: this proxy count is a known-low floor (~8% measured recall against a hand-verified
    # sample), not the gate itself — the gate is decided from that sample (see `make status`).
    print(f"cross-shop overlap (proxy floor)   {report.shared:,}   — NOT the gate, see ADR-0023")
    print(f"sources compared       {report.sources}")
    print(f"listings considered    {report.listings_considered:,} (latest observation per product)")
    print(f"keys built             {report.keys_built:,} ({report.keyable_share:.0%})")
    print(f"unkeyable              {report.unkeyable:,} (no net weight in the title)")

    if report.sources < 2:
        print(
            "\nOne source only. Overlap is 0 by definition until a second adapter lands — "
            "this is expected while petmax.ro collects alone (ADR-0010)."
        )
    else:
        print(
            "\nThe gate (CLAUDE.md §7, ADR-0023) is decided from a hand-verified random sample, "
            "not this proxy count — see `make status` and DECISIONS.md ADR-0023."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

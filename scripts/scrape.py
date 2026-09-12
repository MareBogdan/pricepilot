r"""`make scrape` — run one source adapter.

    uv run python scripts/scrape.py --source petmax_ro --limit 5 --dry-run
    uv run python scripts/scrape.py --source petmax_ro --limit 0      # full run
    .\make.ps1 scrape

CLAUDE.md §5.2/§5.3: `--limit` defaults to `SCRAPER_DEFAULT_LIMIT` (5) and `--dry-run` parses and
prints but writes nothing. `--limit 0` means no cap and is how the daily schedule runs.

This script is also the daily schedule's entry point — see `scripts/schedule_daily.ps1`.
"""

from __future__ import annotations

import argparse
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


from pricepilot.scrapers import SCRAPERS  # noqa: E402
from pricepilot.scrapers.base import RobotsDisallowed, ScraperConfigError  # noqa: E402
from pricepilot.scrapers.runner import run_source  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        required=True,
        choices=sorted(SCRAPERS),
        help="which adapter to run",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="max listings to collect; 0 means no cap. Default: SCRAPER_DEFAULT_LIMIT from .env",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="parse and report, write nothing (not even the scrape_runs row)",
    )
    parser.add_argument(
        "--categories",
        nargs="*",
        default=None,
        help="override the adapter's default category slugs",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    scraper_cls = SCRAPERS[args.source]
    scraper = scraper_cls(categories=tuple(args.categories)) if args.categories else scraper_cls()

    try:
        outcome = run_source(scraper, limit=args.limit, dry_run=args.dry_run)
    except ScraperConfigError as exc:
        print(f"REFUSING TO RUN: {exc}", file=sys.stderr)
        return 2
    except RobotsDisallowed as exc:
        print(f"REFUSING TO RUN: {exc}", file=sys.stderr)
        return 3

    print(f"source            {outcome.source}")
    print(f"status            {outcome.status}")
    print(f"items found       {outcome.items_found}")
    print(f"items ingested    {outcome.ingested}")
    print(f"out of scope      {outcome.skipped_out_of_scope}")
    print(f"parse errors      {outcome.errors}")
    print(f"duration          {outcome.duration_seconds:.1f}s")
    if outcome.notes:
        print(f"notes             {outcome.notes}")

    if outcome.alerted:
        print(
            "\nVOLUME ALERT — nothing was ingested. Re-fetch a fixture and check the adapter "
            "before running again (CLAUDE.md §5.6).",
            file=sys.stderr,
        )
        return 1
    return 0 if outcome.status in ("ok", "dry_run") else 1


if __name__ == "__main__":
    raise SystemExit(main())

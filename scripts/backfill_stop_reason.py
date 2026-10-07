r"""One-off: fill `recommendations.llm_stop_reason` for the session-5 rows (migration 0014).

    $env:PRICEPILOT_DB_DRIVER = "pg8000"
    .venv\Scripts\python scripts/backfill_stop_reason.py [--run-label s5-real] [--max-tokens 400]

The 50 real replies were cached by `client.complete` (content-addressed, `data/llm-cache`), and the
cache entry records the provider's stop_reason. The key is recomputed from the stored prompt, so
each row is matched to ITS OWN response; the cached text must equal the stored `llm_raw_reply`
or the script stops without writing. No LLM call, $0.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select  # noqa: E402

from pricepilot.db import session_scope  # noqa: E402
from pricepilot.decision.engine import SYSTEM_PROMPT  # noqa: E402
from pricepilot.llm.client import DEFAULT_CACHE_DIR, cache_key  # noqa: E402
from pricepilot.models import Recommendation  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-label", default="s5-real")
    parser.add_argument("--max-tokens", type=int, default=400)
    args = parser.parse_args()
    updated = 0
    with session_scope() as session:
        rows = session.execute(
            select(Recommendation).where(
                Recommendation.run_label == args.run_label, Recommendation.is_mock.is_(False)
            )
        ).scalars()
        for row in rows:
            key = cache_key(
                row.llm_model, str(args.max_tokens), repr(None), SYSTEM_PROMPT, row.prompt_text
            )
            path = DEFAULT_CACHE_DIR / f"{key}.json"
            if not path.exists():
                print(f"row {row.id}: no cache entry {key[:12]}; stopping")
                return 1
            cached = json.loads(path.read_text(encoding="utf-8"))
            if cached["text"] != row.llm_raw_reply:
                print(f"row {row.id}: cached text differs from the stored reply; stopping")
                return 1
            row.llm_stop_reason = cached.get("stop_reason")
            updated += 1
    print(f"backfilled {updated} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

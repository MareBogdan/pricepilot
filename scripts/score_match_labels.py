r"""Precision and wrong-gramaj rate of the s3b matcher from the committed labels (ADR-0038/ADR-0040).

    .venv\Scripts\python scripts/score_match_labels.py                 # every labelled link
    .venv\Scripts\python scripts/score_match_labels.py --links <csv>   # only links in that worksheet

The only script behind the numbers in `docs/learned/results/phase5/gate-s3b.md`. It computes; it does
not judge pass/fail.

`--links` joins on (link_key, competitor_title), NOT link_key alone: `link_key` is
`product_id:shop`, and once the consistency guard removes a listing a different listing can take
the same (product, shop) slot under the same key (ADR-0041). A link whose title was never labelled
is reported as unlabelled and is excluded from the precision denominator.

A labelled NO counts as a wrong-gramaj false positive when its `reason` starts with GRAMAJ, WEIGHT
or SIZE (the labelling convention in the labels file: the reason leads with the error class).
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PHASE5 = ROOT / "docs" / "learned" / "results" / "phase5"
GRAMAJ_PREFIXES = ("GRAMAJ", "WEIGHT", "SIZE")


def score(labels: list[dict[str, str]], links: list[dict[str, str]] | None) -> dict[str, object]:
    by_pair = {(r["link_key"], r["competitor_title"]): r for r in labels}
    if links is None:
        rows, unlabelled = labels, []
    else:
        rows, unlabelled = [], []
        for link in links:
            hit = by_pair.get((link["link_key"], link["competitor_title"]))
            if hit is None:
                unlabelled.append(link["link_key"])
            else:
                rows.append(hit)
    yes = sum(r["label"] == "YES" for r in rows)
    gramaj = sum(
        r["label"] == "NO" and r["reason"].upper().startswith(GRAMAJ_PREFIXES) for r in rows
    )
    n = len(rows)
    return {
        "links_scored": n,
        "yes": yes,
        "precision": round(yes / n, 4) if n else None,
        "wrong_gramaj_false_positives": gramaj,
        "wrong_gramaj_rate": round(gramaj / n, 4) if n else None,
        "false_positives": [r["link_key"] for r in rows if r["label"] == "NO"],
        "unlabelled_links": unlabelled,
    }


def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--labels", type=Path, default=PHASE5 / "match-verification-labels.csv")
    parser.add_argument("--links", type=Path, help="worksheet CSV; default = all labelled links")
    args = parser.parse_args()
    links = read(args.links) if args.links else None
    print(json.dumps(score(read(args.labels), links), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

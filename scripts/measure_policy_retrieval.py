r"""Phase 5 session 2 -- retrieval eval against the PRE-REGISTERED question set (ADR-0036).

    uv run python scripts/measure_policy_retrieval.py

Reads `docs/learned/phase5-policy-retrieval-eval.csv` (committed before this script ever ran, so
the question set could not have been tuned to the metrics), runs `retrieve_policy` for every
question against the FULL ranking (k = number of policy sections, so a correct-but-not-top-3
answer still shows up in the MRR rather than looking like a miss), and computes:

- hit@1: the top-ranked passage's section_ref is in the question's expected set
- hit@3: any of the top-3 passages' section_ref is in the expected set
- MRR: 1 / (rank of the first correct passage in the full ranking), 0 if never found

Read-only: this script writes nothing to the database. Results go to
`docs/learned/results/phase5-policy-retrieval-eval.json`.
"""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import func, select  # noqa: E402

from pricepilot.db import check_database, session_scope  # noqa: E402
from pricepilot.models import PolicyChunk  # noqa: E402
from pricepilot.policy.retrieval import retrieve_policy  # noqa: E402

EVAL_CSV = ROOT / "docs" / "learned" / "phase5-policy-retrieval-eval.csv"
RESULTS_PATH = ROOT / "docs" / "learned" / "results" / "phase5-policy-retrieval-eval.json"


def load_questions() -> list[tuple[str, set[str]]]:
    rows = []
    with EVAL_CSV.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            expected = set(row["expected_section_refs"].split(";"))
            rows.append((row["question"], expected))
    return rows


def main() -> int:
    if not check_database():
        print("database UNREACHABLE", file=sys.stderr)
        return 2

    with session_scope() as session:
        section_count = session.execute(select(func.count()).select_from(PolicyChunk)).scalar_one()
    if section_count == 0:
        print("policy_chunks is empty -- run scripts/build_policy_index.py first", file=sys.stderr)
        return 2

    questions = load_questions()
    print(f"{len(questions)} pre-registered questions, {section_count} indexed sections\n")

    hits_at_1 = 0
    hits_at_3 = 0
    reciprocal_ranks: list[float] = []
    misses: list[dict[str, object]] = []
    per_question: list[dict[str, object]] = []

    for question, expected in questions:
        ranked = retrieve_policy(question, k=section_count)
        ranks_of_hits = [i for i, p in enumerate(ranked, start=1) if p.section_ref in expected]
        rank1 = ranked[0].section_ref in expected
        rank3 = any(p.section_ref in expected for p in ranked[:3])
        rr = 1.0 / ranks_of_hits[0] if ranks_of_hits else 0.0

        hits_at_1 += rank1
        hits_at_3 += rank3
        reciprocal_ranks.append(rr)
        per_question.append(
            {
                "question": question,
                "expected_section_refs": sorted(expected),
                "ranked_section_refs": [p.section_ref for p in ranked],
                "hit_at_1": rank1,
                "hit_at_3": rank3,
                "reciprocal_rank": rr,
            }
        )
        if not rank3:
            misses.append(
                {
                    "question": question,
                    "expected_section_refs": sorted(expected),
                    "ranked_section_refs": [p.section_ref for p in ranked],
                }
            )

    n = len(questions)
    hit_at_1 = hits_at_1 / n
    hit_at_3 = hits_at_3 / n
    mrr = sum(reciprocal_ranks) / n

    print(f"hit@1: {hits_at_1}/{n} = {hit_at_1:.3f}")
    print(f"hit@3: {hits_at_3}/{n} = {hit_at_3:.3f}")
    print(f"MRR:   {mrr:.3f}")
    if misses:
        print(f"\n{len(misses)} question(s) missed top-3:")
        for m in misses:
            print(f"  Q: {m['question']}")
            print(f"     expected {m['expected_section_refs']}, got {m['ranked_section_refs']}")
    else:
        print("\nevery question's correct section landed in the top 3.")

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(
            {
                "n_questions": n,
                "n_sections": section_count,
                "hit_at_1": hit_at_1,
                "hit_at_3": hit_at_3,
                "mrr": mrr,
                "misses": misses,
                "per_question": per_question,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote {RESULTS_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

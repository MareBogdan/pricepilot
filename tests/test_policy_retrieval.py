"""Phase 5 session 2: `retrieve_policy` and the policy index build (ADR-0036).

Both tests need a live Postgres with `policy_chunks` populated (`scripts/build_policy_index.py`)
-- pgvector's cosine operator has no SQLite equivalent, unlike the pure-schema tests in
`test_norm_listings.py`. Marked `requires_db` and skipped when `DATABASE_URL` is unreachable, per
that marker's own definition in pyproject.toml.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import func, select

from pricepilot.db import check_database, session_scope
from pricepilot.models import PolicyChunk
from pricepilot.policy.retrieval import retrieve_policy

ROOT = Path(__file__).resolve().parents[1]
DB_REACHABLE = check_database()

pytestmark = [
    pytest.mark.requires_db,
    pytest.mark.skipif(not DB_REACHABLE, reason="DATABASE_URL unreachable"),
]


def _chunk_count() -> int:
    with session_scope() as session:
        return session.execute(select(func.count()).select_from(PolicyChunk)).scalar_one()


@pytest.mark.parametrize(
    ("query", "expected_section_ref"),
    [
        ("What is the minimum margin floor for dry food?", "1"),
        ("How much can a price move in a single day?", "4"),
        ("How should final prices be rounded, ,99 or ,90?", "6"),
    ],
)
def test_retrieve_policy_returns_the_expected_section(
    query: str, expected_section_ref: str
) -> None:
    passages = retrieve_policy(query, k=3)
    assert passages, "retrieve_policy returned nothing"
    assert passages[0].section_ref == expected_section_ref
    # TEXT ONLY -- a passage is never a place a number could hide (CLAUDE.md section 6 rule 1).
    for p in passages:
        assert isinstance(p.text, str)
        assert isinstance(p.heading, str)


def test_index_build_is_idempotent() -> None:
    """Re-running the index build must not duplicate or drop rows for an unchanged document."""
    before = _chunk_count()
    assert before > 0, "policy_chunks is empty -- run scripts/build_policy_index.py first"

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_policy_index.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    assert result.returncode == 0, result.stderr

    after = _chunk_count()
    assert after == before

    with session_scope() as session:
        section_refs = list(session.execute(select(PolicyChunk.section_ref)).scalars().all())
    assert len(section_refs) == len(set(section_refs)), "duplicate section_ref after re-run"

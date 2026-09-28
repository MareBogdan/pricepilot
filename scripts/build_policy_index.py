r"""Phase 5 session 2 -- index the pricing policy for RAG (ADR-0036).

    uv run python scripts/build_policy_index.py [--dry-run]

Reads `docs/policy/pricing-policy.md`, chunks it BY SECTION (the document's 7 numbered `## N.
Heading` sections -- the natural retrieval unit for a ~500-word policy: a rule and its exceptions
live together, so a chunk boundary never lands mid-rule), embeds heading + section text together
with the shared model (`pricepilot.embeddings.embed`, same model `scripts/build_embeddings.py`
uses for `norm_listings`), and upserts into `policy_chunks` keyed by `section_ref`.

Idempotent: re-running replaces each section's row in place (no duplicates), and deletes any
existing row whose section no longer appears in the current document -- an edited-down policy
never leaves a stale chunk behind for retrieval to still surface.

`--dry-run`: parses the document and computes embeddings (so an encode-time error is still
caught), prints the chunk list, writes nothing. Needs no database connection.

CLAUDE.md section 6, hard rule 1: this script stores POLICY TEXT ONLY. No threshold value from
`config/pricing-policy.toml` is ever written into `policy_chunks`.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select  # noqa: E402

from pricepilot.db import check_database, session_scope  # noqa: E402
from pricepilot.embeddings import MODEL_NAME, embed  # noqa: E402
from pricepilot.models import PolicyChunk  # noqa: E402

POLICY_PATH = ROOT / "docs" / "policy" / "pricing-policy.md"
SOURCE_DOC = "docs/policy/pricing-policy.md"

# A numbered H2 section heading, e.g. "## 1. Minimum margin by category".
_SECTION_PATTERN = re.compile(r"^##\s+(\d+)\.\s+(.+?)\s*$", re.MULTILINE)
_VERSION_PATTERN = re.compile(r"Status:\s*APPROVED\s*(v[\d.]+)")


def parse_doc_version(text: str) -> str:
    match = _VERSION_PATTERN.search(text)
    if match is None:
        raise ValueError(f"could not find 'Status: APPROVED vX.Y' in {POLICY_PATH}")
    return match.group(1)


def parse_sections(text: str) -> list[tuple[str, str, str]]:
    """`[(section_ref, heading, body), ...]` in document order. `body` is the section's own
    prose, trimmed, up to (not including) the next `## N.` heading or end of file."""
    matches = list(_SECTION_PATTERN.finditer(text))
    sections = []
    for i, m in enumerate(matches):
        section_ref, heading = m.group(1), m.group(2)
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end() : end].strip()
        sections.append((section_ref, heading, body))
    return sections


def embedding_text(heading: str, body: str) -> str:
    """Heading + section text together -- the section is the retrieval unit, and the heading
    alone often carries the query-matching keywords a question would use (TASK 3, session brief)."""
    return f"{heading}\n{body}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="parse + embed, don't write")
    args = parser.parse_args(argv)

    raw = POLICY_PATH.read_bytes()
    text = raw.decode("utf-8")
    source_sha256 = hashlib.sha256(raw).hexdigest()
    doc_version = parse_doc_version(text)
    sections = parse_sections(text)
    if not sections:
        print(f"ERROR: no '## N. Heading' sections found in {POLICY_PATH}", file=sys.stderr)
        return 2

    print(
        f"parsed {len(sections)} sections from {SOURCE_DOC} "
        f"(doc_version={doc_version}, source_sha256={source_sha256[:12]}...)"
    )
    for section_ref, heading, body in sections:
        print(f"  [{section_ref}] {heading} ({len(body)} chars)")

    print(f"\nloading model {MODEL_NAME} ...")
    embeddings = embed([embedding_text(h, b) for _, h, b in sections])

    if args.dry_run:
        print(
            f"\n--dry-run: computed {len(embeddings)} embeddings (dim {len(embeddings[0])}), wrote nothing."
        )
        return 0

    if not check_database():
        print("database UNREACHABLE", file=sys.stderr)
        return 2

    current_refs = {s[0] for s in sections}
    with session_scope() as session:
        existing = {
            row.section_ref: row for row in session.execute(select(PolicyChunk)).scalars().all()
        }
        for (section_ref, heading, body), emb in zip(sections, embeddings, strict=True):
            row = existing.get(section_ref)
            if row is None:
                row = PolicyChunk(section_ref=section_ref)
                session.add(row)
            row.heading = heading
            row.text = body
            row.embedding = emb
            row.source_doc = SOURCE_DOC
            row.doc_version = doc_version
            row.source_sha256 = source_sha256

        stale_refs = set(existing) - current_refs
        for ref in stale_refs:
            session.delete(existing[ref])
        session.flush()

    stale_note = f", {len(stale_refs)} stale removed" if stale_refs else ""
    print(f"\nAPPLIED: {len(sections)} chunks upserted{stale_note}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

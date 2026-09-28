"""RAG retrieval over the pricing-policy prose (CLAUDE.md section 6, hard architectural rule 1:
RAG is ONLY for policy text). `retrieve_policy` returns passages -- section_ref, heading, text,
a similarity score -- for the decision engine (session 3) to hand the LLM as context. It never
derives or returns a number: cost, price, margin, stock, competitor prices and every threshold
still come from SQL or `config/pricing-policy.toml`, queried separately.

The query is embedded with `pricepilot.embeddings.embed` -- the SAME model
`scripts/build_policy_index.py` used to build the index. A mismatched model here would still
return a score for every row; it would just be comparing two unrelated vector spaces, a silent bug
rather than a loud one.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from pricepilot.db import session_scope
from pricepilot.embeddings import embed
from pricepilot.models import PolicyChunk


@dataclass(frozen=True, slots=True)
class PolicyPassage:
    section_ref: str
    heading: str
    text: str
    # Cosine similarity (1 - pgvector's `<=>` cosine distance), higher is more relevant. Named
    # `similarity`, not `score`, so it cannot be mistaken downstream for a business number --
    # CLAUDE.md section 6 rule 1: it ranks passages, it is never itself a price/margin/threshold.
    similarity: float


def retrieve_policy(query: str, k: int = 3) -> list[PolicyPassage]:
    """Top-`k` policy passages by cosine similarity to `query`, most relevant first."""
    if k <= 0:
        raise ValueError(f"k must be positive, got {k}")
    [query_embedding] = embed([query])
    with session_scope() as session:
        distance = PolicyChunk.embedding.cosine_distance(query_embedding)
        rows = session.execute(
            select(PolicyChunk, distance.label("distance")).order_by(distance).limit(k)
        ).all()
    return [
        PolicyPassage(
            section_ref=chunk.section_ref,
            heading=chunk.heading,
            text=chunk.text,
            similarity=1.0 - dist,
        )
        for chunk, dist in rows
    ]

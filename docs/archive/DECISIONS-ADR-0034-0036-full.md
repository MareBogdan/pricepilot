# ADR-0034 and ADR-0036 full text (moved out of DECISIONS.md at Phase 5 close, 2026-10-07)

## ADR-0034 — Pricing-policy thresholds as one config; the guard is the final authority

**Context.** Phase 5 session 1: the margin/price guard needs the policy's numbers (margin floors,
speed limits, discount eligibility, charm rounding) without ever parsing
`docs/policy/pricing-policy.md` at runtime (CLAUDE.md section 6, hard rule 2 -- guardrails live in
code, not prompts/prose).
**Decision.** `config/pricing-policy.toml` is the single structured source; `src/pricepilot/policy/
thresholds.py` loads and validates it (Pydantic v2: all six categories present, every floor in
(0,1), all limits positive) via stdlib `tomllib`. `src/pricepilot/policy/guard.py` reads only this
config (never the markdown doc) and exposes one composed entry point, `enforce()`: eligibility ->
margin floor -> speed limit -> charm round -> re-check floor after rounding, returning
APPROVE(price) / REJECT(reason) / FLAG(reason). All money is `Decimal` (ADR-0007). An unknown
category raises (fail closed) instead of ever being approved; a missing 7-day reference price
raises inside `within_speed_limits` and `enforce` turns that into FLAG, never a silent pass. This
guard, not the LLM that will later propose a price (session 3), is the final authority -- the LLM's
proposal is only ever a suggestion `enforce()` can override.
**Alternatives rejected.** Threshold literals inline in the guard code -- one config keeps the
guard, a future admin UI, and tests all reading the same numbers. Enforcing the margin inside the
LLM prompt -- a prompt is a suggestion; CLAUDE.md requires the rule to be code. MAP-brand,
new-product-age, manual-lock and promotion/competitor-hold checks (policy §2-5) are OUT of scope
this session -- the mock store's `Product` model has no fields for them yet (see STATE.md Open
issues); stubbing or faking them was explicitly avoided rather than inventing a number.
**Date.** 2026-09-28

**Correction, same session (`reviewer` catch before push).** The first cut checked eligibility and
the speed limit against the *unrounded* proposal, then rounded last -- charm rounding (which can
move a price by up to ~1 RON) could invalidate a check that had already passed, letting APPROVE
through with a price that violated eligibility or the speed limit (e.g. an unchanged 179.00
proposal on a zero-stock product rounds down to 178.90, an unchecked discount). Fixed (Bogdan's
choice, of 3 named options) by rounding FIRST and running every remaining check -- floor,
eligibility, speed -- against the final price. Also, per Bogdan's choice: a speed-limit breach is
FLAG, not REJECT (matches policy §4's "requires human approval" wording, and covers the case where
rounding itself introduces the breach). Also added: non-positive `cost`/`price` now raises instead
of silently producing a trivially-passing margin. Never pushed in the broken form.

**Addendum, session 1b (2026-09-28).** Architect audit: no mock-store catalogue price is itself a
charm value, so the round-first order (above) turned every genuine "keep the price"
recommendation into a small unintended move (e.g. 179.00 -> 178.90 on zero stock -- an unchecked
discount policy §7 says should never be manufactured: "doing nothing is always acceptable"). Fixed:
`enforce` now short-circuits BEFORE `charm_round` when `proposed_price == current_price` --
APPROVE `current_price` exactly (no rounding), or FLAG if that kept price is already below the
category floor (the core invariant -- never APPROVE below the floor -- holds on this path too). A
real change (`proposed_price != current_price`) is untouched: still round-first-then-check.
**Alternative rejected.** Rounding every proposal uniformly, no-change or not -- manufactures a
move out of every no-op, which is exactly what policy §7 forbids.

## ADR-0036 — RAG over the pricing policy: section chunks, shared model, numbers stay out

**Context.** Phase 5 session 2: the decision engine (session 3) needs relevant policy prose as LLM
context without sending the whole document every call. CLAUDE.md section 6, hard rule 1: RAG is
only for policy TEXT -- every number stays in SQL/`config/pricing-policy.toml`.
**Decision.** `policy_chunks` (migration 0010) co-located with `norm_listings.embedding` in the
same database -- ADR-0014's split is Neon vs. local-test-docker, not two production databases.
Chunked by the document's 7 numbered sections (a rule and its exceptions stay together), embedded
with the SAME model `norm_listings` uses (`paraphrase-multilingual-MiniLM-L12-v2`, 384-dim, local,
free) via a new shared `src/pricepilot/embeddings.py` (used by the two new Phase 5 call sites only
-- `scripts/build_embeddings.py` is untouched). `retrieve_policy()` embeds the query with the same
model and ranks by pgvector cosine distance; returns text only, never a number. No ANN index at ~7
rows. Verified against the real database this session: migration applied (`alembic current`: 0010
head), 7 rows after indexing, still 7 after a second run (idempotent, no dupes). Retrieval eval, 20
pre-registered questions: hit@1 0.850, hit@3 0.950, MRR 0.912 -- one miss not chased further
(editing the question set after seeing a metric is exactly the thing pre-registration exists to
prevent). **Process note:** the eval CSV's commit landed after an exploratory run of the eval
script rather than strictly before it as intended -- content was authored blind and unedited since,
disclosed in that commit's own message rather than silently reordered.
**Also this session:** the psycopg/Application-Control DB block that blocked earlier sessions
proved transient -- `DATABASE_URL` (Neon) connects directly again; the `pg8000` workaround
(ADR-0028) was probed once but not needed for the actual work.
**Alternatives rejected.** Sentence- or fixed-token-window chunking -- breaks rule coherence at
this document's size. A second embedding model for policy text -- a query/index mismatch is a
silent RAG bug; reusing the one model already in the stack avoids it by construction. Storing a
threshold value in `policy_chunks` for convenience -- exactly the "number retrieved by similarity"
bug CLAUDE.md names as what an interviewer looks for.
**Date.** 2026-09-28

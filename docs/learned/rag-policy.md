# RAG over the pricing policy (Phase 5, session 2)

**What it does.** The pricing policy is prose: margin rules, exceptions, rounding conventions. The
decision engine (session 3) needs the relevant paragraphs as LLM context, not the whole document
every call. `scripts/build_policy_index.py` chunks the policy by its 7 numbered sections, embeds
each with `paraphrase-multilingual-MiniLM-L12-v2` (local, free, already used for `norm_listings`),
stores the vectors in `policy_chunks` (pgvector, migration 0010). `retrieve_policy(query, k)`
embeds a query the same way and ranks by cosine distance. **Text only** -- CLAUDE.md's hard rule:
every number a recommendation acts on comes from SQL or `config/pricing-policy.toml`, never here.

**Design choice: chunk by section, not sentence or token window.** A rule and its exceptions belong
together ("discount, unless stock < 3, new, or locked" -- splitting mid-rule returns a fragment that
reads true but isn't the whole condition). ~500 words -> exactly 7 coherent chunks.

**Failure mode.** Embedding the query with a different model than the index -- cosine similarity
still returns a number, just meaningless, comparing unrelated vector spaces. Guarded by both ends
importing the same `pricepilot.embeddings.embed`. Also: an edited policy must actually drop a
removed section's chunk, or a stale rule stays retrievable forever -- covered by the idempotency
test.

**Numbers (20 questions, authored before any query ran -- commit-order note in STATE.md):**

| Metric | Value |
|---|---|
| hit@1 | 17/20 = 0.850 |
| hit@3 | 19/20 = 0.950 |
| MRR | 0.912 |

One miss: "Is undercutting the market a goal?" (section 5, ranked 4th) -- a single-sentence claim
inside a longer, mixed section, genuinely hard at this corpus size. Not chased further: the
question set was fixed first; editing it now would be tuning to the eval. A quality check, not the
Phase 5 gate (the 50-recommendation run, session 4).

# ADR-0039 and ADR-0042 full text (moved out of DECISIONS.md, 2026-10-08)

## ADR-0039 — Served matcher: torch/safetensors on CPU (not ONNX), `product_matches` grain, block-and-score

**Context.** Phase 5 s3b needs our 30 products matched to competitor listings. `models/ce-ft-best.zip`
is HuggingFace format (safetensors + `tokenizer.json`), not ONNX. DB shape (verified 2026-10-04):
`norm_listings.content_hash` is title-only and shared across shops (11,152 hashes in one shop, 18
in two), so shop and price come from `raw_listings`; one shop can list several SKUs under one
normalized title (6 of 11,074 current (shop, hash) pairs), with 1 differing in price.
**Decision.** (1) Serve the fp32 torch weights on CPU: ONNX is a Phase-7 latency concern and the
benchmark's own PyTorch and ONNX scores agree to 1e-5. Faithfulness guarantee: before any scoring,
`check_ce_faithfulness.run` must reproduce the committed `preds-ce-ptfp32-test.json` (tolerance
1e-3 and zero flips at 0.89, pre-registered in code before the first run) -- `match_catalogue.py`
stops otherwise. **First attempt FAILED** (max |diff| 0.187, 1 flip): transformers 5.17's
`AutoTokenizer` joins the pair with `</s></s>`, the model's `tokenizer.json` (used by the Kaggle
runs) with a single `</s>`. Fixed by tokenising with `tokenizer.json` via `tokenizers`; result
max |diff| 1.8e-6, 0 flips, sha256 of the weights matches `model-facts.json`. Scoring is directional
`(our, competitor)`, no symmetrisation (Phase 3 never symmetrised). (2) `product_matches` grain =
one row per (our product, shop), `UNIQUE(product_id, source)`, with the exact shop listing
(`external_id`, `url`, `price_date`) the Decimal price came from; same-day multi-SKU tie ->
in-stock, then cheapest, then lowest id; a price older than 7 days before that shop's newest scrape
is not current; vet-diet exclusions never match. `score` stored rounded DOWN, `threshold` per row,
CHECK `score >= threshold`. Rebuilt by delete + insert in one transaction (idempotent). (3)
Candidates = `norm_listings` with our `brand_blocking_key`; blocks <= 300 scored in full (ADR-0030's
K=100 was for the 10k-vs-10k re-match), blocks > 300 cut to top-100 by embedding cosine.
**Provenance of the numbers above.** The block cut-off (> 300 -> top-100 cosine), torch instead
of ONNX, and the 0.89 threshold all come from the s3b session brief and ADR-0030, fixed before the
matcher ran; they deviate from ADR-0038's wording ("K=100, ONNX") deliberately and are not tuned to
any result. Reviewer-driven hardening: the worksheet is keyed on `product_id:source` (the SERIAL
`id` advances on every delete + insert re-run); the run summary now reports shops whose newest
scrape is > 2 days old, chosen links whose shop SKU has a newer observation under another title,
and block rows with no embedding (always cut by the cosine ORDER BY).
**Result (not a gate verdict).** 28 links, 14 of 30 products with >= 1 link. The `--audit-truncation`
diagnostic found **5 listings >= 0.89 beyond the top-100 cut** in the 13 truncated products (the
cut loses real candidates; scoring whole blocks costs ~12 min, so a decision for the architect).
**Consequence for the ADR-0038 gate:** its coverage criterion (>= 15 of 30 products with a
CORRECT match) is arithmetically unreachable at 14 products with any link. Not edited here; the
gate verdict still waits for Bogdan's blind labels, and changing the criterion needs a new ADR.
**Alternatives rejected.** ONNX export (no benefit before Phase 7); `AutoTokenizer` (wrong
separator under transformers 5.x); K=100 everywhere (needless at <= 300); symmetrising (not how it
was benchmarked).
**Date.** 2026-10-04

## ADR-0042 -- Decision engine: the proposer seam, the trace table, and how session 5 reaches 50

**Context.** Phase 5 s4 builds the per-product engine at $0. The gate (50 recommendations, zero
margin violations) must come from the REAL LLM in s5, so the engine cannot be coupled to a mock,
and the rule "the guard is the final authority" must hold on every code path.
**Decision.** (1) `decision/engine.py`: gather (SQL: `products`, `product_matches`, synthetic
mock-store `price_7d_ago`) -> `retrieve_policy` -> `build_prompt` -> an injected **proposer** ->
strict `parse_reply` -> `guard.enforce` -> trace. The seam is `Proposer.__call__(ProposalRequest)
-> RawReply(text, model, cost, latency)`; `MockProposer` (deterministic, no network, never
touches `llm_calls`, cost asserted 0) is s4's; `LlmProposer` (a wrapper over `client.complete`,
model has no default) is built and fake-tested but NOT instantiated by any s4 script. Prompt
building and parsing are shared, so s5 changes one object. (2) An unparseable reply FLAGs and
the guard is not consulted -- no guessed price. (3) Every limit shown to the model is read from
`config/pricing-policy.toml`; retrieved text is appended last, labelled reference-only, and a
test proves a number planted in it never reaches the facts. (4) Elasticity is a value-less
labelled placeholder (`value: null`): the mock store's planted constants are a generator input,
and feeding them back is the Phase 4 circularity trap. (5) `recommendations` (migration 0013)
stores snapshot, RAG sections, prompt, raw reply, parsed proposal, cost/latency, guard verdict;
`is_mock` separates $0 mock rows from real ones; a CHECK ties `guard_final_price` to APPROVE.
Mock rows (run_label `s4-mock`) are kept as wiring evidence and never count toward the gate.
(6) Drift test: every % / stock minimum / rounding rule in the policy prose equals the TOML.
**How s5 reaches 50 (proposal; default if Bogdan says "go").** The unit is one recommendation per
(product, scenario). **30 baseline** rows -- every catalogue product on its real inputs (13
matched, 17 with no competitor price, which exercises cost+policy-only) -- plus **20 labelled
scenario rows** on matched products: `undercut_15` (every matched competitor price x 0.85) on all
13, then `undercut_30` on the 7 lowest-id matched products. Scenarios are hypothetical
counterfactuals, stored in `recommendations.scenario`, and exist to put price pressure on the
floor; the README must say "30 on real inputs + 20 on labelled hypothetical scenarios". s5 adds
the scenario builder (no migration: the column exists). Estimated cost ~$0.16 for 50 calls
(ESTIMATE: ~1.1k input + ~100 output tokens at $2/$10 per Mtok), inside the ~$2 reserve; s5
prints the estimate and asks `SPEND:` first. **Rejected:** per-(product, collection day) --
competitor prices move rarely, so the rows would be near-duplicates and cache hits; one row per
product only -- 30 < 50 and no stress on the guard.
**Known, not fixed here.** `charm_round` rounds to the NEAREST charm value, so on cheap items it
can flip a proposal's direction (5.20 -> proposed 5.36 -> approved 4.99, a -4% cut). No floor,
eligibility or speed rule is broken, so the gate is unaffected, but the applied move contradicts
the rationale; a guard change (ADR-0034) for the architect.
**Review addendum (same day, `reviewer`).** Fixed before push: (a) a tiny proposal (< 0.50) made
`charm_round` go negative and `enforce` raise, which would have dropped the trace of an already-paid
reply -- `decide` now turns a guard `ValueError` into a FLAG row (no applied price); (b) the parser
is CRLF-safe and requires the exact `PRICE` then `RATIONALE` shape (no preamble, no leading zeros);
(c) scraped competitor titles are flattened to one quote-free line before entering the prompt; (d)
the prompt says so when no 7-day reference exists. Recorded, not fixed: the synthetic
`price_7d_ago` includes mock promo windows and skews the weekly-cap FLAG rate; cache-hit rows are
`is_mock = false` at $0; the rationale is model text, escape it when rendered (Phase 7).
**Date.** 2026-10-07

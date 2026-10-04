# Serving the matcher: what was built and what nearly went wrong

**What it does.** For each of our 30 products, take every competitor listing with the same brand
key, build the same "title + 10 attributes" text the model was trained on, and ask the fine-tuned
cross-encoder for a same-product probability. Keep >= 0.89, then at most one link per
(product, shop), and read the price from `raw_listings` in SQL (never from the model).

**Design choice that mattered.** The model's score only means "0.89" if the input is built exactly
as in training. So the matcher refuses to run until the loaded model reproduces the committed
Phase 3 predictions on 287 pairs. A model that "loads fine" is not proof it is the same model.

**What it caught.** First attempt: max score difference 0.187, one pair flipped across 0.89. Weights
were identical (sha256 match). Cause: the newer `transformers` tokenizer joins the two texts with
`</s></s>`; the model's own `tokenizer.json` uses one `</s>`. Every sequence was one token off. Fix:
tokenize with `tokenizer.json` directly. After: max difference 1.8e-6, 0 flips. Lesson: version
upgrades change preprocessing silently; only a score-against-score check reveals it.

**What would break it.** (1) Domain shift: our titles are clean, competitors' are messy; only the
hand-labelled precision measures that. (2) Blocks > 300 are cut to the top-100 by embedding cosine;
an audit found 5 listings >= 0.89 beyond the cut. (3) A brand with no block (Smolke) gets no match.

**Numbers (2026-10-04).** 28 links, 14 of 30 products covered. Precision: NOT yet measured --
pending blind labels (ADR-0038). Reproduce: `scripts/check_ce_faithfulness.py`,
`scripts/match_catalogue.py`.

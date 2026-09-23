# Phase 3 baseline model choice

Date: 2026-09-21. Question: which pretrained model is the classical baseline, and is zero-shot enough?

## Recommendation

**Baseline = `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`, reported twice: zero-shot and fine-tuned on the 672 distinct TRAIN_VAL pairs.** Headline comparison against the LoRA 0.5B LLM uses the fine-tuned row. Cost: free (local CPU).

**Correction (2026-09-22, architect review):** this doc previously said "fine-tuned on the 697
TRAIN_VAL pairs" — wrong twice over. 697 is the TRAIN_VAL **row** count, and 25 of those rows are
repeats of a pair already shown once under `trivial_spot_check`; the distinct pair count is
**672**. Training on rows double-weights those 25 pairs and, pre-review, would feed three pairs
two contradictory labels (the pair repeated, disagreed on both occurrences). Train on the **672
distinct pairs from `docs/learned/phase3-eval-view.json`** (`scripts/build_eval_view.py`), which
already applies the repeat-resolution rule (first decision in display order); drop `S` for
trainable pairs.

**Correction 2 (2026-09-22, post-review, ADR-0028 addendum #17):** the annotator's review pass
over 12 flagged occurrences moved 1 pair from `S` to `N` (`01b880c1f365_33394df3427d`) — **6 of
672 pairs are `S` (was 7), so 666 trainable pairs (was 665).** Every "665" figure in this doc below
is updated to 666. This is not a starting point yet — Phase 3 item 5 has not started this session.

## Candidates

| | mmarco-mMiniLMv2 (cross-encoder) | bge-reranker-v2-m3 (cross-encoder) | paraphrase-multilingual-MiniLM-L12-v2 (embedding) | multilingual-e5-small (embedding) |
|---|---|---|---|---|
| Params | 0.1B (card rounds; exact UNVERIFIED) | 0.6B | 0.1B (card rounds; exact UNVERIFIED) | UNVERIFIED (12 layers, 384-dim) |
| Licence | Apache 2.0 | Apache 2.0 | Apache 2.0 | UNVERIFIED (not retrievable) |
| Romanian | 15 languages, machine-translated MS MARCO; Romanian listed: UNVERIFIED | "Multilingual"; Romanian not confirmed | "50 languages"; Romanian not explicitly listed | 100 languages claimed |
| Dev PC (CPU) | Yes, ESTIMATE: fine-tuning 666 pairs is minutes | Inference yes; fine-tuning slow, ESTIMATE | Yes | Yes |
| CX22 (2 vCPU / 4 GB) | Yes, ESTIMATE (~0.4 GB fp32 = 0.1B x 4 bytes) | Doubtful: ~2.4 GB fp32 (0.6B x 4 bytes, ESTIMATE) competes with Postgres plus the quantized 0.5B LLM | Yes, ESTIMATE | Yes, ESTIMATE |
| Cost | Free | Free | Free | Free |
| Role | Baseline | Optional zero-shot ceiling | Retrieval (recall@20) | Alternative retrieval |

Latency on CX22: UNVERIFIED for all; Phase 3 must measure it.

Sources:
- https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1
- https://huggingface.co/BAAI/bge-reranker-v2-m3
- https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
- https://huggingface.co/intfloat/multilingual-e5-small (search snippet only: 12 layers, 384 dim)

## Why this pick

- It is small enough to serve on the CX22 next to the LLM, so the later cost/latency table is a fair three-way comparison.
- bge-reranker-v2-m3 is 6x larger; it would beat the LLM on memory, not on merit. Run it zero-shot only if time allows.
- Both rerankers were trained for query-to-passage relevance, not "same SKU?". Expect zero-shot to score "Brit L 12 kg" and "Brit L 3 kg" as near-identical. That is the dominant hard negative, so zero-shot is a weak baseline. This is a hypothesis to test, not a result.

## Zero-shot versus fine-tuned

| Row | Adaptation | Purpose |
|---|---|---|
| Zero-shot | None; threshold chosen on TRAIN_VAL only | Shows what off-the-shelf gets you |
| Fine-tuned | Trained on TRAIN_VAL (672 distinct pairs, 666 after dropping S) | Fair baseline; the LLM also sees TRAIN_VAL |

Zero-shot alone would be a strawman, because the LoRA model is adapted on the same data.

Rules for fairness:
1. Split TRAIN_VAL into train and validation at product level (CLAUDE.md rule 3), deduplicated to
   672 distinct pairs first (same first-occurrence-in-display-order rule as the eval view).
2. Tune the threshold and epochs on validation only.
3. Touch the 287 TEST pairs once per model.
4. **Drop S labels and report the count: 3 in TEST, 6 in TRAIN_VAL** (post-review; was 7 pre-review — `01b880c1f365_33394df3427d` moved S→N — `docs/learned/phase3-eval-view.json`).
5. Report per-error-class results (size variant, breed-size code, life stage, flavour).
6. **Per-tier reportability rule** — precision/recall/F1 is not computable on every tier. A tier
   with fewer than 5 positives reports **false-positive rate (FP / N) with a Wilson 95% CI** and an
   explicit "recall not computable, n_pos = X" note; never print `recall = 0.000` for a tier with
   zero positives. On TEST (`docs/learned/phase3-eval-view.json`, per-tier positives): full
   precision/recall/F1 is meaningful only on `proxy_key_collision` (74 pos) and
   `blocked_retrieval_candidate` (15 pos). Below the 5-positive floor: `same_capacity_diff_breedsize`
   (4 pos) and `capacity_differs_cross_shop` (1 pos) — FP rate + CI, "recall not computable" note.
   `same_capacity_diff_flavour` (0/26), `capacity_differs_within_shop` (0/22) and
   `diff_brand_similar_title` (0/16) have **zero** positives — FP rate + CI only, recall undefined.
7. **Dominance caveat.** 74 of 97 TEST positives (76.3%) sit in `proxy_key_collision`, and 13 of
   those 74 are the duplicated `trivial_spot_check` pairs (near-identical titles, all `M`). Always
   report overall recall **alongside recall excluding those 13** — otherwise the headline number
   reads as harder-won than it is.

## What would change my mind

- If fine-tuning the mMiniLM cross-encoder does not beat zero-shot on validation, switch the headline to bge-reranker-v2-m3 and check the CX22 memory figure by measurement.

## Decision rule for the LoRA comparison (written BEFORE the result exists)

Recorded 2026-09-23, before the Qwen2.5-0.5B-Instruct LoRA run has produced a single number.
The bar is the cross-encoder's TEST F1 of **0.8737** (P 0.8925, R 0.8557, threshold 0.89 chosen
on validation). The LoRA model is scored the same way: epoch and threshold chosen on the 133
validation pairs, then TEST scored once.

- **If the LoRA 0.5B does not beat 0.8737 on TEST, that is the finding.** It is reported as-is in
  the README results table, with error analysis. It is not tuned toward, re-thresholded on TEST,
  or re-run until it wins.
- **Two legitimate follow-ups, and only these:**
  1. A **documented second attempt at Qwen2.5-1.5B**, as a separate, labelled experiment with its
     own ledger entry -- never a silent swap of the base model.
  2. The **item 8 cost/latency comparison** (CPU quantized p50/p95, cost per 1,000 comparisons),
     which may favour the smaller model even at equal or slightly lower F1, per CLAUDE.md §7's
     tie rule.
- **Not a legitimate follow-up: weakening the cross-encoder baseline** -- fewer epochs, a worse
  threshold, dropping the epoch-6 checkpoint, or restricting the comparison to tiers where it does
  worse. The baseline stays exactly as recorded.

### Verdict (recorded 2026-09-23, after the LoRA TEST result)

LoRA Qwen2.5-0.5B (epoch 8, validation-selected threshold 0.86): TEST F1 **0.8796**, P 0.8936
(84/94), R 0.8660 (84/97). Cross-encoder: 0.8737. The point estimate is 0.0059 higher, **but the
confidence intervals overlap on every metric and McNemar's exact test gives 8 vs 9 discordant pairs,
p = 1.0000** (`scripts/compare_models.py`, `docs/learned/phase3-model-comparison.md`). **Verdict: a
tie on F1.** No claim that the fine-tune beat the baseline is made. Under CLAUDE.md §7's tie rule the
item 8 serving benchmark is the result. The cross-encoder baseline was not re-run, retuned or
weakened.


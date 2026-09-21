# Phase 3 baseline model choice

Date: 2026-09-21. Question: which pretrained model is the classical baseline, and is zero-shot enough?

## Recommendation

**Baseline = `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`, reported twice: zero-shot and fine-tuned on the 697 TRAIN_VAL pairs.** Headline comparison against the LoRA 0.5B LLM uses the fine-tuned row. Cost: free (local CPU).

## Candidates

| | mmarco-mMiniLMv2 (cross-encoder) | bge-reranker-v2-m3 (cross-encoder) | paraphrase-multilingual-MiniLM-L12-v2 (embedding) | multilingual-e5-small (embedding) |
|---|---|---|---|---|
| Params | 0.1B (card rounds; exact UNVERIFIED) | 0.6B | 0.1B (card rounds; exact UNVERIFIED) | UNVERIFIED (12 layers, 384-dim) |
| Licence | Apache 2.0 | Apache 2.0 | Apache 2.0 | UNVERIFIED (not retrievable) |
| Romanian | 15 languages, machine-translated MS MARCO; Romanian listed: UNVERIFIED | "Multilingual"; Romanian not confirmed | "50 languages"; Romanian not explicitly listed | 100 languages claimed |
| Dev PC (CPU) | Yes, ESTIMATE: fine-tuning 697 pairs is minutes | Inference yes; fine-tuning slow, ESTIMATE | Yes | Yes |
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
| Fine-tuned | Trained on TRAIN_VAL (697 pairs) | Fair baseline; the LLM also sees TRAIN_VAL |

Zero-shot alone would be a strawman, because the LoRA model is adapted on the same data.

Rules for fairness:
1. Split TRAIN_VAL into train and validation at product level (CLAUDE.md rule 3).
2. Tune the threshold and epochs on validation only.
3. Touch the 287 TEST pairs once per model.
4. Drop S labels from scoring and report the count.
5. Report per-error-class results (size variant, breed-size code, life stage, flavour).

## What would change my mind

- If fine-tuning the mMiniLM cross-encoder does not beat zero-shot on validation, switch the headline to bge-reranker-v2-m3 and check the CX22 memory figure by measurement.

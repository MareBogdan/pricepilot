# docs/learned

One short write-up per component that touches **RAG, embeddings, fine-tuning, model evaluation or
PyTorch** (CLAUDE.md §3). Written *after* the component is finished and verified, under 300 words
each, and aimed at one reader: Bogdan, preparing to defend this work in an interview.

Each file answers four questions:

1. What it does and why it is needed here
2. The one design decision that mattered, and the realistic alternatives
3. What breaks it, and how you would notice
4. The actual numbers measured — with the command that produced them

Expected files, by phase:

| File | Phase |
|---|---|
| `attribute-extraction.md` | 2 — regex-first extraction, LLM fallback, content-hash caching |
| `embeddings-and-retrieval.md` | 3 — candidate generation, recall@20 |
| `annotation-dataset.md` | 3 — what was labelled, why product-level splits |
| `baseline-cross-encoder.md` | 3 — the number fine-tuning has to beat |
| `lora-finetune.md` | 3 — QLoRA setup, training curve, error analysis |
| `cpu-serving-benchmark.md` | 3 — quantized 0.5B on CPU vs hosted API |
| `demand-model.md` | 4 — PyTorch, elasticity, and the real/synthetic split |
| `rag-pricing-policy.md` | 5 — why RAG here and *not* for numbers |

Nothing here yet. Phase 0 contains no ML.

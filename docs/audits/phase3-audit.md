# Phase 3 audit — Matching

Date: 2026-09-25. Auditor: architect session (Opus), independent of the Claude Code sessions that
produced the numbers. Repo state audited: `ec8bf05` (clean tree).

Method: every figure below was **recomputed from the committed prediction, label and serving files
with the auditor's own code**, not read from the reports or re-run through the project's scripts.
Where a recomputation matches the report, the report is confirmed; where the report is correct but
misleading, that is called out separately.

## 1. Verdict

**Phase 3 gate (CLAUDE.md §7): MET**, with two stated deviations, both pre-registered and honestly
reported:

1. "By category" is reported **per hard-case tier** (9 tiers), not per product category. This
   interpretation was recorded before scoring (archived ADR-0028, the per-category reporting rule).
   The in-scope catalogue is food/litter only, so a product-category split would add little.
2. The "quantized fine-tuned model" row does not exist: LoRA int8 had **no eligible configuration**
   (three ORT dynamic-int8 configs, two CPUs). The pre-registered fallback (protocol 5.11) served the
   LoRA as ONNX fp32 CPU instead. A correctly reported negative result, not a gap.

No number was found wrong. Four statements were found **misleading or stale** (section 6).

## 2. Frozen dataset

| Check | Result |
|---|---|
| SHA-256 of `docs/learned/phase3-labels.json`, raw bytes | `27b5de0c…8d52` (CRLF on disk — expected) |
| SHA-256, LF-normalised | `540a4fd6ccfc52525014ac770caadbf544243dccc5a85d3fcb279fd7d052eed4` — **matches** STATE.md, DECISIONS.md, README, `phase3-eval-view.json` |
| TEST scored pairs / positives (from `phase3-eval-view.json`) | 284 / 97 — matches |

## 3. TEST-touch ledger — 7 entries, 0 rescores, every F1 reproduced

Rule: predicted M iff `score >= threshold` (same convention as `score_predictions.py` L123).
Thresholds read from the ledger; both new thresholds (CE int8 0.83, LoRA ONNX 0.71) were selected
by `select_threshold.py` on 133 validation pairs, timestamped seconds **before** their ledger entry.

| model_id | thr | TP | FP | FN | TN | P | R | F1 (recomputed) | ledger F1 |
|---|---|---|---|---|---|---|---|---|---|
| mmarco-mMiniLMv2-zeroshot | 0.86 | 91 | 174 | 6 | 13 | 0.3434 | 0.9381 | 0.5028 | 0.5028 |
| mmarco-mMiniLMv2-finetuned-ep6 | 0.89 | 83 | 10 | 14 | 177 | 0.8925 | 0.8557 | 0.8737 | 0.8737 |
| qwen2.5-0.5b-lora-ep8 | 0.86 | 84 | 10 | 13 | 177 | 0.8936 | 0.8660 | 0.8796 | 0.8796 |
| hosted-claude-sonnet-5-zeroshot | 0.5 | 89 | 10 | 8 | 177 | 0.8990 | 0.9175 | 0.9082 | 0.9082 |
| mmarco-mMiniLMv2-finetuned-ep6-int8 | 0.83 | 84 | 23 | 13 | 164 | 0.7850 | 0.8660 | 0.8235 | 0.8235 |
| qwen2.5-0.5b-lora-ep8-onnxfp32-cpu | 0.71 | 84 | 11 | 13 | 176 | 0.8842 | 0.8660 | 0.8750 | 0.8750 |
| hosted-claude-sonnet-5-zeroshot-v2 | 0.5 | 89 | 11 | 8 | 176 | 0.8900 | 0.9175 | 0.9036 | 0.9036 |

All 7 match to ≤1e-16. No prediction file is missing a TEST pair. Hosted unparseable replies are
stored as 0.0 (counted as N) — conservative for the hosted model, as the protocol states.

**Served CE artefact.** `serving/preds-ce-onnxfp32-test.json` at 0.89 gives TP 83 / FP 10 / FN 14,
F1 0.8737 — the ONNX file that would be deployed scores identically to the ledgered PyTorch model.

McNemar exact (recomputed, two-sided, discordant counts):

| pair | discordant | p |
|---|---|---|
| CE fp32 vs LoRA fp16 (the verdict) | 8 vs 9 | 1.0000 |
| CE fp32 vs CE int8 | 14 vs 2 | 0.0042 |
| LoRA fp16 vs LoRA ONNX fp32 | 2 vs 1 | 1.0000 |
| CE fp32 vs LoRA ONNX fp32 | 7 vs 7 | 1.0000 |
| CE fp32 vs hosted v2 *(post-hoc, auditor's)* | 7 vs 12 | 0.3593 |

The last row is new and post-hoc: the hosted zero-shot model's +0.03 F1 over the served CE is **not
statistically significant** on this TEST set either. It is not a pre-registered comparison and is
not a result; it is context for the serving decision.

## 4. Serving table — every cell reproduced

From `serving/latency-*.json` (287 samples each), `serving/throughput.json` (10 batches × 16),
`serving/model-facts.json`, and `docs/phase3-serving-prices.md` (CX23 €0.0088/h × ECB 1.1411 =
$0.010042/h).

| model | p50 ms | p95 ms | pairs/s | $/1k | peak RSS | K=20 h | K=100 h |
|---|---|---|---|---|---|---|---|
| CE ONNX fp32 | 78.9 | 92.7 | 12.264 | 0.000227 | 963 MB | 4.77 | 23.85 |
| CE ONNX int8 | 54.5 | 65.0 | 18.181 | 0.000153 | 627 MB | 3.22 | 16.09 |
| LoRA ONNX fp32 | 2032.1 | 2242.4 | 0.393 | 0.007104 | 2347 MB | 149.02 | 745.08 |
| hosted v1 | 1258 | 1883 | — | 1.396718 | — | — | — |
| hosted v2 | 1303 | 2361 | — | 1.450098 | — | — | — |

K scorings: 10,532 × 20 = 210,640 and × 100 = 1,053,200. All match the committed table.

Caveats that must travel with these numbers (already partly in the doc):

- Latency is a **Kaggle 2-thread proxy** (AMD EPYC 7B12). The VPS is re-measured in Phase 7.
- Local $/1k is a **marginal cost that assumes the VPS is billed only for the seconds it spends
  scoring**. The VPS is really a fixed monthly cost; the honest reading is "the scoring fits inside a
  server we pay for anyway". The ratio vs hosted is **~6,400× for CE fp32, ~9,500× for CE int8,
  ~200× for LoRA** — never "6,000–9,000×" as one range for "local CPU serving".

## 5. Gate check (CLAUDE.md §7 Phase 3)

| Gate element | Evidence | Status |
|---|---|---|
| Baseline vs fine-tuned on held-out product-level TEST | ledger rows 2–3; split has 0 listing overlap | MET |
| Broken down by category and overall | `phase3-model-comparison.md` per-tier table (9 tiers) | MET (tier = category, recorded before scoring) |
| Three-way serving benchmark: fine-tuned quantized on CPU vs classical baseline vs hosted | `phase3-serving-benchmark.md` | MET with deviation: LoRA int8 non-eligible, fp32 fallback per protocol 5.11 |
| Tie rule applied honestly | verdict "TIE", no "fine-tune beat baseline" claim in the comparison doc | MET — but see 6.2 |

## 6. Findings — correct numbers, misleading or stale text

1. **STATE.md "Where we are": "local CPU serving is roughly 6,000–9,000× cheaper".** True only for
   the cross-encoder. LoRA is ~200×. Must name the model.
2. **README contradicts the tie verdict and the serving result.**
   - "The three things this project is built to demonstrate: … a fine-tune that beats a documented
     baseline" — the result is a tie. The README must state the result, not the ambition.
   - "the matching model is a small fine-tuned LLM running **quantized on CPU** on a **€4/month**
     VPS" — no quantized LLM exists, the served model is the cross-encoder, and the VPS is €5.49/mo
     excl. VAT (CX23).
   - Architecture diagram node "embeddings → fine-tuned 0.5B" — the served model is the CE.
   - Results "Serving" row lists CE int8 first as "Implemented" — int8 is reported, not served.
3. **CLAUDE.md §6 "Model serving (decided): 0.5B quantized on CPU … real time"** and "Deployment
   target: Hetzner CX22" — both contradicted by data/market. §7 Phase 7 also names CX22.
4. **`phase3-serving-benchmark.md`: "No TEST prediction file for any of the three was ever read."**
   V1's `preds-llm-int8-test.json` was read by `check_serving_gates.py` (G2 flips vs fp32 — 95
   flips). That comparison is **label-free**, so it is not a TEST touch; the sentence should say
   "no TEST labels were ever scored against any LLM int8 variant".
5. **`phase3-model-comparison.md` intro: "the TEST-touch ledger still holds exactly three entries."**
   True when written (2026-09-23); now 7. Needs a dated note, not a rewrite.
6. **`docs/COSTS.md` reserve table is stale**: CX22 ~€4/mo; Phase 2 LLM extraction line (Phase 2
   closed at $0, deterministic); Phase 3 pre-labelling line (unused); "GPU at week 5" (resolved:
   Kaggle free tier).

## 7. Open decisions — recommendations

### 7.1 Which model is served — **CE fine-tuned, ONNX fp32, CPU**

| Option | F1 | p50 | RSS | Verdict |
|---|---|---|---|---|
| CE fp32 | 0.8737 | 79 ms | 963 MB | **serve** |
| CE int8 | 0.8235 (p=0.0042 vs fp32) | 54 ms | 627 MB | reject: pays 13 extra false positives for 24 ms nobody waits for |
| LoRA ONNX fp32 | 0.8750 (tie with CE) | 2032 ms | 2347 MB | reject: same accuracy, 26× slower, 2.3 GB on a 4 GB box shared with Postgres + API + Caddy + dashboard |
| hosted zero-shot | 0.9036 (not significant vs CE, p=0.36 post-hoc) | 1303 ms | — | reject for bulk matching: ~6,400× per pair, data leaves the box, eats the budget |

Why: the tie rule says when F1 ties, cost and latency decide — and they decide for the CE. The
interview story is "I fine-tuned a 0.5B LLM, it tied a 118M cross-encoder, so I serve the
cross-encoder", which is stronger than serving the LLM for show. Consequence to accept: **the
fine-tuned LLM is a result, not a production component.**

Serving mode: **incremental batch after each daily collection run** (only new/changed
`content_hash` pairs), not real-time per request — matching is not on any user request path.

### 7.2 K=20 vs K=100 — **K=100, incremental; the one-off full run happens off the VPS**

- Recall evidence: blocked recall 74% → 96% from K=20 to K=100 (archived ADR-0028 #7).
- Cost is only large for a **full** re-match: 23.85 h at K=100 on the 2-thread proxy — that would
  saturate the VPS for a day. But a full re-match is needed only (a) once, at first deployment, and
  (b) when the model changes. Both can run on Kaggle's free CPU with the same ONNX file, and the
  resulting `product_links` are loaded into the DB.
- Daily, only new or re-titled listings are scored: new listings/day × 100. The count of new
  `content_hash` values per day is **not measured yet** — it is measured in the Phase 4 measurement
  session (same tables, zero cost).
- Risk not yet measured: precision at K=100 on real candidates (TEST precision is on curated hard
  pairs, not on ranks 21–100). Mitigation at build time: at most one match per (our product,
  competitor shop), highest score wins; a hand-verified sample of produced links at Phase 7, as in
  ADR-0023.

### 7.3 Hosting — **the ~$15 reserve no longer covers three months; Bogdan decides at Phase 7**

ESTIMATE (CX23 €5.49/mo excl. VAT; Romanian standard VAT 21% applies because the PFA is not
VAT-registered; ECB 1.1411; primary IPv4 cost UNVERIFIED and excluded):
3 × 5.49 × 1.21 × 1.1411 ≈ **$22.7** for three months, **$15.2** for two.
Available: $20.00 − $0.82 = **$19.18**. Phase 5's $5–8 reserve is itself an old guess (50
recommendations at Sonnet 5 prices is plausibly under $2 — re-estimate from real token counts at
Phase 5).

Recommendation: raise the hosting reserve to ~$23 (ESTIMATE), cut the Phase 5 reserve to ~$2
(ESTIMATE), and record the shortfall (~$4–6) as a Phase 7 decision for Bogdan: host 2 months, or
raise "available" by ~$5. CX23 availability ("currently unavailable" on 2026-09-23) is re-checked at
Phase 7. RAM: CE fp32 (963 MB peak) fits a 4 GB box; LoRA would not have.

### 7.4 What leaves CLAUDE.md §7 when Phase 3 closes

Move verbatim to `docs/archive/phases-3.md`: items 1–8, the gate text, and the tie-rule block.
Replace with a one-paragraph CLOSED summary (like Phases 0–2) carrying: the tie verdict, the served
model, the int8 negative result, pointers to the audit and ADR-0030.
Keep live (rewritten, old text archived verbatim): §6 "Model serving (decided)", §6 deployment
target, §7 Phase 7 VPS name. The general principle "decision rules are written before the numbers"
survives as one line in §4, because Phases 4–5 need it.

## 8. What was not audited

- Label quality itself (one annotator; 12% self-disagreement on trivial repeats is already disclosed
  in the README).
- Retrieval recall@20 = 88% (n=50) — accepted as a measurement-power finding in ADR-0028 #8.
- The Kaggle notebooks' code paths beyond what the committed outputs and gate files show.

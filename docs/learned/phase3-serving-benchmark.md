# Phase 3 item 8 — serving benchmark (final)

CLAUDE.md §7's tie rule makes this table the Phase 3 headline: F1 between the two fine-tuned models (cross-encoder, LoRA) is a **parity claim**, not a winner. The hosted row is **zero-shot** and is not a fair accuracy comparison (protocol 5.1c) -- it is a cost/latency data point.

**The two latency runs are on DIFFERENT CPUs, never compared as same-hardware:** the serving run -- cross-encoder fp32/int8 and LoRA ONNX fp32, everything actually SERVED -- used **AMD EPYC 7B12** (no VNNI); the int8-variants run -- LoRA int8 V2/V3, neither served (see below) -- used **Intel(R) Xeon(R) CPU @ 2.20GHz** (no VNNI). Every quoted local latency is a **Kaggle 2-thread proxy**, re-measured on the real Hetzner VPS in Phase 7.

## Headline table

| model | TEST F1 | precision (k) [CI] | recall (k) [CI] | p50 ms | p95 ms | pairs/s (batch 16) | $/1,000 | peak RSS (VmHWM) | artefact | CPU | proxy note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Cross-encoder mMiniLMv2, fine-tuned (ONNX fp32 CPU) | 0.8737 | 0.8925 (93) [0.8133, 0.9405] | 0.8557 (97) [0.7722, 0.9120] | 78.9 | 92.7 | 12.26 | $0.000227 | 963 MB | 449.0 MB | AMD EPYC 7B12 | Kaggle 2-thread proxy (AMD EPYC 7B12, no VNNI); re-measured on the Hetzner VPS in Phase 7. |
| Cross-encoder mMiniLMv2, fine-tuned (ONNX int8 CPU) | 0.8235 | 0.7850 (107) [0.6981, 0.8523] | 0.8660 (97) [0.7841, 0.9200] | 54.5 | 65.0 | 18.18 | $0.000153 | 627 MB | 112.8 MB | AMD EPYC 7B12 | Kaggle 2-thread proxy (AMD EPYC 7B12, no VNNI). Significant F1 drop vs fp32 (McNemar p=0.0042; false positives 10 -> 23) -- reported, not recommended for serving. |
| LoRA Qwen2.5-0.5B, epoch 8 (ONNX fp32 CPU) | 0.8750 | 0.8842 (95) [0.8045, 0.9341] | 0.8660 (97) [0.7841, 0.9200] | 2032.1 | 2242.4 | 0.39 | $0.007104 | 2347 MB | 1885.5 MB | AMD EPYC 7B12 | Kaggle 2-thread proxy (AMD EPYC 7B12, no VNNI); re-measured on the Hetzner VPS in Phase 7. Served as ONNX fp32 -- no int8 variant was eligible (protocol 5.11). |
| LoRA Qwen2.5-0.5B, epoch 8 (fp16 GPU, reference only) | 0.8796 | 0.8936 (94) [0.8151, 0.9412] | 0.8660 (97) [0.7841, 0.9200] | n/a (GPU, different hardware) | n/a | n/a | n/a | n/a | n/a | NVIDIA T4 (Kaggle GPU) | reference only, not served |
| Hosted zero-shot, claude-sonnet-5 (v1, max_tokens=5) | 0.9082 | 0.8990 (99) [0.8240, 0.9442] | 0.9175 (97) [0.8456, 0.9576] | 1258 | 1883 | n/a (API) | $1.396718 | n/a | n/a | Anthropic-hosted | zero-shot, not a fair accuracy comparison (5.1c) |
| Hosted zero-shot, claude-sonnet-5 (v2, max_tokens=64) | 0.9036 | 0.8900 (100) [0.8137, 0.9375] | 0.9175 (97) [0.8456, 0.9576] | 1303 | 2361 | n/a (API) | $1.450098 | n/a | n/a | Anthropic-hosted | zero-shot, not a fair accuracy comparison (5.1c) |

F1 carries no CI of its own (harmonic mean of precision and recall, two different proportions; see the metrics files). `n` for precision/recall is its own denominator (predicted-M count / actual-M count), shown in parentheses.

## LoRA int8 -- no row (protocol 5.11: no eligible configuration)

Three ORT `quantize_dynamic` configurations were tried; none separated the classes on the 133 validation pairs (`median_p_yes_true_M > 0.5 > median_p_yes_true_N` required):

| config | CPU | validation median P(Yes), true M | true N | best validation F1 |
|---|---|---|---|---|
| default (V1, from the serving run) | AMD EPYC 7B12 | 0.235 | 0.251 | 0.514 (= predict-all-positive) |
| v2 (per_channel+reduce_range, int8-variants run) | Intel(R) Xeon(R) CPU @ 2.20GHz | 0.431 | 0.326 | 0.535 |
| v3 (per_channel+reduce_range  + MatMul-only, int8-variants run) | Intel(R) Xeon(R) CPU @ 2.20GHz | 0.322 | 0.213 | 0.599 |

Validation pairs scored: 133. No TEST labels were ever scored against any LLM int8 variant (V1's TEST predictions were read once, label-free, for the G2 flip count). Finding: ORT dynamic int8 (three configurations: default, per_channel+reduce_range, per_channel+reduce_range+MatMul-only) destroys this 0.5B decoder's discrimination on two AVX2-without-VNNI CPUs (AMD EPYC 7B12, Intel Xeon @ 2.20GHz). The 'AMD-specific' hypothesis is refuted (Intel failed too); the 'per-tensor/saturation only' hypothesis is weakened (per-channel + reduce_range did not fix it). Weight-only quantization (e.g. MatMulNBits) was NOT tested -- untested future work, not run here.

## Full-catalogue re-match wall-clock, projected for the Hetzner VPS from the Kaggle proxy (per served local model)

The input the pending K decision (ADR-0028 addendum #7 item 3) was waiting for -- wall-clock only, at the pairs/s measured above (Kaggle 2-thread proxy; re-measure on the real VPS in Phase 7).

| model | K=20 (210,640 scorings) | K=100 (1,053,200 scorings) |
|---|---|---|
| Cross-encoder mMiniLMv2, fine-tuned (ONNX fp32 CPU) | 4.77 h | 23.85 h |
| Cross-encoder mMiniLMv2, fine-tuned (ONNX int8 CPU) | 3.22 h | 16.09 h |
| LoRA Qwen2.5-0.5B, epoch 8 (ONNX fp32 CPU) | 149.02 h | 745.08 h |

## Hosted v1 vs v2 diagnostics

v1 (max_tokens=5): 40/287 unparseable replies (40 empty, all_empty_hit_max_tokens=True, protocol 5.10 item 6). Cost $0.4009 actual.

v2 (max_tokens=64, protocol 5.12): 11/287 unparseable. `stop_reason` counts: {'end_turn': 276, 'max_tokens': 11}. Content block-type counts (per block, not per call -- a call can emit more than one block): {'text': 276, 'thinking': 40}. Cost $0.4162 actual.


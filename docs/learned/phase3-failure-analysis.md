# Phase 3 failure analysis (CLAUDE.md §7 item 7)

Model inspected: **qwen2.5-0.5b-lora-ep8** (TEST F1 0.8796 vs 0.8737 for mmarco-mMiniLMv2-finetuned-ep6). It is inspected only because its point F1 is higher; the difference is not statistically significant (`phase3-model-comparison.md`), so this is not a claim that it is the better model.

Its errors on the 284 scored TEST pairs: **23** (per tier: proxy_key_collision 9, blocked_retrieval_candidate 6, same_capacity_diff_breedsize 4, capacity_differs_within_shop 2, capacity_differs_cross_shop 1, same_capacity_diff_lifestage 1).

## Selection rule (deterministic, scripts/select_failure_cases.py)

1. Errors = scored TEST pairs where the model's prediction (score >= its ledger threshold) differs from the label.
2. Tiers containing errors ordered by error count (descending), ties by the fixed tier order.
3. Within a tier, errors ordered by confidence = |score - threshold| (largest first), ties by pair_id.
4. Round-robin over tiers (top error of each, then second of each, ...) until 10 are chosen.

Cause sentences are hand-written from the displayed data only (`docs/learned/phase3-failure-causes.json`); selection never reads that file.

## Case 1 -- proxy_key_collision -- false negative

- pair_id: `03c89d94a8c8_c919165d92e3`  true label: **M**
- title A: Hrana uscata pentru pisici Royal Canin Fit 2kg
- title B: Royal Canin Fit 32, 2 kg
- differing extracted attributes (A vs B): product_line: 'Fit' vs 'Fit 32'; food_form: 'dry' vs None
- scores: qwen2.5-0.5b-lora-ep8 0.0005 (t=0.86, predicted N); mmarco-mMiniLMv2-finetuned-ep6 0.0045 (t=0.89, predicted N); distance of qwen2.5-0.5b-lora-ep8 from its threshold 0.8595
- plausible cause: The extracted product lines differ ('Fit' vs 'Fit 32') and one side has no food_form; both models scored it near zero, i.e. read 'Fit 32' as a different line even though the label says same unit.

## Case 2 -- blocked_retrieval_candidate -- false negative

- pair_id: `eb7dab4ddee7_a476eecd2a6b`  true label: **M**
- title A: ROYAL CANIN Rottweiller Puppy, hrană uscată câini junior, 12kg
- title B: Royal Canin Golden Retriever Puppy 12 Kg
- differing extracted attributes (A vs B): product_line: 'Rottweiller Puppy' vs 'Golden Retriever Puppy'; food_form: 'dry' vs None
- scores: qwen2.5-0.5b-lora-ep8 0.0026 (t=0.86, predicted N); mmarco-mMiniLMv2-finetuned-ep6 0.0290 (t=0.89, predicted N); distance of qwen2.5-0.5b-lora-ep8 from its threshold 0.8574
- plausible cause: The extracted product lines name different breeds ('Rottweiller Puppy' vs 'Golden Retriever Puppy'); both models scored it near zero, and the label M sits at odds with a different-breed-line reading, so this may be a labelling inconsistency (labels are frozen and were not changed).

## Case 3 -- same_capacity_diff_breedsize -- false negative

- pair_id: `3747121b25de_fad0975e7321`  true label: **M**
- title A: HILL'S SCIENCE PLAN Senior Vitality 7+, M, Pui, hrană uscată câini senior, 14kg
- title B: Hill's SP Canine Adult Healthy Mobility Medium 14 kg
- differing extracted attributes (A vs B): product_line: 'SCIENCE PLAN Senior Vitality 7+, M, Pui' vs 'SP Canine Adult Healthy Mobility Medium'; breed_size_code: 'M' vs 'Medium'; life_stage: 'senior+7' vs 'adult'; food_form: 'dry' vs None; flavour: 'chicken' vs None
- scores: qwen2.5-0.5b-lora-ep8 0.0005 (t=0.86, predicted N); mmarco-mMiniLMv2-finetuned-ep6 0.0023 (t=0.89, predicted N); distance of qwen2.5-0.5b-lora-ep8 from its threshold 0.8595
- plausible cause: life_stage differs (senior+7 vs adult) and the product lines differ ('Senior Vitality' vs 'Healthy Mobility'); both models scored it near zero, and the label M conflicts with the rule the prompt states (a different life-stage means NOT the same unit), so this may be a labelling inconsistency.

## Case 4 -- capacity_differs_within_shop -- false positive

- pair_id: `0e45d9b997f8_153c7e549d19`  true label: **N**
- title A: PURINA Pro Plan Sterilised Maintenance, Ton și Somon, hrană umedă pisici sterilizate, (pate), bax, 85g x 24buc
- title B: PURINA Pro Plan Sterilised Maintenance, Ton și Somon, hrană umedă pisici sterilizate, (pate), 85g
- differing extracted attributes (A vs B): pack_count: 24 vs None
- scores: qwen2.5-0.5b-lora-ep8 0.9993 (t=0.86, predicted M); mmarco-mMiniLMv2-finetuned-ep6 0.9761 (t=0.89, predicted M); distance of qwen2.5-0.5b-lora-ep8 from its threshold 0.1393
- plausible cause: The two titles are identical except for the 'bax ... x 24buc' suffix and only pack_count differs (24 vs missing); both models treated near-identical text as a match, so the pack-count cue was not decisive for either.

## Case 5 -- capacity_differs_cross_shop -- false positive

- pair_id: `39b24e4f4cbf_523714647355`  true label: **N**
- title A: Hrana uscata pentru caini Royal Canin Mini Puppy 8 kg
- title B: ROYAL CANIN Mini Puppy, hrană uscată câini junior, 800g
- differing extracted attributes (A vs B): net_weight_g: 8000 vs 800
- scores: qwen2.5-0.5b-lora-ep8 0.9857 (t=0.86, predicted M); mmarco-mMiniLMv2-finetuned-ep6 0.0001 (t=0.89, predicted N); distance of qwen2.5-0.5b-lora-ep8 from its threshold 0.1257
- plausible cause: net_weight_g differs by a factor of ten (8000 vs 800; '8 kg' vs '800g' in the titles); the cross-encoder scored it 0.0001 but the LoRA model scored it 0.9857, so only the LoRA model missed the weight difference here.

## Case 6 -- same_capacity_diff_lifestage -- false negative

- pair_id: `ea4980f0e293_f64c6c82fd0a`  true label: **M**
- title A: Hill's SP Canine Senior Vitality Large Breed Chicken 14 kg
- title B: Hrana uscata pentru caini Hill's Science Plan Adult Large Breed cu pui 14kg
- differing extracted attributes (A vs B): product_line: 'SP Canine Senior Vitality Large Breed Chicken' vs 'Science Plan Adult Large Breed cu pui'; life_stage: 'senior' vs 'adult'; food_form: None vs 'dry'
- scores: qwen2.5-0.5b-lora-ep8 0.0107 (t=0.86, predicted N); mmarco-mMiniLMv2-finetuned-ep6 0.5416 (t=0.89, predicted N); distance of qwen2.5-0.5b-lora-ep8 from its threshold 0.8493
- plausible cause: life_stage differs (senior vs adult) with otherwise matching Hill's Science Plan Large Breed 14 kg listings; the LoRA model scored 0.0107 and the cross-encoder 0.5416 (below its 0.89 threshold), and the label M conflicts with the stated life-stage rule, as in case 3.

## Case 7 -- proxy_key_collision -- false negative

- pair_id: `5d22a53683e0_bd73470574eb`  true label: **M**
- title A: ROYAL CANIN X-Small Adult 8+, hrană uscată câini senior, 1.5kg
- title B: Hrana uscata pentru caini Royal Canin X-Small Adult 1.5 kg
- differing extracted attributes (A vs B): product_line: 'X-Small Adult 8+' vs 'X-Small Adult'; life_stage: 'adult+8' vs 'adult'
- scores: qwen2.5-0.5b-lora-ep8 0.0026 (t=0.86, predicted N); mmarco-mMiniLMv2-finetuned-ep6 0.8016 (t=0.89, predicted N); distance of qwen2.5-0.5b-lora-ep8 from its threshold 0.8574
- plausible cause: The only differences are the '8+' marker (life_stage adult+8 vs adult) and the product_line text; by the project's life-stage rule ('Adult' vs 'Adult 7+' is a difference) this pair reads as N, so the label M may be a labelling inconsistency; the LoRA model scored 0.0026 and the cross-encoder 0.8016 (below its 0.89 threshold), so both predicted N.

## Case 8 -- blocked_retrieval_candidate -- false negative

- pair_id: `4d44162593c0_4bb1a1e929f3`  true label: **M**
- title A: NATURES PROTECTION Superior Care Hypoallergenic, Somon, hrană uscată fără cereale câini, afecțiuni digestive și dermatologice, 1.5kg
- title B: NATURES PROTECTION Superior Care Hipoallergenic Adult All Breeds Grain Free, Somon, 1.5kg
- differing extracted attributes (A vs B): product_line: 'Superior Care Hypoallergenic, Somon, afecțiuni digestive și dermatologice' vs 'Superior Care Hipoallergenic Adult All Breeds Grain Free, Somon'; life_stage: None vs 'adult'; food_form: 'dry' vs None
- scores: qwen2.5-0.5b-lora-ep8 0.6619 (t=0.86, predicted N); mmarco-mMiniLMv2-finetuned-ep6 0.0372 (t=0.89, predicted N); distance of qwen2.5-0.5b-lora-ep8 from its threshold 0.1981
- plausible cause: life_stage is missing on one side vs 'adult' on the other and the descriptive wording differs (including 'Hypoallergenic' vs 'Hipoallergenic'); the LoRA model scored 0.6619, the closest to its 0.86 threshold of the selected false negatives, and the cross-encoder scored 0.0372.

## Case 9 -- same_capacity_diff_breedsize -- false negative

- pair_id: `cc7f2bf2a4eb_e87a6f89855f`  true label: **M**
- title A: REMI PREMIUM Junior Medium&Large, M-XL, Pui și Curcan, hrană uscată câini junior, 12.5kg
- title B: Hrana uscata pentru caini Remi Premium Dog Junior Medium&Large Pui si Curcan 12.5kg
- differing extracted attributes (A vs B): product_line: 'PREMIUM Junior Medium&Large, M-XL, Pui și Curcan' vs 'Premium Dog Junior Medium&Large Pui si Curcan'; breed_size_code: 'M-XL' vs 'Medium'; breed_size_class: '3-5' vs '3-3'
- scores: qwen2.5-0.5b-lora-ep8 0.0026 (t=0.86, predicted N); mmarco-mMiniLMv2-finetuned-ep6 0.9969 (t=0.89, predicted M); distance of qwen2.5-0.5b-lora-ep8 from its threshold 0.8574
- plausible cause: breed_size_code was extracted differently ('M-XL' vs 'Medium') although both titles say 'Medium&Large'; the LoRA model scored 0.0026 but the cross-encoder scored 0.9969 (correct), so only the LoRA model missed it.

## Case 10 -- capacity_differs_within_shop -- false positive

- pair_id: `c55327a4a4cb_ecc599237076`  true label: **N**
- title A: MONGE Grill Sterilised, Păstrăv, plic hrană umedă fără cereale pisici sterilizate, obezitate, apetit capricios, (în aspic), bax, 85g x 28buc
- title B: MONGE Grill Sterilised, Păstrăv, plic hrană umedă fără cereale pisici sterilizate, obezitate, apetit capricios, (în aspic), 85g
- differing extracted attributes (A vs B): pack_count: 28 vs None
- scores: qwen2.5-0.5b-lora-ep8 0.9989 (t=0.86, predicted M); mmarco-mMiniLMv2-finetuned-ep6 0.9844 (t=0.89, predicted M); distance of qwen2.5-0.5b-lora-ep8 from its threshold 0.1389
- plausible cause: The two titles are identical except for the 'bax ... 85g x 28buc' suffix and only pack_count differs (28 vs missing); both models treated near-identical text as a match, as in case 4.

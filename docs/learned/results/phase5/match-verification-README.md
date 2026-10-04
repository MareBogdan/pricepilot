# Blind verification worksheet (ADR-0038)

File: `match-verification-queue.csv` -- 28 links, one row each, keyed by `link_key` (`product_id:shop`, stable across re-runs). ADR-0038 says verify ALL links
when there are <= 120, so there is no sampled file.

For each row, decide: is the competitor listing the **same purchasable unit** as our product,
under `docs/learned/phase3-annotation-conventions.md` (current revision)? Same brand, product
line, species/life stage, flavour AND net weight / pack quantity. Same line at a different
gramaj is NOT a match. Use the URL if the title is ambiguous.

The sheet deliberately has no score and no label column. Add your own column `label` with
`YES` or `NO` per row, save the result as `match-verification-labels.csv` in this folder, and
commit it. Do not open `match-run.json` or the database table before labelling (the model's
scores are not in the CSV; keep it that way). Precision and the gate are computed in a later
step, only after the labels are committed.

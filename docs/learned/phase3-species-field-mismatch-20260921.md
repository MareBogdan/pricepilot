# `species` field vs. title mismatch — measured 2026-09-21 (ADR-0028 addendum #13, TASK 5)

**Finding, not a fix.** Phase 2 (Normalization) is closed. This is a recorded defect in the
`species` backfill (`scripts/backfill_phase3_signals.py`, `normalize/species.py`), surfaced by the
Phase 3 mechanical rule-consistency pass, measured over the population and reported here —
`normalize/species.py` was not touched this session.

## What was measured

For every row in `norm_listings` (10,532 rows), run the SAME title-keyword test
`check_label_rule_consistency.py`'s class (e) uses (`normalize.species._from_title` — the
"caini/caine/catei/.../dogs?/puppy" vs "pisic\w*/felin\w*/cats?/kitten" regex pair) against the
title text, and compare it to the stored `species` column (which for `petmax_ro`/`animax_ro` rows
comes from a structured per-source signal first, title text only as a fallback — see
`classify_species()`'s own docstring).

Script: `scripts/measure_species_field_mismatch.py` (`uv run python
scripts/measure_species_field_mismatch.py`). Ran against the live database (`psycopg` is reachable
in this environment — checked directly, `check_database()` returned `True` — so this is the full
population, not the frozen-queue fallback the task anticipated for a blocked environment).

## Result

**53 of 10,532 rows (0.50%)** have a title that clearly states one species while the stored
`species` field says the other.

By source: **46 `animax_ro`, 7 `petmax_ro`, 0 `pentruanimale_ro`** — checked directly, not
assumed. The `pentruanimale_ro` zero is structural, not a clean result: that source has no
structured species signal at all (`classify_species()` falls straight to `_from_title()` for it),
so its stored field IS the title-keyword test, and the two can never disagree by construction.
Every real mismatch is therefore a case where a STRUCTURED per-source signal
(`animax_ro`'s `raw_payload["product_type"]`, `petmax_ro`'s URL path segment) disagreed with the
title's own wording — not a random sample of the population, a specific, inspectable list (full
detail in the script's own stdout, reproducible with one command). Illustrative examples:

| Title | Title says | Field says |
|---|---|---|
| `Hrana umeda pentru pisici Schesir Functions Digestive Topper Dovleac si grau 40g` | cat | dog |
| `Acana Cat First Feast, hrana uscata kitten, 1.8kg` | cat | dog |
| `PRO PLAN Hrana uscata pt caini Adult All Breed Performance cu Pui 14kg` | dog | cat |
| `Jucarie pentru caini Flamingo Gorila 15cm` | dog | cat |

One of the 53 (`3f574dad8b6e...`, the Schesir Digestive Topper row above) is the same
occurrence_id `check_label_rule_consistency.py`'s class (e) flagged in the 300-row TEST label
set — the queue-level and population-level measurements agree on this instance, which is the
kind of cross-check that makes both numbers more trustworthy, not a coincidence to explain away.

## Why this is a real defect, not noise

The annotator's own labelling in the flagged TEST case was correct — they read the real title
("pentru pisici") and matched on that, not on the wrong structured field. This is precisely why
class (e) is reported as a data-quality finding and never as an annotator error (STATE.md /
`docs/learned/phase3-annotation-conventions.md` revision 4 note the same discipline for rule 1).

## Not done this session

- No change to `normalize/species.py` or `scripts/backfill_phase3_signals.py`.
- No re-run of `scripts/backfill_phase3_signals.py` against these 53 rows.
- No re-opening of Phase 2's gate — the gate's own accuracy figures (ADR-0027) predate `species`
  entirely (species was added in the Phase 3 finding-4 session, ADR-0028) and are unaffected.

Recorded as an open issue in `STATE.md`, to be picked up (fix the structured-signal precedence
for `petmax_ro`, or extend the title-keyword fallback's checked-collision list the way
`_from_title`'s own docstring already does for "canine"/English loanwords) whenever species
accuracy next matters — likely before or during Phase 3 fine-tuning, since a wrong `species` field
can silently suppress rule 1 on a real cross-species pair the annotator would have caught.

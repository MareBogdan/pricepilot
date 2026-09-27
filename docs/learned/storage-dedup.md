# Storage: raw_payload dedup by hash (ADR-0032)

**What changed.** `raw_listings.raw_payload` held the shop's static per-listing metadata (brand,
`product_type`, ...) and was re-stored in full on every collection day even when nothing in it had
changed -- price/`compare_at_price`/title/`content_hash` are separate columns and are still written
every day regardless. Migration 0009 adds a nullable `raw_payload_sha256` column. Ingest now
computes the canonical-JSON hash of the new payload and compares it to the hash on that listing's
most recent existing row: identical -> store `raw_payload = NULL`, keep the hash; different (or no
previous row) -> store both. No existing row is modified or deleted.

This surfaced a real, separate bug while testing: SQLAlchemy's `JSON` column type persists a Python
`None` as the JSON literal `null`, not SQL `NULL`, unless `none_as_null=True` is set -- every
`IS NULL` check this feature depends on would otherwise silently do nothing. Fixed on the
`raw_payload` column.

**How to read a payload now.** Most days a row's `raw_payload` is `NULL` by design. Use
`pricepilot.scrapers.runner.get_payload(session, source, external_id, on_or_before)`, which
resolves back to the most recent non-NULL payload on or before that date. Three callers that read a
*specific day's* payload were routed through it: `overlap.compute_overlap`,
`build_retrieval_eval_set.build_proxy_key_pairs`, `quarantine_regulated.reason_for`'s caller. Three
others (`normalize.py`, `backfill_phase3_signals.py`, `build_annotation_queue.py`) already pick a
listing's lowest-id row per `content_hash` -- always a listing's first-ever sighting, always full --
so they needed no change; `preview_product_line.py` got an explicit `ORDER BY id` for the same
guarantee, for determinism.

**Numbers** (`scripts/measure_storage_backfill.py`, 2026-09-27): raw_payload is 28.8 MB across
162,018 rows today. A one-off backfill nulling what this rule would already have nulled from day 1
would free an estimated 21.4 MB (126,374 rows) -- **not run this session**; it is a separate,
destructive decision, and a local export should come first. Projected growth with dedup active:
~5.2 MB/collection day (down from ~12.2 MB/day), pushing the Neon Free (0.5 GB) fill estimate from
2026-10-25/11-15 to **~2026-12-03** (ESTIMATE).

**Backfill option, for later:** re-run `scripts/measure_storage_backfill.py` for a fresh estimate,
export `raw_listings` locally, then null the rows it identifies. Not decided or scheduled.

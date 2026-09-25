# CLAUDE.md — archived Phase 0/1/2 text and the First-session bootstrap (context diet, 2026-09-25)

Full, verbatim text of CLAUDE.md section 7's Phase 0, Phase 1 and Phase 2 entries, plus
section 12 (First session), moved out of the live `CLAUDE.md` to keep that file within
its context budget (CLAUDE.md section 11). All three phases are CLOSED; the live file
keeps a 3-line pointer per phase with the gate result. Section 12's "First session"
bootstrap steps are one-time, already executed, and not needed again. Nothing was
edited or shortened — this is the original text, byte-for-byte.

---

### Phase 0 — Foundation
Scaffold the repo, Docker Compose with Postgres + pgvector, initial schema and migration, `.env.example`, ruff + mypy + pre-commit, pytest, `make` targets, `STATE.md`, `docs/` structure, `.claude/agents/`, `.claude/commands/`.

Also build `services/mock-store` — a small FastAPI service standing in for the user's own shop: a seeded product catalogue (SKU, title, brand, category, purchase cost, current price, stock), synthetic price and sales history, `GET /products`, `GET /products/{id}/history`, and `PATCH /products/{id}/price`. Keep it under ~300 lines. It is a fixture, not a feature — no cart, no checkout, no storefront. Its purpose is to give the pipeline a catalogue to price against and a real endpoint for Phase 6 tool calling to target, mirroring how a Shopify or WooCommerce integration would work.

Also produce `docs/AUDIT.md`: your own critical review of this plan. What is underspecified, what is likely to fail, what you would change. Be blunt. The user wants disagreement, not agreement.

**Gate:** `docker compose up` works, `/health` responds, mock-store serves a seeded catalogue and accepts a price update, `make test` passes, `make lint` passes. Zero dollars spent.

### Phase 1 — Collection

**Product scope — pet food and supplies.**

Include: dry and wet food, treats, litter, grooming and hygiene products, accessories, toys. **Exclude anything regulated** — veterinary medicines, antiparasitics, prescription diets, vaccines. Those are pharmaceutical products and carry compliance questions this project does not need. Filter them out at ingest, not later.

Include a listing only if it has a real manufacturer and a stable product identity another shop could also sell. Build a manufacturer allowlist from the data (Royal Canin, Purina, Pro Plan, Acana, Orijen, Hill's, Brit, Taste of the Wild, Advance, Josera, Calibra, Trixie, Bosch, Petkult, Smølke and so on) and record it in `docs/SOURCES.md`.

**Why this category — the matching problem is genuinely hard.**

No global product code appears in the titles, and the same product is written in fundamentally different title grammars across shops. Verified examples of the identical kind of product:

- `animax.ro`: "Hrana uscata pentru caini Orijen Original Dog Adult Mini **4.5 kg**"
- `zoomalia.ro`: "**12 kg** SMØLKE Hrană uscată Medium cu pui pentru câini seniori" — weight first, plus a price-per-kg figure
- `petmax.ro`: "Recompense caini, Calibra Joy Dog Classic Duck Strips **80 g**"
- `pentruanimale.ro`: "BRIT Premium By Nature Adult Large Breed, **L**, Pui, hrană uscată câini" — comma-separated attribute style

The dominant hard negative is the size variant: same brand, same product line, different weight is **not** a match. Models get this wrong constantly, and it will likely be the largest error class in Phase 3. Related traps: pack counts ("3 pipete", "24x85 g"), dosage bands tied to animal weight ("10-25 kg"), and breed-size codes (Mini, Medium, Maxi, L, XS-XL).

**Known structural difference between sources — handle it in the adapter.**
`petmax.ro` lists each size as its own product row. `pentruanimale.ro` groups variants under one product and shows a price range ("38,01 lei - 62,00 lei", "Vezi 5 variante"). The adapter for grouped sources must expand variants into individual listings, which may require fetching the product page. Normalise to one row per purchasable variant before anything downstream sees the data.

**Sources — verified, do not search the web for alternatives.**

1. **`petmax.ro`** — Gomag platform, fully server-rendered. ✅ Verified. Raw HTML contains title, brand, previous price, current price, discount percentage, stock state and review count. Richest data of the set; use as the anchor source.
2. **`pentruanimale.ro`** — server-rendered. ✅ Verified. Note the variant-grouping issue above.
3. **`animax.ro`** — Magento, server-rendered product pages. ✅ Verified via indexed product pages carrying full titles and weights.
4. **`magazindeanimale.ro`**, **`zoopoint.ro`** — carry the same catalogue, different title conventions. ✅ Overlap confirmed.
5. **`zoomalia.ro`**, **`zoomania.ro`**, **`maxi-pet.ro`** — available, audit before implementing.
6. **Affiliate product feeds** (Profitshare, 2Performant) where a shop offers one — structured CSV/XML built for third-party consumption, refreshed daily. Prefer these when available.

**Cross-shop overlap is confirmed, not assumed.** The same product — Orijen Original Dog Adult Mini, 1.8 kg — appears as:
- `animax.ro`: "Hrana uscata pentru caini Orijen Original Dog Adult Mini 1.8 kg"
- `magazindeanimale.ro`: "Hrană uscată câini ORIJEN Original Dog Adult Mini 1,8 kg"
- `zoopoint.ro`: "Orijen Original Dog Adult Mini" — **no weight in the title at all**; size is a separate variant
- `petmax.ro`: names the line "Orijen Adult Original" — **word order reversed** inside the brand line

Decimal comma versus point, diacritics present or absent, brand casing, weight in title versus weight as variant, and reordered line names. Shops also expose internal SKUs (`ORJ_D_OD_AMI_2`) that are useless across shops. Seed the annotation tool with pairs drawn from exactly these four shops.

*Do not use:* **`shop4pet.ro`** — disallows automated access in `robots.txt`. ❌ Confirmed. Also avoid eMAG and other large marketplaces.

**Before implementing any source,** fetch one page with `curl`, confirm titles and prices are in the raw response rather than injected by JS, read `robots.txt`, note the crawl-delay, and record all of it in `docs/SOURCES.md`. If prices are absent from the raw response, drop the source rather than reaching for a headless browser.

Implement adapters behind a common `Scraper` protocol. Save fixtures. Schedule runs. Log every run and detect volume drops. Validate with Pydantic at the boundary.

**Build order — one scraper first, on a schedule, before the others exist.**

Do not build three adapters and then schedule them. Build **`petmax.ro` only**, put it on a daily
schedule, and let it accumulate history while the other two adapters are written. History is
wall-clock: a day not collected is a day that cannot be recovered later, and Phase 4 is the phase
that pays for it. The other sources join the schedule as each one is finished. The cost of this
ordering is nothing; the cost of the alternative is weeks.

**Cross-shop overlap is a gate condition, not an assumption.**

Phase 3 is a matching problem. If the same product does not appear on two shops, there is no
positive class, and every downstream phase is unfounded. This must be measured while there is still
time to react — in Phase 1, not in week 6.

Measure it with a **cheap proxy key**, no matching model involved, just SQL: normalise
`(brand, product-line tokens, net weight in grams)` and count keys that collide across two or more
sources. The proxy will be wrong in both directions — it will miss real matches the model would
find, and it will join a few products that are not the same. That is acceptable: it is a floor
estimate used to make one decision, and a floor is exactly what is needed here. Do not build a
matching model to compute it.

If the count cannot reach **400**, **add a source before leaving Phase 1** — not later. That is the
whole point of measuring it now. (2026-09-13, ADR-0023: the proxy key's own recall measured at
~8% — too low to decide this on its own. The gate decision is now made from a hand-verified random
sample instead; the proxy key stays a daily floor indicator, not the gate measurement. Threshold
unchanged.)

`make status` reports the overlap count from day one, alongside listings per source, so the number
is visible as it grows rather than discovered at the gate.

**Gate:**
- ≥3,000 in-scope listings from ≥3 sources, at least one of them non-Shopify
- ≥7 consecutive days of history
- **≥400 products appearing on two or more shops** — the threshold, unchanged. Measured by the
  proxy key above only as a first pass; the proxy key's own recall runs low enough (~8%, ADR-0023)
  that it cannot decide this alone. The gate itself is met by a hand-verified random sample of
  listings (method and evidence in DECISIONS.md ADR-0023), reported alongside the proxy key's own
  count — which `make status` prints every day as a floor indicator, explicitly labelled as such,
  never as the gate itself.
- all adapters tested offline against fixtures
- `docs/SOURCES.md` complete

> Start collection as early as possible and let it run in the background. Phase 4 needs price history, and history cannot be backfilled.

### Phase 2 — Normalization

Extract only what is in the title or description: brand and product line, net weight or volume with unit, pack count, breed-size code (Mini, Medium, Maxi, XS-XL, L), life stage (Puppy, Junior, Adult, Senior), flavour or protein source, food form (dry, wet, tin, pouch), and dosage band where present.

Regex and lookup tables first — weights, pack counts and dosage bands are trivially matched and running an LLM over them is wasted money. LLM fallback only for the rest, cached by content hash.

**Unit normalisation is not optional here.** "4.5 kg", "4,5 kg", "4500 g" and "12 kg" as a leading token must all resolve to a comparable numeric field. Get this right and a large share of the matching problem becomes tractable; get it wrong and the fine-tuned model spends its capacity compensating.

Also handle: Romanian descriptive prefixes the shop adds ("Hrana uscata pentru caini...", "Recompense caini, ..."), diacritic inconsistency, brand names with special characters (Smølke, Hill's), and price-per-unit figures that some shops append to the title area.

**Gate:** ≥85% attribute accuracy on 100 manually verified listings, with weight parsing measured separately; the cache demonstrably prevents repeat calls on unchanged titles.


## 12. First session

1. Read this file fully
2. Write `docs/AUDIT.md` — your critical review of this plan. At least five specific concerns and what you would do differently. Be blunt; the user wants disagreement, not agreement.
3. Build Phase 0 end to end, autonomously. Do not ask for approval on scaffolding.
4. Report: what exists now, what the audit flagged, and the decisions you need from the user before Phase 1.

Matching hard cases worth seeding the Phase 3 annotation tool with, so the dataset is not all easy pairs: the same food in different net weights, the same line in different breed sizes, the same product as tin versus pouch versus dry, pack-count differences, life-stage variants, flavour variants within one line, and the same product written by two shops in different title grammars (weight-first versus weight-last, comma-separated attributes versus prose).

(The paragraph that originally followed here, "For Phase 5, the pricing policy document should cover...", was moved verbatim into the live CLAUDE.md's Phase 5 — Decision engine section rather than archived, since it is a still-active instruction, not closed-phase history.)
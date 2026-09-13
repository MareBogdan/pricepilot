# Fixtures — animax.ro

Offline fixtures for the `animax_ro` adapter. **Tests never touch the live site**
(CLAUDE.md §5.1, §9). Everything the parser is tested against lives here.

## Files

| File | Provenance |
|---|---|
| `robots.txt` | `https://www.animax.ro/robots.txt`, fetched 2026-09-13. Verbatim — it is a policy document and trimming it would misrepresent it. It is a modern Shopify robots.txt that invites AI shopping agents to use a UCP/MCP endpoint for cart/checkout; irrelevant here — we only read public catalogue JSON, never touch cart/checkout. |
| `category_hrana-uscata-caini_p1.json` | Trimmed from `https://animax.ro/collections/hrana-uscata-caini/products.json?limit=250&page=1`, fetched 2026-09-13 with `curl -sL --compressed` and the `SCRAPER_USER_AGENT` from `.env`. |

## Platform: Shopify, not Magento

`docs/SOURCES.md`'s original plan-stage guess was Magento. The live `robots.txt` opens with
`# Shopify storefront.` and the sitemap (`sitemap_products_N.xml`, `sitemap_collections_1.xml`) is
Shopify's standard shape. Corrected in `docs/SOURCES.md`; see DECISIONS.md for the ADR.

## Why `products.json`, not scraped HTML

Every Shopify storefront exposes `/collections/<handle>/products.json` — a standard, public,
unauthenticated part of the storefront (not a private or reverse-engineered API; it's what
Shopify's own themes fetch for infinite-scroll and quick-view). It returns exactly the fields the
adapter needs (`vendor`, `variants[].price`, `.compare_at_price`, `.grams`, `.available`, `.sku`,
`.id`) as structured JSON, with no HTML chrome to parse or trim. The live collection page's raw
HTML runs ~8.7 MB per request (facet widgets and quick-add data duplicated inline); the JSON
endpoint for the same 250 products is ~150 KB. Lighter for us, lighter for the shop.

## How the category fixture was trimmed

`docs/LEGAL.md` requires fixtures to be "minimal and trimmed". The live category has 507 products
across 3 requests (`limit=250` × 2 full pages + a 7-product tail); the fixture keeps 7,
hand-selected for what they exercise. Removed from every product: `body_html` (marketing copy,
not used), `images`, `created_at`/`updated_at`/`published_at`, and the internal marketing `tags`
array (irrelevant to parsing, and mostly promo/warehouse bookkeeping strings).

## Why these seven products

| product id | Title | What it exercises |
|---|---|---|
| 7886304837852 | Hrana uscata pentru caini Royal Canin Mini Adult 8 kg | Baseline: ASCII title, no diacritics, ordinary weight, `available: false` (out-of-stock mapping) |
| 7886387937500 | Hrana uscata pentru caini Orijen Junior Talie Mare **11.4 kg** | Decimal **point** in the title |
| 15927073341813 | ORIJEN Regional Red, **11,4 kg** | Same line, same weight, decimal **comma** — within the *same shop*, not just cross-shop |
| 7887512830172 | PURINA® PRO PLAN® SENSITIVE SKIN Adult, bogat în somon, ..., hrană uscată pentru câini, 3kg | Full Romanian diacritics (ă, â, î) — contrast against every ASCII-only title in this fixture |
| 15927071244661 | PEDIGREE ... Adult Talie Medie/Mare, cu Vita/Legume | **No digit anywhere in the title.** Net weight (`grams: 3000`) exists only in the structured field, not in visible text — unkeyable by the current title-only overlap key, and correctly so |
| 7887270805724 | Hrana uscata pentru caini Royal Canin Adult **8+** Mini 2 kg | Age-band code ("8+") that looks like a bonus-pack "+" but isn't one. Also: `grams: 500` while the title says **2 kg** — animax's own structured weight field disagrees with its own title text (merchant data-entry error, not our bug). `compare_at_price` equals `price` exactly — must resolve to *no* discount, same rule as petmax's `compare_at` guard |
| 8700604252498 | Hrana uscata pentru caini Brit Premium Senior **L+XL** Pui 15kg | Breed-size-band code ("L+XL"), genuine discount (`compare_at_price` above `price`) |

The Royal Canin 8+ Mini row is the one that matters most: `grams` cannot be trusted as ground
truth here, which is exactly why the overlap key (untouched this session) parses weight from the
title text rather than from a shop-supplied structured field.

## What was checked and found absent: grouped variants

Unlike pentruanimale.ro (VTEX, one product groups several SKU sizes), animax.ro lists each
purchasable pack size as its own separate Shopify product — the same convention as petmax.ro.
Checked empirically across 750+ products in three categories (`hrana-uscata-caini`,
`jucarii-caini`, plus the two pages behind this fixture): zero products had more than one
variant. The adapter still iterates `product["variants"]` generically rather than assuming
exactly one, in case a future catalogue addition breaks this pattern.

## Refreshing

Re-fetch only when the shop's structure changes and the parser breaks. `products.json` is much
cheaper than an HTML re-fetch — still one request, never in a loop. Record the new date above and
note what changed in `docs/SOURCES.md`.

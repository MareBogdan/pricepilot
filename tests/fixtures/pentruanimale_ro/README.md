# Fixtures — pentruanimale.ro

Offline fixtures for the `pentruanimale_ro` adapter. **Tests never touch the live site**
(CLAUDE.md §5.1, §9). Everything the parser is tested against lives here.

## Files

| File | Provenance |
|---|---|
| `robots.txt` | `https://www.pentruanimale.ro/robots.txt`, fetched 2026-09-13. Verbatim — it is a policy document and trimming it would misrepresent it. |
| `category_caini_hrana-uscata_p1.html` | Trimmed from `https://www.pentruanimale.ro/caini/hrana-caini/hrana-uscata`, fetched 2026-09-13 with `curl -sL --compressed` and the `SCRAPER_USER_AGENT` from `.env`. |

## The site is VTEX, not Gomag — different parsing target entirely

Unlike petmax.ro (Gomag, prices in a `data-Gomag` attribute on each product card),
pentruanimale.ro is built on **VTEX**. The visible product grid is client-rendered, but the page
also carries a `<template data-type="json" data-varname="__STATE__"><script>{...}</script></template>`
block — VTEX's server-rendered Apollo GraphQL cache, present in the raw HTTP response with no JS
execution required (confirmed: `curl` alone returns it). This is what the parser reads instead of
CSS-selecting product cards.

**Why this matters for the grouped-variant problem CLAUDE.md §7 names.** The `__STATE__` blob
already contains every purchasable variant (SKU) of every product on the page — full name (which
embeds the weight, e.g. `"..., 8kg"`), EAN, and a per-SKU price (`Price`/`ListPrice` on the SKU's
`commertialOffer`) — **without fetching the product page**. Expanding one grouped product into one
row per variant is a pure JSON-walk over data already in hand, not an extra network round trip.
This is better than `docs/SOURCES.md`'s original guess ("likely via the product page").

## How the fixture was built

The live page is ~3.2 MB of HTML (mostly site chrome, images, specs and a huge inline
`description` field of unrelated boilerplate — not personal data, just page bloat) carrying 12
products. Rather than trim visible markup (there is nothing to select — the grid renders
client-side), the fixture keeps **only the `__STATE__` JSON**, and only the fields the parser
reads, extracted as the transitive closure of three real products:

| Product key | Name | Why kept |
|---|---|---|
| `Product:sp-45-none` | ROYAL CANIN Mini Adult, hrană uscată câini | **3 variants** (8kg / 2kg / 4kg) — the baseline grouped-product expansion case |
| `Product:sp-459-none` | EXTRU-CAN Standard Hipocaloric, XS-XL, Pui, hrană uscată câini, obezitate, 10kg | **1 variant** — confirms an ungrouped product still produces exactly one row, and `Price == ListPrice` (no discount), exercising the "no compare-at price unless list > price" rule |
| `Product:sp-48-none` | ADVANCE Adult Maxi, L-XL, Pui, hrană uscată câini, 14kg | **2 variants, real bonus-weight trap**: `"...GRATUIT, 14kg + 3kg"` (itemId 13291) vs plain `"...14kg"` (itemId 60) — same "14kg" numeral in both names, genuinely different purchasable items at different prices. The same trap class petmax's fixture seeds (CLAUDE.md §7), found here in real data rather than needing to be constructed |

Removed for every kept node: `specificationGroups`, `skuSpecifications`, `productClusters`,
`properties`, `images`, `description`, and the product-level `priceRange` aggregate (the parser
reads each SKU's own `commertialOffer`, not the product-level range) — none of it is read by the
parser, and all of it is bulk, not personal data. Verified before trimming: no reviewer names or
review text are embedded in `__STATE__` on this page (review widgets load separately, client-side).

The root `productSearch` node's `products` list and `recordsFiltered` are edited to name only
these three (`recordsFiltered: 3`) so the trimmed state stays internally consistent — an honest
reflection of what the fixture actually contains, not a claim that this was ever a real 3-product
page.

## Pagination

`?page=N`, **one-based** — the bare category URL is page 1. Confirmed by fetching `?page=2`: the
embedded query's `"from"`/`"to"` range shifted from `0-11` to `12-23`, `recordsFiltered` stayed
`966` (the real total for this category), 12 products per page. The adapter stops when a page's
`products` list comes back empty, mirroring how the petmax adapter trusts `<link rel="next">`
rather than guessing a fixed page count.

## Category volume and request-count recon (2026-09-13)

One request per category (bare URL, page 1), reading `recordsFiltered` and each product's variant
count directly from `__STATE__` — no extra crawling needed to estimate volume, same approach as
ADR-0017's petmax recon:

| Category | Products | Pages (12/page) | Avg variants/product | Est. listings |
|---|---:|---:|---:|---:|
| `caini/hrana-caini/hrana-uscata` | 966 | 81 | 1.92 | 1,851 |
| `caini/hrana-caini/hrana-umeda` | 526 | 44 | 1.67 | 876 |
| `caini/hrana-caini/recompense---snacks` | 754 | 63 | 1.00 | 754 |
| `pisici/hrana-pisici/hrana-uscata` | 491 | 41 | 2.83 | 1,391 |
| `pisici/hrana-pisici/hrana-umeda` | 836 | 70 | 1.75 | 1,463 |
| `pisici/hrana-pisici/recompense---snacks` | 258 | 22 | 1.00 | 258 |
| **Total** | **3,831** | **321** | — | **~6,593** |

**Estimated one full daily run:** 321 page requests. Measured one real fetch at 2.76s (network +
server); `SCRAPER_MIN/MAX_DELAY_SECONDS` (2–4s) sometimes overlaps with that fetch time rather than
adding to it (the client only sleeps the remainder of the target delay after the previous request
completes) — so wall-clock is bounded between the delay-only floor (321 × ~3s ≈ 16 min) and the
delay-plus-fetch ceiling (321 × ~5.5s ≈ 30 min). **~16–30 minutes**, comfortably inside the
~45-minute per-source budget CLAUDE.md §7 sets for staying a polite guest on a small shop.

**Category scope chosen: the same 6 as petmax's original set** — dry food, wet food, treats, dogs
and cats — not petmax's later-expanded 13. Cross-shop overlap (this session's actual goal) lives in
food and treats; petmax alone already cleared the 3,000-listing volume gate, so there is no
pressure to widen pentruanimale's scope for volume. Litter/accessories/toys can be added later if
the overlap number needs it.

## Regulated products

`caini/hrana-caini/diete-veterinare`, `pisici/hrana-pisici/diete-veterinare` (prescription diets)
and `caini/antiparazitare/*` (antiparasitics) are separate categories from the six scraped, so the
category allowlist is the first line of defence, same as petmax. The adapter also runs a
title/name regulated-token check per SKU as a second line of defence, for a product mis-filed into
a food category.

## Refreshing

Re-fetch only when the shop's markup or GraphQL shape changes and the parser breaks. One request,
never in a loop. Record the new date here and note what changed in `docs/SOURCES.md`.

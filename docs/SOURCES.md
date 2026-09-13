# SOURCES

One entry per competitor shop. **No adapter is written until its row here is filled in**
(CLAUDE.md §7 Phase 1): fetch one page with `curl`, confirm titles and prices are present in the
raw response rather than injected by JS, read `robots.txt`, note the crawl-delay.

> **Status: `petmax.ro` verified 2026-09-12; `pentruanimale.ro` verified 2026-09-12; `animax.ro`
> verified 2026-09-13.** Their rows below and the detailed sections that follow are measurements,
> not restatements of CLAUDE.md. Every other row is still unverified, and the columns marked
> *unverified* are not claims.
>
> Per DECISIONS.md ADR-0010, `petmax.ro` goes on a daily schedule before the next adapter is
> written, because price history is wall-clock and cannot be backfilled.

## Sources

| Shop | Platform | Server-rendered | robots.txt checked | Crawl-delay | Structural note | Status |
|---|---|---|---|---|---|---|
| petmax.ro | Gomag | **yes, verified** | **yes, 2026-09-12** | **none declared for `*`** | Prices in a `data-Gomag` JSON attribute: current *and* pre-discount. One row per size, no variant grouping. Pagination `?p=N`. **Anchor source.** | **implemented, on daily schedule** |
| pentruanimale.ro | **VTEX** | **yes, verified** | **yes, 2026-09-12** | **none declared for `*`** | Prices in a `<template data-varname="__STATE__">` JSON blob (VTEX's server-rendered Apollo cache) — current *and* list price, per SKU. **Groups variants** under one product; expansion needs no extra request, every SKU's price is already in the same blob. Pagination `?page=N`, one-based. | **implemented, on daily schedule** |
| animax.ro | **Shopify** (plan-stage guess of "Magento" was wrong — see recon below) | **yes, verified** | **yes, 2026-09-13** | **none declared for `*`** | Standard Shopify `/collections/<handle>/products.json` — structured JSON, not scraped HTML. One purchasable pack size per product (no variant grouping), same convention as petmax. | **implemented, offline-tested** |
| magazindeanimale.ro | unknown | unverified | unverified | unverified | Same catalogue as zoopoint, different title conventions; diacritics present. | not started |
| zoopoint.ro | unknown | unverified | unverified | unverified | **No weight in title** — size is a separate variant. | not started |
| zoomalia.ro | unknown | unverified | unverified | unverified | Weight-first title grammar, appends price-per-kg. Audit before implementing. | candidate |
| zoomania.ro | unknown | unverified | unverified | unverified | Audit before implementing. | candidate |
| maxi-pet.ro | unknown | unverified | unverified | unverified | Audit before implementing. | candidate |
| Profitshare / 2Performant feeds | affiliate feed | n/a | n/a | n/a | Structured CSV/XML built for third-party consumption, refreshed daily. **Prefer where available.** | candidate |

## petmax.ro — verified recon (2026-09-12)

Fetched with `curl -sL --compressed` and the `SCRAPER_USER_AGENT` from `.env`. Four requests
total — `robots.txt`, `sitemap.xml`, `sitemap_categories.xml`, one category page — spaced by hand.

### Server-rendered? Yes

`https://www.petmax.ro/hrana-uscata-caini` returned HTTP 200, 86 KB gzipped / 619 KB decompressed,
`text/html`. **24 product cards, all with title, brand and both prices in the raw response.** No
JS execution needed, so no Playwright (CLAUDE.md §5.5).

### Canonical host

The apex `petmax.ro` 301-redirects to `www.petmax.ro`. Use the `www` host; `robots.txt` on the
apex returns the redirect page, not the policy.

### robots.txt

Verbatim copy at `tests/fixtures/petmax_ro/robots.txt`.

- **`User-agent: *` declares no `Crawl-delay`.** Named bots get 5 s (`bingbot`, `ClaudeBot`,
  `Pinterest`, `DataForSeoBot`, `Bytespider`), 10 s (`AhrefsBot`, `Amazonbot`, `Applebot`,
  `FacebookBot`, `dotbot`, `meta-externalagent`) or 20 s (`MJ12bot`).
- `PricePilotBot` matches `*`, so nothing is imposed on us. **We use 2–4 s anyway** (CLAUDE.md
  §5.4), and the adapter honours a declared `Crawl-delay` automatically if one ever appears — the
  effective delay is `max(configured floor, declared delay)`.
- `PetalBot` and `BlexBot` are `Disallow: /` — not us.
- Relevant disallows we must not touch: **`/ajax/loadProducts*`** (the AJAX pagination endpoint)
  and **`/*?c=*`**. The adapter paginates with `?p=N` only and calls no AJAX endpoint.
- Facet links in the page carry `?_crawl=0`. The adapter ignores facet links entirely.

### Sitemaps

`sitemap.xml` is an index: `sitemap_blog`, `sitemap_categories`, `sitemap_images`,
`sitemap_pages`, **`sitemap_products`**. `sitemap_categories.xml` lists **134 categories**, which
is where the in-scope allowlist below comes from. `sitemap_products.xml` is the polite way to
enumerate the catalogue and is the fallback if category pagination ever breaks.

### What the markup gives us

Each card is `div.product-box` carrying:

| Field | Where | Note |
|---|---|---|
| shop product id | `data-product-id` | Also embedded in class names (`_productUrl_233`). Stable within the shop, useless across shops |
| **current price** | `data-Gomag` → `Lei_final_price` | Decimal **point**, machine-readable |
| **pre-discount price** | `data-Gomag` → `Lei_price` | Drives `compare_at_price`, and therefore Phase 4 promotion detection |
| discount badge | `span.icon.discount` | e.g. `-20%` |
| title | `a.title` | |
| brand | `a.brand` | A real brand field, not inferred from the title |
| url | `a.title[href]` | Absolute |
| stock | `span.stock-status.available` | |
| review count | `span.-g-listing-review-count` | |
| display prices | `s.price-full` and `span.text-main` | Romanian decimal comma — parsed as a **cross-check** only |

**Why this is the anchor source.** It is the only verified source that hands over the
pre-discount price cleanly. Phase 4 needs promotion timing, and promotion timing is exactly what
`compare_at_price` is. The adapter reads the JSON attribute and rejects any card whose displayed
price disagrees with it by more than 1 leu, rather than ingesting a number it cannot corroborate —
a silent price error poisons a series that cannot be rebuilt.

**Not collected:** the JSON-LD `review` array. It carries customer names, and `docs/LEGAL.md`
commits to collecting no personal data. The trimmed fixture has it stripped too.

### Pagination

`?p=N`, **zero-based** — page 0 is the bare category URL. `<link rel="next">` advertises the next
page, and the adapter follows that rather than guessing a page count, so a crawl stops exactly
when the catalogue ends. `hrana-uscata-caini` showed `?p=37` as its last page: **38 pages × 24
= ~900 listings in one category.**

### In-scope categories on the daily schedule

CLAUDE.md §7 requires regulated products to be filtered **at ingest**. petmax keeps its pharmacy
tree in separate categories, so the first line of defence is a category allowlist:

```
hrana-uscata-caini          hrana-uscata-pisici
hrana-umeda-caini           hrana-umeda-pisici
recompense-delicioase-caini recompense-delicioase-pisici
```

Six categories — food and treats for dogs and cats. This is where cross-shop overlap lives (the
400-product gate).

**STEP 5 (session note 2026-09-12) — expanded to 13 categories.** Six categories alone cannot
reach the ≥3,000-in-scope-listings gate from petmax by itself (petmax is currently the only
adapter that exists; the gate needs ≥3 sources overall, but petmax's own volume is the down
payment while the next two adapters are written — ADR-0010). The smallest in-scope addition that
reliably clears it, per CLAUDE.md §7's product-scope list (litter, grooming/hygiene, accessories,
toys), fetched from petmax's own sitemap of 134 categories (`sitemap_categories.xml`) rather than
guessed:

```
asternut-litiera-nisip-silicat    litter
igiena-si-ingrijire-caini         grooming/hygiene, dogs
igiena-si-ingrijire-pisici        grooming/hygiene, cats
accesorii-caini                   accessories, dogs
accesorii-pisici                  accessories, cats
jucarii-caini                     toys, dogs
jucarii-pisici                    toys, cats
```

Broad umbrella categories were chosen over petmax's many narrower ones (`hamuri-lese-si-zgarzi`,
`castroane-boluri-apa-mancare-*`, `custi-transport-*`, `paturi-perne-si-cosuri-pentru-*`, …)
deliberately: those look like they cross-list the same products Gomag also files under
`accesorii-*`, and scraping both would burn request budget re-fetching listings already collected
rather than growing distinct volume. Regulated products mis-filed into any of these are still
caught by the `REGULATED_TITLE_TOKENS` second line of defence in the adapter regardless of which
category found them.

**Recon (2026-09-12), one page per category, read from the pagination widget's own last-page
link — no extra crawling needed to estimate volume:**

| Category | Pages | Est. listings |
|---|---:|---:|
| hrana-uscata-caini | 38 | 912 |
| hrana-uscata-pisici | 19 | 456 |
| hrana-umeda-caini | 14 | 336 |
| hrana-umeda-pisici | 15 | 360 |
| recompense-delicioase-caini | 16 | 384 |
| recompense-delicioase-pisici | 3 | 72 |
| accesorii-caini | 36 | 864 |
| accesorii-pisici | 14 | 336 |
| igiena-si-ingrijire-caini | 17 | 408 |
| igiena-si-ingrijire-pisici | 18 | 432 |
| jucarii-caini | 10 | 240 |
| jucarii-pisici | 2 | 48 |
| asternut-litiera-nisip-silicat | 6 | 144 |
| **Total** | **208** | **~4,992** |

**Estimated one full daily run:** ~208 page requests, ~4,990 in-scope listings before regulated
filtering and the price cross-check reject a few. At `SCRAPER_MIN/MAX_DELAY_SECONDS` (2–4s) plus
fetch time, roughly 4–5.5s per request → **~15–20 minutes wall-clock**, comfortably inside the
~45-minute budget CLAUDE.md §7 sets for staying a polite guest on a small shop. `~4,990` clears the
3,000 gate with margin for the listings the two filters remove.

**Excluded category prefixes** — the regulated tree, confirmed present in the sitemap:
`farmacie-*`, `produse-farmaceutice-*`, `antiparazitare-*`, `deparazitare-*`, `diete-veterinare-*`,
`antibiotice-*`, `antiinflamatoare-*`, `dermatologice-*`, `afectiuni-*`, `orl-*`,
`suplimente-nutritive-*`, `medicamente-*`, plus farm animals (`*-ferma`, `farmacie-cai`,
`farmacie-bovine`, ...) and `produse-fitosanitare` / pest control.

Also excluded: the campaign and promo categories (`promotii-*`, `campanie-*`, `royal-*`,
`super-reduceri`, `pachete-si-promotii`). They re-list the same products and would double-count.

**Second line of defence:** `REGULATED_TITLE_TOKENS` in `src/pricepilot/scrapers/petmax.py`
drops any listing whose title names a regulated product, for the case where one is mis-filed into
a food category.

### Title grammar observed

Confirms what CLAUDE.md §7 predicts, and adds a trap:

- `Royal Canin Mini Adult 8 kg` — brand field separate from the title
- `Royal Canin Bichon Frise Adult, 1.5 kg` — comma before a decimal-**point** weight, while the
  prices on the same card use a decimal **comma**
- `Advance Dog Adult Sensitive Miel si Orez, 12 kg` — comma-separated attribute grammar
- `Hrana uscata pentru caini EXTRU-CAN MINI cu VITA sac 4kg` — Romanian descriptive prefix,
  no space before the unit
- **`Royal Canin Mini Adult 8 kg + 1 kg gratuit`** and **`Royal Canin Medium Adult 15 + 3 Kg
  Gratis`** — bonus-weight promotions. Same line, same base pack, a *different purchasable unit at
  a different price*. On the second form the unit appears only on the bonus number. This was not
  in the plan's list of traps and it belongs in the Phase 3 annotation set.

### Cost

**$0.** Self-hosted `httpx` + `selectolax`, no proxies, no paid services.

## pentruanimale.ro — verified recon (2026-09-12)

Fetched with `curl -sL --compressed` and the `SCRAPER_USER_AGENT` from `.env`: `robots.txt`,
`sitemap.xml`, `sitemap/category-0.xml`, one category page, one second-page fetch to confirm
pagination — six requests total, spaced 3s by hand.

### Server-rendered? Yes — but not the way petmax is

`https://www.pentruanimale.ro/caini/hrana-caini/hrana-uscata` returned HTTP 200, ~3.2 MB
decompressed. The visible product grid is client-rendered (VTEX IO storefront, React), but the
raw response also carries `<template data-type="json" data-varname="__STATE__"><script>{...}
</script></template>` — VTEX's server-rendered Apollo GraphQL cache. It is present with **zero JS
execution**: `curl` alone returns it, confirmed by grepping the raw response for `sellingPrice`,
`Price`, `ListPrice` (all present) before writing any parsing code. No Playwright (CLAUDE.md §5.5).

### Canonical host

`https://www.pentruanimale.ro` responds directly (no apex redirect observed, unlike petmax).

### robots.txt

Verbatim copy at `tests/fixtures/pentruanimale_ro/robots.txt`.

- **`User-agent: *` declares no `Crawl-delay`.** We use 2–4s anyway (CLAUDE.md §5.4).
- Disallows: `/img/*`, `/account/*`, `/login/*`, `/checkout/*`, `/busca/*` (search), `/quick-view/*`,
  `/espiar/*`, plus tracking-parameter globs (`/*2pau`, `/*2ptt`, …). None touch category pages or
  the `?page=N` pagination we use.
- `Noindex: /buscapagina/*` — not a `Disallow`, and not a path we touch regardless.

### Sitemaps

`sitemap.xml` is an index: `brand-0.xml`, `category-0.xml`, `custom-user-routes-1.xml`,
`product-0.xml` through `product-6.xml`. `category-0.xml` lists real category paths as nested URLs
(e.g. `/caini/hrana-caini/hrana-uscata`) — this is where the six category paths below come from,
fetched rather than guessed (the same discipline as ADR-0017's petmax category expansion).

### What the `__STATE__` blob gives us

The blob is a normalized Apollo cache: a flat map of `"TypeName:id"` keys, cross-referenced by
`{"type":"id","id": "..."}` pointers instead of nesting. Per product, the fields that matter:

| Field | Where | Note |
|---|---|---|
| product id | `Product:sp-<id>-none` node's `productId` | Stable within the shop, useless across shops (same as petmax's `data-product-id`) |
| title | `productName` (product-level) and `items[].name` (**per-SKU**, includes the weight) | The per-SKU `name` is what becomes `Listing.title` — it is the purchasable unit |
| brand | `brand` | A real brand field, not inferred from the title |
| url | `link` (relative, e.g. `/royal-canin-mini-adult-hrana-uscata-caini/p`) | One URL per **product**; all its variant rows share it, same as the site's own PDP-with-a-size-selector UX |
| **variants** | `items({"filter":"ALL_AVAILABLE"})`, a list of SKU refs | Each SKU is one purchasable unit — the expansion target |
| SKU id | `items[].itemId` | **Per-variant**, unlike petmax's per-product id — this is the natural `source_product_id` |
| EAN | `items[].ean` | A real barcode, present on every SKU seen so far. Not used for anything yet (no other verified source exposes one), but worth keeping in `raw_payload` for later |
| **current price** | SKU → `sellers[0]` → `commertialOffer` → `Price` | Decimal, machine-readable, no comma parsing needed at all |
| **list price** | same path → `ListPrice` | Drives `compare_at_price`; only meaningful when it exceeds `Price` |
| stock | same path → `AvailableQuantity` | `> 0` treated as in-stock |

**Why variant expansion needs no extra request.** Every SKU under a grouped product — and each
one's own price — is already in the *category page's* `__STATE__`. `docs/SOURCES.md` originally
guessed this would need a product-page fetch per grouped item; recon shows it does not. This
matters directly for the request-count budget below.

### Pagination

`?page=N`, **one-based** — the bare category URL is page 1. Confirmed by fetching `?page=2`: the
embedded query's `from`/`to` range moved from `0–11` to `12–23`, 12 products returned, the same
`recordsFiltered` total (966) as page 1. The adapter stops when a page's product list is empty,
mirroring how the petmax adapter trusts `<link rel="next">` over guessing a page count.

### In-scope categories on the daily schedule

```
caini/hrana-caini/hrana-uscata           pisici/hrana-pisici/hrana-uscata
caini/hrana-caini/hrana-umeda            pisici/hrana-pisici/hrana-umeda
caini/hrana-caini/recompense---snacks    pisici/hrana-pisici/recompense---snacks
```

The same six-category shape as petmax's *original* set (dry/wet food and treats, dogs and cats) —
not petmax's later-expanded thirteen. This session's goal is cross-shop overlap, which lives in
food and treats; petmax alone already cleared the 3,000-listing volume gate, so there is no
pressure to widen pentruanimale's scope for volume. Litter/accessories/toys can be added later if
the overlap number needs it.

**Excluded, and why:** `caini/hrana-caini/diete-veterinare` and `pisici/hrana-pisici/diete-veterinare`
(prescription diets) and `caini/antiparazitare/*` (antiparasitics, both `deparazitare-interna` and
`-externa`) are separate categories from the six scraped — the allowlist is the first line of
defence. A per-SKU regulated-token check on the name is the second, for a mis-filed item.

### Category volume and request-count recon (2026-09-12) — CORRECTED after the first two real runs

One request per category (page 1), reading `recordsFiltered` and each product's variant count
directly from `__STATE__` — no extra crawling needed to estimate volume:

| Category | Products | Pages (12/page) | Avg variants/product | Est. listings |
|---|---:|---:|---:|---:|
| `caini/hrana-caini/hrana-uscata` | 966 | 81 | 1.92 | 1,851 |
| `caini/hrana-caini/hrana-umeda` | 526 | 44 | 1.67 | 876 |
| `caini/hrana-caini/recompense---snacks` | 754 | 63 | 1.00 | 754 |
| `pisici/hrana-pisici/hrana-uscata` | 491 | 41 | 2.83 | 1,391 |
| `pisici/hrana-pisici/hrana-umeda` | 836 | 70 | 1.75 | 1,463 |
| `pisici/hrana-pisici/recompense---snacks` | 258 | 22 | 1.00 | 258 |
| **Total** | **3,831** | **321** | — | **~6,593** |

**This 321-page estimate is not actually reachable, and the reason is a platform limit, not a
recon error.** `recordsFiltered` itself is confirmed accurate — re-fetched page 1 of all six
categories a session later and every count matched exactly, zero drift. The error is in the
assumption that all `ceil(recordsFiltered / 12)` pages are retrievable via `?page=N`. They are
not: **fetching `?page=51` on `hrana-uscata` returned HTTP 200, but its `__STATE__` blob has no
`$ROOT_QUERY.productSearch(...)` key at all** — only unrelated facet-widget data — while `?page=50`
(the page before it) has a normal, populated one. Confirmed at exactly the same boundary
(page 50 → 51) independently on three categories in the first two real runs
(`hrana-uscata-caini`, `recompense---snacks-caini`, `hrana-umeda-pisici` — precisely the three
whose recon page count exceeds 50; the other three, all under 50 pages, completed with no errors).
**This store's search pagination stops returning product results at 50 pages (600 products) per
category, regardless of how many `recordsFiltered` claims to exist.** Not a bug in this adapter —
the adapter's job here is to fail that gracefully rather than loop or misreport, which
`_should_continue_category`'s consecutive-parse-error cap now does (STEP 1 fix, session note
2026-09-12): it tries a few pages past the wall, logs a clear error, and moves on to the next
category instead of retrying forever or silently truncating everything *before* the wall (the
original, separate bug this same investigation found and fixed first).

**Corrected estimate, capping every category at 50 pages / 600 products:**

| Category | Corrected pages | Corrected est. listings |
|---|---:|---:|
| `caini/hrana-caini/hrana-uscata` | 50 (was 81) | ~1,152 (was 1,851) |
| `caini/hrana-caini/hrana-umeda` | 44 (unaffected) | 876 |
| `caini/hrana-caini/recompense---snacks` | 50 (was 63) | ~600 (was 754) |
| `pisici/hrana-pisici/hrana-uscata` | 41 (unaffected) | 1,391 |
| `pisici/hrana-pisici/hrana-umeda` | 50 (was 70) | ~1,050 (was 1,463) |
| `pisici/hrana-pisici/recompense---snacks` | 22 (unaffected) | 258 |
| **Total** | **257** (was 321) | **~5,327** (was ~6,593) |

**Estimated one full daily run, corrected:** ~257 successful page requests plus a handful of wasted
retries against the wall each time a capped category is hit (observed: 269 pages fetched in the
run that included this discovery, consistent with 257 + ~12 wasted attempts before the three
capped categories each gave up). Still comfortably inside the ~45-minute per-source budget — no
change needed there. **Real second run: 4,012 listings ingested** (up from 3,551 in the first run,
which additionally lost pages to the separate transient-parse-error bug fixed in the same
investigation) — both numbers are below the corrected ~5,327 estimate, which is expected: the
estimate assumes every one of the retrievable products' average-variant-count holds exactly, and
regulated-title filtering and dedup both trim the real count further.

**What this means going forward:** the ~639 products (966−600, plus the smaller shortfalls in the
other two capped categories) beyond each category's first 600 are permanently unreachable through
this pagination mechanism. Reaching them would need a different retrieval path (e.g. enumerating
`sitemap/product-N.xml` directly, matching petmax's own fallback plan for a broken category
crawl) — a real option, not attempted this session; flagged for whoever next touches this adapter.

### Title grammar observed

- `ROYAL CANIN Mini Adult, hrană uscată câini, 8kg` — per-SKU name, weight last, comma-separated
- `EXTRU-CAN Standard Hipocaloric, XS-XL, Pui, hrană uscată câini, obezitate, 10kg` — breed-size
  code (`XS-XL`) and flavour (`Pui` = chicken) both inline, comma-separated, same grammar CLAUDE.md
  §7 predicts for this shop
- **`ADVANCE Adult Maxi, L-XL, Pui, hrană uscată câini, GRATUIT, 14kg + 3kg`** vs
  **`ADVANCE Adult Maxi, L-XL, Pui, hrană uscată câini, 14kg`** — the *same* bonus-weight trap
  CLAUDE.md §7 documents for petmax, found here in real data on the same product (`sp-48-none`):
  two SKUs, same "14kg" numeral in both names, genuinely different purchasable items at different
  prices. Seeded into the offline fixture deliberately (see
  `tests/fixtures/pentruanimale_ro/README.md`).

### Cost

**$0.** Self-hosted `httpx` + `selectolax`/`json`, no proxies, no paid services.

## animax.ro — verified recon (2026-09-13)

Fetched with `curl -sL --compressed` and the `SCRAPER_USER_AGENT` from `.env`, plus a small
Python recon script (not committed — scratch only) for the per-category volume walk. Every
number below is from a real fetch shown or reproducible the same way.

### Platform: Shopify — the plan's "Magento" guess was wrong

`robots.txt` opens with `# Shopify storefront.` and names a UCP/MCP agentic-commerce endpoint
(`https://animax.ro/api/ucp/mcp`) plus `shop.app/SKILL.md` — modern Shopify boilerplate aimed at
AI shopping agents, irrelevant to us since we only read public catalogue JSON and never touch
cart/checkout. `sitemap.xml` is Shopify's standard sitemap-index shape
(`sitemap_products_N.xml`, `sitemap_collections_1.xml`, etc.), confirming the platform
independently of `robots.txt`'s own header comment.

### robots.txt

`https://animax.ro/robots.txt` → HTTP 200, 1093 bytes, fetched verbatim into
`tests/fixtures/animax_ro/robots.txt`. `Allow: /` broadly; disallows are cart/checkout/account/
admin/internal-AJAX and crawl-trap query patterns (`sort_by`, `+`/`%2B` in collection URLs,
double-`filter`). Nothing disallows `/collections/<handle>/products.json` or its query string.
No `Crawl-delay` declared for `User-agent: *` — the configured 2–4s floor applies.

### Server-rendered? Yes — and there's a cheaper structured source than HTML

`https://animax.ro/collections/hrana-uscata-caini` returns full product data in the raw HTML
(price classes present: `price-item--sale`, `price-item--regular-price`), so it would pass
CLAUDE.md §5's "prices in the raw response" test. But every Shopify storefront also exposes
`/collections/<handle>/products.json` — a standard, public, unauthenticated part of the storefront
theme itself (not a private/reverse-engineered API) — returning the same data as structured JSON:
`vendor` (clean brand field), `product_type`, and per-`variants[]` `id`, `sku`, `price`,
`compare_at_price`, `grams`, `available`. The adapter reads this instead of HTML. Bandwidth
comparison, same 250 products: **the HTML collection page is ~8.7 MB decompressed** (full
facet/quick-add JSON duplicated inline for every card); **the JSON endpoint for the same 250 is
~150 KB** — roughly 58× lighter, for both us and the shop.

### Category discovery and volumes

Categories came from `sitemap_collections_1.xml` (470 collections total — most are promo/
Black-Friday/brand-specific duplicates, not a real category tree). Ten were selected: the
food/treats/hygiene/toy categories for dogs and cats, mirroring petmax's 13-category scope minus
categories that don't exist as a clean umbrella here. Volume is an **exact count**, not an
estimate — each category's `products.json?limit=250&page=N` was walked to its final (< 250-item)
page:

| Category (handle) | Products |
|---|---|
| hrana-uscata-caini | 507 |
| hrana-umeda-caini | 337 |
| recompense-caini | 369 |
| igiena-si-ingrijire-caini | 53 |
| jucarii-caini | 81 |
| hrana-uscata-pisici | 367 |
| hrana-umeda-pisici | 537 |
| recompense-snacks-pisici | 128 |
| asternut-litiera-pisici | 65 |
| jucarii-pisici | 107 |
| **Total** | **2,551** |

**2,551 (this table) vs. 2,550 (ingested, `scrape_runs`/`raw_listings`/STATE.md): the two numbers
measure different things, confirmed 2026-09-13, not a bug.** This table sums each category's own
product count, and one product is genuinely a member of *two* of the ten categories: "Hrana umeda
pentru caini si pisici Brit Grain Free VD Recovery 400g" (variant id `47783183057234`) is food
marketed for both species, listed under both `hrana-umeda-caini` and `hrana-umeda-pisici`. Summing
per-category counts counts it twice (contributing to 2,551); the runner's `seen` set dedupes by
`external_id` (the variant id) within one run, so it is ingested once — hence 2,550 distinct rows
actually land in `raw_listings`. Verified by re-fetching all ten categories' full variant-id lists
live and diffing against the ingested `external_id` set: 2,550 distinct ids on both sides, zero
missing, zero extra, with the one variant id appearing under exactly two category fetches. The
live catalog itself was also re-measured at exactly 2,551 (identical per-category counts to this
table) both before and after the real run — so this is not catalogue churn between two points in
time, it is the same double-count every time this table's method is used. **This table's "Total"
row is a sum of category memberships, not a count of distinct products** — 2,550 is the correct
distinct-product number and the one that matters everywhere else in this repo.

**Same investigation surfaced a separate, more important finding, not yet acted on:** ingested
animax listings include a `product_type` of "Diete veterinare pentru caini" (46), "... pentru
pisici" (61), and "... pentru caini si pisici" (1) — 108 listings total, one of them the same
Brit VD Recovery product above. "VD" in that title is short for *veterinary diet*. CLAUDE.md §7
excludes veterinary/prescription diets from scope, and `is_regulated()` is the enforcement
mechanism — but it matches on title substrings ("veterinary diet", "dieta veterinara", "vet diet",
etc.), and none of these titles contain those substrings ("VD Recovery" reads as a product-line
name, not a flagged phrase). These products are in the ten selected categories legitimately from
animax's own collection structure (a "Diete veterinare" product cross-listed into the general food
collections), not from a category-selection mistake. **Not fixed this session** — extending
`is_regulated()`'s vocabulary is a scope/logic change outside this session's three-step brief, and
is flagged in STATE.md's Open issues for a decision.

**`recompense-caini` vs `snack-caini`, and `recompense-snacks-pisici` vs `snackuri-pisici`:**
animax also has narrower "snack" collections that looked like a second, distinct treats category.
Checked directly by comparing product-id sets: `snack-caini`'s 230 products are a 98% subset of
`recompense-caini`'s 369, and `snackuri-pisici`'s 108 are a 99% subset of
`recompense-snacks-pisici`'s 128. Using only the larger umbrella collection avoids nearly-all-
wasted duplicate requests (the runner's `seen` dedup would silently absorb the overlap anyway, but
there is no reason to fetch it twice).

Categories deliberately excluded as regulated, per CLAUDE.md §7: `deparazitare-caini`,
`deparazitare-pisici` (antiparasitics) were visible in the collection list and never added to
the adapter's category set. `is_regulated()` (shared with `petmax.py`, unchanged) is the second
line of defence for a stray regulated item mis-filed elsewhere.

### Structural finding: no grouped variants (unlike pentruanimale)

Checked empirically, not assumed: across 750+ products sampled from three categories
(`hrana-uscata-caini`'s full 507, plus `jucarii-caini`), **zero** products had more than one
Shopify variant. Every purchasable pack size is its own separate product — the same convention
petmax uses, not pentruanimale's VTEX-style grouping. The adapter still iterates
`product["variants"]` generically rather than hardcoding "exactly one", in case this doesn't hold
catalogue-wide.

### Traps found in real data

- **Decimal point vs comma, same shop, same product line:** "Orijen Junior Talie Mare **11.4 kg**"
  vs "ORIJEN Regional Red, **11,4 kg**" — both real animax listings, both `grams: 11400`.
- **Full Romanian diacritics vs none, same shop:** Purina's titles ("hrană uscată pentru câini")
  carry ă/â/î throughout; most other vendors' titles here are plain ASCII ("Hrana uscata pentru
  caini"). Not just a cross-shop inconsistency — animax is inconsistent with itself.
- **The structured `grams` field cannot be trusted as ground truth.** "Royal Canin Adult 8+ Mini
  **2 kg**" carries `grams: 500` — the shop's own shipping-weight field disagrees with its own
  title text by 4×. This is the concrete reason the overlap key (untouched this session) parses
  weight from title text rather than from a shop-supplied structured field — a lesson that would
  otherwise have stayed theoretical.
- **Age-band and breed-size codes that look like bonus packs but aren't:** "Adult **8+** Mini",
  "Mini **12+** Ageing", "Senior **L+XL**", "Senior **S+M**". None of these are a bonus-weight
  promotion (CLAUDE.md §7's "12+2 kg" pattern) — they are age thresholds and breed-size bands. A
  naive `+`-based bonus-pack detector would misfire on all of them; the shared logic doesn't do
  that (it looks for a weight unit on both sides of the `+`).
- **A title with no digit at all.** "PEDIGREE ... Adult Talie Medie/Mare, cu Vita/Legume" states
  no weight anywhere in visible text; `grams: 3000` exists only in the structured field. Correctly
  unkeyable by the current title-only key — the same "no weight in the title" bucket `make status`
  already reports for petmax/pentruanimale, not a new failure mode.
- **`compare_at_price` equal to `price`.** Seen on the Royal Canin 8+ Mini row — both `"104.99"`.
  Not a real discount; the adapter applies the same guard petmax already uses
  (`compare_at_price` counts only when it is genuinely *above* `price`).

### Volume vs request cost

Ten categories, 2,551 products at ≤250 per JSON request → **at most ~13 requests for a full daily
run** (most categories fit in one page; only three exceed 250 and need a second). At the
configured 2–4s floor, a full run is on the order of a minute of wall clock, plus regulated-
filtering and Pydantic validation — far lighter than petmax's ~208 or pentruanimale's ~257 page
fetches, because the JSON endpoint's page size (250) is much larger than either shop's HTML page
size.

### Cost

**$0.** Self-hosted `httpx` + `json`, no proxies, no paid services, no headless browser.

## Excluded

| Shop | Reason |
|---|---|
| **shop4pet.ro** | `robots.txt` disallows automated access. ❌ Confirmed in CLAUDE.md. Do not scrape. |
| eMAG and other large marketplaces | Out of scope: marketplace listings have unstable sellers and duplicated catalogues. |

## Product scope

**In scope:** dry food, wet food, treats, litter, grooming and hygiene, accessories, toys.

**Excluded at ingest, not later:** veterinary medicines, antiparasitics, prescription diets,
vaccines. These are pharmaceutical products and carry compliance questions this project does not
need.

A listing is in scope only if it has a real manufacturer and a stable product identity another shop
could also sell.

## Manufacturer allowlist

Built from the data as collection proceeds. Seed list from CLAUDE.md:

Royal Canin · Purina · Pro Plan · Acana · Orijen · Hill's · Brit · Taste of the Wild · Advance ·
Josera · Calibra · Trixie · Bosch · Petkult · Smølke

Note the spelling traps this list already contains: **Smølke** (ø), **Hill's** (apostrophe), and
brands that appear both with and without Romanian diacritics.

## Confirmed cross-shop overlap — measured, 2026-09-12 (superseded same day — see below)

First real measurement, petmax_ro + pentruanimale_ro, one day of data: the shipped `overlap_key`
found only **13** shared products (session note: precision-optimised, not recall-optimised — see
ADR-0021). A same-day investigation found the key itself was the bottleneck, not thin real
overlap, and fixed it (weight-token spacing, ml/l, apostrophe folding, bonus-weight guard).

### Re-measured after the fix, same day

| Source | In-scope listings | Keyable |
|---|---:|---:|
| petmax_ro | 4,064 | 2,914 (71.7%) |
| pentruanimale_ro | 4,012 | 3,922 (97.8%) |

**Shared products: 94** (up from 13 — a 7.2× increase, from the key fix plus a corrected,
larger pentruanimale.ro dataset after the pagination fixes in STEP 1). **83 of the 94 (88%) are
Royal Canin** — both shops appear to carry Royal Canin's catalogue near-completely, in
near-identical structure; the remaining 11 keys span Applaws (4), Matisse (3), Orijen, Miau Miau,
Equilibrio and Advance (1 each).

**Precision, hand-checked on a random sample of 25 of the 94 (not all 94 — per instruction, a
sample when there are more than 25):** 22 of 25 (88%) are clean — every listing inside the key is
genuinely the same purchasable unit. **3 of 25 (12%) contain at least one false pairing** mixed in
with a genuine one:
- a key merged a plain "Adult" formula with an unrelated "Adult 8+" (senior) formula at the same
  weight — the line tokens don't carry enough signal to separate "8+" from plain when a shop omits
  extra wording,
- a key merged "Giant Adult" with "Giant Junior" at the same weight — life-stage variants the
  tokenizer doesn't distinguish once brand and weight already match,
- a key merged a can (`conservă`) with a pouch (`plic`) variant — a packaging-format nuance the
  proxy doesn't encode (also seen in the original 13, one occurrence there too).

This is exactly what CLAUDE.md §7 accepts — "it will join a few products that are not the same" —
and it is well above the 90% floor this session set as a stop-and-report threshold, so no further
tuning was done. **The bonus-weight guard verified working on real data**: "Royal Canin Mini Adult
8kg" (plain/senior variants) and "Royal Canin Mini Adult 8kg + 1kg gratuit" (the bonus form) landed
as two separate keys — the guard kept the bonus pair from merging into the larger plain/senior
bucket, while still correctly matching the bonus-form listing on each shop to the other.

**What this means for the Phase 1 gate, honestly:** 94 is real, verified, and still short of 400.
The concentration in one brand (88%) is the important structural fact for projecting a third
source: if it also carries Royal Canin's range near-completely (plausible — Royal Canin is
dominant in Romanian pet retail), a third source plausibly adds a similar-order pairwise overlap
with each existing source, but with heavy re-use of the *same* Royal Canin products already
counted, not a clean multiplication. Rough arithmetic: 94 ≈ (2,914 × 0.7717 keyable-rate-weighted
overlap-rate) is dominated by ~83 Royal Canin pairs out of roughly 2,900 keyable Royal Canin-and-
other listings — call it a per-pair "true overlap density" of order 90-ish products when both
shops carry a similar major-brand-heavy catalogue. Adding a third such source gives up to two more
such pairs (source1↔source3, source2↔source3), but with substantial double-counting of the same
Royal Canin SKUs across all three pairs (the "≥2 shops" gate counts a product once no matter how
many pairs it appears in) — a plausible range is **~150–250 distinct products on ≥2 shops with a
well-chosen third source**, not 400, unless that source also broadens which brands/categories
carry real cross-shop overlap. **The gap to 400 is now partly structural** (concentrated in one
brand, in food/treats categories only) rather than purely a key-recall problem — a third adapter
helps, but is not alone plausibly sufficient on this arithmetic.

One product verified by hand in CLAUDE.md, before any real data existed — Orijen Original Dog
Adult Mini, 1.8 kg, kept here for the historical record of what "confirmed" meant before this
session's measurement:

| Shop | Title as written |
|---|---|
| animax.ro | `Hrana uscata pentru caini Orijen Original Dog Adult Mini 1.8 kg` |
| magazindeanimale.ro | `Hrană uscată câini ORIJEN Original Dog Adult Mini 1,8 kg` |
| zoopoint.ro | `Orijen Original Dog Adult Mini` — no weight in the title at all |
| petmax.ro | names the line `Orijen Adult Original` — word order reversed |

## Scraping discipline (CLAUDE.md §5)

- First run fetches **one** page and saves raw HTML to `tests/fixtures/<source>/`. All subsequent
  development and every test runs offline against those fixtures.
- `--limit` (default 5) and `--dry-run` on every adapter.
- Minimum 2s between requests, randomized; `robots.txt` respected; honest User-Agent with a contact.
- `httpx` + `selectolax` first. If prices are absent from the raw response, **drop the source**
  rather than reaching for a headless browser.
- Every run logs to `scrape_runs`. A >40% drop in item count vs the previous run raises an alert
  instead of silently ingesting.

# SOURCES

One entry per competitor shop. **No adapter is written until its row here is filled in**
(CLAUDE.md §7 Phase 1): fetch one page with `curl`, confirm titles and prices are present in the
raw response rather than injected by JS, read `robots.txt`, note the crawl-delay.

> **Status: `petmax.ro` verified 2026-09-12; `pentruanimale.ro` verified 2026-09-12.** Their rows
> below and the detailed sections that follow are measurements, not restatements of CLAUDE.md.
> Every other row is still unverified, and the columns marked *unverified* are not claims.
>
> Per DECISIONS.md ADR-0010, `petmax.ro` goes on a daily schedule before the next adapter is
> written, because price history is wall-clock and cannot be backfilled.

## Sources

| Shop | Platform | Server-rendered | robots.txt checked | Crawl-delay | Structural note | Status |
|---|---|---|---|---|---|---|
| petmax.ro | Gomag | **yes, verified** | **yes, 2026-09-12** | **none declared for `*`** | Prices in a `data-Gomag` JSON attribute: current *and* pre-discount. One row per size, no variant grouping. Pagination `?p=N`. **Anchor source.** | **implemented, on daily schedule** |
| pentruanimale.ro | **VTEX** | **yes, verified** | **yes, 2026-09-12** | **none declared for `*`** | Prices in a `<template data-varname="__STATE__">` JSON blob (VTEX's server-rendered Apollo cache) — current *and* list price, per SKU. **Groups variants** under one product; expansion needs no extra request, every SKU's price is already in the same blob. Pagination `?page=N`, one-based. | **implemented, on daily schedule** |
| animax.ro | Magento | per CLAUDE.md: yes | unverified | unverified | Indexed product pages carry full titles including weight. | not started |
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

## Confirmed cross-shop overlap — measured, 2026-09-12

First real measurement, petmax_ro + pentruanimale_ro, one day of data (2026-09-12):

| Source | In-scope listings | Keyable (brand+line+weight parsed) |
|---|---:|---:|
| petmax_ro | 4,060 | 2,495 (61%) |
| pentruanimale_ro | 3,551 | 3,525 (99%) |

**Shared products (current `overlap_key`, unmodified): 13.** Far below the ≥400 gate. All 13 were
hand-verified (titles, brands, weights, prices compared) — every one is a genuinely identical
purchasable unit on both shops (Applaws 156g/70g ×2 flavours, Equilibrio Cats 7.5kg, Miau Miau
100g, Orijen Kitten 1.8kg, and seven Royal Canin dry lines from 1.5kg to 12kg). One nuance: one
key's group includes a pentruanimale.ro *pouch* variant alongside the matching *can* variant it
shares with petmax — same flavour and weight, different packaging format, which the key does not
distinguish. Precision on the 13 is effectively 100% (13/13 same purchasable unit, with that one
packaging-format caveat noted). **This is well above the 90% bar; the problem is not false
matches, it is recall.**

**Diagnostic-only finding (not applied to `src/pricepilot/overlap.py` — reported, not tuned):**
grouping by `(brand, weight)` alone, dropping the line-token component, finds 142 pairs where both
shops carry the same brand+weight but the current key splits them apart. The overwhelming majority
of these are genuinely *different* products colliding only on brand+weight (Royal Canin alone sells
30–40 distinct 85g wet-food formulas; the line tokens are doing real, correct work separating
them). But ranking those 142 by title similarity surfaces a specific, narrow, real bug: when a
shop writes weight with no space before the unit (`"85g"`, `"400g"`) the digit+unit token survives
`line_tokens()` as noise the current regex doesn't strip (only bare `"kg"`/`"g"` are filtered);
when the other shop writes it with a space (`"85 g"`), the digit is stripped as `isdigit()` and the
bare `"g"` as `_NOISE`, so the *same* product ends up with different token sets purely from spacing.
Simulating that one additional strip (`^\d+(kg|g)$` as noise too) raises the shared count from
**13 to 92** — a 7× difference, entirely from titles that are otherwise identical. Hand-checking
those 79 additional pairs: the large majority are genuine matches (same brand, same line, same
price range) — **but this same relaxation also reintroduces the bonus-weight trap CLAUDE.md §7
names**: "Royal Canin Medium Adult 15kg" collides with "Royal Canin Medium Adult 15 + 3 Kg Gratis"
(a different purchasable unit, different price), and "Royal Canin Mini Adult 8kg" collides with
both an "8+" senior-age variant and "8kg + 1kg gratuit" — three genuinely different products merged
into one bucket. **Conclusion: the true overlap between these two shops is materially higher than
13, but the fix is not a one-line token strip** — it needs to distinguish a bonus-weight/variant
listing from a plain one (e.g. detecting a `+` or "gratuit"/"gratis" in the raw title before
stripping) at the same time it stops the weight-spacing false split. Left as a recommendation for
the next session that touches `overlap.py`, not implemented here.

**What this means for the Phase 1 gate, honestly:** 13 (or even a carefully-fixed ~92) is nowhere
near 400 from two sources. A third adapter alone will not close a gap this size — the keying
itself needs the fix above before more sources can be expected to move this number the way the
gate assumes. This is a real finding to act on, not a volume problem to wait out.

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

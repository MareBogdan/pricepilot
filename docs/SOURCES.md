# SOURCES

One entry per competitor shop. **No adapter is written until its row here is filled in**
(CLAUDE.md §7 Phase 1): fetch one page with `curl`, confirm titles and prices are present in the
raw response rather than injected by JS, read `robots.txt`, note the crawl-delay.

> **Status: `petmax.ro` verified 2026-09-12.** Its row below and the detailed section that
> follows are measurements, not restatements of CLAUDE.md. Every other row is still unverified,
> and the columns marked *unverified* are not claims.
>
> Per DECISIONS.md ADR-0010, `petmax.ro` goes on a daily schedule before the next adapter is
> written, because price history is wall-clock and cannot be backfilled.

## Sources

| Shop | Platform | Server-rendered | robots.txt checked | Crawl-delay | Structural note | Status |
|---|---|---|---|---|---|---|
| petmax.ro | Gomag | **yes, verified** | **yes, 2026-09-12** | **none declared for `*`** | Prices in a `data-Gomag` JSON attribute: current *and* pre-discount. One row per size, no variant grouping. Pagination `?p=N`. **Anchor source.** | **implemented, on daily schedule** |
| pentruanimale.ro | unknown | per CLAUDE.md: yes | unverified | unverified | **Groups variants** under one product with a price range ("38,01 lei - 62,00 lei", "Vezi 5 variante"). Adapter must expand to one row per purchasable variant, likely via the product page. | not started |
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
400-product gate), and it is a modest enough crawl to run daily. Breadth (litter, grooming,
accessories, toys) is added only if the 3,000-listing gate needs it.

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

## Confirmed cross-shop overlap

One product verified by hand in CLAUDE.md — Orijen Original Dog Adult Mini, 1.8 kg:

| Shop | Title as written |
|---|---|
| animax.ro | `Hrana uscata pentru caini Orijen Original Dog Adult Mini 1.8 kg` |
| magazindeanimale.ro | `Hrană uscată câini ORIJEN Original Dog Adult Mini 1,8 kg` |
| zoopoint.ro | `Orijen Original Dog Adult Mini` — no weight in the title at all |
| petmax.ro | names the line `Orijen Adult Original` — word order reversed |

Decimal comma vs point, diacritics present or absent, brand casing, weight in title vs weight as
variant, reordered line names. Shop-internal SKUs (`ORJ_D_OD_AMI_2`) are useless across shops.

> **This is one product, not a base rate.** `docs/AUDIT.md` concern 2 recommends measuring actual
> overlap across sources before committing to the Phase 1 gate, because a low overlap count means
> Phase 3 has no positive class.

## Scraping discipline (CLAUDE.md §5)

- First run fetches **one** page and saves raw HTML to `tests/fixtures/<source>/`. All subsequent
  development and every test runs offline against those fixtures.
- `--limit` (default 5) and `--dry-run` on every adapter.
- Minimum 2s between requests, randomized; `robots.txt` respected; honest User-Agent with a contact.
- `httpx` + `selectolax` first. If prices are absent from the raw response, **drop the source**
  rather than reaching for a headless browser.
- Every run logs to `scrape_runs`. A >40% drop in item count vs the previous run raises an alert
  instead of silently ingesting.

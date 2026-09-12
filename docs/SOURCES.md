# SOURCES

One entry per competitor shop. **No adapter is written until its row here is filled in**
(CLAUDE.md §7 Phase 1): fetch one page with `curl`, confirm titles and prices are present in the
raw response rather than injected by JS, read `robots.txt`, note the crawl-delay.

> **Status: nothing verified yet.** Phase 1 has not started. The table below records what
> CLAUDE.md states about each source; the columns marked *unverified* are mine to fill in, and
> until then they are not claims.

## Sources

| Shop | Platform | Server-rendered | robots.txt checked | Crawl-delay | Structural note | Status |
|---|---|---|---|---|---|---|
| petmax.ro | Gomag | per CLAUDE.md: yes | unverified | unverified | Richest data: title, brand, previous + current price, discount %, stock, review count. **Anchor source.** One row per size. | not started |
| pentruanimale.ro | unknown | per CLAUDE.md: yes | unverified | unverified | **Groups variants** under one product with a price range ("38,01 lei - 62,00 lei", "Vezi 5 variante"). Adapter must expand to one row per purchasable variant, likely via the product page. | not started |
| animax.ro | Magento | per CLAUDE.md: yes | unverified | unverified | Indexed product pages carry full titles including weight. | not started |
| magazindeanimale.ro | unknown | unverified | unverified | unverified | Same catalogue as zoopoint, different title conventions; diacritics present. | not started |
| zoopoint.ro | unknown | unverified | unverified | unverified | **No weight in title** — size is a separate variant. | not started |
| zoomalia.ro | unknown | unverified | unverified | unverified | Weight-first title grammar, appends price-per-kg. Audit before implementing. | candidate |
| zoomania.ro | unknown | unverified | unverified | unverified | Audit before implementing. | candidate |
| maxi-pet.ro | unknown | unverified | unverified | unverified | Audit before implementing. | candidate |
| Profitshare / 2Performant feeds | affiliate feed | n/a | n/a | n/a | Structured CSV/XML built for third-party consumption, refreshed daily. **Prefer where available.** | candidate |

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

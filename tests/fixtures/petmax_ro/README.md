# Fixtures — petmax.ro

Offline fixtures for the `petmax_ro` adapter. **Tests never touch the live site**
(CLAUDE.md §5.1, §9). Everything the parser is tested against lives here.

## Files

| File | Provenance |
|---|---|
| `robots.txt` | `https://www.petmax.ro/robots.txt`, fetched 2026-09-12. Verbatim — it is a policy document and trimming it would misrepresent it. |
| `category_hrana-uscata-caini_p0.html` | Trimmed from `https://www.petmax.ro/hrana-uscata-caini`, fetched 2026-09-12 with `curl -sL --compressed` and the `SCRAPER_USER_AGENT` from `.env`. |

## How the category fixture was trimmed

`docs/LEGAL.md` requires fixtures to be "minimal and trimmed — the smallest fragment that
exercises the parser, not a full page dump of someone else's catalogue". The live page is ~619 KB
and 24 product cards; the fixture is ~28 KB and 5 cards. Removed:

- the site chrome — header, navigation, mega-menu, footer, facet sidebar, scripts, styles
- 19 of 24 product cards
- the `review` array and `description` field from the JSON-LD (customer names are personal data,
  and `docs/LEGAL.md` commits to collecting none)

Kept unmodified: the five product-card `<div>`s, the JSON-LD `Product` objects for those five, the
`rel="canonical"` and `rel="next"` links, and the pagination block — those are exactly what the
parser reads.

## Why these five products

| `data-product-id` | Title | What it exercises |
|---|---|---|
| 233 | Royal Canin Mini Adult 8 kg | The baseline card: brand link, discount badge, `<s>` compare-at price, in-stock, review count |
| 935 | Royal Canin Bichon Frise Adult, 1.5 kg | Comma before the weight; decimal **point** in the title while prices use a decimal **comma** |
| 2542 | Royal Canin Mini Adult 8 kg + 1 kg gratuit | **Bonus-weight trap.** Same line and same 8 kg base as 233, different purchasable unit and a different price. Must not normalise to the same product as 233 |
| 1698 | Royal Canin Medium Adult 15 + 3 Kg Gratis | Second bonus-weight form, "15 + 3 Kg", capital Kg, Romanian "Gratis" |
| 116 | Advance Dog Adult Sensitive Miel si Orez, 12 kg | Non-Royal-Canin brand, comma-separated attribute grammar, flavour tokens |

Cards 233 and 2542 are the pair that matters most: a parser or a matcher that collapses them is
wrong, and this is the error class CLAUDE.md §7 Phase 3 names as the largest.

## Refreshing

Re-fetch only when the shop's markup changes and the parser breaks. One request, never in a loop.
Record the new date in the table above and note what changed in `docs/SOURCES.md`.

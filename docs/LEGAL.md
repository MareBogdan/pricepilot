# LEGAL — scraping posture

This repo is public and Bogdan is named on it. That makes the scraping posture part of the
engineering, not an afterthought. `docs/AUDIT.md` concern 6.3 raised this; here is the position.

## What we do

- **Respect `robots.txt`.** A source that disallows automated access is not scraped. `shop4pet.ro`
  is excluded for exactly this reason and stays excluded.
- **Identify honestly.** `SCRAPER_USER_AGENT` names the bot and carries a contact address, so any
  shop that objects can reach a human instead of silently blocking an unknown agent.
- **Rate limit conservatively.** Minimum 2 seconds between requests, randomized. Far below any
  level that affects a shop's service.
- **Collect only public listing data** — title, price, availability, URL. No accounts, no
  authentication, no paywalled content, no personal data of any kind.
- **Prefer affiliate feeds.** Where a shop publishes a Profitshare/2Performant product feed, that
  feed is built for third-party consumption and is the polite channel. Use it over scraping.
- **Stay out of regulated categories.** Veterinary medicines, antiparasitics, prescription diets
  and vaccines are filtered at ingest.

## Fixtures in the repo

`tests/fixtures/<source>/` holds saved HTML so that tests never touch a live site. Keep these
**minimal and trimmed** — the smallest fragment that exercises the parser, not a full page dump of
someone else's catalogue. They are retained for offline testing only, and a shop that asks for
theirs to be removed gets it removed.

## What this project is

A non-commercial portfolio project. It does not resell collected data, does not run at a volume
that burdens any shop. The deployed dashboard shows our own (mock) catalogue and, for each product
matched to a competitor, that competitor's listing title, current price and daily price history.
Since 2026-10-08 the shop is shown only as an alias (**Shop A / Shop B / Shop C**) on every page and
in every JSON endpoint, and the dashboard carries **no link** to any shop's pages: the real names and
the stored product URLs never leave the database (`src/pricepilot/api/anonymise.py`, enforced by
`tests/test_api_dashboard.py`). The real names remain in the code, the docs and the README, which
describe the project. Residual limits: a competitor's listing *title* is shown as scraped and could
itself contain a shop's name; the committed demo GIF (`docs/assets/demo.gif`) was recorded before this change and may show shop names on its product-page frames.
It has no endpoint that lists or exports competitor listings in bulk.

A declared `Crawl-delay` in `robots.txt` is honoured by the request loop: the pause floor is raised
to the delay declared for our agent (or `*`) and never lowered below the configured 2 s. No source
declares one for generic crawlers (last checked 2026-09-13), so the 2-4 s pause applies in practice.

If any of the above stops being true, revisit this document before the code.

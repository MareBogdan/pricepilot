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
matched to a competitor, that competitor's listing title, current price, daily price history and a
link to the shop's page. It has no endpoint that lists or exports competitor listings in bulk.

Known gap: a declared `Crawl-delay` in `robots.txt` is not yet honoured by the request loop
(`PoliteClient.declared_crawl_delay` exists but is not called). No source declared one for
generic crawlers when last checked (2026-09-13); the fixed 2-4 s pause applies.

If any of the above stops being true, revisit this document before the code.

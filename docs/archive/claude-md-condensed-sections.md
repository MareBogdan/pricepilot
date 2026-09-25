# CLAUDE.md — condensed-section full text (context diet, 2026-09-25)

These two CLAUDE.md sections are still-active rules, not closed-phase history, but were
condensed in the live file to fit its context budget (CLAUDE.md section 11). The live
file keeps the condensed form with a pointer here; this is the original wording,
byte-for-byte, kept because it still carries detail (examples, rationale) the condensed
form drops.

---

## Section 5, "Scrapers" (full text)

### Scrapers
1. **Never test a scraper against a live site in a loop.** First run fetches *one* page and saves the raw HTML to `tests/fixtures/<source>/`. All subsequent development and all tests run against those saved fixtures, offline.
2. Every scraper has a `--limit` flag. Default is 5 items. Full runs are explicit.
3. Every scraper has a `--dry-run` flag that parses and prints but writes nothing.
4. Rate limit: minimum 2 seconds between requests, randomized. Respect `robots.txt`. Honest User-Agent with a contact.
   **The contact address is never committed.** Scrapers read `SCRAPER_USER_AGENT` from `.env`; the repo
   carries only `.env.example` with a placeholder. A scraper that finds no `SCRAPER_USER_AGENT` fails
   loudly at startup rather than falling back to a default or an invented address.
5. Self-hosted HTTP first (`httpx` + `selectolax`). Playwright only when a site genuinely requires JS. Paid scraping services (proxies, Apify-style) only if the user explicitly approves — assume €0 for these by default.
6. Every run logs to a `scrape_runs` table: source, items found, errors, duration. If a source's item count drops more than 40% vs the previous run, raise an alert instead of silently ingesting.


## Section 5, "Spend schedule" (full text)

### Spend schedule

The user currently has **$20 available**. Ceiling for the whole project is **$100**, but the realistic landing point is around $50. Most of this project costs nothing.

**Money is reserved in priority order, not spent in phase order.** The deliverable is a publicly
reachable demo. Hosting is what makes the project visible to a recruiter; a fine-tuned model on a
dead URL is worth nothing. So:

| Priority | What | Reserve | Approval needed |
|---|---|---|---|
| **1 — reserved first** | VPS hosting, three months (Hetzner CX22 ~€4/mo) | **~$15** | yes, once, at Phase 7 |
| **2** | LLM attribute extraction, Phase 2, cached by title hash | $2–3 | yes, before first batch |
| **3** | Recommendation generation, Phase 5 | $5–8 | yes |
| **4** | Optional pre-labelling assist, Phase 3 | $2–4 | yes |
| **not committed** | GPU rental for LoRA fine-tuning | — | **separate decision at week 5** |

Phases 0, 1 and 4 cost nothing and are not in this table.

**GPU fine-tuning is not a committed budget line.** It is a decision taken at week 5, on the
evidence available then: whether the annotated dataset exists, whether the cross-encoder baseline
is recorded, and whether a free tier (Colab / Kaggle T4) can carry the run. Treating it as
committed now is what makes the $20-available arithmetic fail.

**When that decision is taken, the first fine-tune is a deliberate smoke run.** Smallest model,
~200 examples, a few minutes of wall clock, **~$1–2** — its purpose is to prove the pipeline runs
end to end: dataset loads, LoRA attaches, training steps, checkpoint saves, eval harness scores it.
The number it produces is discarded. Only after that succeeds does the real run get approved, as a
second `SPEND:` line. Never start the real run first.

**Rules that follow from this:**
- Phases 0, 1 and 4 must be completed with zero spend. If a design needs money in those phases, the design is wrong.
- Do not start any paid work until the free work around it is finished and tested.
- Announce the cost *before* the action, in the format: `SPEND: <action> — est. $X.XX — proceed?`
- After any paid action, report actual vs estimated.
- Track everything in `docs/COSTS.md`, updated in the same commit as the work.


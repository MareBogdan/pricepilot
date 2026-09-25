# Archive

Append-only history moved out of the live tracking files to keep them within the
context budget (CLAUDE.md section 11, `tests/test_context_budget.py`). Archives are
append-only history; **the live files win when they disagree.**

- `_pre-diet/` — byte-identical snapshot of `CLAUDE.md`, `STATE.md`, `DECISIONS.md` taken immediately before the 2026-09-25 context diet, the baseline `scripts/check_archive_integrity.py` checks every line against.
- `phases-0-2.md` — CLAUDE.md's Phase 0/1/2 full text (all three CLOSED) and section 12 (First session, already executed once).
- `DECISIONS-0001-0027.md` — full text of ADR-0001 through ADR-0027.
- `DECISIONS-0028-phase3-full.md` — full text of ADR-0028, all 25 addenda (Phase 3 prerequisites through the closing serving benchmark).
- `STATE-history.md` — STATE.md's `## History` section, plus every Open-issue item that is now RESOLVED (CLOSED, or overtaken by a later fact).
- `agents/scraper-engineer.md` — the `scraper-engineer` sub-agent definition, retired after Phase 1 (all three source adapters built).
- `claude-md-condensed-sections.md` — full original wording of the "Scrapers" and "Spend schedule" sections, condensed (not archived as history) in the live CLAUDE.md.

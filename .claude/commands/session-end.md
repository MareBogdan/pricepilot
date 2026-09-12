---
description: End a work session — update tracking, verify the repo is clean
---

1. Run `.\make.ps1 check` (lint + typecheck + test) and show the output. Fix anything red.
2. Rewrite `STATE.md` — do not append. Update the gate checklist from real numbers, refresh
   "Last done" to the five most recent items, and be honest in "Open issues".
3. Add an ADR to `DECISIONS.md` for any architectural choice made this session.
4. Update `docs/COSTS.md` if any money was spent.
5. `git status` — report anything uncommitted.

A task with no tracking update is not finished (CLAUDE.md §11).

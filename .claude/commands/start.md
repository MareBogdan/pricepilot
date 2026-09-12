Start-of-session context load. Do this before anything else.

CLAUDE.md loads automatically - do not re-read it. Read, in this order:
STATE.md, DECISIONS.md, docs/AUDIT.md, docs/SOURCES.md, README.md. Then run
`git log --oneline -15` and `make status`. Read any other file you need, but
those first, and assume nothing about project state that is not in them or in
the git history.

Then state in three lines: what phase we are in, what the last session
actually closed, and what the next concrete task is.

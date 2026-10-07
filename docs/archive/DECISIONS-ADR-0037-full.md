# ADR-0037 full text (moved out of DECISIONS.md to stay within the context budget, 2026-10-07)

## ADR-0037 — ADR-0014's Neon test guard had a hole: popping DATABASE_URL doesn't isolate .env

**Context.** `reviewer` review of the retrieval commit (576ea77) found: `tests/conftest.py::
pytest_configure` popped `DATABASE_URL` from `os.environ` when `TEST_DATABASE_URL` was absent,
intending "fully offline". `Settings(env_file=".env")` (pydantic-settings) falls back to `.env`'s
own `DATABASE_URL` whenever the OS environment variable is absent -- precedence is init >
env var > `.env` file, so a POPPED variable is not the same as an OVERRIDDEN one. `TEST_DATABASE_URL`
is not a real OS env var on this machine (only present inside `.env`), so `uv run pytest` /
`.venv\Scripts\python -m pytest` / `make.ps1 test` all resolved `DATABASE_URL` to the real Neon
credential. Session 2's new `tests/test_policy_retrieval.py` was the first test in the repo to
touch a database, and the first to hit this hole -- its idempotency test ran
`scripts/build_policy_index.py` as a subprocess against Neon on every plain `pytest` invocation
this session, before the fix. No data was lost (the writes are idempotent upserts of
`policy_chunks`, a table this same session created and populated on purpose, never touching
`raw_listings`/collected history) but the guard's actual behavior did not match its documented
contract.
**Decision.** `pytest_configure` now sets `DATABASE_URL` to an explicit, unreachable
`OFFLINE_SENTINEL_DATABASE_URL` (`offline.invalid` -- an RFC 2606 hostname guaranteed to fail DNS
resolution in <1s) instead of popping it, so an OS-level value always wins over `.env`'s fallback.
Verified end-to-end (not just the pure-function unit tests that missed this): a new regression
test calls the real `pytest_configure` hook against a clean environment, then builds a real
`Settings()` reading the real `.env` on disk, and asserts it never resolves to Neon --
`test_missing_test_database_url_cannot_fall_back_to_envs_neon_url`. Confirmed the guard also now
correctly REFUSES an explicit attempt to point `TEST_DATABASE_URL` at Neon (tested live this
session: `assert_safe_for_tests` raised `NeonGuardError` as designed).
**Alternatives rejected.** A sentinel on an unbound loopback port -- tried first, rejected: this
machine's environment lets the SYN sit until psycopg's ~15s connect_timeout fires, twice
(`connect_with_wakeup_retry`'s one retry), adding ~32s to every test run that calls
`check_database()`. `.invalid` fails in the DNS-resolution step, before any socket connect,
independent of local network/firewall behavior. Reading `TEST_DATABASE_URL` from `.env` as a
fallback (a second `reviewer` pass suggested this to close the resulting coverage gap -- the
`policy_chunks` DB tests now have zero executing coverage anywhere without a real
`TEST_DATABASE_URL` env var) -- implemented, measured, and reverted: on this machine, checking an
unreachable `localhost:5433` (docker down) takes ~30s per attempt, not an instant refusal, so the
fallback would add ~60s to every plain `pytest` run whenever docker is down. Worse than the
coverage gap it closed; documented as an accepted limitation in STATE.md instead.
**Date.** 2026-09-28

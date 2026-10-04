# psycopg blocked by Windows Application Control (and the pg8000 fallback)

**Symptom.** `import psycopg` (or anything that opens a DB connection: `alembic`, `make status`,
scripts) fails with `DLL load failed while importing pq: An Application Control policy has blocked
this file` / `libpq library not found`. Same family as the blocked `pytest.exe` console script.
It is intermittent -- it cleared in the 2026-09-28 session and was back on 2026-10-04.

**Detect (5 seconds).**
`.venv\Scripts\python -c "import psycopg"` -- an error means blocked, silence means fine.

**Fallback.** `pg8000` is pure Python, so there is no DLL to block. Set an env var for the command,
never edit `.env`:

    $env:PRICEPILOT_DB_DRIVER = "pg8000"
    .venv\Scripts\python -m alembic upgrade head
    .venv\Scripts\python scripts\sync_catalogue.py

`src/pricepilot/db.py::resolve_database_target` swaps the driver and translates the libpq-only
bits: pg8000 rejects `sslmode`/`channel_binding` in the URL and `connect_timeout` as a connect
arg, so it gets `ssl_context=ssl.create_default_context()` (Neon requires TLS) and `timeout`.

**Caveats.** The test suite is offline, so the pg8000 path is covered only by real runs
(ADR-0038). The VPS (Linux) has no such block -- use the default psycopg there.

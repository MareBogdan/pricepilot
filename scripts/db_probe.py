"""Read-only DB probe: public tables + products row count. Honours PRICEPILOT_DB_DRIVER."""

from __future__ import annotations

from sqlalchemy import text

from pricepilot.db import connect_with_wakeup_retry, get_engine


def main() -> None:
    with connect_with_wakeup_retry(get_engine()) as conn:
        print("driver:", get_engine().dialect.driver)
        tables = conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1")
        ).scalars()
        print("tables:", ", ".join(tables))
        print("products rows:", conn.execute(text("SELECT COUNT(*) FROM products")).scalar_one())


if __name__ == "__main__":
    main()

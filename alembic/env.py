"""Alembic environment. The database URL comes from .env, never from alembic.ini."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from pricepilot.config import get_settings
from pricepilot.db import NEON_CONNECT_TIMEOUT_SECONDS, connect_with_wakeup_retry
from pricepilot.models import Base

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # STEP 3 (session note 2026-09-12): Neon suspends compute after 5 minutes idle, and the
    # first migration run of the day is exactly the kind of one-off connection likely to hit
    # a cold start. connect_timeout gives the wake-up room; connect_with_wakeup_retry covers
    # the rest with one retry, so a scheduled run does not fail for no real reason.
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"connect_timeout": NEON_CONNECT_TIMEOUT_SECONDS},
    )
    with connect_with_wakeup_retry(connectable) as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

"""
Alembic environment for jubu_datastore.

Importing jubu_datastore registers every ORM model on the shared
BaseDatastore.Base metadata (datastore_factory imports all datastore modules),
so target_metadata below covers all tables.

The database URL is resolved from, in order:
  1. config.attributes["connection"] (programmatic use, e.g. scripts/verify_migrations.py)
  2. -x db_url=<url> on the alembic command line
  3. the DATABASE_URL environment variable

There is intentionally no default: the repo's .env points DATABASE_URL at a
live dev database, and it must never be migrated by accident.
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

import jubu_datastore

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = jubu_datastore.Base.metadata


def _database_url() -> str:
    url = config.get_main_option("sqlalchemy.url")
    if not url:
        url = context.get_x_argument(as_dictionary=True).get("db_url")
    if not url:
        url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "No database URL configured. Pass -x db_url=<url> or set the "
            "DATABASE_URL environment variable. alembic.ini deliberately has "
            "no default so the dev kidschat.db cannot be migrated by accident."
        )
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' (--sql) mode: emit SQL to stdout."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_with_connection(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection."""
    connection = config.attributes.get("connection")
    if connection is not None:
        _run_with_connection(connection)
        return

    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    try:
        with engine.connect() as conn:
            _run_with_connection(conn)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

"""
SUPERSEDED: converted to Alembic — see alembic/versions/ (baseline 0001,
legacy bridge 0002, data move 0003) and scripts/verify_migrations.py.
Kept only until the Alembic history is verified against production
databases; do not add new migration scripts to this folder.

Add `observed_interests.curiosity_signal` (Float, nullable).

Why: the per-topic curiosity pull (0-1) was computed each session but DROPPED at
session end. Persisting it (max seen) gives the durable `curiosity_mode` derivation
(ENG-347 Phase 3c) real evidence to aggregate. Additive + idempotent + nullable.

What it does:
  1. If `observed_interests` exists and lacks `curiosity_signal` -> ADD COLUMN.
  2. If already present, or table absent (fresh install creates it from the model) -> no-op.

Standalone script (does not import jubu_datastore). Loads .env from repo root.
Run from repo root:
  python migrations/observed_interests_002_add_curiosity_signal.py
Safe to run multiple times.
"""

from __future__ import annotations

import os

_env_loaded = False
try:
    from dotenv import load_dotenv

    _migrations_dir = os.path.dirname(os.path.abspath(__file__))
    _repo_root = os.path.dirname(_migrations_dir)
    _env_path = os.path.join(_repo_root, ".env")
    if os.path.isfile(_env_path):
        _env_loaded = load_dotenv(_env_path)
except ImportError:
    pass
except Exception as e:
    print(f"Warning: could not load .env: {e}")

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError


def _mask_url(url: str) -> str:
    if not url or "@" not in url:
        return url
    try:
        pre, rest = url.split("@", 1)
        if ":" in pre:
            scheme, rest2 = pre.split("://", 1)
            user = rest2.split(":")[0]
            return f"{scheme}://{user}:****@{rest}"
    except Exception:
        pass
    return "****"


def _table_exists(conn, engine, table_name: str) -> bool:
    try:
        if engine.dialect.name == "sqlite":
            cur = conn.execute(
                text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:t"),
                {"t": table_name},
            )
        else:
            cur = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = :t LIMIT 1"
                ),
                {"t": table_name},
            )
        return cur.fetchone() is not None
    except (OperationalError, Exception):
        conn.rollback()
        return False


def _column_exists(conn, engine, table_name: str, column_name: str) -> bool:
    try:
        if engine.dialect.name == "sqlite":
            cur = conn.execute(
                text(
                    f"SELECT 1 FROM pragma_table_info('{table_name}') "
                    f"WHERE name = '{column_name}'"
                )
            )
            return cur.fetchone() is not None
        else:
            conn.execute(text(f"SELECT {column_name} FROM {table_name} LIMIT 0"))
            return True
    except (OperationalError, Exception):
        conn.rollback()
        return False


def run(engine=None):
    if engine is None:
        default_url = "sqlite:///kidschat.db"
        url = os.environ.get("DATABASE_URL", default_url)
        print(f"Using DATABASE_URL: {_mask_url(url)}")
        engine = create_engine(url)

    table = "observed_interests"
    col = "curiosity_signal"

    with engine.connect() as conn:
        if not _table_exists(conn, engine, table):
            print(
                f"Table {table} does not exist; nothing to do "
                f"(fresh install will create {col} from the model)."
            )
            return
        if _column_exists(conn, engine, table, col):
            print(f"Column {table}.{col} already present; nothing to do.")
            return
        # DOUBLE PRECISION on Postgres; SQLite treats the type loosely.
        col_type = "DOUBLE PRECISION" if engine.dialect.name != "sqlite" else "REAL"
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
        conn.commit()
        print(f"Added column {table}.{col} ({col_type}).")

    print("curiosity_signal add-column migration complete.")


if __name__ == "__main__":
    run()

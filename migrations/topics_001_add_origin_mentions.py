"""
Add `origin` and `total_mentions` columns to the child_topics table.

These power the parent-app topic-bubble chart:
  - total_mentions -> bubble SIZE (frequency across sessions)
  - origin         -> bubble MARK/badge (child vs Buju)
(bubble COLOR is the existing last_observed_at.)

Standalone script: does not import jubu_datastore (avoids package
logging/asyncio issues). Loads .env from repo root for DATABASE_URL.
Run from repo root:
  python migrations/topics_001_add_origin_mentions.py
Idempotent: safe to run multiple times (skips columns that already exist).
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

TABLE = "child_topics"
# column name -> (sqlite type + default, postgres type + default)
COLUMNS = {
    "total_mentions": ("INTEGER NOT NULL DEFAULT 1", "INTEGER NOT NULL DEFAULT 1"),
    "origin": ("VARCHAR(8) NOT NULL DEFAULT 'child'", "VARCHAR(8) NOT NULL DEFAULT 'child'"),
}


def _mask_url(url: str) -> str:
    if not url or "@" not in url:
        return url
    try:
        pre, rest = url.split("@", 1)
        scheme, rest2 = pre.split("://", 1)
        user = rest2.split(":")[0]
        return f"{scheme}://{user}:****@{rest}"
    except Exception:
        return "****"


def _table_exists(conn, engine) -> bool:
    try:
        if engine.dialect.name == "sqlite":
            cur = conn.execute(
                text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:t"),
                {"t": TABLE},
            )
        else:
            cur = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables WHERE table_name = :t LIMIT 1"
                ),
                {"t": TABLE},
            )
        return cur.fetchone() is not None
    except (OperationalError, Exception):
        conn.rollback()
        return False


def _column_exists(conn, engine, column: str) -> bool:
    try:
        if engine.dialect.name == "sqlite":
            cur = conn.execute(
                text(f"SELECT 1 FROM pragma_table_info('{TABLE}') WHERE name = '{column}'")
            )
            return cur.fetchone() is not None
        conn.execute(text(f"SELECT {column} FROM {TABLE} LIMIT 0"))
        return True
    except (OperationalError, Exception):
        conn.rollback()
        return False


def run(engine=None):
    if engine is None:
        default_url = "sqlite:///kidschat.db"
        url = os.environ.get("DATABASE_URL", default_url)
        if url == default_url:
            print("Warning: DATABASE_URL not set; using default sqlite DB.")
        print(f"Using DATABASE_URL: {_mask_url(url)}")
        engine = create_engine(url)

    with engine.connect() as conn:
        if not _table_exists(conn, engine):
            print(f"Table {TABLE} does not exist; skipping (the app creates it).")
            return

        for column, (sqlite_def, pg_def) in COLUMNS.items():
            if _column_exists(conn, engine, column):
                print(f"Column {TABLE}.{column} already exists; skipping.")
                continue
            coldef = sqlite_def if engine.dialect.name == "sqlite" else pg_def
            conn.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN {column} {coldef}"))
            conn.commit()
            print(f"Added column {TABLE}.{column}.")


if __name__ == "__main__":
    run()

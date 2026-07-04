"""
Rename `child_profiles.interests` -> `child_profiles.parent_declared_interests`.

Why: "interests" was ambiguous. The parent app now renders TWO distinct signals:
the interests the PARENT explicitly declares (this column, Tier A / parent-owned)
and the interests the SYSTEM observes the child engage with (the separate
`observed_interests` ledger, Tier B). Keeping both called "interests" is a
footgun; the parent-declared field is renamed everywhere in code (ENG-347) and
this migration brings the column in line. The two are intentionally NOT merged.

What it does (idempotent, data-preserving):
  1. If `child_profiles.interests` exists and `parent_declared_interests` does
     not -> RENAME COLUMN (preserves all existing values).
  2. If already renamed -> no-op.
  3. Fresh installs (column already named, or table not present) -> no-op; the
     app's create_all() creates the column from ChildProfileModel directly.

Standalone script (does not import jubu_datastore; avoids package side effects).
Loads .env from repo root so DATABASE_URL is set.
Run from repo root:
  python migrations/profile_001_rename_interests_to_parent_declared.py
Safe to run multiple times.
"""

from __future__ import annotations

import os

# Load .env from repo root (parent of migrations/)
_env_loaded = False
try:
    from dotenv import load_dotenv

    _migrations_dir = os.path.dirname(os.path.abspath(__file__))
    _repo_root = os.path.dirname(_migrations_dir)
    _env_path = os.path.join(_repo_root, ".env")
    if os.path.isfile(_env_path):
        _env_loaded = load_dotenv(_env_path)
except ImportError:
    pass  # optional: run without dotenv if DATABASE_URL already in env
except Exception as e:
    print(f"Warning: could not load .env: {e}")

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError


def _mask_url(url: str) -> str:
    """Hide password in DATABASE_URL for diagnostic output."""
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
        if url == default_url and _env_loaded:
            print(
                "Warning: .env was loaded but DATABASE_URL is still default. "
                "Check .env for DATABASE_URL=..."
            )
        elif url == default_url:
            print(
                "Warning: DATABASE_URL not set; using default. Set DATABASE_URL in "
                ".env or environment to use your DB."
            )
        print(f"Using DATABASE_URL: {_mask_url(url)}")
        engine = create_engine(url)

    table = "child_profiles"
    old_col = "interests"
    new_col = "parent_declared_interests"

    with engine.connect() as conn:
        if not _table_exists(conn, engine, table):
            print(
                f"Table {table} does not exist; nothing to do "
                f"(fresh install will create {new_col} from the model)."
            )
            return

        if _column_exists(conn, engine, table, new_col):
            print(f"Column {table}.{new_col} already present; rename already applied.")
        elif _column_exists(conn, engine, table, old_col):
            # Both Postgres and modern SQLite (>=3.25) support RENAME COLUMN.
            conn.execute(
                text(f"ALTER TABLE {table} RENAME COLUMN {old_col} TO {new_col}")
            )
            conn.commit()
            print(f"Renamed column {table}.{old_col} -> {new_col}.")
        else:
            print(
                f"Neither {old_col} nor {new_col} found on {table}; "
                f"skipping column rename."
            )

    print("parent_declared_interests rename migration complete.")


if __name__ == "__main__":
    run()

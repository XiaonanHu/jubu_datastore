"""
Rename the child-interest ledger from `child_topics` to `observed_interests`.

Why: "topic" was overloaded across the codebase (story fan-out, safety
prohibited_topics, educational_topics, parent-summary categories). The durable,
parent-facing ledger of subjects a child actually engaged with is now named
`observed_interest` everywhere in code; this migration brings the table in line.

What it does (idempotent, data-preserving):
  1. If `child_topics` exists and `observed_interests` does not  -> RENAME TABLE.
  2. Rename column `topic_label` -> `interest_label` (if still present).
  3. Fresh installs (neither table yet) are a no-op — the app's create_all()
     will create `observed_interests` directly from ObservedInterestModel.

Standalone script (does not import jubu_datastore; avoids package side effects).
Loads .env from repo root so DATABASE_URL is set.
Run from repo root:
  python migrations/observed_interests_001_rename_from_child_topics.py
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

    old_table = "child_topics"
    new_table = "observed_interests"
    old_col = "topic_label"
    new_col = "interest_label"

    with engine.connect() as conn:
        old_exists = _table_exists(conn, engine, old_table)
        new_exists = _table_exists(conn, engine, new_table)

        # 1) Rename the table.
        if new_exists and not old_exists:
            print(f"Table {new_table} already exists; rename already applied.")
        elif old_exists and new_exists:
            print(
                f"Both {old_table} and {new_table} exist — not renaming. "
                f"Resolve manually (data may be split across two tables)."
            )
            return
        elif old_exists and not new_exists:
            conn.execute(text(f"ALTER TABLE {old_table} RENAME TO {new_table}"))
            conn.commit()
            print(f"Renamed table {old_table} -> {new_table}.")
        else:
            print(
                f"Neither {old_table} nor {new_table} exists; nothing to do "
                f"(fresh install will create {new_table} from the model)."
            )
            return

        # 2) Rename the column topic_label -> interest_label (if still old).
        if _column_exists(conn, engine, new_table, new_col):
            print(f"Column {new_table}.{new_col} already present; column rename done.")
        elif _column_exists(conn, engine, new_table, old_col):
            # Both Postgres and modern SQLite (>=3.25) support RENAME COLUMN.
            conn.execute(
                text(f"ALTER TABLE {new_table} RENAME COLUMN {old_col} TO {new_col}")
            )
            conn.commit()
            print(f"Renamed column {new_table}.{old_col} -> {new_col}.")
        else:
            print(
                f"Neither {old_col} nor {new_col} found on {new_table}; "
                f"skipping column rename."
            )

    print("observed_interests rename migration complete.")


if __name__ == "__main__":
    run()

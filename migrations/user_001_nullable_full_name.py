"""
Make users.full_name nullable.

Parents may provide only a first/preferred name (optional), so full_name
no longer has a NOT NULL constraint.

Run from repo root:
  python migrations/user_001_nullable_full_name.py
Idempotent: safe to run multiple times.
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


def run(engine=None):
    if engine is None:
        default_url = "sqlite:///kidschat.db"
        url = os.environ.get("DATABASE_URL", default_url)
        if url == default_url:
            print("Warning: DATABASE_URL not set; using default sqlite:///kidschat.db")
        print(f"Using DATABASE_URL: {_mask_url(url)}")
        engine = create_engine(url)

    with engine.connect() as conn:
        dialect = engine.dialect.name

        # Check the table exists
        try:
            if dialect == "sqlite":
                r = conn.execute(
                    text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'")
                )
            else:
                r = conn.execute(
                    text(
                        "SELECT 1 FROM information_schema.tables "
                        "WHERE table_schema = current_schema() AND table_name = 'users' LIMIT 1"
                    )
                )
            if r.fetchone() is None:
                print("Table users does not exist; skipping.")
                return
        except (OperationalError, Exception) as e:
            conn.rollback()
            print(f"Could not check users table: {e}; skipping.")
            return

        if dialect == "sqlite":
            # SQLite does not enforce NOT NULL on existing columns; no DDL needed.
            print("SQLite detected: NOT NULL is not enforced on existing columns; no DDL required.")
            return

        # PostgreSQL: check if already nullable
        try:
            r = conn.execute(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_schema = current_schema() "
                    "AND table_name = 'users' AND column_name = 'full_name'"
                )
            )
            row = r.fetchone()
            if row is None:
                print("Column users.full_name not found; skipping.")
                return
            if row[0].upper() == "YES":
                print("Column users.full_name is already nullable; skipping.")
                return
        except (OperationalError, Exception) as e:
            conn.rollback()
            print(f"Could not inspect users.full_name: {e}; skipping.")
            return

        conn.execute(text("ALTER TABLE users ALTER COLUMN full_name DROP NOT NULL"))
        conn.commit()
        print("Altered users.full_name to be nullable.")


if __name__ == "__main__":
    run()

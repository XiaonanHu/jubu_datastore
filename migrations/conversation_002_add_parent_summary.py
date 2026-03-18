"""
Add parent_summary column to conversations table.

Standalone script: does not import jubu_datastore (avoids package logging/asyncio issues).
Loads .env from repo root so DATABASE_URL, DEMO_CHILD_ID, DEMO_PARENT_ID are set.
Run from repo root:
  python migrations/conversation_002_add_parent_summary.py
Idempotent: safe to run multiple times (skips if column already exists).
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


def _diagnostic(engine, table_name: str) -> None:
    """Print conversation counts for DEMO_CHILD_ID and DEMO_PARENT_ID if set."""
    demo_child = os.environ.get("DEMO_CHILD_ID", "").strip()
    demo_parent = os.environ.get("DEMO_PARENT_ID", "").strip()
    if not demo_child and not demo_parent:
        return
    with engine.connect() as conn:
        dialect = engine.dialect.name
        if demo_child:
            if dialect == "sqlite":
                r = conn.execute(
                    text("SELECT COUNT(*) FROM conversations WHERE child_id = :c"),
                    {"c": demo_child},
                )
            else:
                r = conn.execute(
                    text("SELECT COUNT(*) FROM conversations WHERE child_id = :c"),
                    {"c": demo_child},
                )
            count = r.scalar() or 0
            print(f"DEMO_CHILD_ID: {demo_child} -> {count} conversation(s)")
        if demo_parent:
            # Resolve children for this parent via child_profiles
            try:
                if dialect == "sqlite":
                    r = conn.execute(
                        text(
                            "SELECT id FROM child_profiles WHERE parent_id = :p AND is_active = 1"
                        ),
                        {"p": demo_parent},
                    )
                else:
                    r = conn.execute(
                        text(
                            "SELECT id FROM child_profiles WHERE parent_id = :p AND is_active = true"
                        ),
                        {"p": demo_parent},
                    )
                child_ids = [row[0] for row in r.fetchall()]
            except (OperationalError, Exception):
                conn.rollback()
                print("DEMO_PARENT_ID: could not read child_profiles (table missing or error)")
                return
            if not child_ids:
                print(f"DEMO_PARENT_ID: {demo_parent} -> 0 children, 0 conversations")
                return
            # Count conversations for those children
            placeholders = ", ".join([f":c{i}" for i in range(len(child_ids))])
            params = {f"c{i}": cid for i, cid in enumerate(child_ids)}
            try:
                r = conn.execute(
                    text(f"SELECT COUNT(*) FROM conversations WHERE child_id IN ({placeholders})"),
                    params,
                )
                total = r.scalar() or 0
            except (OperationalError, Exception):
                conn.rollback()
                print(f"DEMO_PARENT_ID: {demo_parent} -> {len(child_ids)} child(ren), conversation count error")
                return
            print(f"DEMO_PARENT_ID: {demo_parent} -> {len(child_ids)} child(ren), {total} conversation(s)")


def run(engine=None):
    if engine is None:
        default_url = "sqlite:///kidschat.db"
        url = os.environ.get("DATABASE_URL", default_url)
        if url == default_url and _env_loaded:
            print("Warning: .env was loaded but DATABASE_URL is still default. Check .env for DATABASE_URL=...")
        elif url == default_url:
            print("Warning: DATABASE_URL not set; using default. Set DATABASE_URL in .env or environment to use your DB.")
        print(f"Using DATABASE_URL: {_mask_url(url)}")
        engine = create_engine(url)

    column_name = "parent_summary"
    table_name = "conversations"

    with engine.connect() as conn:
        # Check table exists (skip if app has not created it yet)
        try:
            if engine.dialect.name == "sqlite":
                cur = conn.execute(
                    text(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=:t"
                    ),
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
            if cur.fetchone() is None:
                print(f"Table {table_name} does not exist; skipping (create it first).")
                return
        except (OperationalError, Exception):
            conn.rollback()
            print(f"Table {table_name} does not exist or not accessible; skipping.")
            return

        _diagnostic(engine, table_name)

        # Idempotent: check if column exists (dialect-specific)
        try:
            if engine.dialect.name == "sqlite":
                cursor = conn.execute(
                    text(
                        f"SELECT 1 FROM pragma_table_info('{table_name}') WHERE name = '{column_name}'"
                    )
                )
                col_exists = cursor.fetchone() is not None
            else:
                conn.execute(
                    text(f"SELECT {column_name} FROM {table_name} LIMIT 0")
                )
                col_exists = True
        except (OperationalError, Exception):
            conn.rollback()
            col_exists = False

        if col_exists:
            print(f"Column {table_name}.{column_name} already exists; skipping.")
            return

        conn.execute(
            text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} TEXT")
        )
        conn.commit()
        print(f"Added column {table_name}.{column_name}.")


if __name__ == "__main__":
    run()

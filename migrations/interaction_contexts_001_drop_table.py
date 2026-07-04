"""
SUPERSEDED: converted to Alembic — see alembic/versions/ (baseline 0001,
legacy bridge 0002, data move 0003) and scripts/verify_migrations.py.
Kept only until the Alembic history is verified against production
databases; do not add new migration scripts to this folder.

Drop the `interaction_contexts` table.

Why: the InteractionContextsDatastore was dead code — no production code path
ever wrote a row (zero save_interaction_context / update_context_data call
sites), and the single read site in conversation_manager always got an empty
list. The class, factory entry, and read path were deleted; this migration
removes the (empty) table so it stops being auto-created and can't hold
orphan child data.

What it does (idempotent):
  1. If `interaction_contexts` exists -> DROP TABLE.
  2. Fresh installs are a no-op — the model no longer exists, so create_all()
     never creates the table.

Standalone script (does not import jubu_datastore; avoids package side effects).
Loads .env from repo root so DATABASE_URL is set.
Run from repo root:
  python migrations/interaction_contexts_001_drop_table.py
Safe to run multiple times.
"""

from __future__ import annotations

import os

# Load .env from repo root (parent of migrations/)
try:
    from dotenv import load_dotenv

    _migrations_dir = os.path.dirname(os.path.abspath(__file__))
    _repo_root = os.path.dirname(_migrations_dir)
    _env_path = os.path.join(_repo_root, ".env")
    if os.path.isfile(_env_path):
        load_dotenv(_env_path)
except ImportError:
    pass  # optional: run without dotenv if DATABASE_URL already in env

from sqlalchemy import create_engine, text


def _table_exists(conn, engine, table_name: str) -> bool:
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


def main() -> None:
    database_url = os.environ.get("DATABASE_URL", "sqlite:///kidschat.db")
    engine = create_engine(database_url)
    with engine.begin() as conn:
        if _table_exists(conn, engine, "interaction_contexts"):
            row_count = conn.execute(
                text("SELECT COUNT(*) FROM interaction_contexts")
            ).scalar()
            if row_count:
                # Should be impossible (no writer ever existed) — refuse to
                # silently destroy data if this assumption is somehow wrong.
                raise RuntimeError(
                    f"interaction_contexts has {row_count} rows; expected 0. "
                    f"Investigate before dropping."
                )
            conn.execute(text("DROP TABLE interaction_contexts"))
            print("Dropped empty table interaction_contexts.")
        else:
            print("Table interaction_contexts does not exist — nothing to do.")


if __name__ == "__main__":
    main()

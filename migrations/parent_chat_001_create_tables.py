"""
Create parent_chat_sessions, parent_chat_messages, and parent_chat_rolling_summary tables.

Run from repo root:
  python migrations/parent_chat_001_create_tables.py
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


def _table_exists(conn, table_name: str) -> bool:
    dialect = conn.engine.dialect.name
    try:
        if dialect == "sqlite":
            r = conn.execute(
                text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:t"),
                {"t": table_name},
            )
        else:
            r = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = current_schema() AND table_name = :t LIMIT 1"
                ),
                {"t": table_name},
            )
        return r.fetchone() is not None
    except (OperationalError, Exception):
        conn.rollback()
        return False


def _create_sessions_table(conn) -> None:
    if _table_exists(conn, "parent_chat_sessions"):
        print("Table parent_chat_sessions already exists; skipping.")
        return
    dialect = conn.engine.dialect.name
    bool_type = "INTEGER" if dialect == "sqlite" else "BOOLEAN"
    conn.execute(text(f"""
        CREATE TABLE parent_chat_sessions (
            id VARCHAR(36) PRIMARY KEY,
            parent_id VARCHAR(36) NOT NULL,
            child_id VARCHAR(36) NOT NULL,
            scenario_key VARCHAR(100),
            created_at TIMESTAMP NOT NULL,
            last_message_at TIMESTAMP NOT NULL,
            is_active {bool_type} NOT NULL DEFAULT {'1' if dialect == 'sqlite' else 'TRUE'},
            summary TEXT,
            summary_generated_at TIMESTAMP
        )
    """))
    conn.execute(text(
        "CREATE INDEX idx_pcs_parent_active ON parent_chat_sessions (parent_id, is_active)"
    ))
    conn.execute(text(
        "CREATE INDEX idx_pcs_parent_created ON parent_chat_sessions (parent_id, created_at)"
    ))
    conn.commit()
    print("Created table parent_chat_sessions.")


def _create_messages_table(conn) -> None:
    if _table_exists(conn, "parent_chat_messages"):
        print("Table parent_chat_messages already exists; skipping.")
        return
    conn.execute(text("""
        CREATE TABLE parent_chat_messages (
            id VARCHAR(36) PRIMARY KEY,
            session_id VARCHAR(36) NOT NULL REFERENCES parent_chat_sessions(id) ON DELETE CASCADE,
            role VARCHAR(20) NOT NULL,
            content TEXT NOT NULL,
            timestamp TIMESTAMP NOT NULL
        )
    """))
    conn.execute(text(
        "CREATE INDEX idx_pcm_session_time ON parent_chat_messages (session_id, timestamp)"
    ))
    conn.commit()
    print("Created table parent_chat_messages.")


def _create_rolling_summary_table(conn) -> None:
    if _table_exists(conn, "parent_chat_rolling_summary"):
        print("Table parent_chat_rolling_summary already exists; skipping.")
        return
    conn.execute(text("""
        CREATE TABLE parent_chat_rolling_summary (
            id VARCHAR(36) PRIMARY KEY,
            parent_id VARCHAR(36) NOT NULL,
            child_id VARCHAR(36) NOT NULL,
            summary TEXT NOT NULL,
            session_count INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMP NOT NULL,
            UNIQUE (parent_id, child_id)
        )
    """))
    conn.commit()
    print("Created table parent_chat_rolling_summary.")


def run(engine=None):
    if engine is None:
        default_url = "sqlite:///kidschat.db"
        url = os.environ.get("DATABASE_URL", default_url)
        if url == default_url:
            print("Warning: DATABASE_URL not set; using default sqlite:///kidschat.db")
        print(f"Using DATABASE_URL: {_mask_url(url)}")
        engine = create_engine(url)

    with engine.connect() as conn:
        _create_sessions_table(conn)
        _create_messages_table(conn)
        _create_rolling_summary_table(conn)

    print("Migration parent_chat_001 complete.")


if __name__ == "__main__":
    run()

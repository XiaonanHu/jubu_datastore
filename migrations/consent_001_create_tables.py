"""
Create consent_events and subscriptions tables.

Run from repo root:
  python migrations/consent_001_create_tables.py
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


def _create_consent_events_table(conn) -> None:
    if _table_exists(conn, "consent_events"):
        print("Table consent_events already exists; skipping.")
        return
    dialect = conn.engine.dialect.name
    json_type = "TEXT" if dialect == "sqlite" else "JSONB"
    conn.execute(text(f"""
        CREATE TABLE consent_events (
            event_id VARCHAR(36) PRIMARY KEY,
            parent_id VARCHAR(36) NOT NULL,
            event_type VARCHAR(64) NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            ip_address VARCHAR(64),
            user_agent TEXT,
            direct_notice_version VARCHAR(64),
            privacy_policy_version VARCHAR(32),
            vpc_method VARCHAR(32),
            apple_transaction_id VARCHAR(255),
            child_id VARCHAR(36),
            failure_reason VARCHAR(255),
            event_metadata {json_type},
            created_at TIMESTAMP NOT NULL
        )
    """))
    conn.execute(text("CREATE INDEX idx_consent_parent_id ON consent_events (parent_id)"))
    conn.execute(text("CREATE INDEX idx_consent_event_type ON consent_events (event_type)"))
    conn.execute(text("CREATE INDEX idx_consent_timestamp ON consent_events (timestamp DESC)"))
    conn.commit()
    print("Created table consent_events.")


def _create_subscriptions_table(conn) -> None:
    if _table_exists(conn, "subscriptions"):
        print("Table subscriptions already exists; skipping.")
        return
    conn.execute(text("""
        CREATE TABLE subscriptions (
            subscription_id VARCHAR(36) PRIMARY KEY,
            parent_id VARCHAR(36) NOT NULL,
            apple_transaction_id VARCHAR(255) NOT NULL UNIQUE,
            apple_original_transaction_id VARCHAR(255) NOT NULL,
            product_id VARCHAR(128) NOT NULL,
            purchase_date TIMESTAMP NOT NULL,
            expires_date TIMESTAMP,
            status VARCHAR(32) NOT NULL DEFAULT 'active',
            receipt_data TEXT,
            created_at TIMESTAMP NOT NULL
        )
    """))
    conn.execute(text("CREATE INDEX idx_sub_parent_id ON subscriptions (parent_id)"))
    conn.commit()
    print("Created table subscriptions.")


def run(engine=None):
    if engine is None:
        default_url = "sqlite:///kidschat.db"
        url = os.environ.get("DATABASE_URL", default_url)
        if url == default_url:
            print("Warning: DATABASE_URL not set; using default sqlite:///kidschat.db")
        print(f"Using DATABASE_URL: {_mask_url(url)}")
        engine = create_engine(url)

    with engine.connect() as conn:
        _create_consent_events_table(conn)
        _create_subscriptions_table(conn)

    print("Migration consent_001 complete.")


if __name__ == "__main__":
    run()

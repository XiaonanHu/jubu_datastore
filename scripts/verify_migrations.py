"""
Verify the Alembic migration history end to end.

For each reachable backend (scratch SQLite always; scratch PostgreSQL when a
server is reachable, otherwise skipped with a note):

  1. `alembic upgrade head` from an empty database
  2. assert zero schema drift between the migrated database and the ORM
     models (alembic autogenerate comparison)
  3. `alembic downgrade base`; assert every table is gone
  4. `alembic upgrade head` again

Additionally, on SQLite, a synthetic pre-Alembic "legacy" database is built
(child_topics with topic_label, conversations without the parent_* columns,
users.full_name NOT NULL, child_profiles.interests, an empty
interaction_contexts table, voice_style_scores inside preferences), stamped
at 0001 and upgraded to head; the bridge (0002) and data move (0003) results
are then asserted row by row.

Exit code 0 means everything passed.

Usage:
  python scripts/verify_migrations.py

PostgreSQL target defaults to a local trust-auth server
(postgresql+psycopg2://localhost:5432/postgres); override with VERIFY_PG_URL.
A scratch database is created there and dropped afterwards.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata

import jubu_datastore

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEAD = "0003"

PASS = "  ok:"
_failures: list[str] = []


def check(condition: bool, label: str) -> None:
    if condition:
        print(f"{PASS} {label}")
    else:
        _failures.append(label)
        print(f"  FAIL: {label}")


def make_config(connection) -> Config:
    cfg = Config(os.path.join(REPO_ROOT, "alembic.ini"))
    cfg.attributes["connection"] = connection
    return cfg


def current_revision(connection) -> str | None:
    return MigrationContext.configure(connection).get_current_revision()


def upgrade_downgrade_cycle(engine: sa.Engine, backend: str) -> None:
    """Empty DB -> head -> drift check -> base -> head."""
    print(f"\n[{backend}] upgrade/downgrade cycle")

    with engine.connect() as conn:
        command.upgrade(make_config(conn), "head")
        conn.commit()

    with engine.connect() as conn:
        check(current_revision(conn) == HEAD, f"upgrade head from empty -> revision {HEAD}")
        tables = set(sa.inspect(conn).get_table_names())
        expected = set(jubu_datastore.Base.metadata.tables)
        check(
            expected <= tables,
            f"all {len(expected)} model tables present after upgrade",
        )

        diffs = compare_metadata(
            MigrationContext.configure(conn, opts={"compare_type": True}),
            jubu_datastore.Base.metadata,
        )
        check(not diffs, "zero autogenerate drift between migrated schema and ORM models")
        if diffs:
            for d in diffs:
                print(f"    drift: {d}")

    with engine.connect() as conn:
        command.downgrade(make_config(conn), "base")
        conn.commit()

    with engine.connect() as conn:
        check(current_revision(conn) is None, "downgrade base -> no current revision")
        leftover = set(sa.inspect(conn).get_table_names()) - {"alembic_version"}
        check(not leftover, f"no tables left after downgrade (leftover: {sorted(leftover) or 'none'})")

    with engine.connect() as conn:
        command.upgrade(make_config(conn), "head")
        conn.commit()

    with engine.connect() as conn:
        check(current_revision(conn) == HEAD, f"second upgrade head -> revision {HEAD}")


LEGACY_DDL = [
    """
    CREATE TABLE users (
        id VARCHAR(36) PRIMARY KEY,
        email VARCHAR(255) NOT NULL,
        full_name VARCHAR(255) NOT NULL,
        hashed_password VARCHAR(255) NOT NULL,
        is_active BOOLEAN NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL
    )
    """,
    """
    CREATE TABLE conversations (
        id VARCHAR(36) PRIMARY KEY,
        child_id VARCHAR(36) NOT NULL,
        state VARCHAR(20) NOT NULL,
        start_time DATETIME NOT NULL,
        end_time DATETIME,
        last_interaction_time DATETIME NOT NULL,
        conv_metadata JSON,
        is_archived BOOLEAN NOT NULL
    )
    """,
    """
    CREATE TABLE child_profiles (
        id VARCHAR(36) PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        age INTEGER NOT NULL,
        interests JSON NOT NULL,
        preferences JSON NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        parent_id VARCHAR(36),
        is_active BOOLEAN NOT NULL,
        last_interaction DATETIME
    )
    """,
    """
    CREATE TABLE child_topics (
        id VARCHAR(36) PRIMARY KEY,
        child_id VARCHAR(36) NOT NULL,
        canonical_key VARCHAR(120) NOT NULL,
        topic_label VARCHAR(120) NOT NULL,
        kind VARCHAR(32) NOT NULL,
        framework_link VARCHAR(255),
        times_visited INTEGER NOT NULL,
        first_session_id VARCHAR(36),
        last_session_id VARCHAR(36),
        first_observed_at DATETIME NOT NULL,
        last_observed_at DATETIME NOT NULL,
        last_depth INTEGER NOT NULL,
        breadth_count INTEGER NOT NULL,
        sentiment VARCHAR(16),
        status VARCHAR(16) NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL
    )
    """,
    "CREATE TABLE interaction_contexts (id VARCHAR(36) PRIMARY KEY, context_data JSON)",
]

VOICE_SCORES = {"robo": {"n": 2, "score": 0.7}, "wizard": {"n": 1, "score": 0.4}}


def legacy_bridge_check(engine: sa.Engine) -> None:
    """Synthetic pre-Alembic DB -> stamp 0001 -> upgrade head -> assert results."""
    print("\n[sqlite] legacy pre-Alembic bridge (0002 + 0003)")

    with engine.begin() as conn:
        for ddl in LEGACY_DDL:
            conn.execute(sa.text(ddl))
        now = "2026-01-01 00:00:00"
        conn.execute(
            sa.text(
                "INSERT INTO users VALUES ('u1', 'p@example.com', 'Pat Parent', 'x', 1, :t, :t)"
            ),
            {"t": now},
        )
        conn.execute(
            sa.text(
                "INSERT INTO conversations VALUES ('conv1', 'c1', 'ended', :t, :t, :t, NULL, 0)"
            ),
            {"t": now},
        )
        conn.execute(
            sa.text(
                "INSERT INTO child_profiles VALUES "
                "('c1', 'Kiddo', 6, :interests, :prefs, :t, :t, 'u1', 1, NULL)"
            ),
            {
                "interests": json.dumps(["space"]),
                "prefs": json.dumps({"voice_style": "warm", "voice_style_scores": VOICE_SCORES}),
                "t": now,
            },
        )
        conn.execute(
            sa.text(
                "INSERT INTO child_topics VALUES "
                "('t1', 'c1', 'dinosaurs', 'Dinosaurs', 'science', NULL, 3, "
                "'s1', 's2', :t, :t, 2, 1, 'positive', 'active', :t, :t)"
            ),
            {"t": now},
        )

    with engine.connect() as conn:
        command.stamp(make_config(conn), "0001")
        conn.commit()
    with engine.connect() as conn:
        command.upgrade(make_config(conn), "head")
        conn.commit()

    with engine.connect() as conn:
        insp = sa.inspect(conn)
        tables = set(insp.get_table_names())

        check("child_topics" not in tables, "child_topics renamed away")
        check("interaction_contexts" not in tables, "interaction_contexts dropped")
        for t in (
            "observed_interests",
            "parent_chat_sessions",
            "parent_chat_messages",
            "parent_chat_rolling_summary",
            "consent_events",
            "subscriptions",
            "child_capability_observations",
            "child_capability_state",
            "inferred_traits",
        ):
            check(t in tables, f"table {t} present after bridge")

        oi_cols = {c["name"] for c in insp.get_columns("observed_interests")}
        check(
            {"interest_label", "total_mentions", "origin", "curiosity_signal"} <= oi_cols
            and "topic_label" not in oi_cols,
            "observed_interests columns renamed/added",
        )
        row = conn.execute(
            sa.text(
                "SELECT interest_label, total_mentions, origin, times_visited "
                "FROM observed_interests WHERE id = 't1'"
            )
        ).one()
        check(
            tuple(row) == ("Dinosaurs", 1, "child", 3),
            f"observed_interests data preserved through rename (got {tuple(row)})",
        )

        conv_cols = {c["name"] for c in insp.get_columns("conversations")}
        check(
            {"parent_summary", "parent_highlights"} <= conv_cols,
            "conversations.parent_summary/parent_highlights added",
        )

        full_name = next(c for c in insp.get_columns("users") if c["name"] == "full_name")
        check(bool(full_name["nullable"]), "users.full_name made nullable")

        cp_cols = {c["name"] for c in insp.get_columns("child_profiles")}
        check(
            "parent_declared_interests" in cp_cols and "interests" not in cp_cols,
            "child_profiles.interests renamed to parent_declared_interests",
        )

        prefs = json.loads(
            conn.execute(
                sa.text("SELECT preferences FROM child_profiles WHERE id = 'c1'")
            ).scalar_one()
        )
        check(
            "voice_style_scores" not in prefs and prefs.get("voice_style") == "warm",
            "voice_style_scores removed from preferences, parent override kept",
        )

        traits = conn.execute(
            sa.text(
                "SELECT voice_style_scores, preferred_style, evidence_count "
                "FROM inferred_traits WHERE child_id = 'c1'"
            )
        ).one()
        check(
            json.loads(traits[0]) == VOICE_SCORES and traits[1] == "robo" and traits[2] == 1,
            f"voice_style_scores moved into inferred_traits (got {tuple(traits)})",
        )


def run_sqlite() -> None:
    with tempfile.TemporaryDirectory(prefix="alembic_verify_") as tmp:
        engine = sa.create_engine(f"sqlite:///{os.path.join(tmp, 'cycle.db')}")
        try:
            upgrade_downgrade_cycle(engine, "sqlite")
        finally:
            engine.dispose()

        legacy_engine = sa.create_engine(f"sqlite:///{os.path.join(tmp, 'legacy.db')}")
        try:
            legacy_bridge_check(legacy_engine)
        finally:
            legacy_engine.dispose()


def run_postgresql() -> None:
    admin_url = os.environ.get("VERIFY_PG_URL", "postgresql+psycopg2://localhost:5432/postgres")

    try:
        admin_engine = sa.create_engine(
            admin_url, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 3}
        )
        with admin_engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
    except Exception as exc:
        print(f"\n[postgresql] SKIPPED — server not reachable at {admin_url}: {exc}")
        return

    scratch = f"jubu_alembic_verify_{uuid.uuid4().hex[:8]}"
    with admin_engine.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{scratch}"'))
    print(f"\n[postgresql] created scratch database {scratch}")

    scratch_url = sa.engine.make_url(admin_url).set(database=scratch)
    engine = sa.create_engine(scratch_url, poolclass=sa.pool.NullPool)
    try:
        upgrade_downgrade_cycle(engine, "postgresql")
    finally:
        engine.dispose()
        with admin_engine.connect() as conn:
            conn.execute(sa.text(f'DROP DATABASE "{scratch}"'))
        admin_engine.dispose()
        print(f"[postgresql] dropped scratch database {scratch}")


def main() -> int:
    run_sqlite()
    run_postgresql()

    print()
    if _failures:
        print(f"FAILED: {len(_failures)} check(s) failed")
        for f in _failures:
            print(f"  - {f}")
        return 1
    print("All migration verification checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""legacy bridge: align pre-Alembic databases with the 0001 baseline.

Converts the intent of the manual schema scripts in migrations/ into the
Alembic history. Every step is conditional and idempotent, so on a fresh
database created by 0001 this whole revision is a no-op. On a pre-Alembic
database (schema built by create_all + some subset of the manual scripts,
then stamped at 0001) it applies whatever is still missing, in the original
chronological order:

  1. capability_001_initial ............ create capability tables if missing
  2. conversation_002_add_parent_summary  add conversations.parent_summary
  3. parent_chat_001_create_tables ..... create parent_chat_* tables if missing
  4. consent_001_create_tables ......... create consent_events/subscriptions
  5. topics_001_add_origin_mentions .... add child_topics.total_mentions/origin
  6. conversation_003_add_parent_highlights  add conversations.parent_highlights
     (legacy script used JSONB on Postgres; this uses sa.JSON to match the
     model — functionally equivalent for our read/write paths)
  7. observed_interests_001_rename ..... child_topics -> observed_interests,
                                         topic_label -> interest_label
  8. user_001_nullable_full_name ....... drop NOT NULL on users.full_name
  9. profile_001_rename_interests ...... interests -> parent_declared_interests
 10. observed_interests_002 ............ add observed_interests.curiosity_signal
 11. inferred_traits_001 (schema part).. create inferred_traits if missing
                                         (the original data script created it
                                         as a side effect of constructing the
                                         datastore; the data move itself is
                                         revision 0003)
 12. interaction_contexts_001_drop ..... drop dead interaction_contexts table
                                         (refuses if it unexpectedly has rows)

Tables never covered by a manual script (telemetry_events and the core
create_all-era tables) are not created here: on any maintained legacy
database they already exist, and the runtime's _ensure_schema()/create_all
continues to self-create runtime-owned tables exactly as before.

downgrade() is intentionally a no-op: the pre-legacy state differs per
deployment and cannot be reconstructed, and on fresh databases (where the
upgrade did nothing) reversing renames would corrupt the 0001 downgrade path.
A no-op is the only downgrade that is correct in both cases.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-03

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return _inspector().has_table(name)


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in _inspector().get_columns(table))


def _create_capability_tables() -> None:
    """migrations/capability_001_initial.py (2026-03-16). Frozen DDL as of 0001."""
    if not _has_table("child_capability_observations"):
        op.create_table(
            "child_capability_observations",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("child_id", sa.String(length=36), nullable=False),
            sa.Column("session_id", sa.String(length=255), nullable=False),
            sa.Column("item_id", sa.String(length=255), nullable=False),
            sa.Column("item_version", sa.Integer(), nullable=False),
            sa.Column("framework", sa.String(length=64), nullable=False),
            sa.Column("domain", sa.String(length=64), nullable=False),
            sa.Column("subdomain", sa.String(length=64), nullable=False),
            sa.Column("observation_status", sa.String(length=64), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("evidence_text", sa.Text(), nullable=True),
            sa.Column("evaluator_type", sa.String(length=64), nullable=False),
            sa.Column("evaluator_version", sa.String(length=64), nullable=True),
            sa.Column("raw_score_json", sa.JSON(), nullable=True),
            sa.Column("observed_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "idx_obs_child_framework",
            "child_capability_observations",
            ["child_id", "framework"],
        )
        op.create_index(
            "idx_obs_child_item",
            "child_capability_observations",
            ["child_id", "item_id"],
        )
        op.create_index("idx_obs_item_id", "child_capability_observations", ["item_id"])
        op.create_index(
            "idx_obs_session", "child_capability_observations", ["session_id"]
        )
        op.create_index(
            "ix_child_capability_observations_child_id",
            "child_capability_observations",
            ["child_id"],
        )
        op.create_index(
            "ix_child_capability_observations_framework",
            "child_capability_observations",
            ["framework"],
        )
        op.create_index(
            "ix_child_capability_observations_observed_at",
            "child_capability_observations",
            ["observed_at"],
        )
        op.create_index(
            "ix_child_capability_observations_session_id",
            "child_capability_observations",
            ["session_id"],
        )

    if not _has_table("child_capability_state"):
        op.create_table(
            "child_capability_state",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("child_id", sa.String(length=36), nullable=False),
            sa.Column("item_id", sa.String(length=255), nullable=False),
            sa.Column("item_version", sa.Integer(), nullable=False),
            sa.Column("framework", sa.String(length=64), nullable=False),
            sa.Column("domain", sa.String(length=64), nullable=False),
            sa.Column("subdomain", sa.String(length=64), nullable=False),
            sa.Column("current_status", sa.String(length=64), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("mastery_score", sa.Float(), nullable=False),
            sa.Column("evidence_count", sa.Integer(), nullable=False),
            sa.Column("first_observed_at", sa.DateTime(), nullable=True),
            sa.Column("last_observed_at", sa.DateTime(), nullable=True),
            sa.Column("last_session_id", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.CheckConstraint(
                "mastery_score >= 0 AND mastery_score <= 1",
                name="chk_mastery_score_range",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "child_id", "item_id", name="uq_child_capability_state_child_item"
            ),
        )
        op.create_index(
            "idx_state_child_framework",
            "child_capability_state",
            ["child_id", "framework"],
        )
        op.create_index(
            "idx_state_child_item", "child_capability_state", ["child_id", "item_id"]
        )
        op.create_index(
            "ix_child_capability_state_child_id", "child_capability_state", ["child_id"]
        )
        op.create_index(
            "ix_child_capability_state_framework",
            "child_capability_state",
            ["framework"],
        )
        op.create_index(
            "ix_child_capability_state_item_id", "child_capability_state", ["item_id"]
        )


def _add_parent_summary() -> None:
    """migrations/conversation_002_add_parent_summary.py (2026-03-17)."""
    if _has_table("conversations") and not _has_column(
        "conversations", "parent_summary"
    ):
        op.add_column(
            "conversations", sa.Column("parent_summary", sa.Text(), nullable=True)
        )


def _create_parent_chat_tables() -> None:
    """migrations/parent_chat_001_create_tables.py (2026-05-27). Frozen DDL as of 0001."""
    if not _has_table("parent_chat_sessions"):
        op.create_table(
            "parent_chat_sessions",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("parent_id", sa.String(length=36), nullable=False),
            sa.Column("child_id", sa.String(length=36), nullable=False),
            sa.Column("scenario_key", sa.String(length=100), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("last_message_at", sa.DateTime(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("summary_generated_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "idx_pcs_parent_active", "parent_chat_sessions", ["parent_id", "is_active"]
        )
        op.create_index(
            "idx_pcs_parent_created",
            "parent_chat_sessions",
            ["parent_id", "created_at"],
        )
        op.create_index(
            "ix_parent_chat_sessions_child_id", "parent_chat_sessions", ["child_id"]
        )
        op.create_index(
            "ix_parent_chat_sessions_parent_id", "parent_chat_sessions", ["parent_id"]
        )

    if not _has_table("parent_chat_messages"):
        op.create_table(
            "parent_chat_messages",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("session_id", sa.String(length=36), nullable=False),
            sa.Column("role", sa.String(length=20), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("timestamp", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["session_id"], ["parent_chat_sessions.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "idx_pcm_session_time", "parent_chat_messages", ["session_id", "timestamp"]
        )
        op.create_index(
            "ix_parent_chat_messages_session_id", "parent_chat_messages", ["session_id"]
        )

    if not _has_table("parent_chat_rolling_summary"):
        op.create_table(
            "parent_chat_rolling_summary",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("parent_id", sa.String(length=36), nullable=False),
            sa.Column("child_id", sa.String(length=36), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("session_count", sa.Integer(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "parent_id", "child_id", name="uq_rolling_summary_parent_child"
            ),
        )


def _create_consent_tables() -> None:
    """migrations/consent_001_create_tables.py (2026-06-02). Frozen DDL as of 0001."""
    if not _has_table("consent_events"):
        op.create_table(
            "consent_events",
            sa.Column("event_id", sa.String(length=36), nullable=False),
            sa.Column("parent_id", sa.String(length=36), nullable=False),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("timestamp", sa.DateTime(), nullable=False),
            sa.Column("ip_address", sa.String(length=64), nullable=True),
            sa.Column("user_agent", sa.Text(), nullable=True),
            sa.Column("direct_notice_version", sa.String(length=64), nullable=True),
            sa.Column("privacy_policy_version", sa.String(length=32), nullable=True),
            sa.Column("vpc_method", sa.String(length=32), nullable=True),
            sa.Column("apple_transaction_id", sa.String(length=255), nullable=True),
            sa.Column("child_id", sa.String(length=36), nullable=True),
            sa.Column("failure_reason", sa.String(length=255), nullable=True),
            sa.Column("event_metadata", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("event_id"),
        )
        op.create_index(
            "ix_consent_events_event_type", "consent_events", ["event_type"]
        )
        op.create_index("ix_consent_events_parent_id", "consent_events", ["parent_id"])
        op.create_index("ix_consent_events_timestamp", "consent_events", ["timestamp"])

    if not _has_table("subscriptions"):
        op.create_table(
            "subscriptions",
            sa.Column("subscription_id", sa.String(length=36), nullable=False),
            sa.Column("parent_id", sa.String(length=36), nullable=False),
            sa.Column("apple_transaction_id", sa.String(length=255), nullable=False),
            sa.Column(
                "apple_original_transaction_id", sa.String(length=255), nullable=False
            ),
            sa.Column("product_id", sa.String(length=128), nullable=False),
            sa.Column("purchase_date", sa.DateTime(), nullable=False),
            sa.Column("expires_date", sa.DateTime(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("receipt_data", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("subscription_id"),
            sa.UniqueConstraint("apple_transaction_id"),
        )
        op.create_index("ix_subscriptions_parent_id", "subscriptions", ["parent_id"])


def _add_child_topics_origin_mentions() -> None:
    """migrations/topics_001_add_origin_mentions.py (2026-06-16).

    Only meaningful on a legacy DB that still has the pre-rename child_topics
    table; server defaults match the original ALTER statements.
    """
    if not _has_table("child_topics"):
        return
    if not _has_column("child_topics", "total_mentions"):
        op.add_column(
            "child_topics",
            sa.Column(
                "total_mentions",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("1"),
            ),
        )
    if not _has_column("child_topics", "origin"):
        op.add_column(
            "child_topics",
            sa.Column(
                "origin",
                sa.String(length=8),
                nullable=False,
                server_default=sa.text("'child'"),
            ),
        )


def _add_parent_highlights() -> None:
    """migrations/conversation_003_add_parent_highlights.py (2026-06-17)."""
    if _has_table("conversations") and not _has_column(
        "conversations", "parent_highlights"
    ):
        op.add_column(
            "conversations", sa.Column("parent_highlights", sa.JSON(), nullable=True)
        )


def _rename_child_topics_to_observed_interests() -> None:
    """migrations/observed_interests_001_rename_from_child_topics.py (2026-06-22)."""
    has_old = _has_table("child_topics")
    has_new = _has_table("observed_interests")
    if has_old and has_new:
        raise RuntimeError(
            "Both child_topics and observed_interests exist — data may be split "
            "across two tables. Resolve manually before migrating."
        )
    if has_old:
        op.rename_table("child_topics", "observed_interests")
    if _has_table("observed_interests") and _has_column(
        "observed_interests", "topic_label"
    ):
        with op.batch_alter_table("observed_interests") as batch_op:
            batch_op.alter_column(
                "topic_label",
                new_column_name="interest_label",
                existing_type=sa.String(length=120),
                existing_nullable=False,
            )


def _make_full_name_nullable() -> None:
    """migrations/user_001_nullable_full_name.py (2026-07-03).

    The original script skipped SQLite; batch mode handles it correctly on
    both dialects.
    """
    if not _has_table("users"):
        return
    full_name = next(
        (c for c in _inspector().get_columns("users") if c["name"] == "full_name"), None
    )
    if full_name is None or full_name["nullable"]:
        return
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "full_name", existing_type=sa.String(length=255), nullable=True
        )


def _rename_profile_interests() -> None:
    """migrations/profile_001_rename_interests_to_parent_declared.py (2026-07-03)."""
    if not _has_table("child_profiles"):
        return
    if _has_column("child_profiles", "parent_declared_interests"):
        return
    if _has_column("child_profiles", "interests"):
        with op.batch_alter_table("child_profiles") as batch_op:
            batch_op.alter_column(
                "interests",
                new_column_name="parent_declared_interests",
                existing_type=sa.JSON(),
                existing_nullable=False,
            )


def _add_curiosity_signal() -> None:
    """migrations/observed_interests_002_add_curiosity_signal.py (2026-07-03)."""
    if _has_table("observed_interests") and not _has_column(
        "observed_interests", "curiosity_signal"
    ):
        op.add_column(
            "observed_interests",
            sa.Column("curiosity_signal", sa.Float(), nullable=True),
        )


def _create_inferred_traits_table() -> None:
    """Schema side effect of migrations/inferred_traits_001_move_voice_style_scores.py
    (2026-07-03): the original script created inferred_traits by constructing
    InferredTraitsDatastore. Frozen DDL as of 0001; the data move is revision 0003.
    """
    if _has_table("inferred_traits"):
        return
    op.create_table(
        "inferred_traits",
        sa.Column("child_id", sa.String(length=36), nullable=False),
        sa.Column("curiosity_mode_by_kind", sa.JSON(), nullable=False),
        sa.Column("preferred_style", sa.String(length=64), nullable=True),
        sa.Column("preferred_style_confidence", sa.Float(), nullable=True),
        sa.Column("voice_style_scores", sa.JSON(), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("child_id"),
    )


def _drop_interaction_contexts() -> None:
    """migrations/interaction_contexts_001_drop_table.py (2026-07-03).

    The table belonged to dead code and no writer ever existed; refuse to
    drop if that assumption is somehow wrong.
    """
    if not _has_table("interaction_contexts"):
        return
    row_count = (
        op.get_bind()
        .execute(sa.text("SELECT COUNT(*) FROM interaction_contexts"))
        .scalar()
    )
    if row_count:
        raise RuntimeError(
            f"interaction_contexts has {row_count} rows; expected 0. "
            f"Investigate before dropping."
        )
    op.drop_table("interaction_contexts")


def upgrade() -> None:
    _create_capability_tables()
    _add_parent_summary()
    _create_parent_chat_tables()
    _create_consent_tables()
    _add_child_topics_origin_mentions()
    _add_parent_highlights()
    _rename_child_topics_to_observed_interests()
    _make_full_name_nullable()
    _rename_profile_interests()
    _add_curiosity_signal()
    _create_inferred_traits_table()
    _drop_interaction_contexts()


def downgrade() -> None:
    # Intentionally a no-op — see module docstring.
    pass

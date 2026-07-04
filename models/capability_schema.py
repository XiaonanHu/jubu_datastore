"""
SQLAlchemy ORM models for capability observations and capability state.

Separate from the YAML definition models (capability_definitions.py).
Used only for persistence; one row per observation, one row per (child_id, item_id) state.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from jubu_datastore.base_datastore import BaseDatastore


class ChildCapabilityObservationModel(BaseDatastore.Base):
    """
    Raw evaluation events: one row per observation from one session.

    Never delete these records. Used for debugging, recalculation, ML, transparency.
    """

    __tablename__ = "child_capability_observations"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    child_id: Mapped[str] = mapped_column(sa.String(36), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(sa.String(255), nullable=False, index=True)

    item_id: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    item_version: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    framework: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    domain: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    subdomain: Mapped[str] = mapped_column(sa.String(64), nullable=False)

    observation_status: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)

    evidence_text: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)

    evaluator_type: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    evaluator_version: Mapped[Optional[str]] = mapped_column(
        sa.String(64), nullable=True
    )

    raw_score_json: Mapped[dict[str, Any] | None] = mapped_column(
        sa.JSON, nullable=True
    )

    observed_at: Mapped[datetime] = mapped_column(
        sa.DateTime, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime, nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        sa.Index("idx_obs_child_item", "child_id", "item_id"),
        sa.Index("idx_obs_child_framework", "child_id", "framework"),
        sa.Index("idx_obs_session", "session_id"),
        sa.Index(
            "idx_obs_item_id", "item_id"
        ),  # analytics: population mastery, model training, dashboards
    )


class ChildCapabilityStateModel(BaseDatastore.Base):
    """
    Current skill status per child per item: one row per (child_id, item_id).

    Parent app reads this for current learning state; do not recompute from observations.
    """

    __tablename__ = "child_capability_state"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    child_id: Mapped[str] = mapped_column(sa.String(36), nullable=False, index=True)
    item_id: Mapped[str] = mapped_column(sa.String(255), nullable=False, index=True)
    item_version: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    framework: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    domain: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    subdomain: Mapped[str] = mapped_column(sa.String(64), nullable=False)

    current_status: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)
    mastery_score: Mapped[float] = mapped_column(sa.Float, nullable=False, default=0.0)

    evidence_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

    first_observed_at: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime, nullable=True
    )
    last_observed_at: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime, nullable=True
    )
    last_session_id: Mapped[Optional[str]] = mapped_column(
        sa.String(255), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "child_id", "item_id", name="uq_child_capability_state_child_item"
        ),
        sa.CheckConstraint(
            "mastery_score >= 0 AND mastery_score <= 1", name="chk_mastery_score_range"
        ),
        sa.Index("idx_state_child_item", "child_id", "item_id"),
        sa.Index("idx_state_child_framework", "child_id", "framework"),
    )

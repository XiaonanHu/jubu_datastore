"""
SQLAlchemy ORM models for capability observations and capability state.

Separate from the YAML definition models (capability_definitions.py).
Used only for persistence; one row per observation, one row per (child_id, item_id) state.
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa

from jubu_datastore.base_datastore import BaseDatastore

Base = BaseDatastore.Base


class ChildCapabilityObservationModel(Base):
    """
    Raw evaluation events: one row per observation from one session.

    Never delete these records. Used for debugging, recalculation, ML, transparency.
    """

    __tablename__ = "child_capability_observations"

    id = sa.Column(sa.String(36), primary_key=True)
    child_id = sa.Column(sa.String(36), nullable=False, index=True)
    session_id = sa.Column(sa.String(255), nullable=False, index=True)

    item_id = sa.Column(sa.String(255), nullable=False)
    item_version = sa.Column(sa.Integer, nullable=False)

    framework = sa.Column(sa.String(64), nullable=False, index=True)
    domain = sa.Column(sa.String(64), nullable=False)
    subdomain = sa.Column(sa.String(64), nullable=False)

    observation_status = sa.Column(sa.String(64), nullable=False)
    confidence = sa.Column(sa.Float, nullable=True)

    evidence_text = sa.Column(sa.Text, nullable=True)

    evaluator_type = sa.Column(sa.String(64), nullable=False)
    evaluator_version = sa.Column(sa.String(64), nullable=True)

    raw_score_json = sa.Column(sa.JSON, nullable=True)

    observed_at = sa.Column(sa.DateTime, nullable=False, index=True)
    created_at = sa.Column(sa.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        sa.Index("idx_obs_child_item", "child_id", "item_id"),
        sa.Index("idx_obs_child_framework", "child_id", "framework"),
        sa.Index("idx_obs_session", "session_id"),
        sa.Index("idx_obs_item_id", "item_id"),  # analytics: population mastery, model training, dashboards
    )


class ChildCapabilityStateModel(Base):
    """
    Current skill status per child per item: one row per (child_id, item_id).

    Parent app reads this for current learning state; do not recompute from observations.
    """

    __tablename__ = "child_capability_state"

    id = sa.Column(sa.String(36), primary_key=True)
    child_id = sa.Column(sa.String(36), nullable=False, index=True)
    item_id = sa.Column(sa.String(255), nullable=False, index=True)
    item_version = sa.Column(sa.Integer, nullable=False)

    framework = sa.Column(sa.String(64), nullable=False, index=True)
    domain = sa.Column(sa.String(64), nullable=False)
    subdomain = sa.Column(sa.String(64), nullable=False)

    current_status = sa.Column(sa.String(64), nullable=False)
    confidence = sa.Column(sa.Float, nullable=True)
    mastery_score = sa.Column(sa.Float, nullable=False, default=0.0)

    evidence_count = sa.Column(sa.Integer, nullable=False, default=0)

    first_observed_at = sa.Column(sa.DateTime, nullable=True)
    last_observed_at = sa.Column(sa.DateTime, nullable=True)
    last_session_id = sa.Column(sa.String(255), nullable=True)

    created_at = sa.Column(sa.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = sa.Column(
        sa.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        sa.UniqueConstraint("child_id", "item_id", name="uq_child_capability_state_child_item"),
        sa.CheckConstraint("mastery_score >= 0 AND mastery_score <= 1", name="chk_mastery_score_range"),
        sa.Index("idx_state_child_item", "child_id", "item_id"),
        sa.Index("idx_state_child_framework", "child_id", "framework"),
    )

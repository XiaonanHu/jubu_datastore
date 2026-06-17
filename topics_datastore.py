"""
Topics datastore — per-child cross-session interest ledger.

Stores what a child has been curious about across sessions, distilled to short
labels. Upserted at session end from TurnState.session_topics. Designed to be
graph-ready: a future `child_topic_edges` table can relate these nodes without
reworking them. See docs/STORY_GENERATION_PLAN.md.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import sqlalchemy as sa

from jubu_datastore.logging import get_logger
from jubu_datastore.common.exceptions import DatastoreError
from jubu_datastore.base_datastore import BaseDatastore

logger = get_logger(__name__)


class ChildTopicModel(BaseDatastore.Base):
    """SQLAlchemy model for a per-child topic the child has engaged with."""

    __tablename__ = "child_topics"

    id = sa.Column(sa.String(36), primary_key=True)
    child_id = sa.Column(sa.String(36), nullable=False, index=True)
    canonical_key = sa.Column(sa.String(120), nullable=False)
    topic_label = sa.Column(sa.String(120), nullable=False)
    kind = sa.Column(sa.String(32), nullable=False, default="other")
    framework_link = sa.Column(sa.String(255), nullable=True)  # nullable NGSS/CASEL item id

    times_visited = sa.Column(sa.Integer, nullable=False, default=1)
    # Total mentions across all sessions (sum of per-session mention counts).
    # Drives the parent-app topic-bubble SIZE (talked about a lot -> bigger).
    total_mentions = sa.Column(sa.Integer, nullable=False, default=1)
    # Who first raised the topic: "child" or "buju". Set once on insert, never
    # updated. Drives the parent-app bubble MARK/badge.
    origin = sa.Column(sa.String(8), nullable=False, default="child")
    first_session_id = sa.Column(sa.String(36), nullable=True)
    last_session_id = sa.Column(sa.String(36), nullable=True)
    first_observed_at = sa.Column(sa.DateTime, nullable=False, default=datetime.utcnow)
    # Drives the parent-app bubble COLOR (lighter = stale, darker = recent).
    last_observed_at = sa.Column(sa.DateTime, nullable=False, default=datetime.utcnow)

    last_depth = sa.Column(sa.Integer, nullable=False, default=0)
    breadth_count = sa.Column(sa.Integer, nullable=False, default=0)
    sentiment = sa.Column(sa.String(16), nullable=True)
    status = sa.Column(sa.String(16), nullable=False, default="active")

    created_at = sa.Column(sa.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = sa.Column(
        sa.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        sa.UniqueConstraint("child_id", "canonical_key", name="uq_child_topic"),
        sa.Index("idx_topic_child", "child_id"),
        sa.Index("idx_topic_child_recent", "child_id", "last_observed_at"),
    )


class TopicsDatastore(BaseDatastore):
    """Datastore for the per-child topic ledger."""

    def __init__(
        self,
        connection_string: Optional[str] = None,
        pool_size: Optional[int] = None,
        encryption_key: Optional[str] = None,
    ):
        super().__init__(
            connection_string=connection_string,
            pool_size=pool_size,
            encryption_key=encryption_key,
            model_class=ChildTopicModel,
        )
        self._ensure_schema()

    # BaseDatastore abstract surface -------------------------------------

    def create(self, data: Dict[str, Any]) -> ChildTopicModel:
        return self.upsert_topic(data["child_id"], data)

    def get(self, record_id: str) -> Optional[ChildTopicModel]:
        with self.session_scope() as session:
            return (
                session.query(ChildTopicModel)
                .filter(ChildTopicModel.id == record_id)
                .first()
            )

    def update(
        self, record_id: str, data: Dict[str, Any]
    ) -> Optional[ChildTopicModel]:
        with self.session_scope() as session:
            row = (
                session.query(ChildTopicModel)
                .filter(ChildTopicModel.id == record_id)
                .first()
            )
            if not row:
                return None
            for key, value in data.items():
                if hasattr(row, key):
                    setattr(row, key, value)
            session.commit()
            return row

    def delete(self, record_id: str) -> bool:
        with self.session_scope() as session:
            row = (
                session.query(ChildTopicModel)
                .filter(ChildTopicModel.id == record_id)
                .first()
            )
            if not row:
                return False
            session.delete(row)
            session.commit()
            return True

    # Ledger operations --------------------------------------------------

    def upsert_topic(self, child_id: str, topic: Dict[str, Any]) -> ChildTopicModel:
        """Insert or update one topic for a child, keyed by canonical_key.

        On update: bumps times_visited, ACCUMULATES total_mentions by
        `mentions_delta`, refreshes recency/session, keeps the max depth seen,
        records the latest sentiment, and PRESERVES origin (first sighting wins).
        `topic` accepts: canonical_key, topic_label, kind, framework_link,
        last_depth, sentiment, session_id, observed_at, origin, mentions_delta.
        """
        canonical_key = topic.get("canonical_key")
        if not canonical_key:
            raise DatastoreError("upsert_topic requires a canonical_key")

        observed_at = topic.get("observed_at") or datetime.utcnow()
        session_id = topic.get("session_id")
        depth = int(topic.get("last_depth", 0) or 0)
        mentions_delta = int(topic.get("mentions_delta", 1) or 1)
        origin = topic.get("origin", "child")
        if origin not in ("child", "buju"):
            origin = "child"

        try:
            with self.session_scope() as session:
                row = (
                    session.query(ChildTopicModel)
                    .filter(
                        ChildTopicModel.child_id == child_id,
                        ChildTopicModel.canonical_key == canonical_key,
                    )
                    .first()
                )
                if row is None:
                    row = ChildTopicModel(
                        id=str(uuid.uuid4()),
                        child_id=child_id,
                        canonical_key=canonical_key,
                        topic_label=topic.get("topic_label", canonical_key)[:120],
                        kind=topic.get("kind", "other"),
                        framework_link=topic.get("framework_link"),
                        times_visited=1,
                        total_mentions=mentions_delta,
                        origin=origin,  # set once, on insert
                        first_session_id=session_id,
                        last_session_id=session_id,
                        first_observed_at=observed_at,
                        last_observed_at=observed_at,
                        last_depth=depth,
                        breadth_count=int(topic.get("breadth_count", 0) or 0),
                        sentiment=topic.get("sentiment"),
                        status="active",
                    )
                    session.add(row)
                else:
                    row.times_visited = (row.times_visited or 0) + 1
                    row.total_mentions = (row.total_mentions or 0) + mentions_delta
                    # origin is intentionally NOT updated — who introduced the
                    # topic doesn't change on later visits.
                    row.last_session_id = session_id
                    row.last_observed_at = observed_at
                    row.last_depth = max(int(row.last_depth or 0), depth)
                    if topic.get("sentiment"):
                        row.sentiment = topic.get("sentiment")
                    if topic.get("framework_link") and not row.framework_link:
                        row.framework_link = topic.get("framework_link")
                    if row.kind == "other" and topic.get("kind", "other") != "other":
                        row.kind = topic.get("kind")
                    row.status = "active"
                session.commit()
                return row
        except Exception as e:
            logger.error(f"Error upserting topic for child {child_id}: {e}")
            raise DatastoreError(f"Failed to upsert topic: {str(e)}")

    def get_topics_for_child(
        self, child_id: str, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Return a child's topics, most-recently-observed first."""
        try:
            with self.session_scope() as session:
                query = (
                    session.query(ChildTopicModel)
                    .filter(ChildTopicModel.child_id == child_id)
                    .order_by(ChildTopicModel.last_observed_at.desc())
                )
                if limit:
                    query = query.limit(limit)
                rows = query.all()
                return [
                    {
                        "id": r.id,
                        "child_id": r.child_id,
                        "canonical_key": r.canonical_key,
                        "topic_label": r.topic_label,
                        "kind": r.kind,
                        "framework_link": r.framework_link,
                        "times_visited": r.times_visited,
                        "total_mentions": r.total_mentions,
                        "origin": r.origin,
                        "first_session_id": r.first_session_id,
                        "last_session_id": r.last_session_id,
                        "first_observed_at": r.first_observed_at,
                        "last_observed_at": r.last_observed_at,
                        "last_depth": r.last_depth,
                        "breadth_count": r.breadth_count,
                        "sentiment": r.sentiment,
                        "status": r.status,
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.error(f"Error retrieving topics for child {child_id}: {e}")
            raise DatastoreError(f"Failed to retrieve topics: {str(e)}")

    def delete_all_for_child(self, child_id: str) -> int:
        """Hard-delete all topics for a child (GDPR)."""
        try:
            with self.session_scope() as session:
                count = (
                    session.query(ChildTopicModel)
                    .filter(ChildTopicModel.child_id == child_id)
                    .delete(synchronize_session=False)
                )
                session.commit()
            logger.info(f"Hard-deleted {count} topics for child {child_id}")
            return count
        except Exception as e:
            logger.error(f"Error deleting topics for child {child_id}: {e}")
            raise DatastoreError(f"Failed to delete topics for child: {str(e)}")

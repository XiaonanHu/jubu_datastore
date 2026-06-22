"""
Observed-interests datastore — per-child cross-session interest ledger.

Stores what a child has been curious about across sessions, distilled to short
labels. Upserted at session end from TurnState.memory.observed_interests. Designed to be
graph-ready: a future `observed_interest_edges` table can relate these nodes without
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


class ObservedInterestModel(BaseDatastore.Base):
    """SQLAlchemy model for a per-child observed interest the child has engaged with."""

    __tablename__ = "observed_interests"

    id = sa.Column(sa.String(36), primary_key=True)
    child_id = sa.Column(sa.String(36), nullable=False, index=True)
    canonical_key = sa.Column(sa.String(120), nullable=False)
    interest_label = sa.Column(sa.String(120), nullable=False)
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
        sa.UniqueConstraint("child_id", "canonical_key", name="uq_child_observed_interest"),
        sa.Index("idx_observed_interest_child", "child_id"),
        sa.Index("idx_observed_interest_child_recent", "child_id", "last_observed_at"),
    )


class ObservedInterestsDatastore(BaseDatastore):
    """Datastore for the per-child observed-interest ledger."""

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
            model_class=ObservedInterestModel,
        )
        self._ensure_schema()

    # BaseDatastore abstract surface -------------------------------------

    def create(self, data: Dict[str, Any]) -> ObservedInterestModel:
        return self.upsert_observed_interest(data["child_id"], data)

    def get(self, record_id: str) -> Optional[ObservedInterestModel]:
        with self.session_scope() as session:
            return (
                session.query(ObservedInterestModel)
                .filter(ObservedInterestModel.id == record_id)
                .first()
            )

    def update(
        self, record_id: str, data: Dict[str, Any]
    ) -> Optional[ObservedInterestModel]:
        with self.session_scope() as session:
            row = (
                session.query(ObservedInterestModel)
                .filter(ObservedInterestModel.id == record_id)
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
                session.query(ObservedInterestModel)
                .filter(ObservedInterestModel.id == record_id)
                .first()
            )
            if not row:
                return False
            session.delete(row)
            session.commit()
            return True

    # Ledger operations --------------------------------------------------

    def upsert_observed_interest(self, child_id: str, interest: Dict[str, Any]) -> ObservedInterestModel:
        """Insert or update one topic for a child, keyed by canonical_key.

        On update: bumps times_visited, ACCUMULATES total_mentions by
        `mentions_delta`, refreshes recency/session, keeps the max depth seen,
        records the latest sentiment, and PRESERVES origin (first sighting wins).
        `topic` accepts: canonical_key, interest_label, kind, framework_link,
        last_depth, sentiment, session_id, observed_at, origin, mentions_delta.
        """
        canonical_key = interest.get("canonical_key")
        if not canonical_key:
            raise DatastoreError("upsert_observed_interest requires a canonical_key")

        observed_at = interest.get("observed_at") or datetime.utcnow()
        session_id = interest.get("session_id")
        depth = int(interest.get("last_depth", 0) or 0)
        mentions_delta = int(interest.get("mentions_delta", 1) or 1)
        origin = interest.get("origin", "child")
        if origin not in ("child", "buju"):
            origin = "child"

        try:
            with self.session_scope() as session:
                row = (
                    session.query(ObservedInterestModel)
                    .filter(
                        ObservedInterestModel.child_id == child_id,
                        ObservedInterestModel.canonical_key == canonical_key,
                    )
                    .first()
                )
                if row is None:
                    row = ObservedInterestModel(
                        id=str(uuid.uuid4()),
                        child_id=child_id,
                        canonical_key=canonical_key,
                        interest_label=interest.get("interest_label", canonical_key)[:120],
                        kind=interest.get("kind", "other"),
                        framework_link=interest.get("framework_link"),
                        times_visited=1,
                        total_mentions=mentions_delta,
                        origin=origin,  # set once, on insert
                        first_session_id=session_id,
                        last_session_id=session_id,
                        first_observed_at=observed_at,
                        last_observed_at=observed_at,
                        last_depth=depth,
                        breadth_count=int(interest.get("breadth_count", 0) or 0),
                        sentiment=interest.get("sentiment"),
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
                    if interest.get("sentiment"):
                        row.sentiment = interest.get("sentiment")
                    if interest.get("framework_link") and not row.framework_link:
                        row.framework_link = interest.get("framework_link")
                    if row.kind == "other" and interest.get("kind", "other") != "other":
                        row.kind = interest.get("kind")
                    row.status = "active"
                session.commit()
                return row
        except Exception as e:
            logger.error(f"Error upserting topic for child {child_id}: {e}")
            raise DatastoreError(f"Failed to upsert topic: {str(e)}")

    def get_observed_interests_for_child(
        self, child_id: str, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Return a child's topics, most-recently-observed first."""
        try:
            with self.session_scope() as session:
                query = (
                    session.query(ObservedInterestModel)
                    .filter(ObservedInterestModel.child_id == child_id)
                    .order_by(ObservedInterestModel.last_observed_at.desc())
                )
                if limit:
                    query = query.limit(limit)
                rows = query.all()
                return [
                    {
                        "id": r.id,
                        "child_id": r.child_id,
                        "canonical_key": r.canonical_key,
                        "interest_label": r.interest_label,
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
                    session.query(ObservedInterestModel)
                    .filter(ObservedInterestModel.child_id == child_id)
                    .delete(synchronize_session=False)
                )
                session.commit()
            logger.info(f"Hard-deleted {count} topics for child {child_id}")
            return count
        except Exception as e:
            logger.error(f"Error deleting topics for child {child_id}: {e}")
            raise DatastoreError(f"Failed to delete topics for child: {str(e)}")

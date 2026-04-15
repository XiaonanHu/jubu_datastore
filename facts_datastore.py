"""
Facts datastore for KidsChat.

This module provides storage and retrieval functionality for child facts,
ensuring proper data security, privacy, and management of fact lifecycle.
"""

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

import sqlalchemy as sa
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from jubu_datastore.logging import get_logger
from jubu_datastore.common.constants import DEFAULT_FACT_EXPIRATION_DAYS
from jubu_datastore.common.exceptions import FactsDataError
from jubu_datastore.base_datastore import BaseDatastore

logger = get_logger(__name__)


class ChildFactModel(BaseDatastore.Base):
    """SQLAlchemy model for child facts."""

    __tablename__ = "child_facts"

    id = sa.Column(sa.String(36), primary_key=True)
    child_id = sa.Column(sa.String(36), nullable=False, index=True)
    source_turn_id = sa.Column(sa.String(36), nullable=True)
    content = sa.Column(sa.Text, nullable=False)
    confidence = sa.Column(sa.Float, nullable=False)
    timestamp = sa.Column(sa.DateTime, nullable=False, default=datetime.utcnow)
    expiration = sa.Column(sa.DateTime, nullable=False, index=True)
    verified = sa.Column(sa.Boolean, nullable=False, default=False)
    active = sa.Column(sa.Boolean, nullable=False, default=True, index=True)
    created_at = sa.Column(sa.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        sa.Index("idx_child_active_expiration", child_id, active, expiration),
        sa.Index("idx_expiration", expiration),
    )


class FactsDatastore(BaseDatastore):
    """
    Datastore for managing child facts.

    This class handles storage, retrieval, and management of facts about children,
    with proper security, privacy measures, and fact lifecycle management.
    """

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
            model_class=ChildFactModel,
        )

        self._ensure_schema()

    def create(self, data: Dict[str, Any]) -> ChildFactModel:
        return self.save_child_fact(data["child_id"], data)

    def get(self, record_id: str) -> Optional[ChildFactModel]:
        with self.session_scope() as session:
            return (
                session.query(ChildFactModel)
                .filter(ChildFactModel.id == record_id)
                .first()
            )

    def update(self, record_id: str, data: Dict[str, Any]) -> Optional[ChildFactModel]:
        with self.session_scope() as session:
            fact = (
                session.query(ChildFactModel)
                .filter(ChildFactModel.id == record_id)
                .first()
            )
            if not fact:
                return None

            for key, value in data.items():
                if hasattr(fact, key):
                    setattr(fact, key, value)

            session.commit()
            return fact

    def delete(self, record_id: str) -> bool:
        with self.session_scope() as session:
            fact = (
                session.query(ChildFactModel)
                .filter(ChildFactModel.id == record_id)
                .first()
            )
            if not fact:
                return False

            session.delete(fact)
            session.commit()
            return True

    def save_child_fact(
        self, child_id: str, fact_data: Dict[str, Any]
    ) -> ChildFactModel:
        """
        Store an extracted fact about a child.

        Args:
            child_id: ID of the child
            fact_data: Dictionary containing fact data

        Returns:
            Created fact record

        Raises:
            FactsDataError: If required fields are missing
        """
        try:
            required_fields = ["content", "confidence"]
            for field in required_fields:
                if field not in fact_data:
                    raise FactsDataError(f"Missing required field: {field}")

            fact_id = fact_data.get("id", str(uuid.uuid4()))

            expiration = fact_data.get("expiration")
            if not expiration:
                expiration = datetime.utcnow() + timedelta(
                    days=DEFAULT_FACT_EXPIRATION_DAYS
                )

            fact = ChildFactModel(
                id=fact_id,
                child_id=child_id,
                source_turn_id=fact_data.get("source_turn_id"),
                content=fact_data["content"],
                confidence=fact_data["confidence"],
                timestamp=fact_data.get("timestamp", datetime.utcnow()),
                expiration=expiration,
                verified=fact_data.get("verified", False),
                active=fact_data.get("active", True),
            )

            with self.session_scope() as session:
                session.add(fact)
                session.commit()
                logger.info(f"Saved fact {fact_id} for child {child_id}")
                return fact
        except Exception as e:
            logger.error(f"Error saving child fact: {e}")
            raise FactsDataError(f"Failed to save child fact: {str(e)}")

    def get_active_facts_for_child(self, child_id: str) -> list:
        """
        Get all active, non-expired facts for a child.

        Returns ChildFactModel instances. Scalar column attributes
        (.content, .confidence, .expiration, .timestamp, .source_turn_id,
        .verified) remain accessible after the session closes because they
        are loaded eagerly by the query.
        Called by conversation_manager.py to populate ConversationContext.child_facts.
        """
        try:
            with self.session_scope() as session:
                facts = (
                    session.query(ChildFactModel)
                    .filter(
                        ChildFactModel.child_id == child_id,
                        ChildFactModel.active == True,
                        ChildFactModel.expiration > datetime.utcnow(),
                    )
                    .all()
                )
                for f in facts:
                    _ = f.content, f.confidence, f.expiration, f.timestamp, f.source_turn_id, f.verified
                return facts
        except Exception as e:
            logger.error(f"Failed to get active facts for child {child_id}: {e}")
            raise FactsDataError(f"Failed to get active facts: {str(e)}")

    def get_facts_by_source_turn(self, turn_id: str) -> list:
        """
        Get all facts extracted from a specific conversation turn.

        Returns list of dicts.
        Called by app_backend/app/api/conversations.py.
        """
        try:
            with self.session_scope() as session:
                facts = (
                    session.query(ChildFactModel)
                    .filter(ChildFactModel.source_turn_id == turn_id)
                    .all()
                )
                return [
                    {
                        "id": f.id,
                        "child_id": f.child_id,
                        "source_turn_id": f.source_turn_id,
                        "content": f.content,
                        "confidence": f.confidence,
                        "timestamp": f.timestamp.isoformat() if f.timestamp else None,
                        "expiration": f.expiration.isoformat() if f.expiration else None,
                        "verified": f.verified,
                        "active": f.active,
                        "created_at": f.created_at.isoformat() if f.created_at else None,
                    }
                    for f in facts
                ]
        except Exception as e:
            logger.error(f"Failed to get facts by source turn {turn_id}: {e}")
            raise FactsDataError(f"Failed to get facts by source turn: {str(e)}")

    def get_child_facts(
        self,
        child_id: str,
        active_only: bool = True,
        verified_only: bool = False,
        min_confidence: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve facts about a child.

        Args:
            child_id: ID of the child
            active_only: Only return active facts
            verified_only: Only return verified facts
            min_confidence: Minimum confidence threshold

        Returns:
            List of fact records
        """
        try:
            with self.session_scope() as session:
                query = session.query(ChildFactModel).filter(
                    ChildFactModel.child_id == child_id
                )

                if active_only:
                    query = query.filter(ChildFactModel.active == True)

                if verified_only:
                    query = query.filter(ChildFactModel.verified == True)

                if min_confidence is not None:
                    query = query.filter(ChildFactModel.confidence >= min_confidence)

                query = query.order_by(ChildFactModel.confidence.desc())

                facts = query.all()

                result = []
                for fact in facts:
                    fact_dict = {
                        "id": fact.id,
                        "child_id": fact.child_id,
                        "source_turn_id": fact.source_turn_id,
                        "content": fact.content,
                        "confidence": fact.confidence,
                        "timestamp": fact.timestamp,
                        "expiration": fact.expiration,
                        "verified": fact.verified,
                        "active": fact.active,
                        "created_at": fact.created_at,
                    }
                    result.append(fact_dict)

                return result
        except Exception as e:
            logger.error(f"Error retrieving child facts: {e}")
            raise FactsDataError(f"Failed to retrieve child facts: {str(e)}")

    def update_fact_confidence(self, fact_id: str, confidence: float) -> bool:
        try:
            with self.session_scope() as session:
                fact = (
                    session.query(ChildFactModel)
                    .filter(ChildFactModel.id == fact_id)
                    .first()
                )
                if not fact:
                    logger.warning(f"Fact {fact_id} not found")
                    return False

                fact.confidence = confidence
                session.commit()
                logger.info(f"Updated confidence for fact {fact_id} to {confidence}")
                return True
        except Exception as e:
            logger.error(f"Error updating fact confidence: {e}")
            raise FactsDataError(f"Failed to update fact confidence: {str(e)}")

    def verify_fact(self, fact_id: str) -> bool:
        try:
            with self.session_scope() as session:
                fact = (
                    session.query(ChildFactModel)
                    .filter(ChildFactModel.id == fact_id)
                    .first()
                )
                if not fact:
                    logger.warning(f"Fact {fact_id} not found")
                    return False

                fact.verified = True
                session.commit()
                logger.info(f"Marked fact {fact_id} as verified")
                return True
        except Exception as e:
            logger.error(f"Error verifying fact: {e}")
            raise FactsDataError(f"Failed to verify fact: {str(e)}")

    def expire_old_facts(self) -> int:
        """Clean up expired facts by marking them as inactive."""
        try:
            current_time = datetime.utcnow()

            with self.session_scope() as session:
                facts = (
                    session.query(ChildFactModel)
                    .filter(
                        ChildFactModel.expiration < current_time,
                        ChildFactModel.active == True,
                    )
                    .all()
                )

                count = 0
                for fact in facts:
                    fact.active = False
                    count += 1

                session.commit()
                logger.info(f"Expired {count} facts")
                return count
        except Exception as e:
            logger.error(f"Error expiring old facts: {e}")
            raise FactsDataError(f"Failed to expire old facts: {str(e)}")

    def get_facts_by_expiration(
        self, expiration_date: datetime
    ) -> List[Dict[str, Any]]:
        try:
            with self.session_scope() as session:
                facts = (
                    session.query(ChildFactModel)
                    .filter(
                        ChildFactModel.expiration <= expiration_date,
                        ChildFactModel.active == True,
                    )
                    .order_by(ChildFactModel.expiration)
                    .all()
                )

                result = []
                for fact in facts:
                    fact_dict = {
                        "id": fact.id,
                        "child_id": fact.child_id,
                        "content": fact.content,
                        "confidence": fact.confidence,
                        "expiration": fact.expiration,
                        "verified": fact.verified,
                    }
                    result.append(fact_dict)

                return result
        except Exception as e:
            logger.error(f"Error retrieving facts by expiration: {e}")
            raise FactsDataError(f"Failed to retrieve facts by expiration: {str(e)}")

    def extend_fact_expiration(self, fact_id: str, days: int = 30) -> bool:
        try:
            with self.session_scope() as session:
                fact = (
                    session.query(ChildFactModel)
                    .filter(ChildFactModel.id == fact_id)
                    .first()
                )
                if not fact:
                    logger.warning(f"Fact {fact_id} not found")
                    return False

                fact.expiration = fact.expiration + timedelta(days=days)
                session.commit()
                logger.info(f"Extended expiration for fact {fact_id} by {days} days")
                return True
        except Exception as e:
            logger.error(f"Error extending fact expiration: {e}")
            raise FactsDataError(f"Failed to extend fact expiration: {str(e)}")

    def get_facts_statistics(self, child_id: Optional[str] = None) -> Dict[str, Any]:
        try:
            with self.session_scope() as session:
                query = session.query(ChildFactModel)

                if child_id:
                    query = query.filter(ChildFactModel.child_id == child_id)

                total_count = query.count()
                active_count = query.filter(ChildFactModel.active == True).count()
                verified_count = query.filter(ChildFactModel.verified == True).count()

                avg_confidence = (
                    session.query(func.avg(ChildFactModel.confidence)).scalar() or 0
                )

                expiring_soon = query.filter(
                    ChildFactModel.expiration <= datetime.utcnow() + timedelta(days=7),
                    ChildFactModel.expiration > datetime.utcnow(),
                    ChildFactModel.active == True,
                ).count()

                return {
                    "total_facts": total_count,
                    "active_facts": active_count,
                    "verified_facts": verified_count,
                    "average_confidence": float(avg_confidence),
                    "expiring_soon": expiring_soon,
                    "filter_child_id": child_id,
                }
        except Exception as e:
            logger.error(f"Error getting facts statistics: {e}")
            raise FactsDataError(f"Failed to get facts statistics: {str(e)}")

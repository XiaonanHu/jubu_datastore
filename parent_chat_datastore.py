"""
Parent chat datastore for Jubu.

Stores parent-facing AI chat sessions, individual messages, and the rolling
cumulative summary used to personalize future chat system prompts.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import sqlalchemy as sa
from sqlalchemy.orm import relationship

from jubu_datastore.logging import get_logger
from jubu_datastore.base_datastore import BaseDatastore

logger = get_logger(__name__)


class ParentChatSessionModel(BaseDatastore.Base):
    __tablename__ = "parent_chat_sessions"

    id = sa.Column(sa.String(36), primary_key=True)
    parent_id = sa.Column(sa.String(36), nullable=False, index=True)
    child_id = sa.Column(sa.String(36), nullable=False, index=True)
    scenario_key = sa.Column(sa.String(100), nullable=True)
    created_at = sa.Column(sa.DateTime, nullable=False, default=datetime.utcnow)
    last_message_at = sa.Column(sa.DateTime, nullable=False, default=datetime.utcnow)
    is_active = sa.Column(sa.Boolean, nullable=False, default=True)
    summary = sa.Column(sa.Text, nullable=True)
    summary_generated_at = sa.Column(sa.DateTime, nullable=True)

    messages = relationship(
        "ParentChatMessageModel",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ParentChatMessageModel.timestamp",
    )

    __table_args__ = (
        sa.Index("idx_pcs_parent_active", "parent_id", "is_active"),
        sa.Index("idx_pcs_parent_created", "parent_id", "created_at"),
    )


class ParentChatMessageModel(BaseDatastore.Base):
    __tablename__ = "parent_chat_messages"

    id = sa.Column(sa.String(36), primary_key=True)
    session_id = sa.Column(
        sa.String(36),
        sa.ForeignKey("parent_chat_sessions.id"),
        nullable=False,
        index=True,
    )
    role = sa.Column(sa.String(20), nullable=False)  # "parent" | "assistant"
    content = sa.Column(sa.Text, nullable=False)
    timestamp = sa.Column(sa.DateTime, nullable=False, default=datetime.utcnow)

    session = relationship("ParentChatSessionModel", back_populates="messages")

    __table_args__ = (
        sa.Index("idx_pcm_session_time", "session_id", "timestamp"),
    )


class ParentChatRollingSummaryModel(BaseDatastore.Base):
    __tablename__ = "parent_chat_rolling_summary"

    id = sa.Column(sa.String(36), primary_key=True)
    parent_id = sa.Column(sa.String(36), nullable=False)
    child_id = sa.Column(sa.String(36), nullable=False)
    summary = sa.Column(sa.Text, nullable=False)
    session_count = sa.Column(sa.Integer, nullable=False, default=0)
    updated_at = sa.Column(sa.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        sa.UniqueConstraint("parent_id", "child_id", name="uq_rolling_summary_parent_child"),
    )


class ParentChatDatastore(BaseDatastore):
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
            model_class=ParentChatSessionModel,
        )
        self._ensure_schema()

    # Required by BaseDatastore ABC
    def create(self, data: Dict[str, Any]) -> ParentChatSessionModel:
        return self.create_session(
            parent_id=data["parent_id"],
            child_id=data["child_id"],
            scenario_key=data.get("scenario_key"),
        )

    def get(self, record_id: str) -> Optional[Dict[str, Any]]:
        session_obj = self.get_session(record_id)
        if session_obj is None:
            return None
        return {
            "id": session_obj.id,
            "parent_id": session_obj.parent_id,
            "child_id": session_obj.child_id,
            "scenario_key": session_obj.scenario_key,
            "created_at": session_obj.created_at,
            "last_message_at": session_obj.last_message_at,
            "is_active": session_obj.is_active,
            "summary": session_obj.summary,
        }

    def update(self, record_id: str, data: Dict[str, Any]) -> Optional[ParentChatSessionModel]:
        with self.session_scope() as db:
            obj = db.query(ParentChatSessionModel).filter_by(id=record_id).first()
            if not obj:
                return None
            for k, v in data.items():
                if hasattr(obj, k):
                    setattr(obj, k, v)
            db.commit()
            return obj

    def delete(self, record_id: str) -> bool:
        with self.session_scope() as db:
            obj = db.query(ParentChatSessionModel).filter_by(id=record_id).first()
            if not obj:
                return False
            db.delete(obj)
            db.commit()
            return True

    # --- Sessions ---

    def create_session(
        self,
        parent_id: str,
        child_id: str,
        scenario_key: Optional[str] = None,
    ) -> str:
        session_id = str(uuid.uuid4())
        now = datetime.utcnow()
        obj = ParentChatSessionModel(
            id=session_id,
            parent_id=parent_id,
            child_id=child_id,
            scenario_key=scenario_key,
            created_at=now,
            last_message_at=now,
        )
        with self.session_scope() as db:
            db.add(obj)
            db.commit()
        logger.info(f"Created parent chat session {session_id} for parent {parent_id}")
        return session_id

    def get_session(self, session_id: str) -> Optional[ParentChatSessionModel]:
        with self.session_scope() as db:
            obj = db.query(ParentChatSessionModel).filter_by(id=session_id).first()
            if obj:
                db.expunge(obj)
            return obj

    def close_session(self, session_id: str) -> Optional[ParentChatSessionModel]:
        with self.session_scope() as db:
            obj = db.query(ParentChatSessionModel).filter_by(id=session_id).first()
            if not obj:
                return None
            obj.is_active = False
            obj.last_message_at = datetime.utcnow()
            db.commit()
            db.expunge(obj)
            return obj

    def list_recent_sessions(
        self, parent_id: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        with self.session_scope() as db:
            rows = (
                db.query(ParentChatSessionModel)
                .filter_by(parent_id=parent_id)
                .order_by(ParentChatSessionModel.last_message_at.desc())
                .limit(limit)
                .all()
            )
            results = []
            for row in rows:
                # Use the first parent message as the chip preview (shows what the
                # chat was about, not Buju's response which is the last message)
                first_parent_msg = (
                    db.query(ParentChatMessageModel)
                    .filter_by(session_id=row.id, role="parent")
                    .order_by(ParentChatMessageModel.timestamp.asc())
                    .first()
                )
                results.append({
                    "session_id": row.id,
                    "scenario_key": row.scenario_key,
                    "created_at": row.created_at,
                    "last_message_at": row.last_message_at,
                    "is_active": row.is_active,
                    "last_message_preview": (first_parent_msg.content[:120] if first_parent_msg else None),
                    "last_message_role": (first_parent_msg.role if first_parent_msg else None),
                })
            return results

    # --- Messages ---

    def save_message(self, session_id: str, role: str, content: str) -> str:
        msg_id = str(uuid.uuid4())
        now = datetime.utcnow()
        msg = ParentChatMessageModel(
            id=msg_id,
            session_id=session_id,
            role=role,
            content=content,
            timestamp=now,
        )
        with self.session_scope() as db:
            db.add(msg)
            # bump session timestamp
            db.query(ParentChatSessionModel).filter_by(id=session_id).update(
                {"last_message_at": now}
            )
            db.commit()
        return msg_id

    def get_session_messages(self, session_id: str) -> List[Dict[str, Any]]:
        with self.session_scope() as db:
            rows = (
                db.query(ParentChatMessageModel)
                .filter_by(session_id=session_id)
                .order_by(ParentChatMessageModel.timestamp.asc())
                .all()
            )
            return [
                {
                    "id": r.id,
                    "session_id": r.session_id,
                    "role": r.role,
                    "content": r.content,
                    "timestamp": r.timestamp,
                }
                for r in rows
            ]

    # --- Per-session summary ---

    def save_session_summary(self, session_id: str, summary: str) -> None:
        with self.session_scope() as db:
            db.query(ParentChatSessionModel).filter_by(id=session_id).update(
                {
                    "summary": summary,
                    "summary_generated_at": datetime.utcnow(),
                }
            )
            db.commit()

    # --- Rolling summary ---

    def get_rolling_summary(self, parent_id: str, child_id: str) -> Optional[str]:
        info = self.get_rolling_summary_info(parent_id, child_id)
        return info[0] if info else None

    def get_rolling_summary_info(
        self, parent_id: str, child_id: str
    ) -> Optional[tuple]:
        """Return (summary, session_count) or None if no rolling summary exists."""
        with self.session_scope() as db:
            row = (
                db.query(ParentChatRollingSummaryModel)
                .filter_by(parent_id=parent_id, child_id=child_id)
                .first()
            )
            if row is None:
                return None
            return (row.summary, row.session_count)

    def upsert_rolling_summary(
        self, parent_id: str, child_id: str, summary: str, session_count: int
    ) -> None:
        with self.session_scope() as db:
            row = (
                db.query(ParentChatRollingSummaryModel)
                .filter_by(parent_id=parent_id, child_id=child_id)
                .first()
            )
            if row:
                row.summary = summary
                row.session_count = session_count
                row.updated_at = datetime.utcnow()
            else:
                row = ParentChatRollingSummaryModel(
                    id=str(uuid.uuid4()),
                    parent_id=parent_id,
                    child_id=child_id,
                    summary=summary,
                    session_count=session_count,
                    updated_at=datetime.utcnow(),
                )
                db.add(row)
            db.commit()
        logger.info(
            f"Updated rolling summary for parent {parent_id} / child {child_id} "
            f"(session_count={session_count})"
        )

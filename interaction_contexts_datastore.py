"""
Interaction Contexts datastore for KidsChat.

This module provides storage and retrieval functionality for interaction-specific
context data, allowing the system to maintain state across conversation sessions.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import sqlalchemy as sa
from sqlalchemy.orm import relationship

from jubu_datastore.logging import get_logger
from jubu_datastore.common.exceptions import InteractionContextError
from jubu_datastore.base_datastore import BaseDatastore

logger = get_logger(__name__)


class InteractionContextModel(BaseDatastore.Base):
    """SQLAlchemy model for interaction contexts."""

    __tablename__ = "interaction_contexts"

    id = sa.Column(sa.String(36), primary_key=True)
    conversation_id = sa.Column(
        sa.String(36), sa.ForeignKey("conversations.id"), nullable=False, index=True
    )
    interaction_type = sa.Column(sa.String(50), nullable=False, index=True)
    context_data = sa.Column(sa.JSON, nullable=False, default=dict)
    created_at = sa.Column(sa.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = sa.Column(
        sa.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        sa.Index("idx_conversation_interaction", conversation_id, interaction_type),
    )


class InteractionContextsDatastore(BaseDatastore):
    """
    Datastore for managing interaction-specific context data.

    This class handles storage and retrieval of context information for different
    interaction types (chitchat, pretend play, edutainment, etc.) to maintain
    state across conversation sessions.
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
            model_class=InteractionContextModel,
        )

        self.Base.metadata.create_all(self.engine)

    def create(self, data: Dict[str, Any]) -> InteractionContextModel:
        return self.save_interaction_context(data)

    def get(self, record_id: str) -> Optional[InteractionContextModel]:
        with self.session_scope() as session:
            return (
                session.query(InteractionContextModel)
                .filter(InteractionContextModel.id == record_id)
                .first()
            )

    def update(
        self, record_id: str, data: Dict[str, Any]
    ) -> Optional[InteractionContextModel]:
        return self.save_interaction_context(data, record_id)

    def delete(self, record_id: str) -> bool:
        with self.session_scope() as session:
            context = (
                session.query(InteractionContextModel)
                .filter(InteractionContextModel.id == record_id)
                .first()
            )
            if not context:
                return False

            session.delete(context)
            session.commit()
            return True

    def save_interaction_context(
        self, context_data: Dict[str, Any], context_id: Optional[str] = None
    ) -> InteractionContextModel:
        """
        Create or update an interaction context.

        Args:
            context_data: Dictionary containing context data
            context_id: ID of the context (if updating existing context)

        Returns:
            Created or updated context record

        Raises:
            InteractionContextError: If required fields are missing
        """
        try:
            required_fields = ["conversation_id", "interaction_type"]
            for field in required_fields:
                if field not in context_data:
                    raise InteractionContextError(f"Missing required field: {field}")

            record_id = context_id or context_data.get("id", str(uuid.uuid4()))

            with self.session_scope() as session:
                context = None
                if context_id:
                    context = (
                        session.query(InteractionContextModel)
                        .filter(InteractionContextModel.id == context_id)
                        .first()
                    )
                else:
                    context = (
                        session.query(InteractionContextModel)
                        .filter(
                            InteractionContextModel.conversation_id
                            == context_data["conversation_id"],
                            InteractionContextModel.interaction_type
                            == context_data["interaction_type"],
                        )
                        .first()
                    )

                if context:
                    if "context_data" in context_data:
                        current_data = context.context_data or {}
                        current_data.update(context_data["context_data"])
                        context.context_data = current_data

                    for key, value in context_data.items():
                        if key != "context_data" and hasattr(context, key):
                            setattr(context, key, value)

                    context.updated_at = datetime.utcnow()
                    logger.info(
                        f"Updated interaction context {context.id} for conversation {context.conversation_id}"
                    )
                else:
                    context_record = {
                        "id": record_id,
                        "conversation_id": context_data["conversation_id"],
                        "interaction_type": context_data["interaction_type"],
                        "context_data": context_data.get("context_data", {}),
                    }

                    context = InteractionContextModel(**context_record)
                    session.add(context)
                    logger.info(
                        f"Created interaction context for conversation {context_data['conversation_id']}"
                    )

                session.commit()
                return context
        except Exception as e:
            logger.error(f"Error saving interaction context: {e}")
            raise InteractionContextError(
                f"Failed to save interaction context: {str(e)}"
            )

    def get_context_for_conversation(
        self, conversation_id: str, interaction_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        try:
            with self.session_scope() as session:
                query = session.query(InteractionContextModel).filter(
                    InteractionContextModel.conversation_id == conversation_id
                )

                if interaction_type:
                    query = query.filter(
                        InteractionContextModel.interaction_type == interaction_type
                    )

                contexts = query.all()

                result = []
                for context in contexts:
                    context_dict = {
                        "id": context.id,
                        "conversation_id": context.conversation_id,
                        "interaction_type": context.interaction_type,
                        "context_data": context.context_data,
                        "created_at": context.created_at,
                        "updated_at": context.updated_at,
                    }
                    result.append(context_dict)

                return result
        except Exception as e:
            logger.error(
                f"Error retrieving context for conversation {conversation_id}: {e}"
            )
            raise InteractionContextError(
                f"Failed to retrieve interaction context: {str(e)}"
            )

    def update_context_data(
        self, conversation_id: str, interaction_type: str, data_updates: Dict[str, Any]
    ) -> bool:
        try:
            with self.session_scope() as session:
                context = (
                    session.query(InteractionContextModel)
                    .filter(
                        InteractionContextModel.conversation_id == conversation_id,
                        InteractionContextModel.interaction_type == interaction_type,
                    )
                    .first()
                )

                if not context:
                    logger.warning(
                        f"No context found for conversation {conversation_id} and interaction {interaction_type}"
                    )
                    return False

                current_data = context.context_data or {}
                current_data.update(data_updates)
                context.context_data = current_data
                context.updated_at = datetime.utcnow()

                session.commit()
                logger.info(
                    f"Updated context data for conversation {conversation_id}, interaction {interaction_type}"
                )
                return True
        except Exception as e:
            logger.error(f"Error updating context data: {e}")
            raise InteractionContextError(f"Failed to update context data: {str(e)}")

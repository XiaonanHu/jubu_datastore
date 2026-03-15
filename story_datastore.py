"""
Story datastore for KidsChat.

This module provides storage and retrieval functionality for stories created
during storytelling interactions, enabling children to save and revisit stories.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import sqlalchemy as sa
from sqlalchemy.orm import relationship

from jubu_datastore.logging import get_logger
from jubu_datastore.common.constants import DEFAULT_STORY_VIEW_LIMIT
from jubu_datastore.common.exceptions import StoryDataError
from jubu_datastore.base_datastore import BaseDatastore

logger = get_logger(__name__)


class StoryModel(BaseDatastore.Base):
    """SQLAlchemy model for stories."""

    __tablename__ = "stories"

    id = sa.Column(sa.String(36), primary_key=True)
    child_id = sa.Column(sa.String(36), nullable=False, index=True)
    conversation_id = sa.Column(
        sa.String(36), sa.ForeignKey("conversations.id"), nullable=False, index=True
    )
    title = sa.Column(sa.String(200), nullable=False)
    content = sa.Column(sa.Text, nullable=False)
    created_at = sa.Column(sa.DateTime, nullable=False, default=datetime.utcnow)
    is_favorite = sa.Column(sa.Boolean, nullable=False, default=False)

    tags = sa.Column(sa.JSON, nullable=True)
    last_viewed_at = sa.Column(sa.DateTime, nullable=True)

    __table_args__ = (
        sa.Index("idx_child_favorite", child_id, is_favorite),
        sa.Index("idx_created_at", created_at),
    )


class StoryDatastore(BaseDatastore):
    """
    Datastore for managing stories.

    This class handles storage, retrieval, and management of stories created
    during storytelling interactions, with proper security and privacy measures.
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
            model_class=StoryModel,
        )

        self.Base.metadata.create_all(self.engine)

    def create(self, data: Dict[str, Any]) -> StoryModel:
        return self.save_story(data)

    def get(self, record_id: str) -> Optional[StoryModel]:
        with self.session_scope() as session:
            return session.query(StoryModel).filter(StoryModel.id == record_id).first()

    def update(self, record_id: str, data: Dict[str, Any]) -> Optional[StoryModel]:
        return self.save_story(data, record_id)

    def delete(self, record_id: str) -> bool:
        with self.session_scope() as session:
            story = session.query(StoryModel).filter(StoryModel.id == record_id).first()
            if not story:
                return False

            session.delete(story)
            session.commit()
            logger.info(f"Deleted story {record_id}")
            return True

    def save_story(
        self, story_data: Dict[str, Any], story_id: Optional[str] = None
    ) -> StoryModel:
        """
        Create or update a story.

        Args:
            story_data: Dictionary containing story data
            story_id: ID of the story (if updating existing story)

        Returns:
            Created or updated story record

        Raises:
            StoryDataError: If required fields are missing
        """
        try:
            if not story_id:
                required_fields = ["child_id", "conversation_id", "title", "content"]
                for field in required_fields:
                    if field not in story_data:
                        raise StoryDataError(f"Missing required field: {field}")

            record_id = story_id or story_data.get("id", str(uuid.uuid4()))

            with self.session_scope() as session:
                story = None
                if story_id:
                    story = (
                        session.query(StoryModel)
                        .filter(StoryModel.id == story_id)
                        .first()
                    )

                if story:
                    for key, value in story_data.items():
                        if hasattr(story, key):
                            setattr(story, key, value)

                    story.last_viewed_at = datetime.utcnow()

                    logger.info(f"Updated story {story.id} for child {story.child_id}")
                else:
                    story_record = {
                        "id": record_id,
                        "child_id": story_data["child_id"],
                        "conversation_id": story_data["conversation_id"],
                        "title": story_data["title"],
                        "content": story_data["content"],
                        "tags": story_data.get("tags", []),
                        "is_favorite": story_data.get("is_favorite", False),
                        "last_viewed_at": datetime.utcnow(),
                    }

                    story = StoryModel(**story_record)
                    session.add(story)
                    logger.info(
                        f"Created story {record_id} for child {story_data['child_id']}"
                    )

                session.commit()
                return story
        except Exception as e:
            logger.error(f"Error saving story: {e}")
            raise StoryDataError(f"Failed to save story: {str(e)}")

    def get_stories_by_child(
        self,
        child_id: str,
        favorites_only: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        try:
            with self.session_scope() as session:
                query = session.query(StoryModel).filter(
                    StoryModel.child_id == child_id
                )

                if favorites_only:
                    query = query.filter(StoryModel.is_favorite == True)

                query = query.order_by(StoryModel.created_at.desc())

                if offset:
                    query = query.offset(offset)

                if limit:
                    query = query.limit(limit)

                stories = query.all()

                result = []
                for story in stories:
                    story_dict = {
                        "id": story.id,
                        "child_id": story.child_id,
                        "conversation_id": story.conversation_id,
                        "title": story.title,
                        "content": story.content,
                        "created_at": story.created_at,
                        "is_favorite": story.is_favorite,
                        "tags": story.tags,
                        "last_viewed_at": story.last_viewed_at,
                    }
                    result.append(story_dict)

                return result
        except Exception as e:
            logger.error(f"Error retrieving stories for child {child_id}: {e}")
            raise StoryDataError(f"Failed to retrieve stories: {str(e)}")

    def mark_as_favorite(self, story_id: str, is_favorite: bool = True) -> bool:
        try:
            with self.session_scope() as session:
                story = (
                    session.query(StoryModel).filter(StoryModel.id == story_id).first()
                )
                if not story:
                    logger.warning(f"Story {story_id} not found")
                    return False

                story.is_favorite = is_favorite
                session.commit()
                logger.info(
                    f"Story {story_id} favorite status updated to {is_favorite}"
                )
                return True
        except Exception as e:
            logger.error(f"Error updating story favorite status: {e}")
            raise StoryDataError(f"Failed to update story favorite status: {str(e)}")

    def record_story_view(self, story_id: str) -> bool:
        try:
            with self.session_scope() as session:
                story = (
                    session.query(StoryModel).filter(StoryModel.id == story_id).first()
                )
                if not story:
                    logger.warning(f"Story {story_id} not found")
                    return False

                story.last_viewed_at = datetime.utcnow()
                session.commit()
                logger.info(f"Story {story_id} view recorded")
                return True
        except Exception as e:
            logger.error(f"Error recording story view: {e}")
            raise StoryDataError(f"Failed to record story view: {str(e)}")

    def search_stories(
        self, child_id: str, search_term: str, limit: int = DEFAULT_STORY_VIEW_LIMIT
    ) -> List[Dict[str, Any]]:
        try:
            with self.session_scope() as session:
                search_pattern = f"%{search_term}%"

                stories = (
                    session.query(StoryModel)
                    .filter(
                        StoryModel.child_id == child_id,
                        sa.or_(
                            StoryModel.title.ilike(search_pattern),
                            StoryModel.content.ilike(search_pattern),
                        ),
                    )
                    .order_by(StoryModel.created_at.desc())
                    .limit(limit)
                    .all()
                )

                result = []
                for story in stories:
                    story_dict = {
                        "id": story.id,
                        "title": story.title,
                        "created_at": story.created_at,
                        "is_favorite": story.is_favorite,
                        "tags": story.tags,
                    }
                    result.append(story_dict)

                return result
        except Exception as e:
            logger.error(f"Error searching stories: {e}")
            raise StoryDataError(f"Failed to search stories: {str(e)}")

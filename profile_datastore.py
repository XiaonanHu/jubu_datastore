"""
Profile datastore for KidsChat.

This module provides storage and retrieval functionality for child profiles,
ensuring proper data security, privacy, and compliance with data protection regulations.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import sqlalchemy as sa
from sqlalchemy.orm import relationship

from jubu_datastore.logging import get_logger
from jubu_datastore.common.exceptions import ProfileDataError
from jubu_datastore.base_datastore import BaseDatastore
from jubu_datastore.user_datastore import UserModel
from jubu_datastore.dto.entities import ChildProfile

logger = get_logger(__name__)


class ChildProfileModel(BaseDatastore.Base):
    """SQLAlchemy model for child profiles."""

    __tablename__ = "child_profiles"

    id = sa.Column(sa.String(36), primary_key=True)
    name = sa.Column(sa.String(100), nullable=False)
    age = sa.Column(sa.Integer, nullable=False)
    interests = sa.Column(sa.JSON, nullable=False, default=list)
    preferences = sa.Column(sa.JSON, nullable=False, default=dict)
    created_at = sa.Column(sa.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = sa.Column(
        sa.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    parent_id = sa.Column(
        sa.String(36), sa.ForeignKey("users.id"), nullable=True, index=True
    )
    is_active = sa.Column(sa.Boolean, nullable=False, default=True, index=True)
    last_interaction = sa.Column(sa.DateTime, nullable=True)

    __table_args__ = (sa.Index("idx_active_parent", is_active, parent_id),)

    parent = relationship("UserModel", back_populates="child_profiles")


class ProfileDatastore(BaseDatastore):
    """
    Datastore for managing child profiles.

    This class handles storage, retrieval, and management of child profiles,
    with proper security, privacy measures, and compliance with data protection regulations.
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
            model_class=ChildProfileModel,
        )

        self._ensure_schema()

    def _model_to_entity(self, model: ChildProfileModel) -> ChildProfile:
        return ChildProfile(
            id=model.id,
            name=model.name,
            age=model.age,
            interests=model.interests or [],
            preferences=model.preferences or {},
            parent_id=model.parent_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
            last_interaction=model.last_interaction,
            is_active=model.is_active,
        )

    def create(self, data: Dict[str, Any]) -> ChildProfile:
        return self.save_child_profile(data)

    def get(self, record_id: str) -> Optional[ChildProfile]:
        return self.get_child_profile(record_id)

    def update(self, record_id: str, data: Dict[str, Any]) -> Optional[ChildProfile]:
        try:
            with self.session_scope() as session:
                profile = (
                    session.query(self.model_class)
                    .filter(self.model_class.id == record_id)
                    .first()
                )

                if not profile:
                    logger.warning(f"Profile {record_id} not found for update.")
                    return None

                for key, value in data.items():
                    if hasattr(profile, key):
                        setattr(profile, key, value)

                profile.updated_at = datetime.utcnow()

                session.commit()
                logger.info(f"Updated profile for child {record_id} with data: {data}")
                return self._model_to_entity(profile)
        except Exception as e:
            logger.error(f"Error updating profile {record_id}: {e}")
            raise ProfileDataError(f"Failed to update profile: {str(e)}")

    def delete(self, record_id: str) -> bool:
        return self.delete_child_data(record_id)

    def save_child_profile(
        self, profile_data: Dict[str, Any], child_id: Optional[str] = None
    ) -> ChildProfile:
        """
        Create or update a child profile.

        Args:
            profile_data: Dictionary containing profile data
            child_id: ID of the child (if updating existing profile)

        Returns:
            Created or updated profile as domain entity

        Raises:
            ProfileDataError: If required fields are missing
        """
        try:
            if not child_id:
                required_fields = ["name", "age"]
                for field in required_fields:
                    if field not in profile_data:
                        raise ProfileDataError(f"Missing required field: {field}")

            profile_id = child_id or profile_data.get("id", str(uuid.uuid4()))

            with self.session_scope() as session:
                profile = (
                    session.query(ChildProfileModel)
                    .filter(ChildProfileModel.id == profile_id)
                    .first()
                )

                if profile:
                    for key, value in profile_data.items():
                        if hasattr(profile, key):
                            setattr(profile, key, value)

                    profile.updated_at = datetime.utcnow()

                    logger.info(f"Updated profile for child {profile_id}")
                else:
                    profile = ChildProfileModel(
                        id=profile_id,
                        name=profile_data["name"],
                        age=profile_data["age"],
                        interests=profile_data.get("interests", []),
                        preferences=profile_data.get("preferences", {}),
                        parent_id=profile_data.get("parent_id"),
                    )
                    session.add(profile)
                    logger.info(f"Created profile for child {profile_id}")

                session.commit()

                return self._model_to_entity(profile)
        except Exception as e:
            logger.error(f"Error saving child profile: {e}")
            raise ProfileDataError(f"Failed to save child profile: {str(e)}")

    def get_child_profile(self, child_id: str) -> Optional[ChildProfile]:
        """
        Retrieve a child's profile.

        Args:
            child_id: ID of the child

        Returns:
            ChildProfile domain entity if found, None otherwise
        """
        try:
            with self.session_scope() as session:
                profile = (
                    session.query(ChildProfileModel)
                    .filter(
                        ChildProfileModel.id == child_id,
                        ChildProfileModel.is_active == True,
                    )
                    .first()
                )

                if not profile:
                    logger.warning(f"Profile for child {child_id} not found")
                    return None

                return self._model_to_entity(profile)
        except Exception as e:
            logger.error(f"Error retrieving child profile: {e}")
            raise ProfileDataError(f"Failed to retrieve child profile: {str(e)}")

    def update_interests(self, child_id: str, interests: List[str]) -> bool:
        try:
            with self.session_scope() as session:
                profile = (
                    session.query(ChildProfileModel)
                    .filter(ChildProfileModel.id == child_id)
                    .first()
                )
                if not profile:
                    logger.warning(f"Profile for child {child_id} not found")
                    return False

                profile.interests = interests
                profile.updated_at = datetime.utcnow()

                session.commit()
                logger.info(f"Updated interests for child {child_id}")
                return True
        except Exception as e:
            logger.error(f"Error updating child interests: {e}")
            raise ProfileDataError(f"Failed to update child interests: {str(e)}")

    def update_preferences(self, child_id: str, preferences: Dict[str, Any]) -> bool:
        try:
            with self.session_scope() as session:
                profile = (
                    session.query(ChildProfileModel)
                    .filter(ChildProfileModel.id == child_id)
                    .first()
                )
                if not profile:
                    logger.warning(f"Profile for child {child_id} not found")
                    return False

                current_prefs = profile.preferences or {}
                current_prefs.update(preferences)
                profile.preferences = current_prefs
                profile.updated_at = datetime.utcnow()

                session.commit()
                logger.info(f"Updated preferences for child {child_id}")
                return True
        except Exception as e:
            logger.error(f"Error updating child preferences: {e}")
            raise ProfileDataError(f"Failed to update child preferences: {str(e)}")

    def delete_child_data(self, child_id: str, hard_delete: bool = False) -> bool:
        """
        Delete a child's data (GDPR compliance).

        By default, performs a soft delete by marking the profile as inactive.
        If hard_delete is True, the profile is permanently deleted.
        """
        try:
            with self.session_scope() as session:
                profile = (
                    session.query(ChildProfileModel)
                    .filter(ChildProfileModel.id == child_id)
                    .first()
                )
                if not profile:
                    logger.warning(f"Profile for child {child_id} not found")
                    return False

                if hard_delete:
                    session.delete(profile)
                    logger.info(f"Permanently deleted profile for child {child_id}")
                else:
                    profile.is_active = False
                    logger.info(f"Soft-deleted profile for child {child_id}")

                session.commit()
                return True
        except Exception as e:
            logger.error(f"Error deleting child data: {e}")
            raise ProfileDataError(f"Failed to delete child data: {str(e)}")

    def get_profiles_by_parent(self, parent_id: str) -> List[ChildProfile]:
        try:
            with self.session_scope() as session:
                profiles = (
                    session.query(ChildProfileModel)
                    .filter(
                        ChildProfileModel.parent_id == parent_id,
                        ChildProfileModel.is_active == True,
                    )
                    .all()
                )

                result = []
                for profile in profiles:
                    result.append(self._model_to_entity(profile))

                return result
        except Exception as e:
            logger.error(f"Error retrieving profiles by parent: {e}")
            raise ProfileDataError(f"Failed to retrieve profiles by parent: {str(e)}")

    def update_last_interaction(
        self, child_id: str, timestamp: Optional[datetime] = None
    ) -> bool:
        try:
            timestamp = timestamp or datetime.utcnow()

            with self.session_scope() as session:
                profile = (
                    session.query(ChildProfileModel)
                    .filter(ChildProfileModel.id == child_id)
                    .first()
                )
                if not profile:
                    logger.warning(f"Profile for child {child_id} not found")
                    return False

                profile.last_interaction = timestamp
                session.commit()
                return True
        except Exception as e:
            logger.error(f"Error updating last interaction: {e}")
            raise ProfileDataError(f"Failed to update last interaction: {str(e)}")

    def convert_to_child_profile(self, profile_data: Dict[str, Any]) -> ChildProfile:
        return ChildProfile(
            id=profile_data.get("id", ""),
            name=profile_data["name"],
            age=profile_data["age"],
            interests=profile_data.get("interests", []),
            preferences=profile_data.get("preferences", {}),
            parent_id=profile_data.get("parent_id"),
            created_at=profile_data.get("created_at"),
            updated_at=profile_data.get("updated_at"),
            last_interaction=profile_data.get("last_interaction"),
            is_active=profile_data.get("is_active", True),
        )

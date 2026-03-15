"""
Datastore for user data (parent accounts).
"""

import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, TypeVar

import sqlalchemy as sa
from sqlalchemy.orm import relationship

from jubu_datastore.logging import get_logger
from jubu_datastore.common.exceptions import UserDataError
from jubu_datastore.base_datastore import BaseDatastore
from jubu_datastore.dto.entities import User

logger = get_logger(__name__)

T = TypeVar("T")


class UserModel(BaseDatastore.Base):
    """SQLAlchemy model for users."""

    __tablename__ = "users"

    id = sa.Column(sa.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = sa.Column(sa.String(255), unique=True, nullable=False, index=True)
    full_name = sa.Column(sa.String(255), nullable=False)
    hashed_password = sa.Column(sa.String(255), nullable=False)
    is_active = sa.Column(sa.Boolean, default=True, nullable=False)
    created_at = sa.Column(sa.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = sa.Column(
        sa.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (sa.Index("idx_email_active", email, is_active),)

    child_profiles = relationship("ChildProfileModel", back_populates="parent")


class UserDatastore(BaseDatastore):
    """Datastore for user operations."""

    def __init__(
        self,
        connection_string: Optional[str] = None,
        pool_size: Optional[int] = None,
        encryption_key: Optional[str] = None,
        password_hasher: Optional[Callable[[str], str]] = None,
    ):
        super().__init__(
            connection_string=connection_string,
            pool_size=pool_size,
            encryption_key=encryption_key,
            model_class=UserModel,
        )
        self.password_hasher = password_hasher
        self.Base.metadata.create_all(self.engine)
        self.model = UserModel
        logger.debug("UserDatastore initialized with UserModel")

    def create(self, user_data: Dict[str, Any]) -> User:
        """
        Create a new user.

        Args:
            user_data: User data including email, full_name, and hashed_password

        Returns:
            The created user

        Raises:
            UserDataError: If there's an error creating the user
        """
        try:
            existing_user = self.get_by_email(user_data.get("email"))
            if existing_user:
                raise UserDataError("Email already registered")

            user_id = user_data.get("id", str(uuid.uuid4()))

            with self.session_scope() as session:
                user = self.model(
                    id=user_id,
                    email=user_data.get("email"),
                    full_name=user_data.get("full_name"),
                    hashed_password=user_data.get("hashed_password"),
                    is_active=True,
                    created_at=datetime.utcnow(),
                )

                session.add(user)
                session.commit()

                return User(
                    id=str(user.id),
                    email=user.email,
                    full_name=user.full_name,
                    is_active=user.is_active,
                    created_at=user.created_at,
                    updated_at=user.updated_at,
                    hashed_password=user.hashed_password,
                )
        except Exception as e:
            logger.error(f"Failed to create user: {e}")
            raise UserDataError(f"Failed to create user: {str(e)}")

    def get_by_email(self, email: str) -> Optional[User]:
        """
        Get a user by email.

        Args:
            email: User email

        Returns:
            User entity or None if not found

        Raises:
            UserDataError: If there's an error retrieving the user
        """
        try:
            with self.session_scope() as session:
                user = (
                    session.query(self.model).filter(self.model.email == email).first()
                )
                if not user:
                    return None

                return User(
                    id=str(user.id),
                    email=user.email,
                    full_name=user.full_name,
                    is_active=user.is_active,
                    created_at=user.created_at,
                    updated_at=user.updated_at,
                    hashed_password=user.hashed_password,
                )
        except Exception as e:
            logger.error(f"Failed to retrieve user by email: {e}")
            raise UserDataError(f"Failed to retrieve user: {str(e)}")

    def get(self, user_id: str) -> Optional[User]:
        """
        Get a user by ID.

        Args:
            user_id: User ID

        Returns:
            User entity or None if not found

        Raises:
            UserDataError: If there's an error retrieving the user
        """
        try:
            with self.session_scope() as session:
                user = (
                    session.query(self.model).filter(self.model.id == user_id).first()
                )
                if not user:
                    return None

                return User(
                    id=str(user.id),
                    email=user.email,
                    full_name=user.full_name,
                    is_active=user.is_active,
                    created_at=user.created_at,
                    updated_at=user.updated_at,
                    hashed_password=user.hashed_password,
                )
        except Exception as e:
            logger.error(f"Failed to retrieve user by ID: {e}")
            raise UserDataError(f"Failed to retrieve user: {str(e)}")

    def update(self, user_id: str, user_data: Dict[str, Any]) -> Optional[User]:
        """
        Update a user.

        Args:
            user_id: User ID
            user_data: User data to update

        Returns:
            Updated user entity or None if not found

        Raises:
            UserDataError: If there's an error updating the user
        """
        try:
            with self.session_scope() as session:
                user = (
                    session.query(self.model).filter(self.model.id == user_id).first()
                )
                if not user:
                    return None

                for key, value in user_data.items():
                    if hasattr(user, key) and key != "id":
                        setattr(user, key, value)

                if "password" in user_data:
                    if self.password_hasher is None:
                        raise UserDataError(
                            "Cannot hash password: no password_hasher provided. "
                            "Pass hashed_password instead of password, or provide "
                            "a password_hasher to UserDatastore."
                        )
                    user.hashed_password = self.password_hasher(user_data["password"])

                user.updated_at = datetime.utcnow()
                session.commit()

                return User(
                    id=str(user.id),
                    email=user.email,
                    full_name=user.full_name,
                    is_active=user.is_active,
                    created_at=user.created_at,
                    updated_at=user.updated_at,
                    hashed_password=user.hashed_password,
                )
        except Exception as e:
            logger.error(f"Failed to update user: {e}")
            raise UserDataError(f"Failed to update user: {str(e)}")

    def delete(self, user_id: str) -> bool:
        """
        Delete a user (soft delete by deactivating).

        Args:
            user_id: User ID

        Returns:
            True if deleted, False if not found

        Raises:
            UserDataError: If there's an error deleting the user
        """
        try:
            with self.session_scope() as session:
                user = (
                    session.query(self.model).filter(self.model.id == user_id).first()
                )
                if not user:
                    return False

                user.is_active = False
                user.updated_at = datetime.utcnow()
                session.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to delete user: {e}")
            raise UserDataError(f"Failed to delete user: {str(e)}")

    def deactivate(self, user_id: str) -> bool:
        """
        Deactivate a user.

        Args:
            user_id: User ID

        Returns:
            True if deactivated, False if not found

        Raises:
            UserDataError: If there's an error deactivating the user
        """
        try:
            with self.session_scope() as session:
                user = (
                    session.query(self.model).filter(self.model.id == user_id).first()
                )
                if not user:
                    return False

                user.is_active = False
                session.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to deactivate user: {e}")
            raise UserDataError(f"Failed to deactivate user: {str(e)}")

    def get_all_users(self) -> List[User]:
        """
        Get all users in the system.

        Returns:
            List of all users

        Raises:
            UserDataError: If there's an error retrieving users
        """
        try:
            with self.session_scope() as session:
                users = session.query(self.model).all()
                user_list = []

                for user in users:
                    user_list.append(
                        User(
                            id=str(user.id),
                            email=user.email,
                            full_name=user.full_name,
                            is_active=user.is_active,
                            created_at=user.created_at,
                            updated_at=user.updated_at,
                            hashed_password=user.hashed_password,
                        )
                    )

                return user_list
        except Exception as e:
            logger.error(f"Failed to retrieve all users: {e}")
            raise UserDataError(f"Failed to retrieve users: {str(e)}")

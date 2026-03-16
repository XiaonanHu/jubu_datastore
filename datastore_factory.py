"""
Datastore factory for KidsChat.

This module provides factory methods for creating datastore instances,
supporting different database backends and configurations.
"""

import os
from typing import Any, Callable, Dict, Optional, Type, Union

from jubu_datastore.logging import get_logger
from jubu_datastore.common.exceptions import DatastoreError
from jubu_datastore.base_datastore import BaseDatastore
from jubu_datastore.capability_datastore import CapabilityDatastore
from jubu_datastore.conversation_datastore import ConversationDatastore
from jubu_datastore.facts_datastore import FactsDatastore
from jubu_datastore.interaction_contexts_datastore import InteractionContextsDatastore
from jubu_datastore.profile_datastore import ProfileDatastore
from jubu_datastore.story_datastore import StoryDatastore
from jubu_datastore.user_datastore import UserDatastore

logger = get_logger(__name__)


class DatastoreFactory:
    """
    Factory for creating datastore instances.

    This class provides methods for creating different types of datastores
    with appropriate configuration, supporting different database backends.
    """

    _datastore_registry: Dict[str, Type[BaseDatastore]] = {
        "capability": CapabilityDatastore,
        "conversation": ConversationDatastore,
        "facts": FactsDatastore,
        "profile": ProfileDatastore,
        "interaction_contexts": InteractionContextsDatastore,
        "story": StoryDatastore,
        "user": UserDatastore,
    }

    _instances: Dict[str, BaseDatastore] = {}

    @classmethod
    def create_datastore(
        cls,
        datastore_type: str,
        connection_string: Optional[str] = None,
        pool_size: Optional[int] = None,
        encryption_key: Optional[str] = None,
        **kwargs,
    ) -> BaseDatastore:
        """
        Create a datastore instance.

        Args:
            datastore_type: Type of datastore to create
            connection_string: Database connection string
            pool_size: Connection pool size
            encryption_key: Key for encrypting sensitive data
            **kwargs: Additional datastore-specific parameters

        Returns:
            Datastore instance

        Raises:
            DatastoreError: If the datastore type is not supported
        """
        if datastore_type not in cls._datastore_registry:
            logger.error(f"Unsupported datastore type: {datastore_type}")
            raise DatastoreError(f"Unsupported datastore type: {datastore_type}")

        datastore_class = cls._datastore_registry[datastore_type]

        try:
            instance = datastore_class(
                connection_string=connection_string,
                pool_size=pool_size,
                encryption_key=encryption_key,
                **kwargs,
            )
            logger.info(f"Created {datastore_type} datastore")
            return instance
        except Exception as e:
            logger.error(f"Error creating {datastore_type} datastore: {e}")
            raise DatastoreError(
                f"Failed to create {datastore_type} datastore: {str(e)}"
            )

    @classmethod
    def get_datastore(cls, datastore_type: str) -> BaseDatastore:
        """
        Get a singleton instance of a datastore.

        This method returns an existing instance if available,
        or creates a new one if not.

        Args:
            datastore_type: Type of datastore to get

        Returns:
            Datastore instance

        Raises:
            DatastoreError: If the datastore type is not supported
        """
        if datastore_type not in cls._instances:
            cls._instances[datastore_type] = cls.create_datastore(datastore_type)

        return cls._instances[datastore_type]

    @classmethod
    def create_capability_datastore(
        cls,
        connection_string: Optional[str] = None,
        pool_size: Optional[int] = None,
        encryption_key: Optional[str] = None,
    ) -> CapabilityDatastore:
        return cls.create_datastore(
            "capability",
            connection_string=connection_string,
            pool_size=pool_size,
            encryption_key=encryption_key,
        )

    @classmethod
    def create_conversation_datastore(
        cls,
        connection_string: Optional[str] = None,
        pool_size: Optional[int] = None,
        encryption_key: Optional[str] = None,
    ) -> ConversationDatastore:
        return cls.create_datastore(
            "conversation",
            connection_string=connection_string,
            pool_size=pool_size,
            encryption_key=encryption_key,
        )

    @classmethod
    def create_facts_datastore(
        cls,
        connection_string: Optional[str] = None,
        pool_size: Optional[int] = None,
        encryption_key: Optional[str] = None,
    ) -> FactsDatastore:
        return cls.create_datastore(
            "facts",
            connection_string=connection_string,
            pool_size=pool_size,
            encryption_key=encryption_key,
        )

    @classmethod
    def create_profile_datastore(
        cls,
        connection_string: Optional[str] = None,
        pool_size: Optional[int] = None,
        encryption_key: Optional[str] = None,
    ) -> ProfileDatastore:
        return cls.create_datastore(
            "profile",
            connection_string=connection_string,
            pool_size=pool_size,
            encryption_key=encryption_key,
        )

    @classmethod
    def create_interaction_contexts_datastore(
        cls,
        connection_string: Optional[str] = None,
        pool_size: Optional[int] = None,
        encryption_key: Optional[str] = None,
    ) -> InteractionContextsDatastore:
        return cls.create_datastore(
            "interaction_contexts",
            connection_string=connection_string,
            pool_size=pool_size,
            encryption_key=encryption_key,
        )

    @classmethod
    def create_story_datastore(
        cls,
        connection_string: Optional[str] = None,
        pool_size: Optional[int] = None,
        encryption_key: Optional[str] = None,
    ) -> StoryDatastore:
        return cls.create_datastore(
            "story",
            connection_string=connection_string,
            pool_size=pool_size,
            encryption_key=encryption_key,
        )

    @classmethod
    def create_user_datastore(
        cls,
        connection_string: Optional[str] = None,
        pool_size: Optional[int] = None,
        encryption_key: Optional[str] = None,
        password_hasher: Optional[Callable[[str], str]] = None,
    ) -> UserDatastore:
        return cls.create_datastore(
            "user",
            connection_string=connection_string,
            pool_size=pool_size,
            encryption_key=encryption_key,
            password_hasher=password_hasher,
        )

    @classmethod
    def close_all(cls) -> None:
        """Close all datastore connections."""
        for datastore_type, instance in cls._instances.items():
            try:
                instance.close()
                logger.info(f"Closed {datastore_type} datastore")
            except Exception as e:
                logger.error(f"Error closing {datastore_type} datastore: {e}")

        cls._instances.clear()

"""
Datastore factory for KidsChat.

This module provides factory methods for creating datastore instances,
supporting different database backends and configurations.
"""

import os
import threading
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
from jubu_datastore.telemetry_datastore import TelemetryDatastore
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
        "telemetry": TelemetryDatastore,
        "user": UserDatastore,
    }

    _instances: Dict[str, BaseDatastore] = {}
    _instances_lock = threading.Lock()

    @classmethod
    def _instance_key(
        cls,
        datastore_type: str,
        connection_string: Optional[str] = None,
        encryption_key: Optional[str] = None,
    ) -> str:
        """Build a cache key from type and connection parameters."""
        # Resolve defaults so that (None, None) and (env-value, env-value) hit the same key
        conn = connection_string or os.environ.get("DATABASE_URL", "sqlite:///kidschat.db")
        enc = encryption_key or os.environ.get("ENCRYPTION_KEY", "")
        return f"{datastore_type}|{conn}|{enc}"

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
        Get or create a datastore instance (singleton per type + connection params).

        Returns an existing instance when one has already been created with the
        same datastore_type, connection_string, and encryption_key.  This prevents
        connection-pool exhaustion caused by creating a new engine per request.

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

        key = cls._instance_key(datastore_type, connection_string, encryption_key)

        # Fast path without lock
        if key in cls._instances:
            return cls._instances[key]

        with cls._instances_lock:
            # Double-check after acquiring lock
            if key in cls._instances:
                return cls._instances[key]

            datastore_class = cls._datastore_registry[datastore_type]

            try:
                instance = datastore_class(
                    connection_string=connection_string,
                    pool_size=pool_size,
                    encryption_key=encryption_key,
                    **kwargs,
                )
                cls._instances[key] = instance
                logger.info(f"Created {datastore_type} datastore (singleton cached)")
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
        key = cls._instance_key(datastore_type)
        if key not in cls._instances:
            cls.create_datastore(datastore_type)
            # create_datastore now caches in _instances

        return cls._instances[key]

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
    def create_telemetry_datastore(
        cls,
        connection_string: Optional[str] = None,
        pool_size: Optional[int] = None,
        encryption_key: Optional[str] = None,
    ) -> TelemetryDatastore:
        return cls.create_datastore(
            "telemetry",
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
        """Close all datastore sessions and dispose shared engine pools."""
        with cls._instances_lock:
            for key, instance in cls._instances.items():
                try:
                    instance.close()
                    logger.info(f"Closed datastore: {key.split('|')[0]}")
                except Exception as e:
                    logger.error(f"Error closing datastore {key}: {e}")
            cls._instances.clear()

        # Dispose shared engines after all sessions are removed
        BaseDatastore.dispose_engines()

"""
Base datastore for KidsChat.

This module provides the abstract base class for all datastores,
implementing common database operations, connection management,
and security features.
"""

import os
import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar, Union

import sqlalchemy
from cryptography.fernet import Fernet
from sqlalchemy import MetaData, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.pool import QueuePool

from jubu_datastore.logging import get_logger
from jubu_datastore.common.constants import MAX_RETRIES, RETRY_DELAY
from jubu_datastore.common.exceptions import DatabaseConnectionError, DatastoreError

logger = get_logger(__name__)

# Type variable for generic database models
T = TypeVar("T")


class BaseDatastore(ABC, Generic[T]):
    """
    Abstract base class for all datastores.

    This class provides common database operations, connection management,
    transaction handling, and security features like encryption.
    """

    # Maximum number of retries for transient errors
    MAX_RETRIES = MAX_RETRIES
    # Delay between retries (in seconds)
    RETRY_DELAY = RETRY_DELAY
    # Class-level Base attribute
    Base = declarative_base(metadata=MetaData())

    def __init__(
        self,
        connection_string: Optional[str] = None,
        pool_size: Optional[int] = None,
        encryption_key: Optional[str] = None,
        model_class: Optional[Type[T]] = None,
    ):
        self.connection_string = connection_string or os.environ.get(
            "DATABASE_URL", "sqlite:///kidschat.db"
        )
        self.pool_size = pool_size or int(os.environ.get("DB_POOL_SIZE", "10"))
        self.encryption_key = encryption_key or os.environ.get(
            "ENCRYPTION_KEY", Fernet.generate_key().decode()
        )
        self.model_class = model_class

        self._initialize_encryption()
        self._initialize_db_connection()

        logger.info(
            f"Initialized {self.__class__.__name__} with {self.connection_string}"
        )

    def _initialize_encryption(self) -> None:
        """Initialize the encryption engine for sensitive data."""
        try:
            self.cipher_suite = Fernet(
                self.encryption_key.encode()
                if isinstance(self.encryption_key, str)
                else self.encryption_key
            )
            logger.debug("Encryption initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize encryption: {e}")
            raise DatastoreError(f"Encryption initialization failed: {str(e)}")

    def _initialize_db_connection(self) -> None:
        """Initialize the database connection and session factory."""
        try:
            self.engine = create_engine(
                self.connection_string,
                poolclass=QueuePool,
                pool_size=self.pool_size,
                max_overflow=10,
                pool_timeout=30,
                pool_recycle=1800,
                echo=False,
            )

            self.Session = scoped_session(
                sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
            )

            logger.debug("Database connection initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database connection: {e}")
            raise DatabaseConnectionError(f"Database connection failed: {str(e)}")

    @contextmanager
    def session_scope(self):
        """Provide a transactional scope around a series of operations."""
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Transaction error: {e}")
            raise
        finally:
            session.close()

    def encrypt_data(self, data: str) -> bytes:
        """Encrypt sensitive data."""
        if not data:
            return b""
        return self.cipher_suite.encrypt(data.encode())

    def decrypt_data(self, encrypted_data: bytes) -> str:
        """Decrypt sensitive data."""
        if not encrypted_data:
            return ""
        return self.cipher_suite.decrypt(encrypted_data).decode()

    def with_retry(self, func, *args, **kwargs):
        """Execute a function with retry logic for transient errors."""
        retries = 0
        last_error = None

        while retries < self.MAX_RETRIES:
            try:
                return func(*args, **kwargs)
            except (sqlalchemy.exc.OperationalError, sqlalchemy.exc.DatabaseError) as e:
                retries += 1
                last_error = e
                logger.warning(
                    f"Database operation failed (attempt {retries}/{self.MAX_RETRIES}): {e}"
                )

                if retries < self.MAX_RETRIES:
                    sleep_time = self.RETRY_DELAY * (2 ** (retries - 1))
                    time.sleep(sleep_time)
                    continue
                else:
                    break

        logger.error(f"All retries failed: {last_error}")
        raise last_error

    @abstractmethod
    def create(self, data: Dict[str, Any]) -> T:
        pass

    @abstractmethod
    def get(self, record_id: str) -> Optional[T]:
        pass

    @abstractmethod
    def update(self, record_id: str, data: Dict[str, Any]) -> Optional[T]:
        pass

    @abstractmethod
    def delete(self, record_id: str) -> bool:
        pass

    def close(self) -> None:
        """Close database connections and release resources."""
        if hasattr(self, "engine"):
            self.engine.dispose()
            logger.debug("Database connections closed")

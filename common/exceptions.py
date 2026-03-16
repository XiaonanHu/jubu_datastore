"""
Exceptions module for Jubu Chat.

This module defines all custom exceptions used throughout the application,
organized by domain and functionality.
"""

from typing import Any, Dict, Optional


class JubuChatError(Exception):
    """Base exception for all Jubu Chat errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)


# Configuration Exceptions
class ConfigurationError(JubuChatError):
    """Base exception for configuration-related errors."""

    pass


class ConfigValidationError(ConfigurationError):
    """Exception raised when configuration validation fails."""

    pass


class ConfigFileNotFoundError(ConfigurationError):
    """Exception raised when a configuration file is not found."""

    pass


class ConfigParsingError(ConfigurationError):
    """Exception raised when parsing a configuration file fails."""

    pass


# Model Exceptions
class ModelError(JubuChatError):
    """Base exception for model-related errors."""

    pass


class ModelInitializationError(ModelError):
    """Exception raised when initializing a model fails."""

    pass


class ModelInferenceError(ModelError):
    """Exception raised when model inference fails."""

    pass


class ModelNotFoundError(ModelError):
    """Exception raised when a requested model is not found."""

    pass


class PromptError(ModelError):
    """Exception raised when there's an issue with a prompt."""

    pass


# Conversation Exceptions
class ConversationError(JubuChatError):
    """Base exception for conversation-related errors."""

    pass


class SafetyEvaluationError(ConversationError):
    """Exception raised when safety evaluation fails."""

    pass


class ResponseGenerationError(ConversationError):
    """Exception raised when response generation fails."""

    pass


class FactExtractionError(ConversationError):
    """Exception raised when fact extraction fails."""

    pass


class ConversationStateError(ConversationError):
    """Exception raised when there's an issue with conversation state."""

    pass


# Interaction Exceptions
class InteractionHandlerError(ConversationError):
    """Base exception for interaction-related errors."""

    pass


# Parsing Exceptions
class ParsingError(JubuChatError):
    """Base exception for parsing-related errors."""

    pass


class JSONParsingError(ParsingError):
    """Exception raised when JSON parsing fails."""

    pass


class SchemaValidationError(ParsingError):
    """Exception raised when schema validation fails."""

    pass


# Storage Exceptions
class StorageError(JubuChatError):
    """Base exception for storage-related errors."""

    pass


class DatabaseError(StorageError):
    """Exception raised when a database operation fails."""

    pass


class FileStorageError(StorageError):
    """Exception raised when a file storage operation fails."""

    pass


# API Exceptions
class APIError(JubuChatError):
    """Base exception for API-related errors."""

    pass


class AuthenticationError(APIError):
    """Exception raised when authentication fails."""

    pass


class RateLimitError(APIError):
    """Exception raised when a rate limit is exceeded."""

    pass


class ResourceNotFoundError(APIError):
    """Exception raised when a requested resource is not found."""

    pass


# Safety Exceptions
class SafetyError(JubuChatError):
    """Base exception for safety-related errors."""

    pass


class ContentFilterError(SafetyError):
    """Exception raised when content filtering fails."""

    pass


class InappropriateContentError(SafetyError):
    """Exception raised when inappropriate content is detected."""

    pass


class PersonalInformationError(SafetyError):
    """Exception raised when personal information is detected."""

    pass


# Utility Exceptions
class UtilityError(JubuChatError):
    """Base exception for utility-related errors."""

    pass


class LoggingError(UtilityError):
    """Exception raised when logging fails."""

    pass


class TelemetryError(UtilityError):
    """Exception raised when telemetry fails."""

    pass


class DatastoreError(JubuChatError):
    """Base exception for datastore-related errors."""

    pass


class ConversationDataError(DatastoreError):
    """Error related to conversation data operations."""

    pass


class InteractionContextError(DatastoreError):
    """Error related to interaction context operations."""

    pass


class StoryDataError(DatastoreError):
    """Error related to story data operations."""

    pass


class DatabaseConnectionError(DatastoreError):
    """Error related to database connection operations."""

    pass


class DatabaseQueryError(DatastoreError):
    """Error related to database query operations."""

    pass


class FactsDataError(DatastoreError):
    """Error related to facts data operations."""

    pass


class ProfileDataError(DatastoreError):
    """Error related to profile data operations."""

    pass


class UserDataError(DatastoreError):
    """Exception for user datastore errors."""

    pass


class CapabilityDataError(DatastoreError):
    """Error related to capability observation or state operations."""

    pass

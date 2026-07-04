"""
jubu_datastore: shared datastore layer for Jubu.
Owns the SQLAlchemy Base, all table models, all datastore classes,
the DatastoreFactory, and shared constants/exceptions/DTOs.

Clean top-level imports for backend:

    from jubu_datastore import (
        CapabilityDatastore,
        CapabilityObservation,
        ChildCapabilityState,
        CapabilityDefinitionRegistry,
        load_default_registry,
    )
"""

from jubu_datastore.base_datastore import BaseDatastore
from jubu_datastore.capability_datastore import CapabilityDatastore
from jubu_datastore.capability_seed import seed_child_capability_state
from jubu_datastore.common.enums import ConversationState
from jubu_datastore.common.exceptions import (
    APIError,
    AuthenticationError,
    CapabilityDataError,
    ConfigFileNotFoundError,
    ConfigParsingError,
    ConfigurationError,
    ConfigValidationError,
    ContentFilterError,
    ConversationDataError,
    ConversationError,
    ConversationStateError,
    DatabaseConnectionError,
    DatabaseError,
    DatabaseQueryError,
    DatastoreError,
    FactExtractionError,
    FactsDataError,
    FileStorageError,
    InappropriateContentError,
    InteractionHandlerError,
    JSONParsingError,
    JubuChatError,
    LoggingError,
    ModelError,
    ModelInferenceError,
    ModelInitializationError,
    ModelNotFoundError,
    ParsingError,
    PersonalInformationError,
    ProfileDataError,
    PromptError,
    RateLimitError,
    ResourceNotFoundError,
    ResponseGenerationError,
    SafetyError,
    SafetyEvaluationError,
    SchemaValidationError,
    StorageError,
    StoryDataError,
    TelemetryError,
    UserDataError,
    UtilityError,
)
from jubu_datastore.conversation_datastore import (
    ConversationDatastore,
    ConversationModel,
    ConversationTurnModel,
)
from jubu_datastore.datastore_factory import DatastoreFactory
from jubu_datastore.dto.entities import (
    CapabilityObservation,
    ChildCapabilityState,
    ChildProfile,
    User,
)
from jubu_datastore.facts_datastore import ChildFactModel, FactsDatastore
from jubu_datastore.loaders import (
    CapabilityDefinitionRegistry,
    DuplicateItemIdError,
    DuplicatePackError,
    load_default_registry,
    load_definition_pack_from_yaml,
)
from jubu_datastore.models.capability_schema import (
    ChildCapabilityObservationModel,
    ChildCapabilityStateModel,
)
from jubu_datastore.profile_datastore import ChildProfileModel, ProfileDatastore
from jubu_datastore.story_datastore import StoryDatastore, StoryModel
from jubu_datastore.user_datastore import UserDatastore, UserModel

Base = BaseDatastore.Base

__all__ = [
    "Base",
    "BaseDatastore",
    "ConversationState",
    "DatastoreFactory",
    "ConversationModel",
    "ConversationTurnModel",
    "UserModel",
    "ChildProfileModel",
    "ChildFactModel",
    "StoryModel",
    "ChildCapabilityObservationModel",
    "ChildCapabilityStateModel",
    "ConversationDatastore",
    "UserDatastore",
    "ProfileDatastore",
    "FactsDatastore",
    "StoryDatastore",
    "CapabilityDatastore",
    "User",
    "ChildProfile",
    "CapabilityObservation",
    "ChildCapabilityState",
    "CapabilityDefinitionRegistry",
    "DuplicateItemIdError",
    "DuplicatePackError",
    "load_default_registry",
    "load_definition_pack_from_yaml",
    "seed_child_capability_state",
    # Exceptions (previously exposed via `from ...exceptions import *`)
    "APIError",
    "AuthenticationError",
    "CapabilityDataError",
    "ConfigFileNotFoundError",
    "ConfigParsingError",
    "ConfigurationError",
    "ConfigValidationError",
    "ContentFilterError",
    "ConversationDataError",
    "ConversationError",
    "ConversationStateError",
    "DatabaseConnectionError",
    "DatabaseError",
    "DatabaseQueryError",
    "DatastoreError",
    "FactExtractionError",
    "FactsDataError",
    "FileStorageError",
    "InappropriateContentError",
    "InteractionHandlerError",
    "JSONParsingError",
    "JubuChatError",
    "LoggingError",
    "ModelError",
    "ModelInferenceError",
    "ModelInitializationError",
    "ModelNotFoundError",
    "ParsingError",
    "PersonalInformationError",
    "ProfileDataError",
    "PromptError",
    "RateLimitError",
    "ResourceNotFoundError",
    "ResponseGenerationError",
    "SafetyError",
    "SafetyEvaluationError",
    "SchemaValidationError",
    "StorageError",
    "StoryDataError",
    "TelemetryError",
    "UserDataError",
    "UtilityError",
]

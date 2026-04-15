# jubu_datastore

Shared datastore layer for the Jubu platform. This package provides a SQLAlchemy-based persistence layer with connection pooling, encryption, retry logic, and a factory pattern for managing datastore instances.

## Quick Start

```python
from jubu_datastore import DatastoreFactory

# Requires ENCRYPTION_KEY and DATABASE_URL in environment
factory = DatastoreFactory

profile_ds = factory.create_profile_datastore()
user_ds = factory.create_user_datastore()

# At shutdown
factory.close_all()
```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ENCRYPTION_KEY` | **Yes** | -- | Fernet symmetric key for encrypting sensitive data |
| `DATABASE_URL` | No | `sqlite:///kidschat.db` | SQLAlchemy connection string |
| `DB_POOL_SIZE` | No | `5` | Connections per engine pool |

Generate an encryption key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Architecture Overview

```
DatastoreFactory (singleton cache, thread-safe)
 |
 +-- BaseDatastore[T]  (abstract)
 |     - Shared engine pool (one engine per connection string)
 |     - Scoped sessions with auto commit/rollback
 |     - Fernet encryption (encrypt_data / decrypt_data)
 |     - Retry with exponential backoff (3 retries, 0.5s base)
 |     - Schema-once initialization (_ensure_schema)
 |
 +-- 7 Concrete Datastores
 |     UserDatastore         -> users
 |     ProfileDatastore      -> child_profiles
 |     ConversationDatastore -> conversations, conversation_turns
 |     FactsDatastore        -> child_facts
 |     StoryDatastore        -> stories
 |     CapabilityDatastore   -> child_capability_observations, child_capability_state
 |     InteractionContextsDatastore -> interaction_contexts
 |
 +-- CapabilityDefinitionRegistry  (YAML-based, in-memory)
       - Loads framework definitions from capability_definitions/
       - Pydantic-validated item schemas
```

## Documentation

| Document | Description |
|---|---|
| [docs/DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md) | All tables, columns, indexes, and relationships |
| [docs/DATASTORES.md](docs/DATASTORES.md) | Per-datastore API reference and special behaviors |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Connection pooling, threading, factory pattern, engine sharing |
| [docs/CAPABILITY_FRAMEWORK.md](docs/CAPABILITY_FRAMEWORK.md) | Capability definitions, YAML format, registry, and aggregation logic |

## Project Structure

```
jubu_datastore/
  __init__.py                  # Public API exports
  base_datastore.py            # Abstract base: pooling, sessions, encryption, retry
  datastore_factory.py         # Singleton factory with thread-safe caching
  capability_datastore.py      # Capability observations + state aggregation
  conversation_datastore.py    # Conversations and turns
  facts_datastore.py           # Child facts with expiration lifecycle
  interaction_contexts_datastore.py
  profile_datastore.py         # Child profiles (soft-delete, GDPR)
  story_datastore.py           # Stories with search and favorites
  user_datastore.py            # User accounts with password hashing
  capability_seed.py           # Seed zero-state capabilities for new children
  common/
    constants.py               # MAX_RETRIES, RETRY_DELAY, default thresholds
    enums.py                   # ConversationState enum
    exceptions.py              # Exception hierarchy (DatastoreError, etc.)
  dto/
    entities.py                # Pydantic DTOs: User, ChildProfile, CapabilityObservation, etc.
  loaders/
    capability_loader.py       # YAML loader + CapabilityDefinitionRegistry
  models/
    capability_schema.py       # SQLAlchemy models for capability tables
    capability_definitions.py  # Pydantic models for YAML item definitions
  capability_definitions/      # YAML definition packs by framework/age
    casel/
    developmental/
    ngss/
  migrations/                  # Manual migration scripts (create_all + alter)
  logging/
    logger.py                  # Loguru-based logger
  tests/
```

## Dependencies

- Python >= 3.10
- SQLAlchemy (ORM + connection pooling)
- cryptography (Fernet encryption)
- Pydantic (DTOs + YAML validation)
- loguru (structured logging)
- PyYAML (capability definitions)
- python-dotenv (environment config)

# Architecture

## Design Principles

1. **Single shared engine per connection string** -- all 7 datastore types reuse one connection pool when pointing at the same database, preventing pool exhaustion.
2. **Thread-safe singletons** -- both the factory cache and schema initialization use double-checked locking.
3. **Fail-loud configuration** -- missing `ENCRYPTION_KEY` raises immediately rather than silently generating a throwaway key.
4. **Soft deletes by default** -- profiles, users, and conversations use `is_active`/`is_archived` flags for GDPR compliance. Hard-delete methods exist but are separate.
5. **Immutable audit trail** -- capability observations are append-only; `update()` and `delete()` are intentional no-ops.

---

## Connection Lifecycle

```
Application startup
  |
  v
DatastoreFactory.create_datastore("profile", conn_str, enc_key)
  |
  +-- _instance_key() -> "profile|postgresql://...|<key>"
  +-- Lock _instances_lock
  +-- Not cached -> ProfileDatastore.__init__()
  |     |
  |     +-- BaseDatastore.__init__()
  |     |     +-- _initialize_encryption()  -> Fernet cipher
  |     |     +-- _initialize_db_connection()
  |     |           +-- _get_or_create_engine(conn_str)
  |     |           |     Lock _engine_lock
  |     |           |     Engine not cached -> create_engine(QueuePool, pre_ping=True)
  |     |           |     Cache in BaseDatastore._engines[conn_str]
  |     |           +-- scoped_session(bind=engine)
  |     |
  |     +-- _ensure_schema()
  |           Lock _schema_lock
  |           Base.metadata.create_all() -- runs once per conn_str
  |
  +-- Cache in DatastoreFactory._instances[key]
  +-- Return instance
  
Subsequent calls with same (type, conn_str, enc_key)
  -> Return cached instance (no lock needed on fast path)

Application shutdown
  |
  v
DatastoreFactory.close_all()
  +-- Lock _instances_lock
  +-- For each instance: Session.remove()
  +-- Clear _instances
  +-- BaseDatastore.dispose_engines()
        Lock _engine_lock
        For each engine: engine.dispose()
        Clear _engines + _schema_initialized
```

---

## Engine Pool Configuration

| Parameter | Value | Purpose |
|---|---|---|
| `poolclass` | `QueuePool` | Thread-safe FIFO connection pool |
| `pool_size` | 5 (env: `DB_POOL_SIZE`) | Base connections kept open |
| `max_overflow` | 10 | Additional connections under load (total max: 15) |
| `pool_timeout` | 30s | Wait time before raising on pool exhaustion |
| `pool_recycle` | 3600s | Max connection age before replacement |
| `pool_pre_ping` | True | Health-check before handing out a connection |

With 7 datastore types sharing one engine, the total connection footprint is **5 base + 10 overflow = 15 connections** per unique database URL (not 7x that).

---

## Session Management

```python
with datastore.session_scope() as session:
    # auto-commit on success
    # auto-rollback on exception
    # session.close() in finally
```

Sessions are `scoped_session` instances (thread-local). Each datastore creates its own scoped session factory bound to the shared engine. This means different datastore types get independent session lifecycles but share the underlying connection pool.

---

## Retry Logic

`with_retry(func, *args, **kwargs)` wraps any callable with:

- **Max retries:** 3 (from `common.constants.MAX_RETRIES`)
- **Base delay:** 0.5s (from `common.constants.RETRY_DELAY`)
- **Backoff:** Exponential -- `0.5s, 1.0s, 2.0s`
- **Caught exceptions:** `sqlalchemy.exc.OperationalError`, `sqlalchemy.exc.DatabaseError`
- **Behavior:** Re-raises the last error after all retries are exhausted

---

## Encryption

- **Algorithm:** Fernet (AES-128-CBC with HMAC-SHA256)
- **Key source:** `ENCRYPTION_KEY` env var or constructor argument (required)
- **API:** `encrypt_data(str) -> bytes`, `decrypt_data(bytes) -> str`
- **Scope:** Application-layer opt-in. The base class provides the cipher; individual datastores decide which fields to encrypt. Currently no fields are encrypted at the ORM level -- the methods are available for use by consuming applications.

---

## Factory Pattern

`DatastoreFactory` provides two access patterns:

### Typed factory methods (preferred)

```python
DatastoreFactory.create_profile_datastore(connection_string=..., encryption_key=...)
DatastoreFactory.create_user_datastore(password_hasher=my_hasher)
```

### Generic access

```python
DatastoreFactory.create_datastore("profile", connection_string=..., encryption_key=...)
DatastoreFactory.get_datastore("profile")  # uses defaults from env
```

Both are singleton-cached. The cache key is `f"{type}|{connection_string}|{encryption_key}"`, so different connection strings produce separate instances.

### Registry

```python
_datastore_registry = {
    "capability":           CapabilityDatastore,
    "conversation":         ConversationDatastore,
    "facts":                FactsDatastore,
    "profile":              ProfileDatastore,
    "interaction_contexts": InteractionContextsDatastore,
    "story":                StoryDatastore,
    "user":                 UserDatastore,
}
```

---

## Thread Safety Summary

| Resource | Protection | Pattern |
|---|---|---|
| `DatastoreFactory._instances` | `_instances_lock` | Double-checked locking |
| `BaseDatastore._engines` | `_engine_lock` | Lock in `_get_or_create_engine()` |
| `BaseDatastore._schema_initialized` | `_schema_lock` | Double-checked locking in `_ensure_schema()` |
| SQLAlchemy sessions | `scoped_session` | Thread-local session registry |
| SQLAlchemy engine pool | `QueuePool` | Built-in thread safety |

---

## Known Limitations

1. **No multi-tenant isolation.** All queries hit the same tables without tenant scoping. Multi-tenancy would require either a `tenant_id` filter on all queries, schema-per-tenant, or database-per-tenant.

2. **SQLite is not production-ready.** The default `sqlite:///kidschat.db` works for development and demos but cannot handle concurrent writes. Use PostgreSQL (or similar) for production.

3. **No connection-per-request pattern.** Sessions are scoped to threads, not to HTTP requests. In async frameworks (FastAPI with async endpoints), additional care is needed to avoid session leakage across requests.

4. **No Alembic integration.** Schema changes are handled by manual migration scripts in `migrations/` and `create_all(checkfirst=True)`. This works for additive changes but doesn't support column renames, drops, or type changes.

5. **Encryption is opt-in at application layer.** No ORM columns are automatically encrypted. The `encrypt_data`/`decrypt_data` methods must be called explicitly by consuming code.

"""
Shared test setup.

ENCRYPTION_KEY must exist before any datastore is constructed (BaseDatastore
refuses to start without one), and DATABASE_URL must never fall back to the
dev kidschat.db — both are pinned here, before jubu_datastore is imported by
any test module.
"""

import os
import uuid

from cryptography.fernet import Fernet

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest  # noqa: E402

from jubu_datastore.datastore_factory import DatastoreFactory  # noqa: E402


@pytest.fixture
def scratch_db(tmp_path) -> str:
    """A unique on-disk SQLite URL, isolating each test's schema and rows."""
    return f"sqlite:///{tmp_path / f'{uuid.uuid4().hex}.db'}"


@pytest.fixture(autouse=True)
def _isolate_datastore_caches():
    """Reset factory singletons and shared engines between tests.

    BaseDatastore caches one engine per connection string, so without this,
    every test using sqlite:///:memory: shares one live in-memory database and
    rows leak across tests.
    """
    yield
    DatastoreFactory.close_all()

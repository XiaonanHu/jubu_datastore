"""Tests for DatastoreFactory: singleton semantics and thread-safety."""

import os
import threading

import pytest

from jubu_datastore.common.exceptions import DatastoreError
from jubu_datastore.conversation_datastore import ConversationDatastore
from jubu_datastore.datastore_factory import DatastoreFactory
from jubu_datastore.user_datastore import UserDatastore

KEY = os.environ["ENCRYPTION_KEY"]


def test_unsupported_type_raises(scratch_db):
    with pytest.raises(DatastoreError, match="Unsupported datastore type"):
        DatastoreFactory.create_datastore("nonsense", connection_string=scratch_db)


def test_singleton_per_type_and_connection(scratch_db):
    first = DatastoreFactory.create_datastore("user", connection_string=scratch_db)
    second = DatastoreFactory.create_datastore("user", connection_string=scratch_db)
    assert first is second


def test_distinct_types_get_distinct_instances(scratch_db):
    user_ds = DatastoreFactory.create_datastore("user", connection_string=scratch_db)
    conv_ds = DatastoreFactory.create_datastore(
        "conversation", connection_string=scratch_db
    )
    assert user_ds is not conv_ds
    assert isinstance(user_ds, UserDatastore)
    assert isinstance(conv_ds, ConversationDatastore)


def test_distinct_connections_get_distinct_instances(scratch_db, tmp_path):
    other_db = f"sqlite:///{tmp_path / 'other.db'}"
    first = DatastoreFactory.create_datastore("user", connection_string=scratch_db)
    second = DatastoreFactory.create_datastore("user", connection_string=other_db)
    assert first is not second


def test_typed_helper_returns_singleton(scratch_db):
    helper = DatastoreFactory.create_user_datastore(connection_string=scratch_db)
    generic = DatastoreFactory.create_datastore("user", connection_string=scratch_db)
    assert helper is generic
    assert isinstance(helper, UserDatastore)


def test_factory_singleton_under_20_thread_hammer(scratch_db):
    """20 threads racing create_datastore must all get the same instance."""
    thread_count = 20
    iterations = 25
    barrier = threading.Barrier(thread_count)
    seen: list[int] = []
    errors: list[Exception] = []
    lock = threading.Lock()

    def hammer() -> None:
        try:
            barrier.wait()
            for _ in range(iterations):
                ds = DatastoreFactory.create_datastore(
                    "user", connection_string=scratch_db, encryption_key=KEY
                )
                with lock:
                    seen.append(id(ds))
        except Exception as exc:  # pragma: no cover - failure path
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=hammer) for _ in range(thread_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(seen) == thread_count * iterations
    assert len(set(seen)) == 1, "factory returned more than one instance under races"


def test_thread_hammer_across_types(scratch_db):
    """Concurrent creation of different datastore types stays type-correct."""
    types = ["user", "conversation", "facts", "story", "profile"]
    barrier = threading.Barrier(20)
    results: dict[int, list] = {i: [] for i in range(20)}
    errors: list[Exception] = []
    lock = threading.Lock()

    def hammer(worker: int) -> None:
        try:
            barrier.wait()
            for datastore_type in types:
                ds = DatastoreFactory.create_datastore(
                    datastore_type, connection_string=scratch_db, encryption_key=KEY
                )
                results[worker].append(ds)
        except Exception as exc:  # pragma: no cover - failure path
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=hammer, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    for i, datastore_type in enumerate(types):
        instances = {id(results[worker][i]) for worker in range(20)}
        assert len(instances) == 1, f"{datastore_type} was not a singleton"

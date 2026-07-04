"""Tests for UserDatastore: CRUD, soft delete, encryption round-trip."""

import pytest

from jubu_datastore.common.exceptions import UserDataError
from jubu_datastore.user_datastore import UserDatastore


@pytest.fixture
def user_ds(scratch_db):
    ds = UserDatastore(connection_string=scratch_db)
    yield ds
    ds.close()


@pytest.fixture
def user_ds_with_hasher(scratch_db):
    ds = UserDatastore(
        connection_string=scratch_db,
        password_hasher=lambda p: f"hashed:{p}",
    )
    yield ds
    ds.close()


PARENT = {
    "email": "parent@example.com",
    "full_name": "Pat Parent",
    "hashed_password": "argon2:fake",
}


def test_create_and_get(user_ds):
    created = user_ds.create(dict(PARENT))
    assert created.email == PARENT["email"]
    assert created.full_name == PARENT["full_name"]
    assert created.is_active is True

    fetched = user_ds.get(created.id)
    assert fetched is not None
    assert fetched.email == PARENT["email"]
    assert fetched.hashed_password == PARENT["hashed_password"]


def test_get_by_email(user_ds):
    user_ds.create(dict(PARENT))
    assert user_ds.get_by_email(PARENT["email"]).full_name == PARENT["full_name"]
    assert user_ds.get_by_email("nobody@example.com") is None


def test_full_name_is_optional(user_ds):
    created = user_ds.create({"email": "a@b.com", "hashed_password": "x"})
    assert created.full_name is None


def test_create_duplicate_email_raises(user_ds):
    user_ds.create(dict(PARENT))
    with pytest.raises(UserDataError, match="Email already registered"):
        user_ds.create(dict(PARENT))


def test_get_missing_returns_none(user_ds):
    assert user_ds.get("no-such-id") is None


def test_update(user_ds):
    created = user_ds.create(dict(PARENT))
    updated = user_ds.update(created.id, {"full_name": "New Name"})
    assert updated is not None
    assert updated.full_name == "New Name"
    assert updated.email == PARENT["email"]
    assert user_ds.update("no-such-id", {"full_name": "X"}) is None


def test_update_password_without_hasher_raises(user_ds):
    created = user_ds.create(dict(PARENT))
    with pytest.raises(UserDataError, match="password_hasher"):
        user_ds.update(created.id, {"password": "hunter2"})


def test_update_password_with_hasher(user_ds_with_hasher):
    created = user_ds_with_hasher.create(dict(PARENT))
    updated = user_ds_with_hasher.update(created.id, {"password": "hunter2"})
    assert updated.hashed_password == "hashed:hunter2"


def test_soft_delete_keeps_row_deactivated(user_ds):
    created = user_ds.create(dict(PARENT))
    assert user_ds.delete(created.id) is True

    survivor = user_ds.get(created.id)
    assert survivor is not None, "soft delete must keep the row"
    assert survivor.is_active is False


def test_delete_missing_returns_false(user_ds):
    assert user_ds.delete("no-such-id") is False


def test_deactivate(user_ds):
    created = user_ds.create(dict(PARENT))
    assert user_ds.deactivate(created.id) is True
    assert user_ds.get(created.id).is_active is False


def test_hard_delete_removes_row(user_ds):
    created = user_ds.create(dict(PARENT))
    assert user_ds.hard_delete(created.id) is True
    assert user_ds.get(created.id) is None
    assert user_ds.hard_delete(created.id) is False


def test_get_all_users(user_ds):
    user_ds.create(dict(PARENT))
    user_ds.create({"email": "second@example.com", "hashed_password": "y"})
    emails = {u.email for u in user_ds.get_all_users()}
    assert emails == {PARENT["email"], "second@example.com"}


def test_encryption_round_trip(user_ds):
    secret = "sensitive parent data"
    token = user_ds.encrypt_data(secret)
    assert token != secret.encode()
    assert user_ds.decrypt_data(token) == secret
    assert user_ds.encrypt_data("") == b""
    assert user_ds.decrypt_data(b"") == ""

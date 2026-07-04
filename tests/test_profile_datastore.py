"""Tests for ProfileDatastore: CRUD, soft delete, encryption round-trip."""

import pytest

from jubu_datastore.common.exceptions import ProfileDataError
from jubu_datastore.profile_datastore import ProfileDatastore


@pytest.fixture
def profile_ds(scratch_db):
    ds = ProfileDatastore(connection_string=scratch_db)
    yield ds
    ds.close()


PROFILE = {
    "name": "Kiddo",
    "age": 6,
    "parent_declared_interests": ["space", "dinosaurs"],
    "preferences": {"voice_style": "warm"},
    "parent_id": "parent-1",
}


def test_create_and_get(profile_ds):
    created = profile_ds.create(dict(PROFILE))
    assert created.name == "Kiddo"
    assert created.age == 6
    assert created.parent_declared_interests == ["space", "dinosaurs"]
    assert created.is_active is True

    fetched = profile_ds.get(created.id)
    assert fetched is not None
    assert fetched.preferences == {"voice_style": "warm"}
    assert fetched.parent_id == "parent-1"


def test_create_missing_required_field_raises(profile_ds):
    with pytest.raises(ProfileDataError, match="Missing required field"):
        profile_ds.create({"name": "No Age"})


def test_get_missing_returns_none(profile_ds):
    assert profile_ds.get("no-such-child") is None


def test_update(profile_ds):
    created = profile_ds.create(dict(PROFILE))
    updated = profile_ds.update(created.id, {"name": "Renamed", "age": 7})
    assert updated is not None
    assert updated.name == "Renamed"
    assert updated.age == 7
    assert profile_ds.update("no-such-child", {"name": "X"}) is None


def test_update_parent_declared_interests(profile_ds):
    created = profile_ds.create(dict(PROFILE))
    assert profile_ds.update_parent_declared_interests(created.id, ["music"]) is True
    assert profile_ds.get(created.id).parent_declared_interests == ["music"]


def test_update_preferences(profile_ds):
    created = profile_ds.create(dict(PROFILE))
    assert profile_ds.update_preferences(created.id, {"voice_style": "wizard"}) is True
    assert profile_ds.get(created.id).preferences == {"voice_style": "wizard"}


def test_soft_delete_hides_profile_but_keeps_row(profile_ds):
    created = profile_ds.create(dict(PROFILE))
    assert profile_ds.delete(created.id) is True

    # Active-only getter no longer sees it...
    assert profile_ds.get_child_profile(created.id) is None
    # ...but the row survives, deactivated, for account-deletion sweeps.
    all_for_parent = profile_ds.get_all_profiles_by_parent("parent-1")
    assert len(all_for_parent) == 1
    assert all_for_parent[0].is_active is False


def test_hard_delete_removes_row(profile_ds):
    created = profile_ds.create(dict(PROFILE))
    assert profile_ds.delete_child_data(created.id, hard_delete=True) is True
    assert profile_ds.get_all_profiles_by_parent("parent-1") == []


def test_delete_missing_returns_false(profile_ds):
    assert profile_ds.delete("no-such-child") is False


def test_get_profiles_by_parent_excludes_inactive(profile_ds):
    first = profile_ds.create(dict(PROFILE))
    profile_ds.create({**PROFILE, "name": "Sibling"})
    profile_ds.delete(first.id)

    active = profile_ds.get_profiles_by_parent("parent-1")
    assert [p.name for p in active] == ["Sibling"]


def test_encryption_round_trip(profile_ds):
    secret = "child profile notes"
    token = profile_ds.encrypt_data(secret)
    assert token != secret.encode()
    assert profile_ds.decrypt_data(token) == secret

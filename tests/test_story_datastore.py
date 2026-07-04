"""Tests for StoryDatastore: CRUD, favorites, encryption round-trip."""

import pytest

from jubu_datastore.common.exceptions import StoryDataError
from jubu_datastore.story_datastore import StoryDatastore


@pytest.fixture
def story_ds(scratch_db):
    ds = StoryDatastore(connection_string=scratch_db)
    yield ds
    ds.close()


def save_story(ds, story_id="story-1", child_id="child-1", **extra):
    data = {
        "id": story_id,
        "child_id": child_id,
        "conversation_id": "conv-1",
        "title": "The Brave Robot",
        "content": "Once upon a time...",
        **extra,
    }
    ds.save_story(data)
    return story_id


def test_create_and_get(story_ds):
    save_story(story_ds, tags=["robots"])
    stories = story_ds.get_stories_by_child("child-1")
    assert len(stories) == 1
    assert stories[0]["title"] == "The Brave Robot"
    assert stories[0]["content"] == "Once upon a time..."
    assert story_ds.get("story-1") is not None
    assert story_ds.get("no-such-story") is None


def test_create_missing_required_field_raises(story_ds):
    with pytest.raises(StoryDataError, match="Missing required field"):
        story_ds.save_story({"child_id": "child-1", "title": "No content"})


def test_update_existing_story(story_ds):
    save_story(story_ds)
    story_ds.save_story({"title": "The Braver Robot"}, story_id="story-1")
    stories = story_ds.get_stories_by_child("child-1")
    assert stories[0]["title"] == "The Braver Robot"


def test_mark_as_favorite_and_filter(story_ds):
    save_story(story_ds)
    save_story(story_ds, story_id="story-2")

    assert story_ds.mark_as_favorite("story-2") is True
    favorites = story_ds.get_stories_by_child("child-1", favorites_only=True)
    assert [s["id"] for s in favorites] == ["story-2"]

    assert story_ds.mark_as_favorite("story-2", is_favorite=False) is True
    assert story_ds.get_stories_by_child("child-1", favorites_only=True) == []
    assert story_ds.mark_as_favorite("ghost") is False


def test_record_story_view(story_ds):
    save_story(story_ds)
    assert story_ds.record_story_view("story-1") is True
    assert story_ds.record_story_view("ghost") is False


def test_limit_and_offset(story_ds):
    for i in range(5):
        save_story(story_ds, story_id=f"story-{i}")
    assert len(story_ds.get_stories_by_child("child-1", limit=3)) == 3
    assert len(story_ds.get_stories_by_child("child-1", offset=4)) == 1


def test_delete_removes_story(story_ds):
    save_story(story_ds)
    assert story_ds.delete("story-1") is True
    assert story_ds.get("story-1") is None
    assert story_ds.delete("story-1") is False


def test_delete_all_for_child(story_ds):
    save_story(story_ds)
    save_story(story_ds, story_id="story-2")
    save_story(story_ds, story_id="other", child_id="child-2")

    assert story_ds.delete_all_for_child("child-1") == 2
    assert story_ds.get_stories_by_child("child-1") == []
    assert len(story_ds.get_stories_by_child("child-2")) == 1


def test_encryption_round_trip(story_ds):
    secret = "the story content"
    token = story_ds.encrypt_data(secret)
    assert token != secret.encode()
    assert story_ds.decrypt_data(token) == secret

"""Tests for ParentChatDatastore: CRUD, session lifecycle, encryption round-trip."""

import pytest

from jubu_datastore.parent_chat_datastore import ParentChatDatastore


@pytest.fixture
def chat_ds(scratch_db):
    ds = ParentChatDatastore(connection_string=scratch_db)
    yield ds
    ds.close()


def test_create_session_and_get(chat_ds):
    session_id = chat_ds.create_session("parent-1", "child-1", scenario_key="sleep")
    fetched = chat_ds.get(session_id)
    assert fetched is not None
    assert fetched["parent_id"] == "parent-1"
    assert fetched["child_id"] == "child-1"
    assert fetched["scenario_key"] == "sleep"
    assert fetched["is_active"] is True
    assert chat_ds.get("no-such-session") is None


def test_create_via_abc_surface(chat_ds):
    session_id = chat_ds.create({"parent_id": "parent-1", "child_id": "child-1"})
    assert chat_ds.get_session(session_id) is not None


def test_update(chat_ds):
    session_id = chat_ds.create_session("parent-1", "child-1")
    assert chat_ds.update(session_id, {"scenario_key": "meals"}) is not None
    assert chat_ds.get(session_id)["scenario_key"] == "meals"
    assert chat_ds.update("ghost", {"scenario_key": "x"}) is None


def test_messages_round_trip_in_order(chat_ds):
    session_id = chat_ds.create_session("parent-1", "child-1")
    chat_ds.save_message(session_id, "parent", "How do I handle bedtime?")
    chat_ds.save_message(session_id, "assistant", "Routines help a lot.")

    messages = chat_ds.get_session_messages(session_id)
    assert [(m["role"], m["content"]) for m in messages] == [
        ("parent", "How do I handle bedtime?"),
        ("assistant", "Routines help a lot."),
    ]


def test_close_session_soft_deactivates(chat_ds):
    session_id = chat_ds.create_session("parent-1", "child-1")
    chat_ds.close_session(session_id)

    fetched = chat_ds.get(session_id)
    assert fetched is not None, "closing must keep the session row"
    assert fetched["is_active"] is False
    assert chat_ds.close_session("ghost") is None


def test_session_summary(chat_ds):
    session_id = chat_ds.create_session("parent-1", "child-1")
    chat_ds.save_session_summary(session_id, "Discussed bedtime routines.")
    assert chat_ds.get(session_id)["summary"] == "Discussed bedtime routines."


def test_rolling_summary_upsert(chat_ds):
    assert chat_ds.get_rolling_summary("parent-1", "child-1") is None

    chat_ds.upsert_rolling_summary("parent-1", "child-1", "First summary.", 1)
    assert chat_ds.get_rolling_summary("parent-1", "child-1") == "First summary."

    chat_ds.upsert_rolling_summary("parent-1", "child-1", "Updated summary.", 2)
    assert chat_ds.get_rolling_summary_info("parent-1", "child-1") == (
        "Updated summary.",
        2,
    )


def test_list_recent_sessions(chat_ds):
    first = chat_ds.create_session("parent-1", "child-1")
    chat_ds.save_message(first, "parent", "About bedtime...")
    chat_ds.create_session("parent-1", "child-1", scenario_key="meals")
    chat_ds.create_session("parent-2", "child-9")

    recent = chat_ds.list_recent_sessions("parent-1")
    assert len(recent) == 2
    previews = {s["session_id"]: s["last_message_preview"] for s in recent}
    assert previews[first] == "About bedtime..."


def test_delete_removes_session_and_messages(chat_ds):
    session_id = chat_ds.create_session("parent-1", "child-1")
    chat_ds.save_message(session_id, "parent", "hello")

    assert chat_ds.delete(session_id) is True
    assert chat_ds.get(session_id) is None
    assert chat_ds.get_session_messages(session_id) == []
    assert chat_ds.delete(session_id) is False


def test_delete_all_for_child(chat_ds):
    chat_ds.create_session("parent-1", "child-1")
    chat_ds.create_session("parent-1", "child-1")
    chat_ds.create_session("parent-1", "child-2")
    chat_ds.upsert_rolling_summary("parent-1", "child-1", "Summary.", 2)

    assert chat_ds.delete_all_for_child("parent-1", "child-1") == 2
    assert chat_ds.get_rolling_summary("parent-1", "child-1") is None
    assert len(chat_ds.list_recent_sessions("parent-1")) == 1


def test_encryption_round_trip(chat_ds):
    secret = "parent chat content"
    token = chat_ds.encrypt_data(secret)
    assert token != secret.encode()
    assert chat_ds.decrypt_data(token) == secret

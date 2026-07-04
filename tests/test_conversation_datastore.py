"""Tests for ConversationDatastore: CRUD, soft delete, encryption round-trip."""

import pytest

from jubu_datastore.common.enums import ConversationState
from jubu_datastore.common.exceptions import ConversationDataError
from jubu_datastore.conversation_datastore import ConversationDatastore


@pytest.fixture
def conv_ds(scratch_db):
    ds = ConversationDatastore(connection_string=scratch_db)
    yield ds
    ds.close()


def make_conversation(ds, conv_id="conv-1", child_id="child-1", **extra):
    ds.save_conversation({"id": conv_id, "child_id": child_id, **extra})
    return conv_id


def test_create_and_get(conv_ds):
    make_conversation(conv_ds, conv_metadata={"origin": "test"})
    fetched = conv_ds.get("conv-1")
    assert fetched is not None
    assert fetched["child_id"] == "child-1"
    assert fetched["state"] == ConversationState.ACTIVE.value
    assert fetched["is_archived"] is False
    assert fetched["conv_metadata"] == {"origin": "test"}


def test_create_requires_child_id(conv_ds):
    with pytest.raises(ConversationDataError, match="Missing required field"):
        conv_ds.save_conversation({"id": "conv-x"})


def test_get_missing_returns_none(conv_ds):
    assert conv_ds.get("no-such-conversation") is None


def test_add_turns_and_history(conv_ds):
    make_conversation(conv_ds)
    conv_ds.add_conversation_turn(
        "conv-1",
        {"id": "turn-1", "child_message": "hi", "interaction_type": "chat"},
    )
    conv_ds.add_conversation_turn(
        "conv-1",
        {
            "id": "turn-2",
            "child_message": "tell me about space",
            "system_message": "Space is big!",
            "interaction_type": "chat",
        },
    )

    history = conv_ds.get_conversation_history("conv-1")
    assert [t["id"] for t in history] == ["turn-1", "turn-2"]
    assert history[1]["system_message"] == "Space is big!"


def test_add_turn_requires_existing_conversation(conv_ds):
    with pytest.raises(ConversationDataError, match="not found"):
        conv_ds.add_conversation_turn(
            "ghost", {"child_message": "hi", "interaction_type": "chat"}
        )


def test_add_turn_requires_fields(conv_ds):
    make_conversation(conv_ds)
    with pytest.raises(ConversationDataError, match="Missing required field"):
        conv_ds.add_conversation_turn("conv-1", {"child_message": "hi"})


def test_update_conversation_turn(conv_ds):
    make_conversation(conv_ds)
    conv_ds.add_conversation_turn(
        "conv-1", {"id": "turn-1", "child_message": "hi", "interaction_type": "chat"}
    )
    ok = conv_ds.update_conversation_turn(
        "conv-1", "turn-1", {"safety_evaluation": {"flagged": False}}
    )
    assert ok is True
    history = conv_ds.get_conversation_history("conv-1")
    assert history[0]["safety_evaluation"] == {"flagged": False}


def test_update_state_to_ended_sets_end_time(conv_ds):
    make_conversation(conv_ds)
    assert conv_ds.update_conversation_state("conv-1", ConversationState.ENDED) is True
    fetched = conv_ds.get("conv-1")
    assert fetched["state"] == ConversationState.ENDED.value
    assert fetched["end_time"] is not None
    assert conv_ds.update_conversation_state("ghost", ConversationState.ENDED) is False


def test_parent_summary_and_highlights(conv_ds):
    make_conversation(conv_ds)
    assert conv_ds.set_conversation_parent_summary("conv-1", "Talked about space.")
    highlights = {"topics": ["space"], "growth": ["curiosity"]}
    assert conv_ds.set_conversation_parent_highlights("conv-1", highlights)

    fetched = conv_ds.get("conv-1")
    assert fetched["parent_summary"] == "Talked about space."
    assert fetched["parent_highlights"] == highlights


def test_soft_delete_archives_but_keeps_row(conv_ds):
    make_conversation(conv_ds)
    assert conv_ds.delete("conv-1") is True

    survivor = conv_ds.get("conv-1")
    assert survivor is not None, "soft delete must keep the row"
    assert survivor["is_archived"] is True
    assert survivor["state"] == ConversationState.ENDED.value
    assert conv_ds.delete("ghost") is False


def test_hard_delete_removes_conversation_and_turns(conv_ds):
    from jubu_datastore.conversation_datastore import ConversationTurnModel

    make_conversation(conv_ds)
    conv_ds.add_conversation_turn(
        "conv-1", {"id": "turn-1", "child_message": "hi", "interaction_type": "chat"}
    )
    assert conv_ds.hard_delete_conversation("conv-1") is True
    assert conv_ds.get("conv-1") is None
    # history for a missing conversation raises (documented behavior)
    with pytest.raises(ConversationDataError, match="not found"):
        conv_ds.get_conversation_history("conv-1")
    # the ORM cascade must have removed the turns too
    with conv_ds.session_scope() as session:
        assert session.query(ConversationTurnModel).count() == 0


def test_delete_all_for_child(conv_ds):
    make_conversation(conv_ds, conv_id="conv-1")
    make_conversation(conv_ds, conv_id="conv-2")
    make_conversation(conv_ds, conv_id="other", child_id="child-2")

    assert conv_ds.delete_all_for_child("child-1") == 2
    assert conv_ds.get("conv-1") is None
    assert conv_ds.get("other") is not None


def test_encryption_round_trip(conv_ds):
    secret = "what the child said"
    token = conv_ds.encrypt_data(secret)
    assert token != secret.encode()
    assert conv_ds.decrypt_data(token) == secret

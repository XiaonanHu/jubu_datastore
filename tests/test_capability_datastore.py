"""
Unit tests for capability datastore (Step 4).

Covers: insert observation (row stored), update state (aggregation), get_child_capability_state.
"""

from datetime import datetime, timezone

import pytest

from jubu_datastore.capability_datastore import CapabilityDatastore
from jubu_datastore.models.capability_schema import (
    ChildCapabilityObservationModel,
    ChildCapabilityStateModel,
)


@pytest.fixture
def capability_datastore():
    """In-memory SQLite datastore for tests."""
    ds = CapabilityDatastore(connection_string="sqlite:///:memory:")
    yield ds
    ds.close()


@pytest.fixture
def sample_observation():
    return {
        "child_id": "child-1",
        "session_id": "session-1",
        "item_id": "casel.self_awareness.identify_basic_emotions",
        "item_version": 1,
        "framework": "casel",
        "domain": "sel",
        "subdomain": "self_awareness",
        "observation_status": "demonstrated",
        "confidence": 0.9,
        "evidence_text": "Child named the emotion correctly.",
        "evaluator_type": "llm_rubric",
        "evaluator_version": "v1",
        "raw_score_json": {"score": "demonstrated"},
        "observed_at": datetime.now(timezone.utc),
    }


def test_insert_observation_stores_row(capability_datastore, sample_observation):
    """Insert observation and ensure row is stored in child_capability_observations."""
    obs = capability_datastore.insert_capability_observation(sample_observation)
    assert obs.id is not None
    assert obs.child_id == sample_observation["child_id"]
    assert obs.session_id == sample_observation["session_id"]
    assert obs.item_id == sample_observation["item_id"]
    assert obs.observation_status == "demonstrated"

    with capability_datastore.session_scope() as session:
        row = (
            session.query(ChildCapabilityObservationModel)
            .filter(ChildCapabilityObservationModel.id == obs.id)
            .first()
        )
        assert row is not None
        assert row.evidence_text == sample_observation["evidence_text"]


def test_insert_observation_updates_state(capability_datastore, sample_observation):
    """Insert observation and ensure capability state is created/updated (aggregation)."""
    capability_datastore.insert_capability_observation(sample_observation)

    state_by_framework = capability_datastore.get_child_capability_state("child-1")
    assert "casel" in state_by_framework
    items = state_by_framework["casel"]
    assert len(items) == 1
    assert items[0].item_id == sample_observation["item_id"]
    assert items[0].current_status == "demonstrated"
    assert items[0].evidence_count == 1
    assert items[0].mastery_score > 0


def test_aggregation_demonstrated_increases_mastery(capability_datastore, sample_observation):
    """Multiple 'demonstrated' observations increase mastery_score."""
    sample_observation["observation_status"] = "demonstrated"
    capability_datastore.insert_capability_observation(sample_observation)
    sample_observation["session_id"] = "session-2"
    sample_observation["observed_at"] = datetime.now(timezone.utc)
    capability_datastore.insert_capability_observation(sample_observation)

    state_by_framework = capability_datastore.get_child_capability_state("child-1")
    state = state_by_framework["casel"][0]
    assert state.evidence_count == 2
    assert state.mastery_score >= 0.33 + 0.33  # at least two deltas


def test_aggregation_emerging_small_increase(capability_datastore, sample_observation):
    """'emerging' observation adds small mastery delta."""
    sample_observation["observation_status"] = "emerging"
    capability_datastore.insert_capability_observation(sample_observation)

    state_by_framework = capability_datastore.get_child_capability_state("child-1")
    state = state_by_framework["casel"][0]
    assert state.current_status == "emerging"
    assert state.mastery_score > 0
    assert state.mastery_score < 0.33  # smaller than demonstrated


def test_aggregation_not_observed_no_mastery_change(capability_datastore, sample_observation):
    """'not_observed' does not increase mastery_score."""
    sample_observation["observation_status"] = "not_observed"
    capability_datastore.insert_capability_observation(sample_observation)

    state_by_framework = capability_datastore.get_child_capability_state("child-1")
    state = state_by_framework["casel"][0]
    assert state.current_status == "not_observed"
    assert state.mastery_score == 0
    assert state.evidence_count == 1


def test_status_best_so_far_no_regression(capability_datastore, sample_observation):
    """Later not_observed does not overwrite previous demonstrated (best-so-far)."""
    sample_observation["observation_status"] = "demonstrated"
    capability_datastore.insert_capability_observation(sample_observation)
    sample_observation["session_id"] = "session-2"
    sample_observation["observation_status"] = "not_observed"
    capability_datastore.insert_capability_observation(sample_observation)

    state_by_framework = capability_datastore.get_child_capability_state("child-1")
    state = state_by_framework["casel"][0]
    assert state.current_status == "demonstrated"
    assert state.evidence_count == 2


def test_get_child_capability_state_grouped_by_framework(
    capability_datastore, sample_observation
):
    """get_child_capability_state returns items grouped by framework."""
    capability_datastore.insert_capability_observation(sample_observation)

    dev_obs = dict(sample_observation)
    dev_obs["item_id"] = "developmental_milestones.social_emotional.follows_rules"
    dev_obs["framework"] = "developmental_milestones"
    dev_obs["domain"] = "developmental"
    dev_obs["subdomain"] = "social_emotional"
    dev_obs["session_id"] = "session-2"
    capability_datastore.insert_capability_observation(dev_obs)

    state_by_framework = capability_datastore.get_child_capability_state("child-1")
    assert "casel" in state_by_framework
    assert "developmental_milestones" in state_by_framework
    assert len(state_by_framework["casel"]) == 1
    assert len(state_by_framework["developmental_milestones"]) == 1


def test_get_child_capability_state_empty_returns_empty_dict(capability_datastore):
    """get_child_capability_state for child with no state returns empty dict."""
    result = capability_datastore.get_child_capability_state("no-such-child")
    assert result == {}


def test_update_capability_state_standalone(capability_datastore, sample_observation):
    """update_capability_state can be called with an observation dict (e.g. for recalculation)."""
    state = capability_datastore.update_capability_state(
        "child-1",
        sample_observation["item_id"],
        sample_observation,
    )
    assert state.child_id == "child-1"
    assert state.item_id == sample_observation["item_id"]
    assert state.current_status == "demonstrated"
    assert state.evidence_count == 1

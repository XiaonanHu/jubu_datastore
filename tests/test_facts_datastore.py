"""Tests for FactsDatastore: CRUD, soft-delete lifecycle, encryption round-trip."""

from datetime import datetime, timedelta

import pytest

from jubu_datastore.common.exceptions import FactsDataError
from jubu_datastore.facts_datastore import FactsDatastore


@pytest.fixture
def facts_ds(scratch_db):
    ds = FactsDatastore(connection_string=scratch_db)
    yield ds
    ds.close()


def save_fact(ds, fact_id="fact-1", child_id="child-1", **extra):
    data = {"id": fact_id, "content": "likes dinosaurs", "confidence": 0.9, **extra}
    ds.save_child_fact(child_id, data)
    return fact_id


def test_create_and_get(facts_ds):
    save_fact(facts_ds)
    facts = facts_ds.get_child_facts("child-1")
    assert len(facts) == 1
    fact = facts[0]
    assert fact["content"] == "likes dinosaurs"
    assert fact["confidence"] == 0.9
    assert fact["active"] is True
    assert fact["verified"] is False
    assert fact["expiration"] is not None  # defaulted ~30 days out


def test_create_missing_required_field_raises(facts_ds):
    with pytest.raises(FactsDataError, match="Missing required field"):
        facts_ds.save_child_fact("child-1", {"content": "no confidence"})


def test_get_returns_handle_or_none(facts_ds):
    save_fact(facts_ds)
    assert facts_ds.get("fact-1") is not None
    assert facts_ds.get("no-such-fact") is None


def test_update_via_abc_surface(facts_ds):
    save_fact(facts_ds)
    assert facts_ds.update("fact-1", {"content": "loves dinosaurs"}) is not None
    assert facts_ds.get_child_facts("child-1")[0]["content"] == "loves dinosaurs"
    assert facts_ds.update("no-such-fact", {"content": "x"}) is None


def test_update_fact_confidence(facts_ds):
    save_fact(facts_ds)
    assert facts_ds.update_fact_confidence("fact-1", 0.4) is True
    assert facts_ds.get_child_facts("child-1")[0]["confidence"] == 0.4


def test_verify_fact(facts_ds):
    save_fact(facts_ds)
    assert facts_ds.verify_fact("fact-1") is True
    assert facts_ds.get_child_facts("child-1", verified_only=True) != []


def test_hard_delete(facts_ds):
    save_fact(facts_ds)
    assert facts_ds.delete("fact-1") is True
    assert facts_ds.get("fact-1") is None
    assert facts_ds.delete("fact-1") is False


def test_expire_old_facts_soft_deletes(facts_ds):
    save_fact(facts_ds, expiration=datetime.utcnow() - timedelta(days=1))
    save_fact(facts_ds, fact_id="fact-fresh")

    assert facts_ds.expire_old_facts() == 1

    active = facts_ds.get_child_facts("child-1", active_only=True)
    assert [f["id"] for f in active] == ["fact-fresh"]
    # Soft delete: the expired fact's row survives, deactivated.
    everything = facts_ds.get_child_facts("child-1", active_only=False)
    expired = next(f for f in everything if f["id"] == "fact-1")
    assert expired["active"] is False


def test_delete_expired_facts_hard_deletes_after_grace(facts_ds):
    save_fact(facts_ds, expiration=datetime.utcnow() - timedelta(days=40))
    save_fact(
        facts_ds,
        fact_id="fact-recent",
        expiration=datetime.utcnow() - timedelta(days=1),
    )

    assert facts_ds.delete_expired_facts(grace_days=30) == 1

    remaining = facts_ds.get_child_facts("child-1", active_only=False)
    assert [f["id"] for f in remaining] == ["fact-recent"]


def test_get_active_facts_excludes_expired(facts_ds):
    save_fact(facts_ds, expiration=datetime.utcnow() - timedelta(days=1))
    save_fact(facts_ds, fact_id="fact-fresh")

    active = facts_ds.get_active_facts_for_child("child-1")
    assert len(active) == 1


def test_min_confidence_filter(facts_ds):
    save_fact(facts_ds, confidence=0.9)
    save_fact(facts_ds, fact_id="fact-low", confidence=0.2)

    confident = facts_ds.get_child_facts("child-1", min_confidence=0.5)
    assert [f["id"] for f in confident] == ["fact-1"]


def test_delete_all_for_child(facts_ds):
    save_fact(facts_ds)
    save_fact(facts_ds, fact_id="fact-2")
    save_fact(facts_ds, fact_id="other", child_id="child-2")

    assert facts_ds.delete_all_for_child("child-1") == 2
    assert facts_ds.get_child_facts("child-1", active_only=False) == []
    assert len(facts_ds.get_child_facts("child-2", active_only=False)) == 1


def test_encryption_round_trip(facts_ds):
    secret = "fact about the child"
    token = facts_ds.encrypt_data(secret)
    assert token != secret.encode()
    assert facts_ds.decrypt_data(token) == secret

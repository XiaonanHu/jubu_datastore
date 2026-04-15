"""
Capability datastore for KidsChat.

Stores evaluation results per child: raw observations (one per session/evaluation)
and aggregated capability state (one row per child_id, item_id) for parent app.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from jubu_datastore.base_datastore import BaseDatastore
from jubu_datastore.common.exceptions import CapabilityDataError
from jubu_datastore.dto.entities import CapabilityObservation, ChildCapabilityState
from jubu_datastore.logging import get_logger
from jubu_datastore.models.capability_schema import (
    ChildCapabilityObservationModel,
    ChildCapabilityStateModel,
)

logger = get_logger(__name__)

# Demo aggregation: score deltas per observation status
MASTERY_DELTA_DEMONSTRATED = 0.33
MASTERY_DELTA_EMERGING = 0.10
MASTERY_MAX = 1.0

# Status ordering for "best so far": do not let a later not_observed overwrite demonstrated
_STATUS_RANK = {"demonstrated": 2, "emerging": 1, "not_observed": 0}


class CapabilityDatastore(BaseDatastore):
    """
    Datastore for capability observations and child capability state.

    Insert observations (never delete); state is updated from observations
    for parent app retrieval.
    """

    def __init__(
        self,
        connection_string: Optional[str] = None,
        pool_size: Optional[int] = None,
        encryption_key: Optional[str] = None,
    ):
        super().__init__(
            connection_string=connection_string,
            pool_size=pool_size,
            encryption_key=encryption_key,
            model_class=ChildCapabilityObservationModel,
        )
        self._ensure_schema()

    def create(self, data: Dict[str, Any]) -> CapabilityObservation:
        """Create and return a capability observation (convenience for generic interface)."""
        return self.insert_capability_observation(data)

    def get(self, record_id: str) -> Optional[CapabilityObservation]:
        """Get one observation by id."""
        try:
            with self.session_scope() as session:
                row = (
                    session.query(ChildCapabilityObservationModel)
                    .filter(ChildCapabilityObservationModel.id == record_id)
                    .first()
                )
                if not row:
                    return None
                return self._observation_to_entity(row)
        except Exception as e:
            logger.error(f"Error getting observation {record_id}: {e}")
            raise CapabilityDataError(f"Failed to get observation: {str(e)}")

    def update(self, record_id: str, data: Dict[str, Any]) -> Optional[CapabilityObservation]:
        """Observations are immutable; update not supported."""
        logger.warning("Capability observations are immutable; update ignored")
        return self.get(record_id)

    def delete(self, record_id: str) -> bool:
        """Observations should never be deleted."""
        logger.warning("Capability observations must not be deleted")
        return False

    def _observation_to_entity(self, m: ChildCapabilityObservationModel) -> CapabilityObservation:
        return CapabilityObservation(
            id=m.id,
            child_id=m.child_id,
            session_id=m.session_id,
            item_id=m.item_id,
            item_version=m.item_version,
            framework=m.framework,
            domain=m.domain,
            subdomain=m.subdomain,
            observation_status=m.observation_status,
            confidence=m.confidence,
            evidence_text=m.evidence_text,
            evaluator_type=m.evaluator_type,
            evaluator_version=m.evaluator_version,
            raw_score_json=m.raw_score_json,
            observed_at=m.observed_at,
            created_at=m.created_at,
        )

    def _state_to_entity(self, m: ChildCapabilityStateModel) -> ChildCapabilityState:
        return ChildCapabilityState(
            id=m.id,
            child_id=m.child_id,
            item_id=m.item_id,
            item_version=m.item_version,
            framework=m.framework,
            domain=m.domain,
            subdomain=m.subdomain,
            current_status=m.current_status,
            confidence=m.confidence,
            mastery_score=m.mastery_score or 0.0,
            evidence_count=m.evidence_count or 0,
            first_observed_at=m.first_observed_at,
            last_observed_at=m.last_observed_at,
            last_session_id=m.last_session_id,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )

    def insert_capability_observation(
        self,
        observation_data: Dict[str, Any],
    ) -> CapabilityObservation:
        """
        Insert one observation and update the corresponding capability state.

        Required keys: child_id, session_id, item_id, item_version, framework, domain, subdomain,
        observation_status, evaluator_type, observed_at.
        Optional: confidence, evidence_text, evaluator_version, raw_score_json.
        """
        try:
            obs_id = observation_data.get("id") or str(uuid.uuid4())
            observed_at = observation_data.get("observed_at")
            if isinstance(observed_at, datetime):
                pass
            elif observed_at is not None:
                observed_at = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
            else:
                observed_at = datetime.utcnow()

            with self.session_scope() as session:
                obs = ChildCapabilityObservationModel(
                    id=obs_id,
                    child_id=observation_data["child_id"],
                    session_id=observation_data["session_id"],
                    item_id=observation_data["item_id"],
                    item_version=int(observation_data["item_version"]),
                    framework=observation_data["framework"],
                    domain=observation_data["domain"],
                    subdomain=observation_data["subdomain"],
                    observation_status=observation_data["observation_status"],
                    confidence=observation_data.get("confidence"),
                    evidence_text=observation_data.get("evidence_text"),
                    evaluator_type=observation_data["evaluator_type"],
                    evaluator_version=observation_data.get("evaluator_version"),
                    raw_score_json=observation_data.get("raw_score_json"),
                    observed_at=observed_at,
                )
                session.add(obs)
                session.flush()
                self._update_capability_state_in_session(
                    session,
                    observation_data["child_id"],
                    observation_data["item_id"],
                    int(observation_data["item_version"]),
                    observation_data["framework"],
                    observation_data["domain"],
                    observation_data["subdomain"],
                    observation_data["observation_status"],
                    observation_data.get("confidence"),
                    observed_at,
                    observation_data["session_id"],
                )
                session.commit()
                return self._observation_to_entity(obs)
        except Exception as e:
            logger.error(f"Error inserting capability observation: {e}")
            raise CapabilityDataError(f"Failed to insert observation: {str(e)}")

    def _update_capability_state_in_session(
        self,
        session: Any,
        child_id: str,
        item_id: str,
        item_version: int,
        framework: str,
        domain: str,
        subdomain: str,
        observation_status: str,
        confidence: Optional[float],
        observed_at: datetime,
        session_id: str,
    ) -> ChildCapabilityStateModel:
        """Upsert child_capability_state from observation (aggregation). Returns the state row."""
        state = (
            session.query(ChildCapabilityStateModel)
            .filter(
                ChildCapabilityStateModel.child_id == child_id,
                ChildCapabilityStateModel.item_id == item_id,
            )
            .first()
        )

        if observation_status == "demonstrated":
            mastery_delta = MASTERY_DELTA_DEMONSTRATED
        elif observation_status == "emerging":
            mastery_delta = MASTERY_DELTA_EMERGING
        else:
            mastery_delta = 0.0

        if state:
            state.item_version = item_version
            state.framework = framework
            state.domain = domain
            state.subdomain = subdomain
            # Best-so-far: do not let not_observed overwrite demonstrated/emerging
            obs_rank = _STATUS_RANK.get(observation_status, -1)
            curr_rank = _STATUS_RANK.get(state.current_status, -1)
            if obs_rank >= curr_rank:
                state.current_status = observation_status
            state.confidence = confidence
            state.mastery_score = min(
                MASTERY_MAX,
                (state.mastery_score or 0.0) + mastery_delta,
            )
            state.evidence_count = (state.evidence_count or 0) + 1
            state.last_observed_at = observed_at
            state.last_session_id = session_id
            if state.first_observed_at is None:
                state.first_observed_at = observed_at
            state.updated_at = datetime.utcnow()
        else:
            # New state: use observation status as-is
            state = ChildCapabilityStateModel(
                id=str(uuid.uuid4()),
                child_id=child_id,
                item_id=item_id,
                item_version=item_version,
                framework=framework,
                domain=domain,
                subdomain=subdomain,
                current_status=observation_status,
                confidence=confidence,
                mastery_score=min(MASTERY_MAX, mastery_delta),
                evidence_count=1,
                first_observed_at=observed_at,
                last_observed_at=observed_at,
                last_session_id=session_id,
            )
            session.add(state)
        session.flush()
        return state

    def update_capability_state(
        self,
        child_id: str,
        item_id: str,
        observation: Dict[str, Any],
    ) -> ChildCapabilityState:
        """
        Update (upsert) capability state for (child_id, item_id) from an observation.

        Usually called internally by insert_capability_observation; exposed for recalculation.
        """
        try:
            observed_at = observation.get("observed_at")
            if isinstance(observed_at, datetime):
                pass
            elif observed_at is not None:
                observed_at = datetime.fromisoformat(str(observed_at).replace("Z", "+00:00"))
            else:
                observed_at = datetime.utcnow()
            with self.session_scope() as session:
                state = self._update_capability_state_in_session(
                    session,
                    child_id,
                    item_id,
                    int(observation["item_version"]),
                    observation["framework"],
                    observation["domain"],
                    observation["subdomain"],
                    observation["observation_status"],
                    observation.get("confidence"),
                    observed_at,
                    observation["session_id"],
                )
                session.commit()
                return self._state_to_entity(state)
        except CapabilityDataError:
            raise
        except Exception as e:
            logger.error(f"Error updating capability state: {e}")
            raise CapabilityDataError(f"Failed to update state: {str(e)}")

    def get_child_capability_state(
        self,
        child_id: str,
    ) -> Dict[str, List[ChildCapabilityState]]:
        """
        Return current capability state for the child, grouped by framework.

        Used by parent app; no need to recompute from observations.
        """
        try:
            with self.session_scope() as session:
                rows = (
                    session.query(ChildCapabilityStateModel)
                    .filter(ChildCapabilityStateModel.child_id == child_id)
                    .all()
                )
                result: Dict[str, List[ChildCapabilityState]] = {}
                for row in rows:
                    ent = self._state_to_entity(row)
                    result.setdefault(row.framework, []).append(ent)
                return result
        except Exception as e:
            logger.error(f"Error getting capability state for child {child_id}: {e}")
            raise CapabilityDataError(f"Failed to get child capability state: {str(e)}")

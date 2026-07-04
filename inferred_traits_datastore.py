"""
Inferred-traits datastore — durable, system-learned engagement traits per child.

One row per child. Part of the `LearnedProfile` umbrella (ENG-347): it holds traits
the SYSTEM inferred about HOW the child likes to engage — kept deliberately separate
from the parent-declared `child_profiles` (declared lifetime) and from the biometric
`voice_signatures` store (gated). Written ONLY at end-of-session consolidation, never
on the hot path.

Every field here is HIDDEN (internal steering) — none of it is parent-facing.
"""

from datetime import datetime
from typing import Any, Dict, Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from jubu_datastore.base_datastore import BaseDatastore
from jubu_datastore.common.exceptions import DatastoreError
from jubu_datastore.logging import get_logger

logger = get_logger(__name__)


class InferredTraitsModel(BaseDatastore.Base):
    """SQLAlchemy model for a child's inferred engagement traits (one row per child)."""

    __tablename__ = "inferred_traits"

    child_id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)

    # {kind: "deepener" | "widener" | "balanced"} — how the child tends to explore
    # each topic kind. Derived from the observed_interests ledger by
    # curiosity_mode_policy. Lifetime learned · owner system · writer end-of-session
    # consolidation · reader session_seed fan-out bias · visibility hidden.
    curiosity_mode_by_kind: Mapped[dict[str, str]] = mapped_column(
        sa.JSON, nullable=False, default=dict
    )

    # Voice style codename that lands best for this child — the derived argmax of
    # `voice_style_scores` (ENG-347 Phase 3d). visibility hidden — NEVER parent-facing.
    preferred_style: Mapped[Optional[str]] = mapped_column(sa.String(64), nullable=True)
    preferred_style_confidence: Mapped[Optional[float]] = mapped_column(
        sa.Float, nullable=True
    )

    # Learned voice-style bandit state, relocated out of the parent-declared
    # `child_profiles.preferences` blob (ENG-347 Phase 3d) into its rightful
    # learned home: {codename: {"n": int, "score": float}} running means the
    # ε-greedy style selector reads. Lifetime learned · owner system · writer
    # end-of-session `update_voice_style_score` · reader `select_style_for_session` ·
    # visibility hidden. (The parent OVERRIDE `voice_style` stays in preferences —
    # that is parent-declared, not learned.)
    voice_style_scores: Mapped[dict[str, Any]] = mapped_column(
        sa.JSON, nullable=False, default=dict
    )

    # How many sessions have contributed to these traits.
    evidence_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class InferredTraitsDatastore(BaseDatastore):
    """Datastore for the per-child inferred-traits row (the LearnedProfile scalars)."""

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
            model_class=InferredTraitsModel,
        )
        self._ensure_schema()

    # BaseDatastore abstract surface -------------------------------------

    def create(self, data: Dict[str, Any]) -> InferredTraitsModel:
        return self.upsert_inferred_traits(data["child_id"], data)

    def get(self, record_id: str) -> Optional[InferredTraitsModel]:
        with self.session_scope() as session:
            return (
                session.query(InferredTraitsModel)
                .filter(InferredTraitsModel.child_id == record_id)
                .first()
            )

    def update(
        self, record_id: str, data: Dict[str, Any]
    ) -> Optional[InferredTraitsModel]:
        return self.upsert_inferred_traits(record_id, data)

    def delete(self, record_id: str) -> bool:
        return self.delete_all_for_child(record_id) > 0

    # Trait operations ---------------------------------------------------

    _WRITABLE = (
        "curiosity_mode_by_kind",
        "preferred_style",
        "preferred_style_confidence",
        "voice_style_scores",
    )

    def upsert_inferred_traits(
        self, child_id: str, traits: Dict[str, Any]
    ) -> InferredTraitsModel:
        """Insert or update a child's inferred-traits row.

        Only the keys present in `traits` (restricted to the writable columns) are
        applied, so a caller updating just `curiosity_mode_by_kind` never clobbers
        `preferred_style`, and vice-versa. `evidence_count` bumps by one per upsert.
        """
        if not child_id:
            raise DatastoreError("upsert_inferred_traits requires a child_id")
        try:
            with self.session_scope() as session:
                row = (
                    session.query(InferredTraitsModel)
                    .filter(InferredTraitsModel.child_id == child_id)
                    .first()
                )
                if row is None:
                    row = InferredTraitsModel(
                        child_id=child_id,
                        curiosity_mode_by_kind=traits.get("curiosity_mode_by_kind", {})
                        or {},
                        preferred_style=traits.get("preferred_style"),
                        preferred_style_confidence=traits.get(
                            "preferred_style_confidence"
                        ),
                        voice_style_scores=traits.get("voice_style_scores", {}) or {},
                        evidence_count=1,
                    )
                    session.add(row)
                else:
                    for key in self._WRITABLE:
                        if key in traits:
                            setattr(row, key, traits[key])
                    row.evidence_count = (row.evidence_count or 0) + 1
                    row.updated_at = datetime.utcnow()
                session.commit()
                return row
        except Exception as e:
            logger.error(f"Error upserting inferred traits for child {child_id}: {e}")
            raise DatastoreError(f"Failed to upsert inferred traits: {str(e)}")

    def get_inferred_traits_for_child(self, child_id: str) -> Optional[Dict[str, Any]]:
        """Return a child's inferred-traits row as a dict, or None if not yet learned."""
        try:
            with self.session_scope() as session:
                row = (
                    session.query(InferredTraitsModel)
                    .filter(InferredTraitsModel.child_id == child_id)
                    .first()
                )
                if row is None:
                    return None
                return {
                    "child_id": row.child_id,
                    "curiosity_mode_by_kind": row.curiosity_mode_by_kind or {},
                    "preferred_style": row.preferred_style,
                    "preferred_style_confidence": row.preferred_style_confidence,
                    "voice_style_scores": row.voice_style_scores or {},
                    "evidence_count": row.evidence_count,
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                }
        except Exception as e:
            logger.error(f"Error retrieving inferred traits for child {child_id}: {e}")
            raise DatastoreError(f"Failed to retrieve inferred traits: {str(e)}")

    def delete_all_for_child(self, child_id: str) -> int:
        """Hard-delete a child's inferred-traits row (GDPR/COPPA)."""
        try:
            with self.session_scope() as session:
                count = (
                    session.query(InferredTraitsModel)
                    .filter(InferredTraitsModel.child_id == child_id)
                    .delete(synchronize_session=False)
                )
                session.commit()
            logger.info(f"Hard-deleted inferred traits for child {child_id}")
            return count
        except Exception as e:
            logger.error(f"Error deleting inferred traits for child {child_id}: {e}")
            raise DatastoreError(f"Failed to delete inferred traits: {str(e)}")

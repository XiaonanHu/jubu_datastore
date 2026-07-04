"""Child aggregate — the READ-ONLY facade over a child's full picture (ENG-347 Phase 4).

Composes the two umbrellas so callers have ONE place to read a child, instead of
wiring up four datastores by hand:

  - `DeclaredProfile` — what the PARENT declared (declared lifetime, parent-owned):
    `child_profiles`.
  - `LearnedProfile` — what the SYSTEM learned (learned lifetime, system-owned):
    `observed_interests` + `child_capability_state` + `inferred_traits`, plus the
    preferred voice style (currently learned by the style bandit and stored under
    `child_profiles.preferences["voice_style"]` — the facade hides that location so a
    later relocation into `inferred_traits` is invisible to callers).

READ-ONLY by design: this class never writes. Every field keeps its own writer and
store; the facade only aggregates reads. Writes stay on `ProfileDatastore`,
`ObservedInterestsDatastore`, the capability eval, and the end-of-session
consolidation — one writer per field, no god-object. See the child-profile plan.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from jubu_datastore.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DeclaredProfile:
    """Parent-declared attributes (declared lifetime, parent-owned, parent-facing)."""

    child_id: str
    name: Optional[str] = None
    age: Optional[int] = None
    parent_declared_interests: List[str] = field(default_factory=list)
    preferences: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LearnedProfile:
    """System-inferred attributes (learned lifetime, system-owned).

    `interests` and `capabilities` are parent-facing (they back the mind-map and the
    skills donut). `curiosity_mode_by_kind` and `preferred_style` are HIDDEN —
    internal steering only, never returned to a parent-facing surface.
    """

    interests: List[Dict[str, Any]] = field(default_factory=list)
    capabilities: Dict[str, Any] = field(default_factory=dict)
    curiosity_mode_by_kind: Dict[str, str] = field(default_factory=dict)
    preferred_style: Optional[str] = None

    def curiosity_mode(self, kind: str) -> Optional[str]:
        """The child's deepener/widener/balanced tendency for `kind`, or None if not
        yet learned for that kind."""
        return self.curiosity_mode_by_kind.get(kind)


@dataclass
class Child:
    """Read-only aggregate: a child's declared + learned picture."""

    child_id: str
    declared: DeclaredProfile
    learned: LearnedProfile

    @classmethod
    def load(
        cls,
        child_id: str,
        *,
        profile_datastore: Any = None,
        observed_interests_datastore: Any = None,
        capability_datastore: Any = None,
        inferred_traits_datastore: Any = None,
    ) -> Optional["Child"]:
        """Load a child's full picture, or None if the child has no profile.

        Each store is read best-effort and in isolation: a failure in one (e.g. the
        capability store) leaves that slice empty but never blocks the rest. Datastores
        may be injected (for tests); otherwise they come from `DatastoreFactory`.
        """
        if not child_id:
            return None

        if (
            profile_datastore is None
            or observed_interests_datastore is None
            or capability_datastore is None
            or inferred_traits_datastore is None
        ):
            # Lazy import to avoid an import cycle at module load.
            from jubu_datastore.datastore_factory import DatastoreFactory

            profile_datastore = (
                profile_datastore or DatastoreFactory.create_profile_datastore()
            )
            observed_interests_datastore = (
                observed_interests_datastore
                or DatastoreFactory.create_observed_interests_datastore()
            )
            capability_datastore = (
                capability_datastore or DatastoreFactory.create_capability_datastore()
            )
            inferred_traits_datastore = (
                inferred_traits_datastore
                or DatastoreFactory.create_inferred_traits_datastore()
            )

        profile = None
        try:
            profile = profile_datastore.get_child_profile(child_id)
        except Exception as e:
            logger.warning(f"Child.load: profile read failed for {child_id}: {e}")
        if profile is None:
            return None

        declared = DeclaredProfile(
            child_id=child_id,
            name=getattr(profile, "name", None),
            age=getattr(profile, "age", None),
            parent_declared_interests=list(
                getattr(profile, "parent_declared_interests", None) or []
            ),
            preferences=dict(getattr(profile, "preferences", None) or {}),
        )

        interests: List[Dict[str, Any]] = []
        try:
            interests = (
                observed_interests_datastore.get_observed_interests_for_child(child_id)
                or []
            )
        except Exception as e:
            logger.warning(f"Child.load: interests read failed for {child_id}: {e}")

        capabilities: Dict[str, Any] = {}
        try:
            capabilities = (
                capability_datastore.get_child_capability_state(child_id) or {}
            )
        except Exception as e:
            logger.warning(f"Child.load: capabilities read failed for {child_id}: {e}")

        curiosity_mode_by_kind: Dict[str, str] = {}
        preferred_style: Optional[str] = None
        try:
            traits = inferred_traits_datastore.get_inferred_traits_for_child(child_id)
            if traits:
                curiosity_mode_by_kind = dict(
                    traits.get("curiosity_mode_by_kind") or {}
                )
                # Learned favourite style (argmax of the bandit scores), now living
                # in inferred_traits (ENG-347 Phase 3d). Distinct from the parent
                # OVERRIDE in declared.preferences["voice_style"].
                preferred_style = traits.get("preferred_style")
        except Exception as e:
            logger.warning(
                f"Child.load: inferred traits read failed for {child_id}: {e}"
            )

        learned = LearnedProfile(
            interests=interests,
            capabilities=capabilities,
            curiosity_mode_by_kind=curiosity_mode_by_kind,
            preferred_style=preferred_style,
        )
        return cls(child_id=child_id, declared=declared, learned=learned)

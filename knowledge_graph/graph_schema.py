"""
Pydantic schema for knowledge-graph YAML packs.

The knowledge graph is the Story Studio curriculum + dashboard engine: four
independent axes (knowledge_domain, sel_theme, value_lesson, story_element)
whose nodes
are tagged onto stories. Nodes are authored at age-band level (3-4 through 11-12)
and carry per-year ``age_treatments`` so each age sees a different lens on the
same node.

The graph describes *content coverage only* — never child assessment. Nothing
in this schema may reference an individual child.
"""

from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Axis = Literal["knowledge_domain", "sel_theme", "value_lesson", "story_element"]

AXES: tuple[str, ...] = (
    "knowledge_domain",
    "sel_theme",
    "value_lesson",
    "story_element",
)

# A node id is its axis name + "." + its label ("knowledge_domain.volcanoes").
# Spelled out in full — no abbreviations to decode.
AXIS_ID_PREFIXES: dict[str, str] = {axis: f"{axis}." for axis in AXES}

# Age bands are the authoring/review granularity (the psychologist reviews
# band graphs, not per-year graphs). Years are the serving granularity.
AGE_BAND_YEARS: dict[str, tuple[int, ...]] = {
    "3-4": (3, 4),
    "5-6": (5, 6),
    "7-8": (7, 8),
    "9-10": (9, 10),
    "11-12": (11, 12),
}

MIN_AGE_YEARS = 3
MAX_AGE_YEARS = 12

# Depth levels are named by meaning, never by index (CLAUDE.md rule 10).
# story_element is a discovery hook, not curriculum, so it has no depth ladder.
AXIS_DEPTH_LEVELS: dict[str, tuple[str, ...]] = {
    "knowledge_domain": ("sensory", "mechanism", "system"),
    "sel_theme": (
        "naming_the_feeling",
        "navigating_the_feeling",
        "understanding_others",
    ),
    "value_lesson": ("concrete_example", "gray_areas"),
    "story_element": (),
}

NodeStatus = Literal["draft", "reviewed", "published"]

# Two tiers of node (see KNOWLEDGE_GRAPH_POLICY.md §5):
#   curriculum — the default map every family sees; full per-year treatments.
#   deep_dive  — a fine-grained child of one curriculum node ("octopus" under
#                "ocean_animals"), revealed when a family expands it. Inherits
#                its parent's bands, treatments, and avoid list as fallback.
Tier = Literal["curriculum", "deep_dive"]

# Node label: canonical topic noun in snake_case ("volcanoes"), never a
# sentence about the child (CLAUDE.md rule 5).
LABEL_PATTERN = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")
NODE_ID_PATTERN = re.compile(
    r"^(" + "|".join(AXES) + r")\.[a-z][a-z0-9]*(_[a-z0-9]+)*$"
)


class AgeTreatment(BaseModel):
    """Per-year lens on a node: what a story at this age should do with it."""

    model_config = ConfigDict(extra="forbid")

    depth: Optional[str] = None
    framing: str = Field(..., min_length=1)
    vocabulary: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)

    @field_validator("vocabulary", "avoid", mode="after")
    @classmethod
    def _strip_entries(cls, values: list[str]) -> list[str]:
        cleaned = [entry.strip() for entry in values]
        if any(not entry for entry in cleaned):
            raise ValueError("empty entry in vocabulary/avoid list")
        return cleaned


class NodeEdges(BaseModel):
    """
    Edges of one node.

    ``adjacent`` is undirected "next territory" (Topic Map hints, recommender).
    ``prerequisite`` is directed and sparse: node ids that should come first.
    """

    model_config = ConfigDict(extra="forbid")

    adjacent: list[str] = Field(default_factory=list)
    prerequisite: list[str] = Field(default_factory=list)


class Crosswalk(BaseModel):
    """Optional links into existing frameworks (NGSS codes, CASEL competencies)."""

    model_config = ConfigDict(extra="forbid")

    ngss: list[str] = Field(default_factory=list)
    casel: list[str] = Field(default_factory=list)


class MilestoneAnnotations(BaseModel):
    """Draft annotations for the developmental psychologist; she edits these."""

    model_config = ConfigDict(extra="forbid")

    note: str = ""
    reviewed_by: Optional[str] = None


class KnowledgeGraphNode(BaseModel):
    """One node on one axis of the knowledge graph."""

    model_config = ConfigDict(extra="forbid")

    id: str
    axis: Axis
    label: str
    display_name: str = Field(..., min_length=1)
    region: Optional[str] = None
    tier: Tier = "curriculum"
    # Required for (and only for) deep_dive nodes: the curriculum node this
    # one sits under, on the same axis.
    subtopic_of: Optional[str] = None
    facets: list[str] = Field(default_factory=list)
    age_bands: list[str] = Field(..., min_length=1)
    age_treatments: dict[int, AgeTreatment] = Field(default_factory=dict)
    edges: NodeEdges = Field(default_factory=NodeEdges)
    crosswalk: Crosswalk = Field(default_factory=Crosswalk)
    milestones: MilestoneAnnotations = Field(default_factory=MilestoneAnnotations)
    status: NodeStatus = "draft"

    @field_validator("id")
    @classmethod
    def _check_id_shape(cls, node_id: str) -> str:
        if not NODE_ID_PATTERN.match(node_id):
            raise ValueError(
                f"node id {node_id!r} must look like "
                "'knowledge_domain.volcanoes' (axis name + snake_case noun)"
            )
        return node_id

    @field_validator("age_bands")
    @classmethod
    def _check_age_bands(cls, age_bands: list[str]) -> list[str]:
        unknown = [band for band in age_bands if band not in AGE_BAND_YEARS]
        if unknown:
            raise ValueError(
                f"unknown age band(s) {unknown}; valid: {sorted(AGE_BAND_YEARS)}"
            )
        if len(set(age_bands)) != len(age_bands):
            raise ValueError("duplicate age bands")
        return age_bands

    @model_validator(mode="after")
    def _check_cross_field_invariants(self) -> "KnowledgeGraphNode":
        expected_prefix = AXIS_ID_PREFIXES[self.axis]
        if not self.id.startswith(expected_prefix):
            raise ValueError(
                f"node {self.id!r}: axis {self.axis!r} requires "
                f"id prefix {expected_prefix!r}"
            )
        if not LABEL_PATTERN.match(self.label):
            raise ValueError(
                f"node {self.id!r}: label {self.label!r} must be a "
                "snake_case canonical noun"
            )
        if self.id != expected_prefix + self.label:
            raise ValueError(
                f"node {self.id!r}: id must equal axis prefix + label "
                f"(expected {expected_prefix + self.label!r})"
            )
        self._check_tier_fields()
        self._check_treatment_years()
        self._check_treatment_depths()
        return self

    def _check_tier_fields(self) -> None:
        if self.tier == "deep_dive":
            if self.subtopic_of is None:
                raise ValueError(
                    f"node {self.id!r}: deep_dive tier requires subtopic_of"
                )
            if self.subtopic_of == self.id:
                raise ValueError(f"node {self.id!r}: subtopic_of points at itself")
            expected_prefix = AXIS_ID_PREFIXES[self.axis]
            if not self.subtopic_of.startswith(expected_prefix):
                raise ValueError(
                    f"node {self.id!r}: subtopic_of {self.subtopic_of!r} must be "
                    f"on the same axis ({self.axis})"
                )
        elif self.subtopic_of is not None:
            raise ValueError(
                f"node {self.id!r}: only deep_dive nodes carry subtopic_of"
            )
        if self.facets and self.tier != "deep_dive":
            raise ValueError(f"node {self.id!r}: facets are for deep_dive nodes")

    def _check_treatment_years(self) -> None:
        band_years = self.years_in_bands()
        stray_years = sorted(set(self.age_treatments) - band_years)
        if stray_years:
            raise ValueError(
                f"node {self.id!r}: age_treatments for years {stray_years} "
                f"outside its age_bands {self.age_bands}"
            )
        # story_element nodes are usually age-invariant; deep_dive nodes
        # inherit their parent's treatments. Both may leave years unfilled.
        if self.axis == "story_element" or self.tier == "deep_dive":
            return
        missing_years = sorted(band_years - set(self.age_treatments))
        if missing_years:
            raise ValueError(
                f"node {self.id!r}: missing age_treatments for years "
                f"{missing_years} (every year of every band needs one)"
            )

    def _check_treatment_depths(self) -> None:
        allowed_depths = AXIS_DEPTH_LEVELS[self.axis]
        for year, treatment in self.age_treatments.items():
            if self.axis == "story_element":
                if treatment.depth is not None:
                    raise ValueError(
                        f"node {self.id!r} year {year}: story_element "
                        "treatments carry no depth ladder"
                    )
                continue
            if treatment.depth is None:
                raise ValueError(
                    f"node {self.id!r} year {year}: depth is required "
                    f"(one of {allowed_depths})"
                )
            if treatment.depth not in allowed_depths:
                raise ValueError(
                    f"node {self.id!r} year {year}: depth "
                    f"{treatment.depth!r} not in {allowed_depths}"
                )

    def years_in_bands(self) -> set[int]:
        """All years covered by this node's age bands."""
        years: set[int] = set()
        for band in self.age_bands:
            years.update(AGE_BAND_YEARS[band])
        return years

    def exists_at_age(self, age: int) -> bool:
        return age in self.years_in_bands()

    def treatment_for_age(self, age: int) -> Optional[AgeTreatment]:
        """
        Treatment for a year, falling back to the nearest year within the
        node's bands (story_element nodes may have none at all).
        """
        if not self.exists_at_age(age):
            return None
        if age in self.age_treatments:
            return self.age_treatments[age]
        if not self.age_treatments:
            return None
        nearest_year = min(self.age_treatments, key=lambda year: abs(year - age))
        return self.age_treatments[nearest_year]


class KnowledgeGraphPack(BaseModel):
    """One YAML file: a named group of nodes on a single axis."""

    model_config = ConfigDict(extra="forbid")

    axis: Axis
    pack: str = Field(..., min_length=1)
    nodes: list[KnowledgeGraphNode] = Field(..., min_length=1)

    @field_validator("pack")
    @classmethod
    def _check_pack_name(cls, pack: str) -> str:
        if not LABEL_PATTERN.match(pack):
            raise ValueError(f"pack name {pack!r} must be snake_case")
        return pack

    @model_validator(mode="after")
    def _check_nodes_match_axis(self) -> "KnowledgeGraphPack":
        mismatched = [node.id for node in self.nodes if node.axis != self.axis]
        if mismatched:
            raise ValueError(
                f"pack {self.pack!r} (axis {self.axis!r}) contains nodes "
                f"of another axis: {mismatched}"
            )
        seen: set[str] = set()
        for node in self.nodes:
            if node.id in seen:
                raise ValueError(f"pack {self.pack!r}: duplicate node id {node.id!r}")
            seen.add(node.id)
        return self

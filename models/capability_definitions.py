"""
Canonical typed models for capability/item definitions.

Framework-agnostic: used by CASEL, developmental milestones, and future frameworks (e.g. NGSS).
Loaded from YAML; this is the stable internal contract—no raw dicts after parse.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# -----------------------------------------------------------------------------
# Constants / allowed values (reduces string drift; extend for NGSS etc.)
# -----------------------------------------------------------------------------

KNOWN_FRAMEWORKS = frozenset({"casel", "developmental_milestones", "ngss"})
VALID_STATUSES = frozenset({"active", "inactive", "deprecated"})
VALID_PRIORITIES = frozenset({"low", "medium", "high"})
VALID_SCORING_TYPES = frozenset({"ternary"})  # extend with "binary", "continuous", etc.
# Demo ternary scoring; other types may use different values
TERNARY_SCORING_VALUES = frozenset({"not_observed", "emerging", "demonstrated"})

# Optional: dotted namespaced id pattern (e.g. casel.self_awareness.identify_basic_emotions)
ID_PATTERN = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")


# -----------------------------------------------------------------------------
# AgeRange
# -----------------------------------------------------------------------------


def _strip_list_strings(v: list[str]) -> list[str]:
    """Strip each string; reject if any entry is blank after strip."""
    out = []
    for s in v:
        if not isinstance(s, str):
            raise ValueError("List entries must be strings")
        t = s.strip()
        if not t:
            raise ValueError("List must not contain blank or whitespace-only entries")
        out.append(t)
    return out


class AgeRange(BaseModel):
    """One expected age window for an item."""

    model_config = ConfigDict(extra="forbid")

    min_age: float = Field(..., ge=0, description="Minimum age (years)")
    max_age: float = Field(..., ge=0, description="Maximum age (years)")
    expected: bool = True

    @model_validator(mode="after")
    def min_lte_max(self) -> "AgeRange":
        if self.min_age > self.max_age:
            raise ValueError("min_age must be <= max_age")
        return self


# -----------------------------------------------------------------------------
# EvaluationMethod
# -----------------------------------------------------------------------------


class EvaluationMethod(BaseModel):
    """How the item should be evaluated (LLM rubric, rule+LLM, etc.)."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(..., min_length=1)
    rubric_id: str = Field(..., min_length=1)
    config: dict[str, Any] = Field(default_factory=dict)
    required_signals: list[str] = Field(default_factory=list)

    @field_validator("required_signals", mode="after")
    @classmethod
    def required_signals_no_blank(cls, v: list[str]) -> list[str]:
        if not v:
            return v
        return _strip_list_strings(v)


# -----------------------------------------------------------------------------
# ScoringConfig
# -----------------------------------------------------------------------------


class ScoringConfig(BaseModel):
    """Allowed score outputs for the item."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(..., min_length=1)
    values: list[str] = Field(..., min_length=1)

    @field_validator("type", mode="after")
    @classmethod
    def type_allowed(cls, v: str) -> str:
        if v not in VALID_SCORING_TYPES:
            raise ValueError(f"scoring type must be one of {sorted(VALID_SCORING_TYPES)}")
        return v

    @field_validator("values", mode="after")
    @classmethod
    def values_stripped_no_blank(cls, v: list[str]) -> list[str]:
        return _strip_list_strings(v)

    @model_validator(mode="after")
    def values_unique(self) -> "ScoringConfig":
        seen = set()
        for val in self.values:
            if val in seen:
                raise ValueError("scoring values must be unique")
            seen.add(val)
        return self


# -----------------------------------------------------------------------------
# DisplayConfig
# -----------------------------------------------------------------------------


class DisplayConfig(BaseModel):
    """Display hints for parent app / UI."""

    model_config = ConfigDict(extra="forbid")

    show_in_parent_app: bool = True
    priority: str = "medium"
    badge_icon: str = Field(default="", description="Optional icon key for badges")

    @field_validator("priority", mode="after")
    @classmethod
    def priority_valid(cls, v: str) -> str:
        if v not in VALID_PRIORITIES:
            raise ValueError(f"priority must be one of {sorted(VALID_PRIORITIES)}")
        return v


# -----------------------------------------------------------------------------
# NgssSource
# -----------------------------------------------------------------------------


class NgssSource(BaseModel):
    """NGSS-specific alignment metadata (performance expectations, DCIs, SEPs, CCCs)."""

    model_config = ConfigDict(extra="forbid")

    performance_expectations: list[str] = Field(default_factory=list)
    disciplinary_core_ideas: list[str] = Field(default_factory=list)
    science_and_engineering_practices: list[str] = Field(default_factory=list)
    crosscutting_concepts: list[str] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# CapabilityItemDefinition
# -----------------------------------------------------------------------------


class CapabilityItemDefinition(BaseModel):
    """One capability/item definition—core runtime contract."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    framework: str = Field(..., min_length=1)
    domain: str = Field(..., min_length=1)
    subdomain: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    short_label: str = Field(..., min_length=1)
    parent_friendly_label: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    age_ranges: list[AgeRange] = Field(..., min_length=1)
    observable_signals: list[str] = Field(default_factory=list)
    example_prompts: list[str] = Field(default_factory=list)
    positive_evidence_patterns: list[str] = Field(default_factory=list)
    negative_evidence_patterns: list[str] = Field(default_factory=list)
    ngss_source: NgssSource | None = None
    evaluation_method: EvaluationMethod
    scoring: ScoringConfig
    display: DisplayConfig
    status: str = "active"
    version: int = Field(..., ge=1)

    @field_validator(
        "id",
        "framework",
        "domain",
        "subdomain",
        "title",
        "short_label",
        "parent_friendly_label",
        "description",
        "status",
        mode="before",
    )
    @classmethod
    def strip_non_empty_strings(cls, v: str) -> str:
        if not isinstance(v, str):
            return v
        s = v.strip()
        if not s:
            raise ValueError("Field must not be empty or whitespace-only")
        return s

    @field_validator("id", mode="after")
    @classmethod
    def id_dotted_pattern(cls, v: str) -> str:
        if not ID_PATTERN.match(v):
            raise ValueError(
                "id must be a dotted namespaced identifier (e.g. framework.subdomain.item_name)"
            )
        return v

    @field_validator("framework", mode="after")
    @classmethod
    def framework_allowed(cls, v: str) -> str:
        if v not in KNOWN_FRAMEWORKS:
            raise ValueError(f"framework must be one of {sorted(KNOWN_FRAMEWORKS)}")
        return v

    @field_validator("status", mode="after")
    @classmethod
    def status_allowed(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(f"status must be one of {sorted(VALID_STATUSES)}")
        return v

    @field_validator(
        "observable_signals",
        "example_prompts",
        "positive_evidence_patterns",
        "negative_evidence_patterns",
        mode="after",
    )
    @classmethod
    def list_strings_stripped_no_blank(cls, v: list[str]) -> list[str]:
        if not v:
            return v
        return _strip_list_strings(v)

    def is_active(self) -> bool:
        """Return True if this item is active."""
        return self.status == "active"

    def applies_to_age(self, age: float) -> bool:
        """Return True if any age range includes the given age (min_age <= age <= max_age)."""
        for ar in self.age_ranges:
            if ar.min_age <= age <= ar.max_age:
                return True
        return False

    def primary_age_range(self) -> AgeRange | None:
        """First expected range, or first range if none marked expected. For sorting/debugging."""
        for ar in self.age_ranges:
            if ar.expected:
                return ar
        return self.age_ranges[0] if self.age_ranges else None


# -----------------------------------------------------------------------------
# CapabilityDefinitionPack
# -----------------------------------------------------------------------------


class CapabilityDefinitionPack(BaseModel):
    """One YAML file / one framework+age pack of items."""

    model_config = ConfigDict(extra="forbid")

    framework: str = Field(..., min_length=1)
    age: int | float = Field(..., ge=0)
    items: list[CapabilityItemDefinition] = Field(..., min_length=1)

    @field_validator("framework", mode="after")
    @classmethod
    def framework_allowed(cls, v: str) -> str:
        if v not in KNOWN_FRAMEWORKS:
            raise ValueError(f"framework must be one of {sorted(KNOWN_FRAMEWORKS)}")
        return v

    @model_validator(mode="after")
    def unique_item_ids_and_framework_match(self) -> "CapabilityDefinitionPack":
        seen_ids: set[str] = set()
        prefix = f"{self.framework}."
        for item in self.items:
            if item.id in seen_ids:
                raise ValueError(f"duplicate item id in pack: {item.id!r}")
            seen_ids.add(item.id)
            if item.framework != self.framework:
                raise ValueError(
                    f"item {item.id!r} framework {item.framework!r} does not match pack framework {self.framework!r}"
                )
            if not item.id.startswith(prefix):
                raise ValueError(
                    f"item id {item.id!r} must start with pack framework prefix {prefix!r}"
                )
        return self

    def get_item_by_id(self, item_id: str) -> CapabilityItemDefinition | None:
        """Return the item with the given id, or None."""
        for item in self.items:
            if item.id == item_id:
                return item
        return None

    def active_items(self) -> list[CapabilityItemDefinition]:
        """Return only items with status active."""
        return [i for i in self.items if i.is_active()]

    def items_for_age(self, age: float) -> list[CapabilityItemDefinition]:
        """Return items that apply to the given age (and are active)."""
        return [i for i in self.active_items() if i.applies_to_age(age)]

    def item_ids(self) -> list[str]:
        """Return ordered list of item ids in this pack."""
        return [i.id for i in self.items]

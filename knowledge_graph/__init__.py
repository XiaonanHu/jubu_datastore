"""
Knowledge graph for the Story Studio: four-axis curriculum + dashboard engine.

Public API: schema models, YAML loader/registry, cross-node validator,
per-age view builder, and coverage reporting.
"""

from jubu_datastore.knowledge_graph.age_view import (
    AgeGraphView,
    build_age_view,
    build_generation_brief,
)
from jubu_datastore.knowledge_graph.graph_loader import (
    DuplicateNodeIdError,
    DuplicatePackError,
    KnowledgeGraphRegistry,
    load_default_registry,
    load_pack_from_yaml,
)
from jubu_datastore.knowledge_graph.graph_schema import (
    AGE_BAND_YEARS,
    AXES,
    AXIS_DEPTH_LEVELS,
    AXIS_ID_PREFIXES,
    AgeTreatment,
    Crosswalk,
    KnowledgeGraphNode,
    KnowledgeGraphPack,
    MilestoneAnnotations,
    NodeEdges,
)
from jubu_datastore.knowledge_graph.graph_validator import (
    GraphValidationIssue,
    validate_registry,
)

__all__ = [
    "AGE_BAND_YEARS",
    "AXES",
    "AXIS_DEPTH_LEVELS",
    "AXIS_ID_PREFIXES",
    "AgeGraphView",
    "AgeTreatment",
    "Crosswalk",
    "DuplicateNodeIdError",
    "DuplicatePackError",
    "GraphValidationIssue",
    "KnowledgeGraphNode",
    "KnowledgeGraphPack",
    "KnowledgeGraphRegistry",
    "MilestoneAnnotations",
    "NodeEdges",
    "build_age_view",
    "build_generation_brief",
    "load_default_registry",
    "load_pack_from_yaml",
    "validate_registry",
]

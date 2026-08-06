"""
Per-age projection of the knowledge graph.

``build_age_view(age)`` returns exactly what parent-api serves to the Topic
Map: the nodes that exist at that age, each annotated with its age treatment
(nearest-year fallback within band), the edges whose two endpoints both exist
at that age, and display regions. ``build_generation_brief(node_id, age)``
returns the per-node, per-age brief handed to the story-generation pipeline.

Frontier state (explored / adjacent_frontier / unexplored) is per-account
data computed in parent-api — it never appears here or in the graph files.

CLI (regenerates the checked-in sample views):

    python -m jubu_datastore.knowledge_graph.age_view --age 6 [--output f.json]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

from jubu_datastore.knowledge_graph.graph_loader import (
    KnowledgeGraphRegistry,
    load_default_registry,
)
from jubu_datastore.knowledge_graph.graph_schema import (
    MAX_AGE_YEARS,
    MIN_AGE_YEARS,
    AgeTreatment,
    Axis,
)


class AgeViewNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    axis: Axis
    label: str
    display_name: str
    region: Optional[str] = None
    tier: str = "curriculum"
    subtopic_of: Optional[str] = None
    facets: list[str] = []
    status: str
    treatment: Optional[AgeTreatment] = None


class AgeViewEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    target: str
    kind: Literal["adjacent", "prerequisite", "subtopic"]


class AgeViewRegion(BaseModel):
    """Display grouping only — regions are not graph structure."""

    model_config = ConfigDict(extra="forbid")

    id: str
    axis: Axis
    display_name: str
    node_ids: list[str]


class AgeGraphView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    age: int
    nodes: list[AgeViewNode]
    edges: list[AgeViewEdge]
    regions: list[AgeViewRegion]


class GenerationBrief(BaseModel):
    """What the story-generation pipeline is told about one node at one age."""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    axis: Axis
    display_name: str
    age: int
    depth: Optional[str] = None
    framing: Optional[str] = None
    vocabulary: list[str] = []
    avoid: list[str] = []
    adjacent_display_names: list[str] = []


def _check_age(age: int) -> None:
    if not MIN_AGE_YEARS <= age <= MAX_AGE_YEARS:
        raise ValueError(f"age must be {MIN_AGE_YEARS}..{MAX_AGE_YEARS}, got {age}")


def build_age_view(
    age: int, registry: KnowledgeGraphRegistry | None = None
) -> AgeGraphView:
    """Project the full graph onto one age (existence, treatment, edges)."""
    _check_age(age)
    if registry is None:
        registry = load_default_registry()

    visible = {node.id: node for node in registry.all_nodes if node.exists_at_age(age)}

    view_nodes = [
        AgeViewNode(
            id=node.id,
            axis=node.axis,
            label=node.label,
            display_name=node.display_name,
            region=node.region,
            tier=node.tier,
            subtopic_of=node.subtopic_of,
            facets=list(node.facets),
            status=node.status,
            # deep dives fall back to their parent's treatment
            treatment=registry.effective_treatment(node.id, age),
        )
        for node in sorted(visible.values(), key=lambda n: n.id)
    ]

    # Adjacency is undirected: emit each visible pair once, ordered by id.
    adjacent_pairs: set[tuple[str, str]] = set()
    prerequisite_edges: list[AgeViewEdge] = []
    for node in visible.values():
        for target_id in node.edges.adjacent:
            if target_id in visible:
                adjacent_pairs.add(tuple(sorted((node.id, target_id))))  # type: ignore[arg-type]
        for target_id in node.edges.prerequisite:
            if target_id in visible:
                prerequisite_edges.append(
                    AgeViewEdge(source=target_id, target=node.id, kind="prerequisite")
                )
    subtopic_edges = sorted(
        (
            AgeViewEdge(source=node.subtopic_of, target=node.id, kind="subtopic")
            for node in visible.values()
            if node.subtopic_of is not None and node.subtopic_of in visible
        ),
        key=lambda edge: (edge.source, edge.target),
    )
    view_edges = (
        [
            AgeViewEdge(source=source, target=target, kind="adjacent")
            for source, target in sorted(adjacent_pairs)
        ]
        + sorted(prerequisite_edges, key=lambda edge: (edge.source, edge.target))
        + subtopic_edges
    )

    regions: dict[tuple[str, str], list[str]] = {}
    for view_node in view_nodes:
        if view_node.region is not None:
            regions.setdefault((view_node.axis, view_node.region), []).append(
                view_node.id
            )
    view_regions = [
        AgeViewRegion(
            id=region_id,
            axis=axis,  # type: ignore[arg-type]
            display_name=region_id.replace("_", " ").title(),
            node_ids=sorted(node_ids),
        )
        for (axis, region_id), node_ids in sorted(regions.items())
    ]

    return AgeGraphView(
        age=age, nodes=view_nodes, edges=view_edges, regions=view_regions
    )


def build_generation_brief(
    node_id: str, age: int, registry: KnowledgeGraphRegistry | None = None
) -> GenerationBrief:
    """Per-node, per-age brief for story generation (framing/vocab/avoid)."""
    _check_age(age)
    if registry is None:
        registry = load_default_registry()
    node = registry.get_node(node_id)
    if not node.exists_at_age(age):
        raise ValueError(
            f"node {node_id!r} does not exist at age {age} (bands: {node.age_bands})"
        )
    treatment = registry.effective_treatment(node.id, age)
    avoid = registry.effective_avoid_list(node.id, age)
    adjacent_display_names = [
        registry.get_node(neighbor_id).display_name
        for neighbor_id in node.edges.adjacent
        if registry.has_node(neighbor_id)
        and registry.get_node(neighbor_id).exists_at_age(age)
    ]
    return GenerationBrief(
        node_id=node.id,
        axis=node.axis,
        display_name=node.display_name,
        age=age,
        depth=treatment.depth if treatment else None,
        framing=treatment.framing if treatment else None,
        vocabulary=list(treatment.vocabulary) if treatment else [],
        avoid=avoid,
        adjacent_display_names=adjacent_display_names,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--age", type=int, required=True)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    view = build_age_view(args.age)
    view_json = view.model_dump_json(indent=2, exclude_none=True)
    if args.output is None:
        print(view_json)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(view_json + "\n", encoding="utf-8")
        print(
            f"wrote age-{args.age} view ({len(view.nodes)} nodes, "
            f"{len(view.edges)} edges) to {args.output}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

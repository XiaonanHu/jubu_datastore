"""
Cross-node validation for the knowledge graph. CI gate:

    python -m jubu_datastore.knowledge_graph.graph_validator

Per-node structural rules (id shape, prefix/axis match, per-year treatment
coverage, depth enums) are enforced by the Pydantic models at load time.
This module checks everything that spans nodes: edge endpoints, prerequisite
acyclicity, per-band orphans, banned assessment language, and review gating.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass

from jubu_datastore.knowledge_graph.graph_loader import (
    KnowledgeGraphRegistry,
    load_default_registry,
)
from jubu_datastore.knowledge_graph.graph_schema import (
    AGE_BAND_YEARS,
    KnowledgeGraphNode,
)
from jubu_datastore.story_generation.craft_gate import BANNED_EVALUATION

# The graph is content coverage, never child evaluation (workstream guardrail).
# These block only unambiguous developmental-report framing. The comparison
# phrases "ahead of" / "...behind" were removed (Aug 2026): in story prose they
# are almost always literal ("the boat ahead of us", "the wave behind them")
# and were the #1 spurious blocker, so the craft gate downgraded them to a warn
# and this display-text check matches that decision.
# NOTE (2026-08): "score" was removed from this list. It was written to catch
# assessment framing, but it also caught the ordinary meaning of the word in
# story prose -- a game score, a scoreboard, a variable named score in a
# story about debugging. The rest of the list still catches real evaluation
# language, and "interest means enjoyment, never ability" is unaffected.
# The child-evaluation vocabulary is owned by the craft gate (one list for
# story prose, graph display text and the library audit); the graph adds the
# per-child address that only makes sense in parent-facing text.
BANNED_LANGUAGE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), reason)
    for pattern, reason in [
        *zip(
            BANNED_EVALUATION,
            (
                "assessment framing",
                "mastery framing",
                "milestone framing in display text",
                "deficit framing",
                "ranking framing",
                "school-grading framing",
            ),
        ),
        (r"\byour child\b", "per-child address"),
    ]
)

# Quality bar from the seed-content spec: every node offers at least two
# "next territory" hops so the Topic Map never dead-ends.
MINIMUM_ADJACENT_NEIGHBORS = 2

# A label is a canonical topic noun, not a sentence.
MAXIMUM_LABEL_WORDS = 5


@dataclass(frozen=True)
class GraphValidationIssue:
    """One validator finding, addressed to a specific node (or axis)."""

    location: str  # node id, or "<axis>" for axis-level findings
    message: str

    def __str__(self) -> str:
        return f"{self.location}: {self.message}"


def validate_registry(registry: KnowledgeGraphRegistry) -> list[GraphValidationIssue]:
    """Run all cross-node checks; empty result means the graph is valid."""
    issues: list[GraphValidationIssue] = []
    issues.extend(_check_labels(registry))
    issues.extend(_check_subtopic_links(registry))
    issues.extend(_check_edge_endpoints(registry))
    issues.extend(_check_prerequisites_acyclic(registry))
    issues.extend(_check_band_orphans(registry))
    issues.extend(_check_banned_language(registry))
    issues.extend(_check_review_gating(registry))
    return issues


def _check_labels(registry: KnowledgeGraphRegistry) -> list[GraphValidationIssue]:
    issues = []
    for node in registry.all_nodes:
        if len(node.label.split("_")) > MAXIMUM_LABEL_WORDS:
            issues.append(
                GraphValidationIssue(
                    node.id,
                    f"label {node.label!r} reads like a sentence "
                    f"(> {MAXIMUM_LABEL_WORDS} words); labels are canonical nouns",
                )
            )
    return issues


def _check_subtopic_links(
    registry: KnowledgeGraphRegistry,
) -> list[GraphValidationIssue]:
    """
    Deep-dive nodes hang off exactly one curriculum parent, one level deep,
    and never widen their parent's age range.
    """
    issues = []
    for node in registry.all_nodes:
        if node.subtopic_of is None:
            continue
        if not registry.has_node(node.subtopic_of):
            issues.append(
                GraphValidationIssue(
                    node.id, f"subtopic_of unknown node {node.subtopic_of!r}"
                )
            )
            continue
        parent = registry.get_node(node.subtopic_of)
        if parent.axis != node.axis:
            issues.append(
                GraphValidationIssue(
                    node.id,
                    f"subtopic_of {parent.id!r} is on another axis",
                )
            )
        if parent.tier != "curriculum":
            issues.append(
                GraphValidationIssue(
                    node.id,
                    f"subtopic_of {parent.id!r} is itself a deep dive; "
                    "deep dives are one level only",
                )
            )
        extra_bands = sorted(set(node.age_bands) - set(parent.age_bands))
        if extra_bands:
            issues.append(
                GraphValidationIssue(
                    node.id,
                    f"age bands {extra_bands} are outside its parent "
                    f"{parent.id!r} ({parent.age_bands})",
                )
            )
    return issues


def _check_edge_endpoints(
    registry: KnowledgeGraphRegistry,
) -> list[GraphValidationIssue]:
    issues = []
    for node in registry.all_nodes:
        for kind, targets in (
            ("adjacent", node.edges.adjacent),
            ("prerequisite", node.edges.prerequisite),
        ):
            for target_id in targets:
                if target_id == node.id:
                    issues.append(
                        GraphValidationIssue(node.id, f"{kind} edge to itself")
                    )
                    continue
                if not registry.has_node(target_id):
                    issues.append(
                        GraphValidationIssue(
                            node.id, f"{kind} edge to unknown node {target_id!r}"
                        )
                    )
                    continue
                target = registry.get_node(target_id)
                if target.axis != node.axis:
                    issues.append(
                        GraphValidationIssue(
                            node.id,
                            f"{kind} edge crosses axes to {target_id!r} "
                            f"({node.axis} → {target.axis}); axes only meet "
                            "at stories",
                        )
                    )
    return issues


def _check_prerequisites_acyclic(
    registry: KnowledgeGraphRegistry,
) -> list[GraphValidationIssue]:
    """Prerequisite edges must form a DAG within each axis."""
    issues = []
    for axis in sorted({node.axis for node in registry.all_nodes}):
        nodes = registry.nodes_for_axis(axis)
        prerequisites_of = {
            node.id: [
                target
                for target in node.edges.prerequisite
                if registry.has_node(target)
            ]
            for node in nodes
        }
        state: dict[str, str] = {}  # unvisited(absent) | "visiting" | "done"

        def walk(node_id: str, path: list[str]) -> list[str] | None:
            state[node_id] = "visiting"
            for target in prerequisites_of.get(node_id, []):
                if state.get(target) == "visiting":
                    return path + [node_id, target]
                if state.get(target) is None:
                    cycle = walk(target, path + [node_id])
                    if cycle is not None:
                        return cycle
            state[node_id] = "done"
            return None

        for node in nodes:
            if state.get(node.id) is None:
                cycle = walk(node.id, [])
                if cycle is not None:
                    issues.append(
                        GraphValidationIssue(
                            f"<{axis}>",
                            "prerequisite cycle: " + " → ".join(cycle),
                        )
                    )
                    break  # one cycle report per axis is enough to act on
    return issues


def _undirected_neighbors(
    registry: KnowledgeGraphRegistry,
) -> dict[str, set[str]]:
    """Adjacency is undirected: authored one-way links count both ways."""
    neighbors: dict[str, set[str]] = {node.id: set() for node in registry.all_nodes}
    for node in registry.all_nodes:
        for target_id in node.edges.adjacent:
            if registry.has_node(target_id) and target_id != node.id:
                neighbors[node.id].add(target_id)
                neighbors[target_id].add(node.id)
    return neighbors


def _check_band_orphans(
    registry: KnowledgeGraphRegistry,
) -> list[GraphValidationIssue]:
    """
    Every node must reach ≥1 same-band neighbor in each of its bands (no
    orphan territories on any band's Topic Map) and meet the minimum degree.
    """
    issues = []
    neighbors = _undirected_neighbors(registry)
    for node in registry.all_nodes:
        # Deep dives reach the map through their curriculum parent, so the
        # degree and orphan rules do not apply to them.
        if node.tier == "deep_dive":
            continue
        node_neighbors = neighbors[node.id]
        if len(node_neighbors) < MINIMUM_ADJACENT_NEIGHBORS:
            issues.append(
                GraphValidationIssue(
                    node.id,
                    f"only {len(node_neighbors)} adjacent neighbor(s); "
                    f"minimum is {MINIMUM_ADJACENT_NEIGHBORS}",
                )
            )
        for band in node.age_bands:
            band_years = set(AGE_BAND_YEARS[band])
            has_band_partner = any(
                band_years & registry.get_node(neighbor_id).years_in_bands()
                for neighbor_id in node_neighbors
            )
            if not has_band_partner:
                issues.append(
                    GraphValidationIssue(
                        node.id,
                        f"orphan in band {band}: no adjacent neighbor "
                        "exists in that band",
                    )
                )
    return issues


def _parent_facing_strings(node: KnowledgeGraphNode) -> list[tuple[str, str]]:
    strings = [("display_name", node.display_name)]
    for year, treatment in sorted(node.age_treatments.items()):
        strings.append((f"age_treatments[{year}].framing", treatment.framing))
    if node.milestones.note:
        strings.append(("milestones.note", node.milestones.note))
    return strings


def _check_banned_language(
    registry: KnowledgeGraphRegistry,
) -> list[GraphValidationIssue]:
    issues = []
    for node in registry.all_nodes:
        for field_name, text in _parent_facing_strings(node):
            for pattern, reason in BANNED_LANGUAGE_PATTERNS:
                match = pattern.search(text)
                if match:
                    issues.append(
                        GraphValidationIssue(
                            node.id,
                            f"banned language in {field_name}: "
                            f"{match.group(0)!r} ({reason})",
                        )
                    )
    return issues


def _check_review_gating(
    registry: KnowledgeGraphRegistry,
) -> list[GraphValidationIssue]:
    issues = []
    for node in registry.all_nodes:
        if node.status == "published" and node.milestones.reviewed_by is None:
            issues.append(
                GraphValidationIssue(
                    node.id,
                    "status 'published' requires milestones.reviewed_by",
                )
            )
    return issues


def main() -> int:
    try:
        registry = load_default_registry()
    except Exception as load_error:  # loader errors are validation failures too
        print(f"FAIL: could not load knowledge graph packs: {load_error}")
        return 1
    issues = validate_registry(registry)
    node_count = len(registry.all_nodes)
    if issues:
        print(f"FAIL: {len(issues)} issue(s) across {node_count} nodes")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print(f"OK: {node_count} nodes across 4 axes, no issues")
    return 0


if __name__ == "__main__":
    sys.exit(main())

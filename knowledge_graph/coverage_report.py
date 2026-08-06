"""
Library coverage reporting: which graph territories have stories, per band.

The story→tags mapping is an interface only for now — Workstream C's tagging
API supplies real data. Shape: ``{story_id: [node_id, ...]}`` (a story tags
nodes across several axes).

CLI:

    python -m jubu_datastore.knowledge_graph.coverage_report --age-band 5-6 \
        [--story-tags story_tags.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from jubu_datastore.knowledge_graph.graph_loader import (
    KnowledgeGraphRegistry,
    load_default_registry,
)
from jubu_datastore.knowledge_graph.graph_schema import AGE_BAND_YEARS, AXES

# A story→tags mapping: story id → list of knowledge-graph node ids.
StoryTagMapping = dict[str, list[str]]

# Flag a node as over-concentrated when it holds more than this share of an
# axis's story tags in a band. Review threshold for content planners; move to
# config the day someone wants to tune it without a deploy.
OVER_CONCENTRATION_SHARE = 0.20
# Concentration is meaningless with a handful of stories; below this many
# tagged stories in an axis+band, skip the over-concentration check.
MINIMUM_STORIES_FOR_CONCENTRATION = 10


class AxisCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    axis: str
    total_nodes: int
    nodes_with_stories: int
    uncovered_node_ids: list[str]
    thin_regions: list[str]  # regions where every node has 0 stories
    over_concentrated_node_ids: list[str]
    story_count_by_node: dict[str, int]


class CoverageReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    age_band: str
    total_stories: int
    axes: list[AxisCoverage]


def load_story_tags(path: Path) -> StoryTagMapping:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"story tags file {path} must be a JSON object")
    return {str(story_id): list(node_ids) for story_id, node_ids in raw.items()}


def build_coverage_report(
    age_band: str,
    story_tags: StoryTagMapping,
    registry: KnowledgeGraphRegistry | None = None,
) -> CoverageReport:
    if age_band not in AGE_BAND_YEARS:
        raise ValueError(
            f"unknown age band {age_band!r}; valid: {sorted(AGE_BAND_YEARS)}"
        )
    if registry is None:
        registry = load_default_registry()

    tags_per_node = Counter(
        node_id for node_ids in story_tags.values() for node_id in node_ids
    )

    axis_reports: list[AxisCoverage] = []
    for axis in AXES:
        band_nodes = [
            node for node in registry.nodes_for_axis(axis) if age_band in node.age_bands
        ]
        story_count_by_node = {
            node.id: tags_per_node.get(node.id, 0) for node in band_nodes
        }
        uncovered = sorted(
            node_id for node_id, count in story_count_by_node.items() if count == 0
        )

        region_nodes: dict[str, list[str]] = {}
        for node in band_nodes:
            if node.region is not None:
                region_nodes.setdefault(node.region, []).append(node.id)
        thin_regions = sorted(
            region
            for region, node_ids in region_nodes.items()
            if all(story_count_by_node[node_id] == 0 for node_id in node_ids)
        )

        total_axis_tags = sum(story_count_by_node.values())
        over_concentrated: list[str] = []
        if total_axis_tags >= MINIMUM_STORIES_FOR_CONCENTRATION:
            over_concentrated = sorted(
                node_id
                for node_id, count in story_count_by_node.items()
                if count / total_axis_tags > OVER_CONCENTRATION_SHARE
            )

        axis_reports.append(
            AxisCoverage(
                axis=axis,
                total_nodes=len(band_nodes),
                nodes_with_stories=sum(
                    1 for count in story_count_by_node.values() if count > 0
                ),
                uncovered_node_ids=uncovered,
                thin_regions=thin_regions,
                over_concentrated_node_ids=over_concentrated,
                story_count_by_node=story_count_by_node,
            )
        )

    return CoverageReport(
        age_band=age_band, total_stories=len(story_tags), axes=axis_reports
    )


def _print_report(report: CoverageReport) -> None:
    print(
        f"Coverage report — band {report.age_band} "
        f"({report.total_stories} tagged stories)"
    )
    for axis in report.axes:
        print(
            f"\n[{axis.axis}] {axis.nodes_with_stories}/{axis.total_nodes} "
            "nodes have at least one story"
        )
        if axis.uncovered_node_ids:
            print(
                f"  no stories yet ({len(axis.uncovered_node_ids)}): "
                + ", ".join(axis.uncovered_node_ids)
            )
        if axis.thin_regions:
            print(
                "  thin regions (zero stories anywhere): "
                + ", ".join(axis.thin_regions)
            )
        if axis.over_concentrated_node_ids:
            print("  over-concentrated: " + ", ".join(axis.over_concentrated_node_ids))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--age-band", required=True, choices=sorted(AGE_BAND_YEARS))
    parser.add_argument(
        "--story-tags",
        type=Path,
        default=None,
        help="JSON file mapping story_id → [node_id, ...]; omit for empty",
    )
    args = parser.parse_args()
    story_tags: StoryTagMapping = (
        load_story_tags(args.story_tags) if args.story_tags else {}
    )
    report = build_coverage_report(args.age_band, story_tags)
    _print_report(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())

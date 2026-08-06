"""Tests for knowledge_graph.age_view + coverage_report (+ checked-in samples)."""

import json
from pathlib import Path

import pytest

from jubu_datastore.knowledge_graph import (
    build_age_view,
    build_generation_brief,
    load_default_registry,
)
from jubu_datastore.knowledge_graph.age_view import AgeGraphView
from jubu_datastore.knowledge_graph.coverage_report import build_coverage_report

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SAMPLES_DIR = _REPO_ROOT / "knowledge_graph_definitions" / "samples"


@pytest.fixture(scope="module")
def registry():
    return load_default_registry()


# ---------------------------------------------------------------------------
# build_age_view
# ---------------------------------------------------------------------------


def test_existence_filter_morphs_with_age(registry):
    view_6 = build_age_view(6, registry)
    view_9 = build_age_view(9, registry)
    ids_6 = {node.id for node in view_6.nodes}
    ids_9 = {node.id for node in view_9.nodes}
    assert "knowledge_domain.plate_tectonics" not in ids_6  # 9-10 band only
    assert "knowledge_domain.plate_tectonics" in ids_9
    assert "knowledge_domain.day_and_night" in ids_6  # 5-6 + 7-8 bands only
    assert "knowledge_domain.day_and_night" not in ids_9
    assert len(ids_9) > len(ids_6)


def test_treatment_lens_changes_per_age(registry):
    framing_at = {}
    for age in (5, 9):
        view = build_age_view(age, registry)
        node = next(n for n in view.nodes if n.id == "knowledge_domain.volcanoes")
        assert node.treatment is not None
        framing_at[age] = node.treatment.framing
    assert framing_at[5] != framing_at[9]


def test_edges_only_between_visible_nodes(registry):
    for age in (5, 6, 9):
        view = build_age_view(age, registry)
        visible = {node.id for node in view.nodes}
        for edge in view.edges:
            assert edge.source in visible and edge.target in visible


def test_adjacent_edges_deduplicated_undirected(registry):
    view = build_age_view(6, registry)
    adjacent_pairs = [
        (edge.source, edge.target) for edge in view.edges if edge.kind == "adjacent"
    ]
    assert len(adjacent_pairs) == len(set(adjacent_pairs))
    assert all(source < target for source, target in adjacent_pairs)


def test_five_year_old_view_has_no_prerequisite_chains(registry):
    view = build_age_view(5, registry)
    assert all(edge.kind != "prerequisite" for edge in view.edges)


def test_deep_dive_nodes_carry_parent_and_subtopic_edges(registry):
    view = build_age_view(6, registry)
    octopus = next(n for n in view.nodes if n.id == "knowledge_domain.octopus")
    assert octopus.tier == "deep_dive"
    assert octopus.subtopic_of == "knowledge_domain.ocean_animals"
    assert octopus.facets  # deep dives name the aspects stories rotate through
    assert any(
        edge.kind == "subtopic"
        and edge.source == "knowledge_domain.ocean_animals"
        and edge.target == "knowledge_domain.octopus"
        for edge in view.edges
    )


def test_deep_dive_inherits_parent_avoid_list(registry):
    parent_avoid = set(
        registry.effective_avoid_list("knowledge_domain.ocean_animals", 5)
    )
    child_avoid = set(registry.effective_avoid_list("knowledge_domain.octopus", 5))
    assert parent_avoid  # the parent has sharp edges to protect against
    assert parent_avoid <= child_avoid  # every one of them still applies


def test_deep_dive_falls_back_to_parent_treatment(registry):
    # sea_turtles authors years 5/7/9; age 6 falls back within its own bands
    brief = build_generation_brief("knowledge_domain.sea_turtles", 6, registry)
    assert brief.framing


def test_regions_group_visible_nodes(registry):
    view = build_age_view(6, registry)
    region_node_ids = {
        node_id for region in view.regions for node_id in region.node_ids
    }
    visible = {node.id for node in view.nodes}
    assert region_node_ids <= visible
    domain_regions = {r.id for r in view.regions if r.axis == "knowledge_domain"}
    assert "nature_and_earth" in domain_regions


def test_age_out_of_range_rejected(registry):
    with pytest.raises(ValueError, match="age must be"):
        build_age_view(2, registry)
    with pytest.raises(ValueError, match="age must be"):
        build_age_view(13, registry)


def test_age_band_3_4_has_authored_content(registry):
    view = build_age_view(3, registry)
    assert view.age == 3
    node_ids = {node.id for node in view.nodes}
    # the first authored 3-4 content: dinosaurs/birds plus their story hooks
    assert "knowledge_domain.dinosaurs" in node_ids
    assert "story_element.fairies" in node_ids


# ---------------------------------------------------------------------------
# build_generation_brief
# ---------------------------------------------------------------------------


def test_generation_brief_carries_treatment(registry):
    brief = build_generation_brief("knowledge_domain.volcanoes", 5, registry)
    assert brief.depth == "sensory"
    assert brief.framing
    assert brief.vocabulary
    assert brief.adjacent_display_names


def test_generation_brief_rejects_age_outside_bands(registry):
    with pytest.raises(ValueError, match="does not exist at age"):
        build_generation_brief("knowledge_domain.plate_tectonics", 5, registry)


def test_generation_brief_nearest_year_fallback(registry):
    # elem nodes may have sparse treatments; fallback picks nearest band year.
    brief = build_generation_brief("story_element.dragons", 6, registry)
    assert brief.depth is None  # story elements have no depth ladder
    assert brief.framing  # but the nearest authored framing is served


# ---------------------------------------------------------------------------
# Checked-in sample views
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("age", [6, 9])
def test_checked_in_sample_views_parse(age):
    path = _SAMPLES_DIR / f"age_view_age_{age}.json"
    view = AgeGraphView.model_validate(json.loads(path.read_text()))
    assert view.age == age
    assert view.nodes and view.edges and view.regions


# ---------------------------------------------------------------------------
# Coverage report
# ---------------------------------------------------------------------------


def test_coverage_with_no_stories_lists_everything_uncovered(registry):
    report = build_coverage_report("5-6", {}, registry)
    assert report.total_stories == 0
    for axis in report.axes:
        assert axis.nodes_with_stories == 0
        assert len(axis.uncovered_node_ids) == axis.total_nodes


def test_coverage_counts_tagged_stories(registry):
    story_tags = {
        "story_1": ["knowledge_domain.volcanoes", "sel_theme.courage"],
        "story_2": [
            "knowledge_domain.volcanoes",
            "value_lesson.honesty",
            "story_element.dragons",
        ],
    }
    report = build_coverage_report("5-6", story_tags, registry)
    domain = next(axis for axis in report.axes if axis.axis == "knowledge_domain")
    assert domain.story_count_by_node["knowledge_domain.volcanoes"] == 2
    assert "knowledge_domain.volcanoes" not in domain.uncovered_node_ids
    assert "nature_and_earth" not in domain.thin_regions


def test_coverage_over_concentration(registry):
    # 12 stories all tagged to one domain node → far above the share threshold.
    story_tags = {f"story_{i}": ["knowledge_domain.volcanoes"] for i in range(12)}
    report = build_coverage_report("5-6", story_tags, registry)
    domain = next(axis for axis in report.axes if axis.axis == "knowledge_domain")
    assert domain.over_concentrated_node_ids == ["knowledge_domain.volcanoes"]


def test_coverage_rejects_unknown_band(registry):
    with pytest.raises(ValueError, match="unknown age band"):
        build_coverage_report("13-14", {}, registry)

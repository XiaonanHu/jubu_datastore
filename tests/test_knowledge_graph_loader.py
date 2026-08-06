"""Tests for knowledge_graph.graph_schema + graph_loader."""

from pathlib import Path

import pytest
import yaml

from jubu_datastore.knowledge_graph import (
    DuplicateNodeIdError,
    KnowledgeGraphRegistry,
    load_default_registry,
    load_pack_from_yaml,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFINITIONS_ROOT = _REPO_ROOT / "knowledge_graph_definitions"


def _domain_node(
    label: str,
    adjacent: list[str],
    age_bands: list[str] | None = None,
    **overrides: object,
) -> dict:
    age_bands = age_bands or ["5-6"]
    years = {"5-6": [5, 6], "7-8": [7, 8], "9-10": [9, 10]}
    depth_for_band = {"5-6": "sensory", "7-8": "mechanism", "9-10": "system"}
    treatments = {}
    for band in age_bands:
        for year in years[band]:
            treatments[year] = {
                "depth": depth_for_band[band],
                "framing": f"{label} as seen at age {year}",
                "vocabulary": ["word_a", "word_b"],
            }
    node: dict = {
        "id": f"knowledge_domain.{label}",
        "axis": "knowledge_domain",
        "label": label,
        "display_name": label.replace("_", " ").title(),
        "region": "test_region",
        "age_bands": age_bands,
        "age_treatments": treatments,
        "edges": {"adjacent": adjacent, "prerequisite": []},
        "crosswalk": {"ngss": [], "casel": []},
        "milestones": {"note": "", "reviewed_by": None},
        "status": "draft",
    }
    node.update(overrides)
    return node


def _triangle_pack() -> dict:
    """Three mutually adjacent nodes: passes every validator check."""
    return {
        "axis": "knowledge_domain",
        "pack": "test_pack",
        "nodes": [
            _domain_node(
                "lakes", ["knowledge_domain.ponds", "knowledge_domain.marshes"]
            ),
            _domain_node(
                "ponds", ["knowledge_domain.lakes", "knowledge_domain.marshes"]
            ),
            _domain_node(
                "marshes", ["knowledge_domain.lakes", "knowledge_domain.ponds"]
            ),
        ],
    }


def _write_pack(directory: Path, filename: str, pack: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_text(yaml.safe_dump(pack, sort_keys=False), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Real checked-in definitions
# ---------------------------------------------------------------------------


def test_default_registry_loads_all_axes():
    registry = load_default_registry()
    axes = {node.axis for node in registry.all_nodes}
    assert axes == {"knowledge_domain", "sel_theme", "value_lesson", "story_element"}
    assert len(registry.all_nodes) > 150
    volcanoes = registry.get_node("knowledge_domain.volcanoes")
    assert volcanoes.label == "volcanoes"
    assert volcanoes.exists_at_age(5)


def test_default_registry_nodes_are_all_draft():
    registry = load_default_registry()
    assert all(node.status == "draft" for node in registry.all_nodes)


# ---------------------------------------------------------------------------
# Loading synthetic packs
# ---------------------------------------------------------------------------


def test_load_valid_pack(tmp_path):
    path = _write_pack(tmp_path, "test_pack.yaml", _triangle_pack())
    pack = load_pack_from_yaml(path)
    assert pack.axis == "knowledge_domain"
    assert [node.label for node in pack.nodes] == ["lakes", "ponds", "marshes"]


def test_duplicate_node_id_across_packs_rejected(tmp_path):
    _write_pack(tmp_path, "first.yaml", _triangle_pack())
    second = _triangle_pack()
    second["pack"] = "other_pack"
    _write_pack(tmp_path, "second.yaml", second)
    registry = KnowledgeGraphRegistry()
    with pytest.raises(DuplicateNodeIdError):
        registry.load_all_packs(tmp_path)


def test_id_must_equal_prefix_plus_label(tmp_path):
    pack = _triangle_pack()
    pack["nodes"][0]["id"] = "knowledge_domain.not_lakes"
    path = _write_pack(tmp_path, "test_pack.yaml", pack)
    with pytest.raises(ValueError, match="Validation error"):
        load_pack_from_yaml(path)


def test_missing_treatment_year_rejected(tmp_path):
    pack = _triangle_pack()
    del pack["nodes"][0]["age_treatments"][6]
    path = _write_pack(tmp_path, "test_pack.yaml", pack)
    with pytest.raises(ValueError, match="missing age_treatments"):
        load_pack_from_yaml(path)


def test_treatment_year_outside_bands_rejected(tmp_path):
    pack = _triangle_pack()
    pack["nodes"][0]["age_treatments"][9] = {
        "depth": "system",
        "framing": "a stray year nine treatment",
    }
    path = _write_pack(tmp_path, "test_pack.yaml", pack)
    with pytest.raises(ValueError, match="outside its age_bands"):
        load_pack_from_yaml(path)


def test_wrong_depth_for_axis_rejected(tmp_path):
    pack = _triangle_pack()
    pack["nodes"][0]["age_treatments"][5]["depth"] = "naming_the_feeling"
    path = _write_pack(tmp_path, "test_pack.yaml", pack)
    with pytest.raises(ValueError, match="depth"):
        load_pack_from_yaml(path)


def test_story_element_treatments_carry_no_depth(tmp_path):
    pack = {
        "axis": "story_element",
        "pack": "test_elements",
        "nodes": [
            {
                "id": "story_element.moon_bases",
                "axis": "story_element",
                "label": "moon_bases",
                "display_name": "Moon Bases",
                "age_bands": ["5-6"],
                "age_treatments": {
                    5: {"depth": "sensory", "framing": "domes and moon boots"}
                },
                "edges": {"adjacent": [], "prerequisite": []},
            }
        ],
    }
    path = _write_pack(tmp_path, "elements.yaml", pack)
    with pytest.raises(ValueError, match="no depth ladder"):
        load_pack_from_yaml(path)


def test_axis_prefix_mismatch_rejected(tmp_path):
    pack = _triangle_pack()
    pack["nodes"][0]["id"] = "sel_theme.lakes"
    path = _write_pack(tmp_path, "test_pack.yaml", pack)
    with pytest.raises(ValueError, match="Validation error"):
        load_pack_from_yaml(path)


def test_no_duplicate_pack_files_in_definitions_tree():
    """Guard against the capability_definitions duplicate-file gotcha."""
    registry = KnowledgeGraphRegistry()
    registry.load_all_packs(_DEFINITIONS_ROOT)  # raises on duplicates
    assert len(registry.all_nodes) > 150

"""Tests for knowledge_graph.graph_validator (cross-node rules)."""

from pathlib import Path

import yaml

from jubu_datastore.knowledge_graph import (
    KnowledgeGraphRegistry,
    load_default_registry,
    validate_registry,
)


def _domain_node(
    label: str,
    adjacent: list[str],
    age_bands: list[str] | None = None,
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
    return {
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


def _registry_from(tmp_path: Path, *packs: dict) -> KnowledgeGraphRegistry:
    tmp_path.mkdir(parents=True, exist_ok=True)
    for index, pack in enumerate(packs):
        path = tmp_path / f"pack_{index}.yaml"
        path.write_text(yaml.safe_dump(pack, sort_keys=False), encoding="utf-8")
    registry = KnowledgeGraphRegistry()
    registry.load_all_packs(tmp_path)
    return registry


def _messages(registry: KnowledgeGraphRegistry) -> list[str]:
    return [str(issue) for issue in validate_registry(registry)]


# ---------------------------------------------------------------------------
# The checked-in graph is the contract: it must validate clean.
# ---------------------------------------------------------------------------


def test_checked_in_definitions_validate_clean():
    issues = validate_registry(load_default_registry())
    assert issues == []


# ---------------------------------------------------------------------------
# Individual rules
# ---------------------------------------------------------------------------


def test_valid_triangle_has_no_issues(tmp_path):
    registry = _registry_from(tmp_path, _triangle_pack())
    assert _messages(registry) == []


def test_unknown_adjacent_endpoint_flagged(tmp_path):
    pack = _triangle_pack()
    pack["nodes"][0]["edges"]["adjacent"].append("knowledge_domain.nowhere")
    registry = _registry_from(tmp_path, pack)
    assert any(
        "unknown node 'knowledge_domain.nowhere'" in m for m in _messages(registry)
    )


def test_cross_axis_edge_flagged(tmp_path):
    domain_pack = _triangle_pack()
    domain_pack["nodes"][0]["edges"]["adjacent"].append("sel_theme.patience_test")
    sel_pack = {
        "axis": "sel_theme",
        "pack": "test_sel",
        "nodes": [
            {
                "id": "sel_theme.patience_test",
                "axis": "sel_theme",
                "label": "patience_test",
                "display_name": "Patience Test",
                "age_bands": ["5-6"],
                "age_treatments": {
                    5: {
                        "depth": "naming_the_feeling",
                        "framing": "waiting is hard",
                    },
                    6: {
                        "depth": "naming_the_feeling",
                        "framing": "waiting for a turn on the swing",
                    },
                },
                "edges": {"adjacent": [], "prerequisite": []},
            }
        ],
    }
    registry = _registry_from(tmp_path, domain_pack, sel_pack)
    assert any("crosses axes" in m for m in _messages(registry))


def test_prerequisite_cycle_flagged(tmp_path):
    pack = _triangle_pack()
    pack["nodes"][0]["edges"]["prerequisite"] = ["knowledge_domain.ponds"]
    pack["nodes"][1]["edges"]["prerequisite"] = ["knowledge_domain.lakes"]
    registry = _registry_from(tmp_path, pack)
    assert any("prerequisite cycle" in m for m in _messages(registry))


def test_band_orphan_flagged(tmp_path):
    pack = _triangle_pack()
    # knowledge_domain.lakes now also lives in 7-8, but no neighbor exists there.
    pack["nodes"][0] = _domain_node(
        "lakes",
        ["knowledge_domain.ponds", "knowledge_domain.marshes"],
        age_bands=["5-6", "7-8"],
    )
    registry = _registry_from(tmp_path, pack)
    assert any("orphan in band 7-8" in m for m in _messages(registry))


def test_minimum_degree_enforced(tmp_path):
    pack = _triangle_pack()
    # Cut marshes out of every adjacency: lakes↔ponds remain, marshes degree 0.
    pack["nodes"][0]["edges"]["adjacent"] = ["knowledge_domain.ponds"]
    pack["nodes"][1]["edges"]["adjacent"] = ["knowledge_domain.lakes"]
    pack["nodes"][2]["edges"]["adjacent"] = []
    registry = _registry_from(tmp_path, pack)
    messages = _messages(registry)
    assert any(
        "knowledge_domain.marshes" in m and "adjacent neighbor" in m for m in messages
    )


def test_banned_language_flagged(tmp_path):
    pack = _triangle_pack()
    pack["nodes"][0]["age_treatments"][5]["framing"] = "an assessment of how lakes work"
    registry = _registry_from(tmp_path, pack)
    assert any("banned language" in m for m in _messages(registry))


def test_innocent_behind_is_not_flagged(tmp_path):
    pack = _triangle_pack()
    pack["nodes"][0]["age_treatments"][5]["framing"] = (
        "the sun hiding behind the clouds over the lake"
    )
    registry = _registry_from(tmp_path, pack)
    assert not any("banned language" in m for m in _messages(registry))


def test_published_requires_reviewed_by(tmp_path):
    pack = _triangle_pack()
    pack["nodes"][0]["status"] = "published"
    registry = _registry_from(tmp_path, pack)
    assert any("requires milestones.reviewed_by" in m for m in _messages(registry))

    pack["nodes"][0]["milestones"]["reviewed_by"] = "dr_reviewer"
    registry_ok = _registry_from(tmp_path / "ok", pack)
    assert not any(
        "requires milestones.reviewed_by" in m for m in _messages(registry_ok)
    )

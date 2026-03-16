"""
Unit tests for capability definition YAML loader and registry (Step 3).

Covers: load CASEL pack, load milestone pack, duplicate item id fails,
invalid schema fails, get_items_for_child_age.
"""

import shutil
from pathlib import Path

import pytest

from jubu_datastore.loaders.capability_loader import (
    CapabilityDefinitionRegistry,
    DuplicateItemIdError,
    DuplicatePackError,
    load_definition_pack_from_yaml,
    load_default_registry,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CASEL_YAML = _REPO_ROOT / "capability_definitions" / "casel" / "age_5.yaml"
_DEV_YAML = _REPO_ROOT / "capability_definitions" / "developmental" / "age_5.yaml"


# -----------------------------------------------------------------------------
# Test 1 — load CASEL pack
# -----------------------------------------------------------------------------


def test_empty_yaml_fails(tmp_path: Path) -> None:
    """Empty or invalid YAML file raises."""
    empty = tmp_path / "empty.yaml"
    empty.write_text("")
    with pytest.raises(ValueError, match="Empty or invalid YAML"):
        load_definition_pack_from_yaml(empty)


def test_load_casel_pack() -> None:
    """casel/age_5.yaml loads successfully via load_definition_pack_from_yaml."""
    pack = load_definition_pack_from_yaml(_CASEL_YAML)
    assert pack.framework == "casel"
    assert pack.age == 5
    assert len(pack.items) >= 1
    assert pack.items[0].id == "casel.self_awareness.identify_basic_emotions"


# -----------------------------------------------------------------------------
# Test 2 — load milestone pack
# -----------------------------------------------------------------------------


def test_load_milestone_pack() -> None:
    """developmental/age_5.yaml (developmental_milestones) loads successfully."""
    pack = load_definition_pack_from_yaml(_DEV_YAML)
    assert pack.framework == "developmental_milestones"
    assert pack.age == 5
    assert len(pack.items) >= 1
    assert "developmental_milestones" in pack.items[0].id


# -----------------------------------------------------------------------------
# Test 3 — duplicate item id fails
# -----------------------------------------------------------------------------


def test_duplicate_item_id_across_packs_fails(tmp_path: Path) -> None:
    """Two packs defining the same item id causes DuplicateItemIdError."""
    # Pack 1: casel age 5 with one item
    p1 = tmp_path / "casel"
    p1.mkdir()
    (p1 / "age_5.yaml").write_text("""
framework: casel
age: 5
items:
  - id: casel.test.duplicate_item
    framework: casel
    domain: sel
    subdomain: self_awareness
    title: One
    short_label: One
    parent_friendly_label: One
    description: D
    age_ranges:
      - min_age: 4.5
        max_age: 5.5
        expected: true
    evaluation_method:
      type: llm_rubric
      rubric_id: r1
    scoring:
      type: ternary
      values: [not_observed, emerging, demonstrated]
    display:
      show_in_parent_app: true
      priority: medium
      badge_icon: x
    status: active
    version: 1
""")
    # Pack 2: same framework, different age, but same item id (duplicate)
    (p1 / "age_6.yaml").write_text("""
framework: casel
age: 6
items:
  - id: casel.test.duplicate_item
    framework: casel
    domain: sel
    subdomain: self_awareness
    title: Two
    short_label: Two
    parent_friendly_label: Two
    description: D
    age_ranges:
      - min_age: 5.5
        max_age: 6.5
        expected: true
    evaluation_method:
      type: llm_rubric
      rubric_id: r2
    scoring:
      type: ternary
      values: [not_observed, emerging, demonstrated]
    display:
      show_in_parent_app: true
      priority: medium
      badge_icon: x
    status: active
    version: 1
""")
    registry = CapabilityDefinitionRegistry()
    with pytest.raises(DuplicateItemIdError) as exc_info:
        registry.load_all_packs(tmp_path)
    assert "casel.test.duplicate_item" in str(exc_info.value)
    assert "duplicate" in str(exc_info.value).lower()


# -----------------------------------------------------------------------------
# Test 4 — invalid schema fails
# -----------------------------------------------------------------------------


def test_invalid_schema_fails(tmp_path: Path) -> None:
    """YAML with missing required field (e.g. title) raises validation error."""
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("""
framework: casel
age: 5
items:
  - id: casel.test.missing_title
    framework: casel
    domain: sel
    subdomain: self_awareness
    title: ""
    short_label: S
    parent_friendly_label: P
    description: D
    age_ranges:
      - min_age: 4.5
        max_age: 5.5
        expected: true
    evaluation_method:
      type: llm_rubric
      rubric_id: r1
    scoring:
      type: ternary
      values: [not_observed, emerging, demonstrated]
    display:
      show_in_parent_app: true
      priority: medium
      badge_icon: x
    status: active
    version: 1
""")
    with pytest.raises(ValueError, match="Validation error|empty or whitespace"):
        load_definition_pack_from_yaml(bad_yaml)


# -----------------------------------------------------------------------------
# Test 5 — get_items_for_child_age works
# -----------------------------------------------------------------------------


def test_get_items_for_child_age_returns_expected_items(tmp_path: Path) -> None:
    """Registry.get_items_for_child_age(5) returns items that apply to age 5."""
    (tmp_path / "casel").mkdir(parents=True)
    (tmp_path / "developmental_milestones").mkdir(parents=True)
    shutil.copy(_CASEL_YAML, tmp_path / "casel" / "age_5.yaml")
    shutil.copy(_DEV_YAML, tmp_path / "developmental_milestones" / "age_5.yaml")

    registry = CapabilityDefinitionRegistry()
    registry.load_all_packs(tmp_path)

    items = registry.get_items_for_child_age(5.0)
    assert len(items) >= 1
    for item in items:
        assert item.is_active()
        assert item.applies_to_age(5.0)
    ids = {i.id for i in items}
    assert any("casel" in id for id in ids)
    assert any("developmental_milestones" in id for id in ids)


def test_get_pack_raises_when_not_found(tmp_path: Path) -> None:
    """get_pack(framework, age) raises KeyError when no such pack is loaded."""
    registry = CapabilityDefinitionRegistry()
    with pytest.raises(KeyError, match="No pack"):
        registry.get_pack("casel", 5)


def test_registry_get_pack_get_item(tmp_path: Path) -> None:
    """get_pack and get_item return expected data after load."""
    (tmp_path / "casel").mkdir(parents=True)
    shutil.copy(_CASEL_YAML, tmp_path / "casel" / "age_5.yaml")

    registry = CapabilityDefinitionRegistry()
    registry.load_all_packs(tmp_path)

    pack = registry.get_pack("casel", 5)
    assert pack.framework == "casel"
    assert pack.age == 5

    item_id = "casel.self_awareness.identify_basic_emotions"
    item = registry.get_item(item_id)
    assert item is not None
    assert item.id == item_id
    assert registry.get_item("nonexistent.id") is None


def test_registry_get_items_for_framework(tmp_path: Path) -> None:
    """get_items_for_framework returns all items for that framework."""
    (tmp_path / "casel").mkdir(parents=True)
    shutil.copy(_CASEL_YAML, tmp_path / "casel" / "age_5.yaml")

    registry = CapabilityDefinitionRegistry()
    registry.load_all_packs(tmp_path)

    items = registry.get_items_for_framework("casel")
    assert len(items) >= 1
    assert all(i.framework == "casel" for i in items)


def test_registry_duplicate_pack_fails(tmp_path: Path) -> None:
    """Two YAML files with same (framework, age) raises DuplicatePackError."""
    (tmp_path / "casel").mkdir(parents=True)
    shutil.copy(_CASEL_YAML, tmp_path / "casel" / "age_5.yaml")
    shutil.copy(_CASEL_YAML, tmp_path / "casel" / "age_5_dup.yaml")

    registry = CapabilityDefinitionRegistry()
    with pytest.raises(DuplicatePackError) as exc_info:
        registry.load_all_packs(tmp_path)
    assert exc_info.value.framework == "casel"
    assert exc_info.value.age == 5.0


def test_load_default_registry_uses_given_path(tmp_path: Path) -> None:
    """load_default_registry(path) loads from the given path."""
    (tmp_path / "casel").mkdir(parents=True)
    (tmp_path / "developmental_milestones").mkdir(parents=True)
    shutil.copy(_CASEL_YAML, tmp_path / "casel" / "age_5.yaml")
    shutil.copy(_DEV_YAML, tmp_path / "developmental_milestones" / "age_5.yaml")

    registry = load_default_registry(tmp_path)
    assert len(registry.packs_by_framework_age) >= 2
    items = registry.get_items_for_child_age(5.0)
    assert len(items) >= 1


def test_get_demo_items(tmp_path: Path) -> None:
    """get_demo_items(age) returns CASEL + developmental_milestones items for that age."""
    (tmp_path / "casel").mkdir(parents=True)
    (tmp_path / "developmental_milestones").mkdir(parents=True)
    shutil.copy(_CASEL_YAML, tmp_path / "casel" / "age_5.yaml")
    shutil.copy(_DEV_YAML, tmp_path / "developmental_milestones" / "age_5.yaml")

    registry = CapabilityDefinitionRegistry()
    registry.load_all_packs(tmp_path)

    demo = registry.get_demo_items(5.0)
    assert len(demo) >= 1
    frameworks = {i.framework for i in demo}
    assert "casel" in frameworks
    assert "developmental_milestones" in frameworks
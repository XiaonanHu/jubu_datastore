"""
Unit tests for capability definition models.

Covers: valid CASEL/developmental parsing, validation errors (age range, duplicate
scoring values, duplicate item IDs, framework mismatch), and age/active helpers.
"""

from pathlib import Path

import pytest
import yaml

from jubu_datastore.models.capability_definitions import (
    AgeRange,
    CapabilityDefinitionPack,
    CapabilityItemDefinition,
    DisplayConfig,
    EvaluationMethod,
    NgssSource,
    ScoringConfig,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CASEL_YAML = _REPO_ROOT / "capability_definitions" / "casel" / "age_5.yaml"
_DEV_YAML = _REPO_ROOT / "capability_definitions" / "developmental" / "age_5.yaml"
_NGSS_YAML = _REPO_ROOT / "capability_definitions" / "ngss" / "age_5.yaml"


def _load_pack(path: Path) -> CapabilityDefinitionPack:
    with open(path) as f:
        data = yaml.safe_load(f)
    return CapabilityDefinitionPack.model_validate(data)


# -----------------------------------------------------------------------------
# Valid parsing: CASEL
# -----------------------------------------------------------------------------


def test_valid_casel_item_parsing() -> None:
    """Parsing valid CASEL age_5.yaml produces a valid CapabilityDefinitionPack."""
    pack = _load_pack(_CASEL_YAML)
    assert pack.framework == "casel"
    assert pack.age == 5
    assert len(pack.items) >= 1
    first = pack.items[0]
    assert first.id == "casel.self_awareness.identify_basic_emotions"
    assert first.framework == "casel"
    assert first.domain == "sel"
    assert first.subdomain == "self_awareness"
    assert first.title == "Identifies basic emotions"
    assert first.status == "active"
    assert first.version >= 1
    assert first.scoring.type == "ternary"
    assert first.scoring.values == ["not_observed", "emerging", "demonstrated"]
    assert first.display.priority == "high"
    assert first.evaluation_method.type == "llm_rubric_with_keyword_support"
    assert first.evaluation_method.rubric_id == "sel_emotion_identification_v1"


# -----------------------------------------------------------------------------
# Valid parsing: developmental milestones
# -----------------------------------------------------------------------------


def test_valid_developmental_milestone_item_parsing() -> None:
    """Parsing valid developmental age_5.yaml produces a valid CapabilityDefinitionPack."""
    pack = _load_pack(_DEV_YAML)
    assert pack.framework == "developmental_milestones"
    assert pack.age == 5
    assert len(pack.items) >= 1
    first = pack.items[0]
    assert first.id == "developmental_milestones.social_emotional.follows_rules_or_takes_turns"
    assert first.framework == "developmental_milestones"
    assert first.domain == "developmental"
    assert first.subdomain == "social_emotional"
    assert first.status == "active"
    assert first.version >= 1
    assert first.scoring.values == ["not_observed", "emerging", "demonstrated"]


# -----------------------------------------------------------------------------
# Invalid age range
# -----------------------------------------------------------------------------


def test_invalid_age_range_min_gt_max() -> None:
    """AgeRange rejects min_age > max_age."""
    with pytest.raises(ValueError, match="min_age must be <= max_age"):
        AgeRange(min_age=6.0, max_age=4.0, expected=True)


def test_invalid_age_range_negative() -> None:
    """AgeRange rejects negative ages."""
    with pytest.raises(ValueError):
        AgeRange(min_age=-0.5, max_age=5.0, expected=True)
    with pytest.raises(ValueError):
        AgeRange(min_age=0.0, max_age=-1.0, expected=True)


def test_valid_age_range() -> None:
    """AgeRange accepts valid range."""
    r = AgeRange(min_age=4.5, max_age=5.5, expected=True)
    assert r.min_age == 4.5
    assert r.max_age == 5.5


# -----------------------------------------------------------------------------
# Duplicate scoring values
# -----------------------------------------------------------------------------


def test_duplicate_scoring_values_rejected() -> None:
    """ScoringConfig rejects duplicate values."""
    with pytest.raises(ValueError, match="unique"):
        ScoringConfig(
            type="ternary",
            values=["not_observed", "emerging", "emerging", "demonstrated"],
        )


def test_scoring_values_non_empty() -> None:
    """ScoringConfig requires non-empty values."""
    with pytest.raises(ValueError):
        ScoringConfig(type="ternary", values=[])


# -----------------------------------------------------------------------------
# Duplicate item IDs in pack
# -----------------------------------------------------------------------------


def test_duplicate_item_ids_in_pack_rejected() -> None:
    """CapabilityDefinitionPack rejects duplicate item ids."""
    item = _minimal_item(id="casel.dup.id", framework="casel")
    with pytest.raises(ValueError, match="duplicate item id"):
        CapabilityDefinitionPack(
            framework="casel",
            age=5,
            items=[item, _minimal_item(id="casel.dup.id", framework="casel")],
        )


# -----------------------------------------------------------------------------
# Framework mismatch in pack
# -----------------------------------------------------------------------------


def test_framework_mismatch_in_pack_rejected() -> None:
    """CapabilityDefinitionPack rejects items whose framework != pack framework."""
    with pytest.raises(ValueError, match="does not match pack framework"):
        CapabilityDefinitionPack(
            framework="casel",
            age=5,
            items=[
                _minimal_item(id="developmental_milestones.one.item", framework="developmental_milestones"),
            ],
        )


# -----------------------------------------------------------------------------
# Age filtering and helpers
# -----------------------------------------------------------------------------


def test_applies_to_age() -> None:
    """CapabilityItemDefinition.applies_to_age returns True when age in range."""
    item = _minimal_item(
        id="casel.x.item",
        framework="casel",
        age_ranges=[
            AgeRange(min_age=4.0, max_age=5.0, expected=True),
            AgeRange(min_age=6.0, max_age=7.0, expected=False),
        ],
    )
    assert item.applies_to_age(4.0) is True
    assert item.applies_to_age(4.5) is True
    assert item.applies_to_age(5.0) is True
    assert item.applies_to_age(5.5) is False
    assert item.applies_to_age(6.5) is True
    assert item.applies_to_age(7.0) is True
    assert item.applies_to_age(3.9) is False
    assert item.applies_to_age(7.1) is False


def test_is_active() -> None:
    """CapabilityItemDefinition.is_active True only for status active."""
    active = _minimal_item(id="casel.a.item", framework="casel", status="active")
    inactive = _minimal_item(id="casel.b.item", framework="casel", status="inactive")
    assert active.is_active() is True
    assert inactive.is_active() is False


def test_pack_get_item_by_id() -> None:
    """CapabilityDefinitionPack.get_item_by_id returns item or None."""
    pack = CapabilityDefinitionPack(
        framework="casel",
        age=5,
        items=[
            _minimal_item(id="casel.first.item", framework="casel"),
            _minimal_item(id="casel.second.item", framework="casel"),
        ],
    )
    assert pack.get_item_by_id("casel.first.item").id == "casel.first.item"
    assert pack.get_item_by_id("casel.second.item").id == "casel.second.item"
    assert pack.get_item_by_id("missing") is None


def test_pack_active_items() -> None:
    """CapabilityDefinitionPack.active_items returns only active items."""
    pack = CapabilityDefinitionPack(
        framework="casel",
        age=5,
        items=[
            _minimal_item(id="casel.a.item", framework="casel", status="active"),
            _minimal_item(id="casel.b.item", framework="casel", status="inactive"),
            _minimal_item(id="casel.c.item", framework="casel", status="active"),
        ],
    )
    active = pack.active_items()
    assert len(active) == 2
    assert {i.id for i in active} == {"casel.a.item", "casel.c.item"}


def test_pack_items_for_age() -> None:
    """CapabilityDefinitionPack.items_for_age returns active items that apply to age."""
    item_4_5 = _minimal_item(
        id="casel.young.item",
        framework="casel",
        age_ranges=[AgeRange(min_age=4.0, max_age=5.0, expected=True)],
    )
    item_6_7 = _minimal_item(
        id="casel.old.item",
        framework="casel",
        age_ranges=[AgeRange(min_age=6.0, max_age=7.0, expected=True)],
    )
    pack = CapabilityDefinitionPack(
        framework="casel",
        age=5,
        items=[item_4_5, item_6_7],
    )
    for_5 = pack.items_for_age(5.0)
    assert len(for_5) == 1
    assert for_5[0].id == "casel.young.item"
    assert len(pack.items_for_age(6.5)) == 1
    assert pack.items_for_age(6.5)[0].id == "casel.old.item"
    assert len(pack.items_for_age(3.0)) == 0


def test_pack_item_ids() -> None:
    """CapabilityDefinitionPack.item_ids returns ordered list of ids."""
    pack = CapabilityDefinitionPack(
        framework="casel",
        age=5,
        items=[
            _minimal_item(id="casel.b.item", framework="casel"),
            _minimal_item(id="casel.a.item", framework="casel"),
        ],
    )
    assert pack.item_ids() == ["casel.b.item", "casel.a.item"]


def test_primary_age_range() -> None:
    """CapabilityItemDefinition.primary_age_range returns expected range or first."""
    expected_first = [
        AgeRange(min_age=4.0, max_age=5.0, expected=True),
        AgeRange(min_age=6.0, max_age=7.0, expected=False),
    ]
    item = _minimal_item(id="casel.x.item", framework="casel", age_ranges=expected_first)
    assert item.primary_age_range() is not None
    assert item.primary_age_range().min_age == 4.0
    assert item.primary_age_range().max_age == 5.0
    only_one = [AgeRange(min_age=3.0, max_age=4.0, expected=False)]
    item2 = _minimal_item(id="casel.y.item", framework="casel", age_ranges=only_one)
    assert item2.primary_age_range() is not None
    assert item2.primary_age_range().min_age == 3.0


def test_version_ge_1() -> None:
    """CapabilityItemDefinition requires version >= 1."""
    with pytest.raises(ValueError):
        _minimal_item(id="casel.x.item", framework="casel", version=0)


def test_display_priority_valid() -> None:
    """DisplayConfig accepts only low, medium, high."""
    for p in ("low", "medium", "high"):
        DisplayConfig(show_in_parent_app=True, priority=p, badge_icon="x")
    with pytest.raises(ValueError, match="priority"):
        DisplayConfig(show_in_parent_app=True, priority="invalid", badge_icon="x")


def test_display_priority_default_medium() -> None:
    """DisplayConfig defaults priority to medium when omitted."""
    d = DisplayConfig(show_in_parent_app=True, badge_icon="x")
    assert d.priority == "medium"


def test_framework_must_be_known() -> None:
    """Item and pack reject framework not in KNOWN_FRAMEWORKS (e.g. typo)."""
    with pytest.raises(ValueError, match="framework must be one of"):
        _minimal_item(id="casel.a.item", framework="casell")
    with pytest.raises(ValueError, match="framework must be one of"):
        CapabilityDefinitionPack(
            framework="casell",
            age=5,
            items=[_minimal_item(id="casel.one.item", framework="casel")],
        )


def test_empty_pack_rejected() -> None:
    """CapabilityDefinitionPack requires at least one item."""
    with pytest.raises(ValueError, match="at least 1"):
        CapabilityDefinitionPack(framework="casel", age=5, items=[])


def test_item_id_prefix_must_match_framework() -> None:
    """Item id must start with pack framework prefix (e.g. casel. for casel pack)."""
    with pytest.raises(ValueError, match="must start with pack framework prefix"):
        CapabilityDefinitionPack(
            framework="casel",
            age=5,
            items=[_minimal_item(id="other.casel.item", framework="casel")],
        )


def test_status_must_be_allowed() -> None:
    """CapabilityItemDefinition rejects status not in active/inactive/deprecated."""
    with pytest.raises(ValueError, match="status must be one of"):
        _minimal_item(id="casel.x.item", framework="casel", status="draft")


def test_id_must_be_dotted_pattern() -> None:
    """CapabilityItemDefinition id must be dotted namespaced (e.g. framework.subdomain.item)."""
    with pytest.raises(ValueError, match="dotted namespaced"):
        _minimal_item(id="single", framework="casel")
    with pytest.raises(ValueError, match="dotted namespaced"):
        _minimal_item(id="no_dots", framework="casel")
    # Valid
    _minimal_item(id="casel.a.item", framework="casel")


def test_scoring_type_must_be_known() -> None:
    """ScoringConfig type must be in VALID_SCORING_TYPES (e.g. typo 'ternery' fails)."""
    with pytest.raises(ValueError, match="scoring type must be one of"):
        ScoringConfig(type="ternery", values=["not_observed", "emerging", "demonstrated"])


def test_list_entries_no_blank() -> None:
    """String list fields (e.g. observable_signals, scoring.values) reject blank entries."""
    with pytest.raises(ValueError, match="blank or whitespace-only"):
        CapabilityItemDefinition(
            id="casel.a.item",
            framework="casel",
            domain="d",
            subdomain="s",
            title="T",
            short_label="S",
            parent_friendly_label="P",
            description="D",
            age_ranges=[AgeRange(min_age=4.5, max_age=5.5, expected=True)],
            observable_signals=["valid", "  ", "also valid"],
            evaluation_method=EvaluationMethod(type="llm_rubric", rubric_id="r1"),
            scoring=ScoringConfig(type="ternary", values=["not_observed", "emerging", "demonstrated"]),
            display=DisplayConfig(show_in_parent_app=True, priority="medium", badge_icon="icon"),
            status="active",
            version=1,
        )
    with pytest.raises(ValueError, match="blank or whitespace-only"):
        ScoringConfig(type="ternary", values=["not_observed", "", "demonstrated"])


def test_extra_forbid() -> None:
    """Models reject unknown keys (typos in YAML)."""
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        AgeRange(min_age=4.5, max_age=5.5, expected=True, minn_age=4.0)
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        CapabilityDefinitionPack(
            framework="casel",
            age=5,
            items=[_minimal_item(id="casel.one.item", framework="casel")],
            framwork="casel",
        )


def test_string_fields_stripped_and_non_empty() -> None:
    """Required string fields are stripped and cannot be whitespace-only."""
    with pytest.raises(ValueError, match="empty or whitespace"):
        CapabilityItemDefinition(
            id="casel.x.item",
            framework="casel",
            domain="d",
            subdomain="s",
            title="   ",
            short_label="S",
            parent_friendly_label="P",
            description="D",
            age_ranges=[AgeRange(min_age=4.5, max_age=5.5, expected=True)],
            evaluation_method=EvaluationMethod(type="llm_rubric", rubric_id="r1"),
            scoring=ScoringConfig(type="ternary", values=["not_observed", "emerging", "demonstrated"]),
            display=DisplayConfig(show_in_parent_app=True, priority="medium", badge_icon="icon"),
            status="active",
            version=1,
        )


# -----------------------------------------------------------------------------
# Valid parsing: NGSS
# -----------------------------------------------------------------------------


def test_valid_ngss_pack_parsing() -> None:
    """ngss/age_5.yaml loads and all items pass schema validation."""
    pack = _load_pack(_NGSS_YAML)
    assert pack.framework == "ngss"
    assert pack.age == 5
    assert len(pack.items) >= 1
    for item in pack.items:
        assert item.framework == "ngss"
        assert item.id.startswith("ngss.")
        assert item.status == "active"
        assert item.version >= 1
        assert item.scoring.type == "ternary"
        assert item.scoring.values == ["not_observed", "emerging", "demonstrated"]


def test_ngss_items_have_ngss_source() -> None:
    """Every item in ngss/age_5.yaml has a parsed ngss_source block."""
    pack = _load_pack(_NGSS_YAML)
    for item in pack.items:
        assert item.ngss_source is not None, f"{item.id} is missing ngss_source"
        assert isinstance(item.ngss_source, NgssSource)
        assert len(item.ngss_source.performance_expectations) >= 1, (
            f"{item.id}: expected at least one performance_expectation"
        )


def test_ngss_list_fields_are_plain_strings() -> None:
    """All list string fields in ngss/age_5.yaml are plain strings, not dicts.

    Guards against YAML colon-in-string bugs (e.g. 'foo: bar' parsed as a mapping).
    """
    pack = _load_pack(_NGSS_YAML)
    for item in pack.items:
        for field_name in (
            "observable_signals",
            "example_prompts",
            "positive_evidence_patterns",
            "negative_evidence_patterns",
        ):
            values = getattr(item, field_name)
            for v in values:
                assert isinstance(v, str), (
                    f"{item.id}.{field_name}: expected str, got {type(v).__name__!r} ({v!r}). "
                    "Likely an unquoted colon in the YAML value."
                )


def test_ngss_subdomains_are_known() -> None:
    """NGSS items use one of the expected subdomains."""
    expected_subdomains = {
        "physical_science",
        "life_science",
        "earth_space_science",
        "engineering",
    }
    pack = _load_pack(_NGSS_YAML)
    for item in pack.items:
        assert item.subdomain in expected_subdomains, (
            f"{item.id}: unexpected subdomain {item.subdomain!r}"
        )


def test_ngss_item_applies_to_age_5() -> None:
    """All items in ngss/age_5.yaml apply to age 5.0."""
    pack = _load_pack(_NGSS_YAML)
    for item in pack.items:
        assert item.applies_to_age(5.0), f"{item.id} should apply to age 5.0"


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _minimal_item(
    *,
    id: str,
    framework: str,
    status: str = "active",
    version: int = 1,
    age_ranges: list[AgeRange] | None = None,
) -> CapabilityItemDefinition:
    """Build a minimal valid item. id must start with framework prefix (e.g. casel.xxx.yyy)."""
    if age_ranges is None:
        age_ranges = [AgeRange(min_age=4.5, max_age=5.5, expected=True)]
    return CapabilityItemDefinition(
        id=id,
        framework=framework,
        domain="d",
        subdomain="s",
        title="T",
        short_label="S",
        parent_friendly_label="P",
        description="D",
        age_ranges=age_ranges,
        evaluation_method=EvaluationMethod(type="llm_rubric", rubric_id="r1"),
        scoring=ScoringConfig(type="ternary", values=["not_observed", "emerging", "demonstrated"]),
        display=DisplayConfig(show_in_parent_app=True, priority="medium", badge_icon="icon"),
        status=status,
        version=version,
    )

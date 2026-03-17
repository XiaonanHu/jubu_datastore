"""
YAML loader and registry for capability definitions.

Single entry point: load YAML files into validated CapabilityDefinitionPack instances,
register them in a CapabilityDefinitionRegistry, and query by framework, age, or item id.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from jubu_datastore.models.capability_definitions import (
    CapabilityDefinitionPack,
    CapabilityItemDefinition,
)


# -----------------------------------------------------------------------------
# Loader errors (fail fast, no silent ignore)
# -----------------------------------------------------------------------------


class DuplicatePackError(Exception):
    """Raised when (framework, age) is already registered."""

    def __init__(self, framework: str, age: float) -> None:
        self.framework = framework
        self.age = age
        super().__init__(f"Duplicate pack for {framework!r} age {age}")


class DuplicateItemIdError(Exception):
    """Raised when an item id is already registered (e.g. across packs)."""

    def __init__(self, item_id: str, first_seen_in: str) -> None:
        self.item_id = item_id
        self.first_seen_in = first_seen_in
        super().__init__(f"Duplicate item id {item_id!r} (already in {first_seen_in!r})")


# -----------------------------------------------------------------------------
# YAML loading
# -----------------------------------------------------------------------------


def load_definition_pack_from_yaml(path: Path) -> CapabilityDefinitionPack:
    """
    Read a YAML file and return a validated CapabilityDefinitionPack.

    Runs all model validators from the typed definition layer.
    Raises on invalid YAML structure or schema validation failure.
    """
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        raise ValueError(f"Empty or invalid YAML: {path}")
    try:
        return CapabilityDefinitionPack.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"Validation error in {path}: {e}") from e


# -----------------------------------------------------------------------------
# Registry
# -----------------------------------------------------------------------------


class CapabilityDefinitionRegistry:
    """
    Central registry of all loaded capability packs and items.

    Maintains indexes for fast lookup by (framework, age), item id, and framework.
    """

    def __init__(self) -> None:
        self._packs_by_framework_age: dict[tuple[str, float], CapabilityDefinitionPack] = {}
        self._items_by_id: dict[str, CapabilityItemDefinition] = {}
        self._items_by_framework: dict[str, list[CapabilityItemDefinition]] = {}
        self._item_origin: dict[str, tuple[str, float]] = {}  # item_id -> (framework, age)

    def load_all_packs(self, root_directory: Path) -> None:
        """
        Discover all .yaml files under root_directory and load them as packs.

        Registers each pack after validation. Fails fast on:
        - Duplicate (framework, age)
        - Duplicate item id (global across packs)
        - Invalid YAML or schema
        """
        root = Path(root_directory)
        if not root.is_dir():
            raise ValueError(f"Not a directory: {root}")

        yaml_files = sorted(root.rglob("*.yaml"))
        if not yaml_files:
            return

        for path in yaml_files:
            pack = load_definition_pack_from_yaml(path)
            self._register_pack(pack)

    def _register_pack(self, pack: CapabilityDefinitionPack) -> None:
        """Register one pack and its items. Raises on duplicate pack or duplicate item id."""
        key = (pack.framework, float(pack.age))
        if key in self._packs_by_framework_age:
            raise DuplicatePackError(pack.framework, float(pack.age))

        for item in pack.items:
            if item.id in self._items_by_id:
                orig = self._item_origin.get(item.id, (pack.framework, float(pack.age)))
                first_seen = f"pack {orig[0]}/{orig[1]}"
                raise DuplicateItemIdError(item.id, first_seen)

        self._packs_by_framework_age[key] = pack
        for item in pack.items:
            self._items_by_id[item.id] = item
            self._item_origin[item.id] = (pack.framework, float(pack.age))
            self._items_by_framework.setdefault(pack.framework, []).append(item)

    def get_pack(self, framework: str, age: float) -> CapabilityDefinitionPack:
        """Return the pack for (framework, age). Raises KeyError if not found."""
        key = (framework, float(age))
        if key not in self._packs_by_framework_age:
            raise KeyError(f"No pack for framework={framework!r} age={age}")
        return self._packs_by_framework_age[key]

    def get_item(self, item_id: str) -> CapabilityItemDefinition | None:
        """Return the item by id, or None if not registered."""
        return self._items_by_id.get(item_id)

    def get_items_for_framework(self, framework: str) -> list[CapabilityItemDefinition]:
        """Return all items for the given framework (any age)."""
        return list(self._items_by_framework.get(framework, []))

    def get_items_for_child_age(self, age: float) -> list[CapabilityItemDefinition]:
        """Return all active items that apply to the given child age (any framework)."""
        out: list[CapabilityItemDefinition] = []
        for item in self._items_by_id.values():
            if item.is_active() and item.applies_to_age(age):
                out.append(item)
        return out

    def get_demo_items(self, age: float) -> list[CapabilityItemDefinition]:
        """
        Return demo items for the given age: CASEL + developmental_milestones
        items that apply to this age (active only).
        """
        out: list[CapabilityItemDefinition] = []
        for fw in ("casel", "developmental_milestones"):
            for item in self._items_by_framework.get(fw, []):
                if item.is_active() and item.applies_to_age(age):
                    out.append(item)
        return out

    def get_all_items_definitions(self) -> list[dict]:
        """
        Return all capability items with id, title, description, and definition fields.

        Used by backend/LLM to decide whether a conversation shows hints related to
        these capabilities. No age filtering; returns every registered item.
        Each element is a dict with: id, title, description, age_ranges,
        observable_signals, positive_evidence_patterns, negative_evidence_patterns,
        framework, domain, subdomain, version.
        """
        out: list[dict] = []
        for item in self._items_by_id.values():
            out.append({
                "id": item.id,
                "title": item.title,
                "description": item.description,
                "age_ranges": [
                    {"min_age": ar.min_age, "max_age": ar.max_age}
                    for ar in item.age_ranges
                ],
                "observable_signals": list(item.observable_signals),
                "positive_evidence_patterns": list(item.positive_evidence_patterns),
                "negative_evidence_patterns": list(item.negative_evidence_patterns),
                "framework": item.framework,
                "domain": item.domain,
                "subdomain": item.subdomain,
                "version": getattr(item, "version", 1),
            })
        return out

    @property
    def packs_by_framework_age(self) -> dict[tuple[str, float], CapabilityDefinitionPack]:
        """Read-only view of packs by (framework, age)."""
        return dict(self._packs_by_framework_age)

    @property
    def items_by_id(self) -> dict[str, CapabilityItemDefinition]:
        """Read-only view of items by id."""
        return dict(self._items_by_id)


# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------


def load_default_registry(definition_root_path: Path | None = None) -> CapabilityDefinitionRegistry:
    """
    Build a registry and load all packs from the default definition root.

    If definition_root_path is None, uses the capability_definitions directory
    next to the jubu_datastore package (so repo root capability_definitions/).
    """
    if definition_root_path is None:
        # Resolve from this file: loaders/capability_loader.py -> repo root -> capability_definitions
        this_file = Path(__file__).resolve()
        repo_root = this_file.parent.parent
        definition_root_path = repo_root / "capability_definitions"
    registry = CapabilityDefinitionRegistry()
    registry.load_all_packs(definition_root_path)
    return registry

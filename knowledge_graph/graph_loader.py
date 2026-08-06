"""
YAML loader and registry for knowledge-graph packs.

Mirrors ``loaders/capability_loader.py``: load YAML files into validated
``KnowledgeGraphPack`` instances, register them in a
``KnowledgeGraphRegistry``, and query by node id or axis.

Structural validation (id shape, prefix/axis match, treatment coverage) lives
in the Pydantic models; cross-node validation (edge endpoints, DAG-ness,
orphans, banned language) lives in ``graph_validator``.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from jubu_datastore.knowledge_graph.graph_schema import (
    AgeTreatment,
    KnowledgeGraphNode,
    KnowledgeGraphPack,
)


class DuplicateNodeIdError(Exception):
    """Raised when a node id is already registered (e.g. across packs)."""

    def __init__(self, node_id: str, first_seen_in: str) -> None:
        self.node_id = node_id
        self.first_seen_in = first_seen_in
        super().__init__(
            f"Duplicate node id {node_id!r} (already in {first_seen_in!r})"
        )


class DuplicatePackError(Exception):
    """Raised when (axis, pack) is already registered."""

    def __init__(self, axis: str, pack: str) -> None:
        self.axis = axis
        self.pack = pack
        super().__init__(f"Duplicate pack {pack!r} for axis {axis!r}")


def load_pack_from_yaml(path: Path) -> KnowledgeGraphPack:
    """Read a YAML file and return a validated KnowledgeGraphPack."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        raise ValueError(f"Empty or invalid YAML: {path}")
    try:
        return KnowledgeGraphPack.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"Validation error in {path}: {e}") from e


class KnowledgeGraphRegistry:
    """Central registry of all loaded knowledge-graph packs and nodes."""

    def __init__(self) -> None:
        self._packs_by_axis_name: dict[tuple[str, str], KnowledgeGraphPack] = {}
        self._nodes_by_id: dict[str, KnowledgeGraphNode] = {}
        self._nodes_by_axis: dict[str, list[KnowledgeGraphNode]] = {}
        self._node_origin_pack: dict[str, str] = {}

    def load_all_packs(self, root_directory: Path) -> None:
        """Load every ``*.yaml`` under ``root_directory`` (recursive)."""
        root = Path(root_directory)
        if not root.is_dir():
            raise ValueError(f"Not a directory: {root}")
        for path in sorted(root.rglob("*.yaml")):
            self._register_pack(load_pack_from_yaml(path))

    def _register_pack(self, pack: KnowledgeGraphPack) -> None:
        key = (pack.axis, pack.pack)
        if key in self._packs_by_axis_name:
            raise DuplicatePackError(pack.axis, pack.pack)
        for node in pack.nodes:
            if node.id in self._nodes_by_id:
                raise DuplicateNodeIdError(
                    node.id, self._node_origin_pack.get(node.id, "<unknown>")
                )
        self._packs_by_axis_name[key] = pack
        for node in pack.nodes:
            self._nodes_by_id[node.id] = node
            self._nodes_by_axis.setdefault(node.axis, []).append(node)
            self._node_origin_pack[node.id] = f"{pack.axis}/{pack.pack}"

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_node(self, node_id: str) -> KnowledgeGraphNode:
        node = self._nodes_by_id.get(node_id)
        if node is None:
            raise KeyError(f"Unknown knowledge-graph node id {node_id!r}")
        return node

    def has_node(self, node_id: str) -> bool:
        return node_id in self._nodes_by_id

    def nodes_for_axis(self, axis: str) -> list[KnowledgeGraphNode]:
        return list(self._nodes_by_axis.get(axis, []))

    def nodes_for_axis_at_age(self, axis: str, age: int) -> list[KnowledgeGraphNode]:
        return [
            node
            for node in self._nodes_by_axis.get(axis, [])
            if node.exists_at_age(age)
        ]

    def children_of(self, node_id: str) -> list[KnowledgeGraphNode]:
        """Deep-dive nodes hanging off this curriculum node."""
        return [
            node for node in self._nodes_by_id.values() if node.subtopic_of == node_id
        ]

    def effective_treatment(self, node_id: str, age: int) -> AgeTreatment | None:
        """
        The treatment to use for a node at an age, following the deep-dive
        inheritance rule: a deep-dive node's own treatment if it authored
        one, otherwise its curriculum parent's.
        """
        node = self.get_node(node_id)
        own = node.treatment_for_age(age)
        if own is not None:
            return own
        if node.subtopic_of and self.has_node(node.subtopic_of):
            return self.get_node(node.subtopic_of).treatment_for_age(age)
        return None

    def effective_avoid_list(self, node_id: str, age: int) -> list[str]:
        """A deep-dive node's own avoid entries plus everything its parent avoids."""
        node = self.get_node(node_id)
        avoid: list[str] = []
        own = node.treatment_for_age(age)
        if own is not None:
            avoid.extend(own.avoid)
        if node.subtopic_of and self.has_node(node.subtopic_of):
            inherited = self.get_node(node.subtopic_of).treatment_for_age(age)
            if inherited is not None:
                avoid.extend(entry for entry in inherited.avoid if entry not in avoid)
        return avoid

    def origin_pack_of(self, node_id: str) -> str:
        return self._node_origin_pack.get(node_id, "<unknown>")

    @property
    def all_nodes(self) -> list[KnowledgeGraphNode]:
        return list(self._nodes_by_id.values())

    @property
    def nodes_by_id(self) -> dict[str, KnowledgeGraphNode]:
        return dict(self._nodes_by_id)

    @property
    def packs_by_axis_name(self) -> dict[tuple[str, str], KnowledgeGraphPack]:
        return dict(self._packs_by_axis_name)


def default_definitions_root() -> Path:
    """Repo-root ``knowledge_graph_definitions/`` directory."""
    this_file = Path(__file__).resolve()
    repo_root = this_file.parent.parent
    return repo_root / "knowledge_graph_definitions"


def load_default_registry(
    definition_root_path: Path | None = None,
) -> KnowledgeGraphRegistry:
    """Load the checked-in graph definitions into a fresh registry."""
    if definition_root_path is None:
        definition_root_path = default_definitions_root()
    registry = KnowledgeGraphRegistry()
    registry.load_all_packs(definition_root_path)
    return registry

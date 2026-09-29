"""Validated nominal data types and their multiple-inheritance semantics.

This module is the single seam for type hierarchy validation, C3
linearization, graph-flow compatibility, and parameterized abstract ports.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .contracts import DATA_TYPES, DataTypeDefinition


BUILTIN_DATA_TYPES: dict[str, DataTypeDefinition] = {
    name: DataTypeDefinition(name=name, builtin=True) for name in DATA_TYPES
}


class DataTypeRegistry:
    """A validated, immutable-by-convention view of the complete type graph."""

    def __init__(self, custom_types: Mapping[str, Mapping[str, Any]] | None = None):
        definitions = {name: definition.model_copy(deep=True) for name, definition in BUILTIN_DATA_TYPES.items()}
        for key, raw in (custom_types or {}).items():
            payload = dict(raw)
            payload.setdefault("name", key)
            payload["builtin"] = False
            definition = DataTypeDefinition.model_validate(payload)
            if definition.name != key:
                raise ValueError(f"Data type key {key} does not match its name {definition.name}")
            if key in BUILTIN_DATA_TYPES:
                raise ValueError(f"Built-in data type cannot be replaced: {key}")
            definitions[key] = definition
        self._definitions = definitions
        self._linearizations: dict[str, tuple[str, ...]] = {}
        self._validate()

    def names(self) -> tuple[str, ...]:
        return tuple(self._definitions)

    def definitions(self) -> dict[str, dict[str, Any]]:
        return {name: definition.model_dump() for name, definition in self._definitions.items()}

    def get(self, name: str) -> DataTypeDefinition:
        try:
            return self._definitions[name]
        except KeyError as exc:
            raise ValueError(f"Unknown data type: {name}") from exc

    def linearization(self, name: str) -> tuple[str, ...]:
        self.get(name)
        return self._linearizations[name]

    def can_flow(self, source_type: str, target_type: str) -> bool:
        """Return whether a source may feed a target.

        MatFlow intentionally permits a parent output to feed an input that
        requires a descendant. Exact matches are included.
        """
        if source_type not in self._definitions or target_type not in self._definitions:
            return False
        return source_type in self._linearizations[target_type]

    def validate_port_types(self, type_names: Iterable[str]) -> None:
        unknown = sorted(set(type_names) - set(self._definitions))
        if unknown:
            raise ValueError(f"Unknown data types: {', '.join(unknown)}")

    def resolve_ports(self, spec: Any, node: Any) -> tuple[dict[str, str], dict[str, str]]:
        """Resolve concrete ports, including a parameterized abstract cast node."""
        if not getattr(spec, "abstract", False):
            return dict(spec.inputs), dict(spec.outputs)
        if spec.tool_id != "type_cast":
            raise ValueError(f"Unsupported abstract node: {spec.tool_id}")
        source_type = str(node.params.get("source_type") or "")
        target_type = str(node.params.get("target_type") or "")
        self.validate_port_types((source_type, target_type))
        return {"value": source_type}, {"value": target_type}

    def _validate(self) -> None:
        for name, definition in self._definitions.items():
            if name in definition.parents:
                raise ValueError(f"Data type {name} cannot inherit from itself")
            missing = sorted(set(definition.parents) - set(self._definitions))
            if missing:
                raise ValueError(f"Data type {name} has unknown parent(s): {', '.join(missing)}")

        visiting: list[str] = []

        def linearize(name: str) -> tuple[str, ...]:
            cached = self._linearizations.get(name)
            if cached is not None:
                return cached
            if name in visiting:
                cycle = visiting[visiting.index(name):] + [name]
                raise ValueError(f"Data type inheritance cycle: {' -> '.join(cycle)}")
            visiting.append(name)
            parents = self._definitions[name].parents
            sequences = [list(linearize(parent)) for parent in parents] + [list(parents)]
            merged: list[str] = []
            while any(sequences):
                sequences = [sequence for sequence in sequences if sequence]
                candidate = next(
                    (sequence[0] for sequence in sequences if not any(sequence[0] in other[1:] for other in sequences)),
                    None,
                )
                if candidate is None:
                    raise ValueError(f"Inconsistent multiple inheritance for data type {name}")
                merged.append(candidate)
                for sequence in sequences:
                    if sequence and sequence[0] == candidate:
                        sequence.pop(0)
            visiting.pop()
            result = (name, *merged)
            self._linearizations[name] = result
            return result

        for type_name in self._definitions:
            linearize(type_name)

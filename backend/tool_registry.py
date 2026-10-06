"""The registry module hides ToolSpec lifecycle and legacy serialization details."""
from __future__ import annotations

from typing import Any, Mapping

from .contracts import ToolSpec
from .data_types import DataTypeRegistry


def builtin_specs() -> dict[str, ToolSpec]:
    """Return the domain-neutral v0.2 platform catalog.

    Scientific Tools are contributed by a Domain Package and registered through
    ``ToolRegistry(package_specs=...)``; they are not declared here.
    """
    entries = {
        "raw_file_import": {"label": "Raw File Import", "category": "Input", "inputs": {}, "outputs": {"raw": "RawData"}, "params": {"file_name": "measurement.csv", "upload_id": ""}, "description": "Import a specific uploaded CSV, Excel, TXT or JSON data file.", "preview_spec": {"outputs": {"raw": {"renderer": "table_head"}}}},
        "normalize_columns": {"label": "Normalize / Column Mapping", "category": "Transform", "inputs": {"raw": "RawData"}, "outputs": {"table": "TypedTable"}, "params": {"x_column": "x", "y_column": "y"}, "open_params": True, "description": "Map user column names onto typed columns. The mapping keys are user data, so any declared axis may be mapped; each mapped name must exist in the uploaded file.", "preview_spec": {"outputs": {"table": {"renderer": "json_tree"}}}},
        "type_cast": {"label": "Type Cast", "category": "Transform", "inputs": {"value": "RawData"}, "outputs": {"value": "RawData"}, "params": {"source_type": "RawData", "target_type": "RawData"}, "description": "Abstract pass-through node whose concrete input and output types are selected per node instance.", "preview_spec": {"outputs": {"value": {"renderer": "json_tree"}}}, "abstract": True},
        "skill_node": {"label": "AI Skill Node", "category": "AI", "inputs": {"dataset": "TypedTable"}, "outputs": {"artifact": "Artifact"}, "params": {"skill_id": "", "instructions": "", "output_schema": {}}, "description": "Runs a versioned domain skill against typed data and returns a schema-bound artifact.", "preview_spec": {"outputs": {"artifact": {"renderer": "json_tree"}}}},
        "join": {"label": "Join", "category": "Control", "inputs": {"items": "Artifact"}, "outputs": {"combined": "Artifact"}, "params": {"label": ""}, "description": "Combine every artifact connected to the multi-input 'items' port into one auditable collection.", "multi_input": ["items"], "preview_spec": {"outputs": {"combined": {"renderer": "json_tree"}}}},
        "aggregate": {"label": "Aggregate", "category": "Control", "inputs": {"items": "Artifact"}, "outputs": {"summary": "Artifact"}, "params": {"group_key": ""}, "description": "Summarize the numeric fields that the upstream artifacts share.", "multi_input": ["items"], "preview_spec": {"outputs": {"summary": {"renderer": "json_tree"}}}},
        "quality_report": {"label": "Quality Report", "category": "Control", "inputs": {"data": "Artifact"}, "outputs": {"report": "QualityReport"}, "params": {"required_keys": [], "metric_key": "", "minimum": None, "maximum": None}, "description": "Evaluate declared expectations about an upstream artifact and report pass or fail; declaring no check fails closed.", "preview_spec": {"outputs": {"report": {"renderer": "json_tree"}}}},
        "conditional_gate": {"label": "Conditional Gate", "category": "Control", "inputs": {"data": "Artifact", "report": "QualityReport"}, "outputs": {"data": "Artifact"}, "params": {"on_fail": "stop", "prompt": "Continue after this quality gate?"}, "description": "Pass an artifact through only while its quality report passes; a failing report stops downstream work. The decision is recorded inside the passed artifact under 'gate' and 'decision'.", "preview_spec": {"outputs": {"data": {"renderer": "json_tree"}}}},
    }
    return {
        tool_id: ToolSpec(tool_id=tool_id, executor_ref=f"builtin:{tool_id}", **entry)
        for tool_id, entry in entries.items()
    }


class ToolRegistry:
    """A small interface over active, versioned tool declarations."""

    def __init__(
        self,
        custom_nodes: dict[str, dict[str, Any]] | None = None,
        type_registry: DataTypeRegistry | None = None,
        package_specs: Mapping[str, ToolSpec] | None = None,
    ):
        self.type_registry = type_registry or DataTypeRegistry()
        self._specs = builtin_specs()
        package_tool_ids = set(package_specs or {})
        for tool_id, spec in (package_specs or {}).items():
            if tool_id in self._specs:
                raise ValueError(f"A Domain Package cannot redeclare a platform tool: {tool_id}")
            if spec.tool_id != tool_id:
                raise ValueError(f"Domain package tool key {tool_id} does not match its tool_id {spec.tool_id}")
            self._specs[tool_id] = spec
        for tool_id, node in (custom_nodes or {}).items():
            if tool_id in self._specs:
                raise ValueError(
                    f"A custom node cannot replace an existing tool: {tool_id}. Choose a unique node key."
                )
            payload = dict(node)
            payload.setdefault("tool_id", tool_id)
            payload.setdefault("executor_ref", f"custom:{tool_id}")
            payload.setdefault("provenance", {"kind": "custom", "reviewed_by": "local-user"})
            self._specs[tool_id] = ToolSpec.model_validate(payload)
        for tool_id, spec in self._specs.items():
            try:
                self.type_registry.validate_port_types((*spec.inputs.values(), *spec.outputs.values()))
            except ValueError as exc:
                if tool_id in package_tool_ids:
                    raise ValueError(
                        f"Domain Package tool {tool_id} declares a port type it did not contribute: {exc}"
                    ) from exc
                raise

    def get(self, tool_id: str) -> ToolSpec:
        try:
            return self._specs[tool_id]
        except KeyError as exc:
            raise ValueError(f"Unknown registry node: {tool_id}") from exc

    def active(self) -> dict[str, ToolSpec]:
        return {tool_id: spec for tool_id, spec in self._specs.items() if spec.status == "active"}

    def agent_selectable(self) -> dict[str, ToolSpec]:
        """Active tools eligible for natural-language candidate retrieval."""
        return {tool_id: spec for tool_id, spec in self.active().items() if spec.agent_selectable}

    def legacy_view(self, *, agent_selectable_only: bool = False) -> dict[str, dict[str, Any]]:
        """Compatibility adapter for the v0.1 UI and executor call sites."""
        specs = self.agent_selectable() if agent_selectable_only else self.active()
        return {
            tool_id: {
                "label": spec.label,
                "category": spec.category,
                "inputs": spec.inputs,
                "outputs": spec.outputs,
                "params": spec.params,
                "description": spec.description,
                "version": spec.version,
                "status": spec.status,
                "agent_selectable": spec.agent_selectable,
                "preview_spec": spec.preview_spec.model_dump(),
                "parent_tool_id": spec.parent_tool_id,
                "parent_version": spec.parent_version,
                "generated_code_status": spec.generated_code_status,
                "abstract": spec.abstract,
                "input_schema": spec.input_schema,
                "output_schema": spec.output_schema,
                "parameter_schema": spec.parameter_schema,
                "required_inputs": spec.required_inputs,
                "required_params": spec.parameter_schema.get("required", []),
            }
            for tool_id, spec in specs.items()
        }

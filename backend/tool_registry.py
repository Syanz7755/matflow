"""The registry module hides ToolSpec lifecycle and legacy serialization details."""
from __future__ import annotations

from typing import Any, Mapping

from .contracts import ToolSpec
from .data_types import DataTypeRegistry


def _schema_type(value: Any) -> dict[str, Any]:
    """A JSON Schema type for one declared default value."""
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, (int, float)):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string"}
    if isinstance(value, list):
        return {"type": "array"}
    if isinstance(value, dict):
        return {"type": "object"}
    return {}


def parameter_schema_for(params: Mapping[str, Any], *, open_params: bool = False) -> dict[str, Any]:
    """Derive an explicit parameter schema from a tool's declared defaults.

    A client that turns registry tools into agent tools, CLI flags or ComfyUI
    inputs needs to know exactly which parameters exist.  Deriving the schema
    from ``params`` keeps it from drifting away from the catalogue, and
    ``additionalProperties`` states whether undeclared keys are meaningful:
    ``normalize_columns`` maps user column names and is therefore open, while a
    closed tool tells a client that the declared set is the whole set.
    """
    return {
        "type": "object",
        "properties": {name: _schema_type(value) for name, value in params.items()},
        "additionalProperties": bool(open_params),
    }


#: Optional sub-schema inside ``parameter_schema``: what the parameters must
#: satisfy before the node can do useful work. Graph validation ignores it, so a
#: client can still add a node with defaults and configure it afterwards; the
#: workflow planner refuses to call a plan complete while it is unmet.
READY_SCHEMA_KEY = "x-matflow-ready"


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
        "quality_report": {"label": "Quality Report", "category": "Control", "inputs": {"data": "Artifact"}, "outputs": {"report": "QualityReport"}, "params": {"required_keys": [], "metric_key": "", "minimum": None, "maximum": None}, "description": "Evaluate declared expectations about an upstream artifact and report pass or fail; declaring no check fails closed.", "preview_spec": {"outputs": {"report": {"renderer": "json_tree"}}}, "ready_schema": {"description": "declare at least one check: required_keys or metric_key", "anyOf": [{"required": ["required_keys"], "properties": {"required_keys": {"minItems": 1}}}, {"required": ["metric_key"], "properties": {"metric_key": {"minLength": 1}}}]}},
        "conditional_gate": {"label": "Conditional Gate", "category": "Control", "inputs": {"data": "Artifact", "report": "QualityReport"}, "outputs": {"data": "Artifact"}, "params": {"on_fail": "stop", "prompt": "Continue after this quality gate?"}, "description": "Pass an artifact through only while its quality report passes; a failing report stops downstream work. The decision is recorded inside the passed artifact under 'gate' and 'decision'.", "preview_spec": {"outputs": {"data": {"renderer": "json_tree"}}}},
    }
    specs = {}
    for tool_id, entry in entries.items():
        entry = dict(entry)
        schema = parameter_schema_for(entry.get("params", {}), open_params=bool(entry.get("open_params")))
        ready = entry.pop("ready_schema", None)
        if ready is not None:
            schema[READY_SCHEMA_KEY] = ready
        specs[tool_id] = ToolSpec(tool_id=tool_id, executor_ref=f"builtin:{tool_id}", parameter_schema=schema, **entry)
    return specs


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
        # Everything declared in code (platform + Domain Packages) owes clients an
        # explicit parameter contract; user custom nodes are exempt below.
        declared = dict(self._specs)
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
        self._require_declared_parameters(declared)

    @staticmethod
    def _require_declared_parameters(declared: Mapping[str, ToolSpec]) -> None:
        """Refuse an agent-selectable tool that does not state its parameters.

        Without this rule half the catalogue ships an empty ``{"type": "object"}``
        schema, and every client (agent bridge, TUI, ComfyUI pack) has to guess or
        hardcode the parameter set.  Custom nodes are excluded by the caller.
        """
        for tool_id, spec in declared.items():
            if spec.status != "active" or not spec.agent_selectable:
                continue
            schema = spec.parameter_schema
            if not isinstance(schema, dict) or not ({"properties", "additionalProperties"} & set(schema)):
                raise ValueError(
                    f"Tool {tool_id} must declare an explicit parameter_schema with properties and additionalProperties"
                )
            if not spec.open_params and schema.get("additionalProperties") is not False:
                raise ValueError(
                    f"Tool {tool_id} must set parameter_schema.additionalProperties to false, or declare open_params"
                )

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

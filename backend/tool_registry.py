"""The registry module hides ToolSpec lifecycle and legacy serialization details."""
from __future__ import annotations

from typing import Any

from .contracts import ToolSpec


def builtin_specs() -> dict[str, ToolSpec]:
    """Return the v0.2 built-in catalog. Callers receive immutable-by-convention specs."""
    entries = {
        "raw_file_import": {"label": "Raw File Import", "category": "Input", "inputs": {}, "outputs": {"raw": "RawData"}, "params": {"file_name": "eis_measurement.csv", "upload_id": ""}, "description": "Import a specific uploaded CSV, Excel, TXT or JSON data file."},
        "normalize_columns": {"label": "Normalize / Column Mapping", "category": "Transform", "inputs": {"raw": "RawData"}, "outputs": {"table": "TypedTable"}, "params": {"frequency_column": "frequency_hz", "real_column": "z_real", "imag_column": "z_imag"}, "description": "Map user column names into a typed measurement table."},
        "eis_basic_qc": {"label": "EIS Basic Analysis", "category": "Analysis", "inputs": {"data": "TypedTable"}, "outputs": {"report": "EISQCReport", "data": "EISData"}, "params": {"min_frequency_hz": 10, "fit_model": "None"}, "description": "Nyquist/Bode quality checks and a typed EIS output."},
        "plot_nyquist": {"label": "Plot Nyquist", "category": "Output", "inputs": {"data": "EISData"}, "outputs": {"plot": "Plot"}, "params": {"title": "Nyquist plot"}, "description": "Create a standard Nyquist plot."},
        "human_decision": {"label": "Human Decision", "category": "Control", "inputs": {"context": "EISQCReport"}, "outputs": {"decision": "Decision"}, "params": {"prompt": "Approve the EIS fit?", "options": ["approve", "revise"]}, "description": "Pause a workflow for an expert choice."},
        "skill_node": {"label": "AI Skill Node", "category": "AI", "inputs": {"dataset": "TypedTable"}, "outputs": {"artifact": "Artifact"}, "params": {"skill_id": "", "instructions": "", "output_schema": {}}, "description": "Runs a versioned domain skill against typed data and returns a schema-bound artifact."},
    }
    return {
        tool_id: ToolSpec(tool_id=tool_id, executor_ref=f"builtin:{tool_id}", **entry)
        for tool_id, entry in entries.items()
    }


class ToolRegistry:
    """A small interface over active, versioned tool declarations."""

    def __init__(self, custom_nodes: dict[str, dict[str, Any]] | None = None):
        self._specs = builtin_specs()
        for tool_id, node in (custom_nodes or {}).items():
            self._specs[tool_id] = ToolSpec(
                tool_id=tool_id,
                executor_ref=f"custom:{tool_id}",
                provenance={"kind": "custom", "reviewed_by": "local-user"},
                **node,
            )

    def get(self, tool_id: str) -> ToolSpec:
        try:
            return self._specs[tool_id]
        except KeyError as exc:
            raise ValueError(f"Unknown registry node: {tool_id}") from exc

    def active(self) -> dict[str, ToolSpec]:
        return {tool_id: spec for tool_id, spec in self._specs.items() if spec.status == "active"}

    def legacy_view(self) -> dict[str, dict[str, Any]]:
        """Compatibility adapter for the v0.1 UI and executor call sites."""
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
            }
            for tool_id, spec in self.active().items()
        }

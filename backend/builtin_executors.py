"""Domain-neutral executors owned by Platform Core.

Every executor here is declared by ``builtin_specs()`` and contains no
measurement-method vocabulary. Scientific executors belong to a Domain Package
and register through the same ``ExecutorRegistry``.
"""
from __future__ import annotations

import copy
import json
from typing import Any

from .analysis_recipes import RecipeEngine
from .executors import ExecutionOutcome, ExecutorRegistry, NodeExecution


def raw_file_import(ctx: NodeExecution) -> dict[str, Any]:
    upload_id = str(ctx.node.params.get("upload_id") or "")
    if not upload_id:
        raise ValueError("Raw File Import has no upload_id")
    inspected = ctx.runtime.inspect_dataset(upload_id)
    if inspected["kind"] != "table":
        raise ValueError("Raw File Import only supports tabular data")
    return {
        "kind": "RawData",
        "upload_id": upload_id,
        "rows": inspected["rows"],
        "columns": [column["name"] for column in inspected["columns"]],
        "preview": inspected["preview"],
    }


def normalize_columns(ctx: NodeExecution) -> dict[str, Any]:
    """Map user column names onto typed columns.

    Every mapped name must exist in the uploaded file. The mapping keys are the
    node's own data (see ``ToolSpec.open_params``), so Core validates the values
    against the real columns instead of carrying a fixed list of measurement
    column names.
    """
    raw = ctx.runtime.node_input(ctx.state, ctx.node.id, "raw")
    if not raw.output:
        raise ValueError(f"Upstream node {raw.id} has not run")
    columns = set(raw.output["columns"])
    mapping = ctx.node.params
    missing = [mapped for mapped in mapping.values() if mapped not in columns]
    if missing:
        raise ValueError(f"Column mapping does not match the uploaded file: {missing}")
    return {
        "kind": "TypedTable",
        "upload_id": raw.output["upload_id"],
        "mapping": mapping,
        "rows": raw.output["rows"],
    }


def type_cast(ctx: NodeExecution) -> dict[str, Any]:
    upstream = ctx.runtime.node_input(ctx.state, ctx.node.id, "value")
    if not upstream.output:
        raise ValueError(f"Upstream node {upstream.id} has not run")
    type_registry = ctx.runtime.data_type_registry()
    source_type = str(ctx.node.params.get("source_type") or "")
    target_type = str(ctx.node.params.get("target_type") or "")
    type_registry.validate_port_types((source_type, target_type))
    output = copy.deepcopy(upstream.output)
    output["kind"] = target_type
    output["cast"] = {"from": source_type, "to": target_type, "node_id": ctx.node.id}
    return output


def skill_node(ctx: NodeExecution) -> dict[str, Any]:
    if not ctx.runtime.model_adapter_configured:
        raise ValueError("Skill Node execution requires a configured model adapter")
    table = ctx.runtime.node_input(ctx.state, ctx.node.id, "dataset")
    if not table.output:
        raise ValueError(f"Upstream node {table.id} has not run")
    contract = {
        "skill_id": ctx.node.params.get("skill_id"),
        "instructions": ctx.node.params.get("instructions"),
        "input": {
            "mapping": table.output.get("mapping"),
            "preview": ctx.runtime.inspect_dataset(str(table.output["upload_id"])).get("preview", []),
        },
        "output_schema": ctx.node.params.get("output_schema", {}),
    }
    answer = ctx.runtime.complete_with_model(
        [
            {"role": "system", "content": "Execute this Skill Node. Return only JSON conforming to output_schema."},
            {"role": "user", "content": json.dumps(contract, ensure_ascii=False)},
        ],
        [],
    )
    try:
        payload = json.loads(answer.get("content") or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"Skill Node returned invalid JSON: {exc}") from exc
    return {
        "kind": "Artifact",
        "skill_id": ctx.node.params.get("skill_id"),
        "schema": ctx.node.params.get("output_schema", {}),
        "data": payload,
    }


def declarative_recipe(ctx: NodeExecution) -> dict[str, Any]:
    """Execute any ``recipe:`` tool from its own declarative declaration."""
    raw = ctx.runtime.node_input(ctx.state, ctx.node.id, "data")
    if not raw.output:
        raise ValueError(f"Upstream node {raw.id} has not run")
    upload_id = str(raw.output.get("upload_id") or "")
    frame = ctx.runtime.dataset_frame(upload_id)
    recipe = ctx.node.params.get("recipe") or ctx.spec.params.get("recipe")
    if not recipe:
        raise ValueError("Recipe-backed tool has no declarative recipe")
    payload = RecipeEngine().execute(recipe, frame)
    return {"kind": "Artifact", "recipe_id": recipe.get("recipe_id"), "data": payload}


def _flatten_numbers(payload: Any, prefix: str = "") -> dict[str, float]:
    """Collect numeric fields from nested artifacts without interpreting them."""
    numbers: dict[str, float] = {}
    if not isinstance(payload, dict):
        return numbers
    for key, value in payload.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            numbers[path] = float(value)
        elif isinstance(value, dict):
            numbers.update(_flatten_numbers(value, path))
    return numbers


def join(ctx: NodeExecution) -> dict[str, Any]:
    """Combine every artifact on a multi-input port into one auditable collection."""
    upstream = ctx.runtime.node_inputs(ctx.state, ctx.node.id, "items")
    for node in upstream:
        if not node.output:
            raise ValueError(f"Upstream node {node.id} has not run")
    return {
        "kind": "Artifact",
        "join": {
            "count": len(upstream),
            "sources": [node.id for node in upstream],
            "label": str(ctx.node.params.get("label") or ""),
        },
        "items": [copy.deepcopy(node.output) for node in upstream],
    }


def aggregate(ctx: NodeExecution) -> dict[str, Any]:
    """Summarize the numeric fields that the upstream artifacts share."""
    upstream = ctx.runtime.node_inputs(ctx.state, ctx.node.id, "items")
    payloads: list[dict[str, Any]] = []
    for node in upstream:
        if not node.output:
            raise ValueError(f"Upstream node {node.id} has not run")
        payloads.append(node.output)

    collected: dict[str, list[float]] = {}
    for payload in payloads:
        for key, value in _flatten_numbers(payload).items():
            collected.setdefault(key, []).append(value)

    return {
        "kind": "Artifact",
        "aggregate": {
            "count": len(payloads),
            "sources": [node.id for node in upstream],
            "group_key": str(ctx.node.params.get("group_key") or ""),
            "numeric": {
                key: {"count": len(values), "min": min(values), "max": max(values), "mean": sum(values) / len(values)}
                for key, values in sorted(collected.items())
            },
        },
    }


def quality_report(ctx: NodeExecution) -> dict[str, Any]:
    """Turn declared expectations about an upstream artifact into a QualityReport.

    No domain knowledge is involved: the node declares which keys must exist and
    optionally bounds one numeric metric. Declaring no check fails closed.
    """
    upstream = ctx.runtime.node_input(ctx.state, ctx.node.id, "data")
    if not upstream.output:
        raise ValueError(f"Upstream node {upstream.id} has not run")
    payload = upstream.output
    checks: list[dict[str, Any]] = []

    required = [str(key) for key in ctx.node.params.get("required_keys") or []]
    if required:
        missing = [key for key in required if key not in payload]
        checks.append({"check": "required_keys", "passed": not missing, "missing": missing})

    metric_key = str(ctx.node.params.get("metric_key") or "")
    if metric_key:
        value = payload.get(metric_key)
        minimum = ctx.node.params.get("minimum")
        maximum = ctx.node.params.get("maximum")
        numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
        within = numeric and (minimum is None or value >= minimum) and (maximum is None or value <= maximum)
        checks.append({
            "check": "metric_range",
            "metric": metric_key,
            "value": value,
            "minimum": minimum,
            "maximum": maximum,
            "passed": bool(within),
        })

    return {
        "kind": "QualityReport",
        "passed": bool(checks) and all(check["passed"] for check in checks),
        "checks": checks,
        "source_node_id": upstream.id,
        "source_kind": payload.get("kind"),
    }


def conditional_gate(ctx: NodeExecution) -> ExecutionOutcome:
    """Pass an artifact through only while its quality report passes.

    A failing report stops downstream work through the control-plane `stop` fact,
    so no executor evaluates `if domain == ...` to decide what may run.
    """
    data = ctx.runtime.node_input(ctx.state, ctx.node.id, "data")
    report = ctx.runtime.node_input(ctx.state, ctx.node.id, "report")
    if not data.output:
        raise ValueError(f"Upstream node {data.id} has not run")
    if not report.output:
        raise ValueError(f"Upstream node {report.id} has not run")

    passed = bool(report.output.get("passed"))
    decision = "continue" if passed else str(ctx.node.params.get("on_fail") or "stop")
    output = copy.deepcopy(data.output)
    output["gate"] = {
        "passed": passed,
        "decision": decision,
        "report_node_id": report.id,
        "prompt": str(ctx.node.params.get("prompt") or "Continue after this quality gate?"),
    }
    output["decision"] = decision
    return ExecutionOutcome(output=output, stop=decision == "stop")


def register_platform_executors(registry: ExecutorRegistry) -> None:
    registry.register("builtin:raw_file_import", raw_file_import)
    registry.register("builtin:normalize_columns", normalize_columns)
    registry.register("builtin:type_cast", type_cast)
    registry.register("builtin:skill_node", skill_node)
    registry.register("builtin:join", join)
    registry.register("builtin:aggregate", aggregate)
    registry.register("builtin:quality_report", quality_report)
    registry.register("builtin:conditional_gate", conditional_gate)
    registry.register_prefix("recipe:", declarative_recipe)

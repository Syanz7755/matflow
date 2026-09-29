"""Safe, two-stage node revision proposals and deterministic edge migration."""
from __future__ import annotations

import copy
import re
import uuid
from typing import Any

from .contracts import Edge, Node, ToolSpec
from .tool_registry import ToolRegistry


def _derived_tool_id(tool_id: str, node_id: str) -> str:
    suffix = re.sub(r"[^a-z0-9_]+", "_", node_id.lower()).strip("_")[:24] or "node"
    return f"{tool_id}_{suffix}_{uuid.uuid4().hex[:6]}"[:64]


def _ports(payload: Any, fallback: dict[str, str], registry: ToolRegistry) -> dict[str, str]:
    if payload is None: return copy.deepcopy(fallback)
    if not isinstance(payload, dict): raise ValueError("Model-proposed ports must be a JSON object")
    registry.type_registry.validate_port_types(payload.values())
    return {str(name): str(kind) for name, kind in payload.items()}


def _edge_plan(edge: Edge, node: Node, original: ToolSpec, proposed: ToolSpec, state_nodes: list[Node], registry: ToolRegistry) -> dict[str, Any]:
    incoming = edge.target == node.id
    old_port = edge.target_port if incoming else edge.source_port
    old_ports = original.inputs if incoming else original.outputs
    new_ports = proposed.inputs if incoming else proposed.outputs
    old_type = old_ports.get(old_port)
    peer_id = edge.source if incoming else edge.target
    peer = next(item for item in state_nodes if item.id == peer_id)
    peer_spec = registry.get(peer.type)
    peer_port = edge.source_port if incoming else edge.target_port
    peer_inputs, peer_outputs = registry.type_registry.resolve_ports(peer_spec, peer)
    peer_type = peer_outputs.get(peer_port) if incoming else peer_inputs.get(peer_port)
    compatible = (
        (lambda kind: registry.type_registry.can_flow(peer_type, kind))
        if incoming else
        (lambda kind: registry.type_registry.can_flow(kind, peer_type))
    )
    candidates = [name for name, kind in new_ports.items() if peer_type and compatible(kind)]
    if old_port in new_ports and peer_type and compatible(new_ports[old_port]):
        status, mapped = "exact", old_port
    elif len(candidates) == 1:
        status, mapped = "suggested", candidates[0]
    else:
        status, mapped = "unresolved", None
    return {
        "edge_id": edge.id,
        "direction": "incoming" if incoming else "outgoing",
        "old_port": old_port,
        "data_type": old_type,
        "peer": {"node_id": peer_id, "port": peer_port, "data_type": peer_type},
        "status": status,
        "suggested_port": mapped,
        "candidates": candidates,
    }


def build_revision_proposal(*, state, registry: ToolRegistry, node_id: str, prompt: str, provider_id: str, model: str, model_payload: dict[str, Any]) -> dict[str, Any]:
    node = next((item for item in state.nodes if item.id == node_id), None)
    if node is None: raise ValueError(f"Unknown node: {node_id}")
    original = registry.get(node.type)
    generated_code = model_payload.get("generated_code")
    inputs = _ports(model_payload.get("inputs"), original.inputs, registry)
    outputs = _ports(model_payload.get("outputs"), original.outputs, registry)
    ports_changed = inputs != original.inputs or outputs != original.outputs
    requires_code_review = bool(generated_code) or ports_changed
    tool_id = _derived_tool_id(original.tool_id, node.id)
    proposed = ToolSpec(
        tool_id=tool_id,
        version="1.0.0",
        label=str(model_payload.get("label") or node.label or original.label)[:120],
        category=str(model_payload.get("category") or original.category)[:80],
        description=str(model_payload.get("description") or original.description)[:1000],
        inputs=inputs,
        outputs=outputs,
        params={**copy.deepcopy(original.params), **(model_payload.get("params") or {})},
        input_schema=model_payload.get("input_schema") or original.input_schema,
        output_schema=model_payload.get("output_schema") or original.output_schema,
        parameter_schema=model_payload.get("parameter_schema") or original.parameter_schema,
        executor_ref=None if requires_code_review else original.executor_ref,
        risk_level=model_payload.get("risk_level") or original.risk_level,
        status="draft",
        provenance={"kind": "generated"},
        parent_tool_id=original.tool_id,
        parent_version=original.version,
        preview_spec=model_payload.get("preview_spec") or original.preview_spec.model_dump(),
        generated_code_status="draft" if generated_code else "none",
    )
    incident = [edge for edge in state.edges if edge.source == node.id or edge.target == node.id]
    proposal_id = str(uuid.uuid4())
    return {
        "proposal_id": proposal_id,
        "status": "proposed",
        "base_graph_version": state.version,
        "node_id": node.id,
        "prompt": prompt,
        "provider_id": provider_id,
        "model": model,
        "original_tool": original.model_dump(),
        "proposed_tool": proposed.model_dump(),
        "parameter_migration": {key: node.params.get(key, value) for key, value in proposed.params.items()},
        "edge_plan": [_edge_plan(edge, node, original, proposed, state.nodes, registry) for edge in incident],
        "generated_code": generated_code,
        "requires_code_review": requires_code_review,
        "risk_findings": (["Port changes require an executor and code review before this proposal can be applied."] if ports_changed else []) + (["Generated code is stored as a draft and is never executed automatically."] if generated_code else []),
    }


def reconnect_edges(proposal: dict[str, Any], state, decisions: dict[str, str | None]) -> list[Edge]:
    by_id = {edge.id: edge for edge in state.edges}
    result: list[Edge] = []
    for plan in proposal["edge_plan"]:
        edge = by_id.get(plan["edge_id"])
        if edge is None: raise ValueError(f"Incident edge changed since proposal: {plan['edge_id']}")
        port = plan["suggested_port"] if plan["status"] == "exact" else decisions.get(edge.id)
        if port is None:
            if edge.id not in decisions:
                raise ValueError(f"Edge {edge.id} needs an explicit reconnect or drop decision")
            continue
        if port not in plan["candidates"] and port != plan["suggested_port"]:
            raise ValueError(f"Invalid replacement port for edge {edge.id}: {port}")
        payload = edge.model_dump()
        payload["target_port" if plan["direction"] == "incoming" else "source_port"] = port
        result.append(Edge.model_validate(payload))
    return result

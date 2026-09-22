"""Graph mutation validation behind one seam shared by HTTP and agent callers."""
from __future__ import annotations

import copy

from .contracts import GraphPatch, GraphState, Node
from .tool_registry import ToolRegistry


def node_by_id(state: GraphState, node_id: str) -> Node:
    for node in state.nodes:
        if node.id == node_id:
            return node
    raise ValueError(f"Unknown node: {node_id}")


class GraphValidator:
    """Validate graph patches without mutating the caller's graph state."""

    def validate(self, state: GraphState, patch: GraphPatch, registry: ToolRegistry) -> None:
        if patch.base_version != state.version:
            raise ValueError(f"Version conflict: patch is based on v{patch.base_version}, current graph is v{state.version}")
        scratch = copy.deepcopy(state)
        active = registry.active()
        for operation in patch.operations:
            if operation.op == "add_node":
                node = operation.node
                if node is None or node.type not in active:
                    raise ValueError(f"Unknown registry node: {node.type if node else 'missing'}")
                if any(existing.id == node.id for existing in scratch.nodes):
                    raise ValueError(f"Duplicate node id: {node.id}")
                scratch.nodes.append(node)
            elif operation.op == "update_node":
                node = node_by_id(scratch, operation.node_id or "")
                allowed = active[node.type].params
                invalid = set(operation.params or {}) - set(allowed)
                if invalid:
                    raise ValueError(f"Unsupported parameter(s) for {node.type}: {', '.join(sorted(invalid))}")
                node.params.update(operation.params or {})
            elif operation.op == "delete_node":
                node_id = operation.node_id or ""
                node_by_id(scratch, node_id)
                scratch.nodes = [node for node in scratch.nodes if node.id != node_id]
                scratch.edges = [edge for edge in scratch.edges if edge.source != node_id and edge.target != node_id]
            elif operation.op == "connect":
                edge = operation.edge
                if edge is None:
                    raise ValueError("connect requires edge")
                source = node_by_id(scratch, edge.source)
                target = node_by_id(scratch, edge.target)
                source_type = active[source.type].outputs.get(edge.source_port)
                target_type = active[target.type].inputs.get(edge.target_port)
                if not source_type or not target_type:
                    raise ValueError("Unknown port in edge")
                if source_type != target_type:
                    raise ValueError(f"Type mismatch: {source_type} cannot connect to {target_type}")
                if any(existing.id == edge.id for existing in scratch.edges):
                    raise ValueError(f"Duplicate edge id: {edge.id}")
                scratch.edges.append(edge)
            elif operation.op == "disconnect":
                edge_id = operation.edge_id or ""
                if not any(edge.id == edge_id for edge in scratch.edges):
                    raise ValueError(f"Unknown edge: {edge_id}")

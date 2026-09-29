"""Graph mutation validation behind one seam shared by HTTP and agent callers."""
from __future__ import annotations

import copy

from .contracts import GraphPatch, GraphState, Node, ReviewPolicy
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
                invalid = set(node.params) - set(active[node.type].params)
                if invalid:
                    raise ValueError(f"Unsupported parameter(s) for {node.type}: {', '.join(sorted(invalid))}")
                scratch.nodes.append(node)
            elif operation.op == "update_node":
                node = node_by_id(scratch, operation.node_id or "")
                allowed = active[node.type].params
                invalid = set(operation.params or {}) - set(allowed)
                if invalid:
                    raise ValueError(f"Unsupported parameter(s) for {node.type}: {', '.join(sorted(invalid))}")
                node.params.update(operation.params or {})
                changes = operation.changes or {}
                unsupported = set(changes) - {"label", "position", "review_policy"}
                if unsupported:
                    raise ValueError(f"Unsupported node change(s): {', '.join(sorted(unsupported))}")
                if "label" in changes:
                    label = changes["label"]
                    if label is not None and (not isinstance(label, str) or not label.strip() or len(label) > 120):
                        raise ValueError("Node label must be 1 to 120 characters")
                    node.label = label.strip() if isinstance(label, str) else None
                if "position" in changes:
                    position = changes["position"]
                    if not isinstance(position, dict) or set(position) != {"x", "y"}:
                        raise ValueError("Node position must contain numeric x and y values")
                    try:
                        node.position = {"x": float(position["x"]), "y": float(position["y"])}
                    except (TypeError, ValueError) as exc:
                        raise ValueError("Node position must contain numeric x and y values") from exc
                if "review_policy" in changes:
                    node.review_policy = ReviewPolicy.model_validate(changes["review_policy"])
            elif operation.op == "delete_node":
                node_id = operation.node_id or ""
                node_by_id(scratch, node_id)
                scratch.nodes = [node for node in scratch.nodes if node.id != node_id]
                scratch.edges = [edge for edge in scratch.edges if edge.source != node_id and edge.target != node_id]
            elif operation.op == "connect":
                edge = operation.edge
                if edge is None:
                    raise ValueError("connect requires edge")
                if any(existing.id == edge.id for existing in scratch.edges):
                    raise ValueError(f"Duplicate edge id: {edge.id}")
                scratch.edges.append(edge)
            elif operation.op == "disconnect":
                edge_id = operation.edge_id or ""
                if not any(edge.id == edge_id for edge in scratch.edges):
                    raise ValueError(f"Unknown edge: {edge_id}")
                scratch.edges = [edge for edge in scratch.edges if edge.id != edge_id]
            elif operation.op == "replace_node_revision":
                node_id = operation.node_id or ""
                node_by_id(scratch, node_id)
                replacement = operation.replacement_node
                if replacement is None or replacement.id != node_id or replacement.type not in active:
                    raise ValueError("Replacement node must keep the node id and reference an active tool")
                allowed = active[replacement.type].params
                invalid = set(replacement.params) - set(allowed)
                if invalid:
                    raise ValueError(f"Unsupported replacement parameter(s): {', '.join(sorted(invalid))}")
                scratch.nodes = [replacement if node.id == node_id else node for node in scratch.nodes]
                scratch.edges = [edge for edge in scratch.edges if edge.source != node_id and edge.target != node_id]
                scratch.edges.extend(operation.reconnect_edges or [])

        self.validate_state(scratch, registry)

    def validate_state(self, state: GraphState, registry: ToolRegistry) -> None:
        """Validate a complete graph through the same interface used for patches."""
        active = registry.active()
        node_ids: set[str] = set()
        for node in state.nodes:
            if node.id in node_ids:
                raise ValueError(f"Duplicate node id: {node.id}")
            node_ids.add(node.id)
            if node.type not in active:
                raise ValueError(f"Unknown registry node: {node.type}")
            invalid = set(node.params) - set(active[node.type].params)
            if invalid:
                raise ValueError(f"Unsupported parameter(s) for {node.type}: {', '.join(sorted(invalid))}")
            registry.type_registry.resolve_ports(active[node.type], node)

        edge_ids: set[str] = set()
        occupied_inputs: set[tuple[str, str]] = set()
        adjacency = {node.id: [] for node in state.nodes}
        for edge in state.edges:
            if edge.id in edge_ids:
                raise ValueError(f"Duplicate edge id: {edge.id}")
            edge_ids.add(edge.id)
            source = node_by_id(state, edge.source)
            target = node_by_id(state, edge.target)
            source_outputs = registry.type_registry.resolve_ports(active[source.type], source)[1]
            target_inputs = registry.type_registry.resolve_ports(active[target.type], target)[0]
            source_type = source_outputs.get(edge.source_port)
            target_type = target_inputs.get(edge.target_port)
            if not source_type or not target_type:
                raise ValueError("Unknown port in edge")
            if not registry.type_registry.can_flow(source_type, target_type):
                raise ValueError(f"Type mismatch: {source_type} cannot connect to {target_type}")
            input_key = (edge.target, edge.target_port)
            if input_key in occupied_inputs:
                raise ValueError(f"Input port already connected: {edge.target}.{edge.target_port}")
            occupied_inputs.add(input_key)
            adjacency[edge.source].append(edge.target)

        visiting: set[str] = set()
        visited: set[str] = set()

        def has_cycle(node_id: str) -> bool:
            if node_id in visiting:
                return True
            if node_id in visited:
                return False
            visiting.add(node_id)
            if any(has_cycle(target_id) for target_id in adjacency[node_id]):
                return True
            visiting.remove(node_id)
            visited.add(node_id)
            return False

        if any(has_cycle(node_id) for node_id in adjacency):
            raise ValueError("Graph must be acyclic")

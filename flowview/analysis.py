"""Derived views over the mirror model: phase folding, topological order, graph layers.

Pure standard library and pure functions: no printing, no file access, no backend import.
Renderers must not re-implement this logic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from .codes import FlowCycleError
from .model import (
    FlowDocument,
    FlowEdge,
    FlowEvent,
    FlowGraph,
    FlowIssue,
    FlowNode,
    FlowPhase,
    FlowStep,
    FlowTrace,
    NodeStatus,
    StepStatus,
)

# Worst-first precedence. `unknown` ranks with `pending` because "we were not told" must
# never look like success.
_STATUS_RANK: Mapping[StepStatus, int] = {
    "error": 6,
    "running": 5,
    "waiting": 4,
    "completed": 3,
    "skipped": 2,
    "pending": 1,
    "unknown": 1,
}

_NODE_STATUS_ORDER: Mapping[str, int] = {
    "error": 0,
    "waiting": 1,
    "running": 2,
    "ready": 3,
    "cancelled": 4,
    "completed": 5,
    "unknown": 6,
}


def phase_status(phase: FlowPhase) -> StepStatus:
    """Fold the statuses of a phase's steps into one status for the phase."""
    if phase.error:
        return "error"
    if not phase.steps:
        return "pending"
    worst: StepStatus = "pending"
    for step in phase.steps:
        if _STATUS_RANK.get(step.status, 1) > _STATUS_RANK.get(worst, 1):
            worst = step.status
    return worst


def summarize_steps(steps: Sequence[FlowStep]) -> Mapping[str, int]:
    """Count steps per status, including zero counts for every status."""
    counts = {status: 0 for status in ("pending", "running", "completed", "waiting", "error", "skipped", "unknown")}
    for step in steps:
        counts[step.status] = counts.get(step.status, 0) + 1
    return counts


@dataclass(frozen=True, slots=True)
class TraceSummary:
    """A renderer-friendly digest of one recorded trace."""

    task_id: str | None
    trace_id: str | None
    total_events: int
    counts: Mapping[str, int]
    failed: tuple[FlowEvent, ...]
    phases: tuple[FlowPhase, ...]
    first_index: int | None
    last_index: int | None

    @property
    def ok(self) -> bool:
        return not self.failed


def summarize_trace(trace: FlowTrace) -> TraceSummary:
    """Digest a trace into counts, failures and its derived phase list."""
    events = trace.ordered_events
    counts = {status: 0 for status in ("pending", "running", "completed", "waiting", "error", "skipped", "unknown")}
    for event in events:
        counts[event.status] = counts.get(event.status, 0) + 1
    return TraceSummary(
        task_id=trace.task_id,
        trace_id=trace.trace_id,
        total_events=len(events),
        counts=counts,
        failed=trace.failed_events,
        phases=derive_phases(trace),
        first_index=events[0].index if events else None,
        last_index=events[-1].index if events else None,
    )


def derive_phases(trace: FlowTrace) -> tuple[FlowPhase, ...]:
    """Group a trace's events into phases, preserving the recorded phase order.

    A trace that carries explicit phases keeps them, with missing steps filled in from the
    events. Phase ids that appear only in events are appended rather than dropped.
    """
    explicit = {phase.name: phase for phase in trace.phases}
    order: list[str] = [phase.name for phase in trace.phases]
    grouped: dict[str, list[FlowEvent]] = {name: [] for name in order}
    for event in trace.ordered_events:
        if event.phase not in grouped:
            grouped[event.phase] = []
            order.append(event.phase)
        grouped[event.phase].append(event)

    phases: list[FlowPhase] = []
    for name in order:
        events = grouped.get(name, [])
        declared = explicit.get(name)
        steps: list[FlowStep] = []
        declared_names: set[str] = set()
        if declared is not None:
            for index, step in enumerate(declared.steps):
                matching = events[index] if index < len(events) else None
                if matching is not None:
                    declared_names.add(matching.name)
                    steps.append(
                        FlowStep(
                            name=step.name,
                            status=matching.status,
                            detail=matching.detail or step.detail,
                            error=matching.error or step.error,
                            node_id=matching.node_id or step.node_id,
                            tools=tuple(dict.fromkeys((*step.tools, *([matching.tool_id] if matching.tool_id else [])))),
                        )
                    )
                else:
                    steps.append(step)
            extra = events[len(declared.steps):]
        else:
            extra = events
        for event in extra:
            if event.name in declared_names:
                continue
            steps.append(
                FlowStep(
                    name=event.name,
                    status=event.status,
                    detail=event.detail,
                    error=event.error,
                    node_id=event.node_id,
                    tools=(event.tool_id,) if event.tool_id else (),
                )
            )
        phases.append(
            FlowPhase(
                name=name,
                title=declared.title if declared is not None else name,
                steps=tuple(steps),
                error=declared.error if declared is not None else None,
            )
        )
    return tuple(phases)


def graph_phases(graph: FlowGraph) -> tuple[FlowPhase, ...]:
    """Structural phases for a graph with no recorded runtime trace.

    This is what lets ``flowview graph`` show a flow even when the workspace has never run.
    """
    issues_by_node: dict[str, list[str]] = {}
    for node in graph.nodes:
        for issue in node.issues:
            issues_by_node.setdefault(node.id, []).append(f"{issue.code}: {issue.message}")

    nodes = sorted(graph.nodes, key=lambda node: (_NODE_STATUS_ORDER.get(node.status, 9), node.id))
    steps = tuple(
        FlowStep(
            name=node.display,
            status=_node_status_to_step(node.status),
            detail=f"{node.registry_id} v{node.tool_version or '?'} [{node.status}]",
            error=node.error or ("; ".join(issues_by_node.get(node.id, ())) or None),
            node_id=node.id,
            tools=(node.registry_id,),
        )
        for node in nodes
    )
    truncated = ", ".join(graph.truncated) if graph.truncated else None
    topology_error = None
    try:
        layers = graph_layers(graph)
        topology_detail = f"{len(graph.nodes)} node(s) in {len(layers)} layer(s); {len(graph.edges)} edge(s)"
    except FlowCycleError as exc:
        topology_detail = "cycle detected; no valid topological order"
        topology_error = exc.issue.message
    if graph.nodes:
        nodes_phase = FlowPhase(name="nodes", title="Nodes (structural)", steps=steps)
        graph_step_status: StepStatus = "completed"
    else:
        # An empty workspace is a healthy, never-used state, not a failure: it must not raise
        # the document's error count, or `flowview graph` would exit 3 on a clean install.
        nodes_phase = FlowPhase(
            name="nodes",
            title="Nodes (structural)",
            steps=(
                FlowStep(
                    name="(no nodes declared)",
                    status="pending",
                    detail="The workspace graph has no nodes yet, so there is nothing to draw.",
                ),
            ),
        )
        graph_step_status = "waiting"
    phases = (
        FlowPhase(
            name="graph",
            title="Workspace graph",
            steps=(
                FlowStep(
                    name=f"{graph.graph_id} @ v{graph.version}",
                    status=graph_step_status,
                    detail=f"source: {graph.source or '(unspecified)'}",
                ),
            ),
        ),
        FlowPhase(
            name="topology",
            title="Topology (structural, not a run)",
            steps=(FlowStep(name="topological order", status="error" if topology_error else "completed", detail=topology_detail, error=topology_error),),
        ),
        nodes_phase,
    )
    if truncated:
        phases = phases + (
            FlowPhase(name="caps", title="Truncation", steps=(FlowStep(name="caps applied", status="waiting", detail=truncated),)),
        )
    return phases


def _node_status_to_step(status: NodeStatus) -> StepStatus:
    mapping: Mapping[str, StepStatus] = {
        "ready": "pending",
        "running": "running",
        "completed": "completed",
        "waiting": "waiting",
        "error": "error",
        "cancelled": "skipped",
        "unknown": "unknown",
    }
    return mapping.get(status, "unknown")


def build_document(
    *,
    title: str,
    source: str,
    graph: FlowGraph | None = None,
    trace: FlowTrace | None = None,
    phases: Sequence[FlowPhase] = (),
    issues: Sequence[FlowIssue] = (),
    modes: Sequence[str] = (),
    meta: Mapping[str, str] | None = None,
) -> FlowDocument:
    """Assemble a document and pick its canonical phase checkout.

    Precedence: explicitly supplied phases, then a trace's phases, then a graph's structural
    phases. Issues from every part are merged so the CLI can report one list.
    """
    if not phases:
        if trace is not None and (trace.events or trace.phases):
            phases = derive_phases(trace)
        elif graph is not None:
            phases = graph_phases(graph)
    truncated: list[str] = []
    if graph is not None:
        truncated.extend(graph.truncated)
    collected: list[FlowIssue] = list(issues)
    if graph is not None:
        collected.extend(graph.issues)
        for node in graph.nodes:
            collected.extend(node.issues)
    if trace is not None:
        collected.extend(trace.issues)
    document_meta = dict(meta or {})
    if modes:
        document_meta.setdefault("modes", ",".join(modes))
    if graph is not None:
        document_meta.setdefault("graph_version", str(graph.version))
        document_meta.setdefault("node_count", str(len(graph.nodes)))
        document_meta.setdefault("edge_count", str(len(graph.edges)))
    if trace is not None:
        if trace.task_id:
            document_meta.setdefault("task_id", trace.task_id)
        if trace.trace_id:
            document_meta.setdefault("trace_id", trace.trace_id)
        document_meta.setdefault("event_count", str(len(trace.events)))
    return FlowDocument(
        title=title,
        source=source,
        graph=graph,
        trace=trace,
        phases=tuple(phases),
        issues=tuple(dedupe_issues(collected)),
        meta=document_meta,
        truncated=tuple(dict.fromkeys(truncated)),
    )


def dedupe_issues(issues: Iterable[FlowIssue]) -> list[FlowIssue]:
    """Drop repeated findings, keyed by severity, code and location."""
    seen: set[tuple[str, str, str | None]] = set()
    unique: list[FlowIssue] = []
    for issue in issues:
        key = (issue.severity, issue.code, issue.where)
        if key in seen:
            continue
        seen.add(key)
        unique.append(issue)
    return unique


def collect_issues(document: FlowDocument) -> tuple[FlowIssue, ...]:
    """Every distinct issue on a document, its graph (and nodes) and its trace.

    Deduplication matters because a document assembled by :func:`build_document` already contains
    its parts' issues; without this, a reader would see the same problem twice.
    """
    collected: list[FlowIssue] = list(document.issues)
    if document.graph is not None:
        collected.extend(document.graph.issues)
        for node in document.graph.nodes:
            collected.extend(node.issues)
    if document.trace is not None:
        collected.extend(document.trace.issues)
    return tuple(dedupe_issues(collected))


def adjacent_nodes(graph: FlowGraph) -> Mapping[str, tuple[str, ...]]:
    """Successor map; edges pointing at unknown nodes are ignored."""
    known = set(graph.node_ids)
    successors: dict[str, list[str]] = {node_id: [] for node_id in known}
    for edge in graph.sorted_edges:
        if edge.source in known and edge.target in known:
            successors[edge.source].append(edge.target)
    return {node_id: tuple(targets) for node_id, targets in successors.items()}


def find_cycles(graph: FlowGraph) -> tuple[tuple[str, ...], ...]:
    """Every distinct cycle in the graph. Never raises, even for a self-loop.

    The walk is iterative on purpose: a recursive depth-first search overflows the interpreter
    stack on a long chain (a few thousand nodes), and "the graph is too big to inspect" is not an
    acceptable failure for a read-only printer.
    """
    successors = adjacent_nodes(graph)
    # Iterative colouring DFS: 0 = unvisited, 1 = on the current path, 2 = finished.
    state: dict[str, int] = {node_id: 0 for node_id in successors}
    cycles: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()

    for start in sorted(successors):
        if state.get(start, 0) != 0:
            continue
        stack: list[tuple[str, int]] = [(start, 0)]
        path: list[str] = []
        while stack:
            node_id, child_index = stack[-1]
            if child_index == 0:
                state[node_id] = 1
                path.append(node_id)
            children = successors.get(node_id, ())
            advanced = False
            while child_index < len(children):
                target = children[child_index]
                child_index += 1
                child_state = state.get(target, 2)
                if child_state == 1:
                    marker = path.index(target)
                    cycle = tuple(path[marker:])
                    key = tuple(sorted(cycle))
                    if key not in seen:
                        seen.add(key)
                        cycles.append(cycle + (target,))
                    continue
                if child_state == 0:
                    stack[-1] = (node_id, child_index)
                    stack.append((target, 0))
                    advanced = True
                    break
            if advanced:
                continue
            stack.pop()
            if path and path[-1] == node_id:
                path.pop()
            state[node_id] = 2
    return tuple(cycles)


def topological_order(graph: FlowGraph) -> tuple[str, ...]:
    """Deterministic Kahn order; raises :class:`FlowCycleError` when the graph is cyclic."""
    successors = adjacent_nodes(graph)
    indegree = {node_id: 0 for node_id in successors}
    for node_id in successors:
        for target in successors[node_id]:
            indegree[target] += 1
    ready = sorted(node_id for node_id, degree in indegree.items() if degree == 0)
    order: list[str] = []
    while ready:
        current = ready.pop(0)
        order.append(current)
        for target in successors.get(current, ()):
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
        ready.sort()
    if len(order) != len(successors):
        raise FlowCycleError(find_cycles(graph), where=graph.source or None)
    return tuple(order)


def graph_layers(graph: FlowGraph) -> tuple[tuple[FlowNode, ...], ...]:
    """Nodes grouped into dependency layers, each layer sorted by node id.

    A layer is computed inside the original declaration order so the printer stays
    deterministic; the graph is simplified step by step, which is what makes a partially
    broken graph (dangling edge) still printable.
    """
    order = topological_order(graph)  # validates acyclicity
    depth: dict[str, int] = {node_id: 0 for node_id in order}
    successors = adjacent_nodes(graph)
    for node_id in order:
        for target in successors.get(node_id, ()):
            depth[target] = max(depth.get(target, 0), depth.get(node_id, 0) + 1)
    if not depth:
        return ()
    max_depth = max(depth.values())
    layers: list[tuple[FlowNode, ...]] = []
    for level in range(max_depth + 1):
        members = tuple(
            node for node in graph.nodes if depth.get(node.id) == level
        )
        layers.append(members)
    return tuple(layer for layer in layers if layer)


def focus_subgraph(graph: FlowGraph, node_ids: Iterable[str], *, radius: int = 1) -> FlowGraph:
    """A graph restricted to the given nodes plus neighbours within ``radius`` hops."""
    known = set(graph.node_ids)
    keep = {node_id for node_id in node_ids if node_id in known}
    missing = [node_id for node_id in node_ids if node_id not in known]
    issues = list(graph.issues)
    for node_id in missing:
        issues.append(
            FlowIssue(
                severity="warning",
                code="focus.unknown_node",
                message=f"Focus node is not in the graph: {node_id}",
                where=graph.source or None,
            )
        )
    frontier = set(keep)
    for _ in range(max(0, radius)):
        next_frontier: set[str] = set()
        for edge in graph.edges:
            if edge.source in frontier and edge.target in known:
                next_frontier.add(edge.target)
            if edge.target in frontier and edge.source in known:
                next_frontier.add(edge.source)
        next_frontier -= keep
        keep |= next_frontier
        frontier = next_frontier
        if not frontier:
            break
    nodes = tuple(node for node in graph.nodes if node.id in keep)
    edges = tuple(
        edge for edge in graph.edges if edge.source in keep and edge.target in keep
    )
    return FlowGraph(
        graph_id=graph.graph_id,
        version=graph.version,
        nodes=nodes,
        edges=edges,
        source=graph.source,
        issues=tuple(issues),
        truncated=graph.truncated,
    )


def filter_graph(
    graph: FlowGraph,
    *,
    statuses: Sequence[str] = (),
    tool_ids: Sequence[str] = (),
    search: str | None = None,
) -> FlowGraph:
    """Filter nodes by status, registry id or free text, keeping matching edges only."""
    wanted_statuses = {status.strip().lower() for status in statuses if status.strip()}
    wanted_tools = {tool.strip().lower() for tool in tool_ids if tool.strip()}
    needle = (search or "").strip().lower()

    def keep(node: FlowNode) -> bool:
        if wanted_statuses and node.status not in wanted_statuses:
            return False
        if wanted_tools and node.registry_id.lower() not in wanted_tools and (node.category or "").lower() not in wanted_tools:
            return False
        if needle:
            haystack = " ".join(
                filter(None, (node.id, node.label, node.registry_id, node.category, node.error))
            ).lower()
            if needle not in haystack:
                return False
        return True

    nodes = tuple(node for node in graph.nodes if keep(node))
    keep_ids = {node.id for node in nodes}
    edges = tuple(edge for edge in graph.edges if edge.source in keep_ids and edge.target in keep_ids)
    dropped = len(graph.nodes) - len(nodes)
    issues = list(graph.issues)
    if dropped:
        issues.append(
            FlowIssue(
                severity="info",
                code="filter.applied",
                message=f"Filter hid {dropped} of {len(graph.nodes)} node(s).",
                hint="Re-run without filter options to see the whole graph.",
            )
        )
    return FlowGraph(
        graph_id=graph.graph_id,
        version=graph.version,
        nodes=nodes,
        edges=edges,
        source=graph.source,
        issues=tuple(issues),
        truncated=graph.truncated,
    )


def edge_health(graph: FlowGraph) -> tuple[FlowIssue, ...]:
    """Offline consistency findings a source may not have flagged itself."""
    issues: list[FlowIssue] = []
    known = set(graph.node_ids)
    occupied: dict[tuple[str, str], int] = {}
    seen_ids: set[str] = set()
    seen_nodes: set[str] = set()
    cycles = find_cycles(graph)
    if cycles:
        rendered = "; ".join(" -> ".join(cycle) for cycle in cycles[:3])
        more = "" if len(cycles) <= 3 else f" (+{len(cycles) - 3} more)"
        issues.append(
            FlowIssue(
                severity="warning",
                code="graph.cycle",
                message=f"The graph is not acyclic: {rendered}{more}",
                where=graph.source or None,
                hint="A cyclic graph has no valid topological order, so it cannot be executed as a DAG.",
            )
        )
    for node in graph.nodes:
        if node.id in seen_nodes:
            issues.append(
                FlowIssue(
                    severity="error",
                    code="graph.duplicate_node",
                    message=f"Duplicate node id: {node.id}",
                    where=graph.source or None,
                    hint="Repair the graph with apply_graph_patch, then re-run flowview graph.",
                )
            )
        seen_nodes.add(node.id)
    for edge in graph.sorted_edges:
        if edge.id in seen_ids:
            issues.append(
                FlowIssue(
                    severity="warning",
                    code="graph.duplicate_edge",
                    message=f"Duplicate edge id: {edge.id}",
                    where=graph.source or None,
                )
            )
        seen_ids.add(edge.id)
        if edge.source not in known or edge.target not in known:
            issues.append(
                FlowIssue(
                    severity="warning",
                    code="graph.dangling_edge",
                    message=f"Edge {edge.id} points outside the graph: {edge.source} -> {edge.target}",
                    where=graph.source or None,
                    hint="The graph and its edges were recorded at different times.",
                )
            )
        key = (edge.target, edge.target_port or "")
        occupied[key] = occupied.get(key, 0) + 1
        if occupied[key] > 1:
            issues.append(
                FlowIssue(
                    severity="warning",
                    code="graph.multiple_edges_into_port",
                    message=f"Input port {edge.target}.{edge.target_port or '?'} has {occupied[key]} incoming edges",
                    where=graph.source or None,
                    hint="Only ports declared multi_input accept more than one edge.",
                )
            )
    return tuple(issues)


def min_width_floor() -> int:
    """The narrowest text width FlowView can render readably.

    Kept as a lazy lookup into ``cli`` so there is exactly one definition of the floor; the
    dependency direction (analysis -> cli) is only touched at call time, never at import time.
    """
    from .cli import MIN_WIDTH

    return MIN_WIDTH


def status_legend() -> tuple[tuple[str, str], ...]:
    """The vocabulary a reader needs, printed by every text rendering."""
    return (
        ("ready", "declared, never run"),
        ("running", "execution in progress"),
        ("completed", "finished successfully"),
        ("waiting", "paused for a human decision"),
        ("error", "stopped with an error"),
        ("cancelled", "stopped by a gate or reviewer"),
        ("unknown", "source did not say (never treated as success)"),
    )


@dataclass(frozen=True, slots=True)
class GraphStats:
    """Small structural summary used by text and JSON output."""

    nodes: int = 0
    edges: int = 0
    by_status: Mapping[str, int] = field(default_factory=dict)
    layers: int | None = None
    depth_known: bool = False
    cycles: tuple[tuple[str, ...], ...] = ()
    dangling_edges: int = 0
    known_tools: int = 0
    unknown_tools: int = 0


def graph_stats(graph: FlowGraph) -> GraphStats:
    """Compute a structural summary without ever raising on a broken graph."""
    by_status: dict[str, int] = {}
    for node in graph.nodes:
        by_status[node.status] = by_status.get(node.status, 0) + 1
    cycles = find_cycles(graph)
    layers: int | None = None
    try:
        layers = len(graph_layers(graph))
    except FlowCycleError:
        layers = None
    known = set(graph.node_ids)
    dangling = sum(1 for edge in graph.edges if edge.dangling or edge.source not in known or edge.target not in known)
    return GraphStats(
        nodes=len(graph.nodes),
        edges=len(graph.edges),
        by_status=by_status,
        layers=layers,
        depth_known=layers is not None,
        cycles=cycles,
        dangling_edges=dangling,
        known_tools=sum(1 for node in graph.nodes if node.known_tool is True),
        unknown_tools=sum(1 for node in graph.nodes if node.known_tool is False),
    )


def status_line(document: FlowDocument) -> str:
    """One-line document digest shared by the CLI banners and ``doctor``."""
    parts = [f"source={document.source or '(none)'}", f"title={document.title}"]
    if document.graph is not None:
        stats = graph_stats(document.graph)
        parts.append(f"graph v{document.graph.version}")
        parts.append(f"nodes={stats.nodes}")
        parts.append(f"edges={stats.edges}")
        if stats.layers is not None:
            parts.append(f"layers={stats.layers}")
    if document.trace is not None:
        summary = summarize_trace(document.trace)
        parts.append(f"events={summary.total_events}")
        if summary.failed:
            parts.append(f"failed={len(summary.failed)}")
    parts.append(f"phases={len(document.phases)}")
    parts.append(f"errors={document.error_count}")
    parts.append(f"warnings={document.warning_count}")
    return " ".join(parts)


def node_sort_key(node: FlowNode) -> tuple[int, str]:
    """Stable display order: problem nodes first, then by id."""
    return (_NODE_STATUS_ORDER.get(node.status, 9), node.id)


def events_by_phase(trace: FlowTrace) -> Mapping[str, tuple[FlowEvent, ...]]:
    """Events grouped by phase name, keeping recorded order."""
    grouped: dict[str, list[FlowEvent]] = {}
    for event in trace.ordered_events:
        grouped.setdefault(event.phase, []).append(event)
    return {name: tuple(items) for name, items in grouped.items()}


def expected_exit_code(document: FlowDocument) -> int:
    """The exit code this document implies: 3 for a diagnosed failure, else 0.

    FlowView keeps ``--strict`` out of this value on purpose: the hint describes the *data*, and a
    consumer can apply its own policy to warnings.

    A document may also carry ``meta["exit_code"]``, which wins: error documents built for a usage
    error (exit 2) must not tell a consumer to expect 3, or the hint contradicts the process it
    describes.
    """
    from .codes import EXIT_OK, EXIT_SOURCE

    declared = document.meta.get("exit_code")
    if isinstance(declared, str):
        try:
            return int(declared)
        except ValueError:
            pass
    return EXIT_SOURCE if document.error_count else EXIT_OK


def document_payload(document: FlowDocument) -> dict[str, Any]:
    """The JSON contract emitted by ``--format json``: document plus derived sections."""
    stats = graph_stats(document.graph) if document.graph is not None else None
    summary = summarize_trace(document.trace) if document.trace is not None else None
    payload: dict[str, Any] = {
        "flowview_schema": "1.0",
        "document": document.to_dict(),
        "phases": [phase.to_dict() for phase in document.phases],
        "issues": [issue.to_dict() for issue in collect_issues(document)],
        "exit_code_hint": expected_exit_code(document),
    }
    if stats is not None:
        payload["graph_stats"] = {
            "nodes": stats.nodes,
            "edges": stats.edges,
            "by_status": dict(stats.by_status),
            "layers": stats.layers,
            "cycles": [list(cycle) for cycle in stats.cycles],
            "dangling_edges": stats.dangling_edges,
            "known_tools": stats.known_tools,
            "unknown_tools": stats.unknown_tools,
        }
    if summary is not None:
        payload["trace_summary"] = {
            "task_id": summary.task_id,
            "trace_id": summary.trace_id,
            "total_events": summary.total_events,
            "counts": dict(summary.counts),
            "failed": [event.to_dict() for event in summary.failed],
        }
    return payload

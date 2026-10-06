"""Offline readers: workspace graph state, trace files, and recorded task summaries.

Every function in this module works without importing ``backend``. A missing or corrupt file
becomes a :class:`FlowIssue` on a best-effort document, never an exception, so ``flowview``
can still print *something* useful and explain what is wrong.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .analysis import build_document, edge_health
from .codes import FlowSourceError, describe_exception, issue_from_exception
from .model import (
    FlowDocument,
    FlowEdge,
    FlowGraph,
    FlowIssue,
    FlowNode,
    SourceStatus,
)

MAX_READ_BYTES = 32 * 1024 * 1024
MAX_NODES = 500
MAX_EDGES = 2000

BACKEND_NODE_STATUSES = frozenset({"ready", "running", "completed", "waiting", "error", "cancelled"})

ROOT = Path(__file__).resolve().parents[1]


def _safe_resolve(value: Path | str) -> Path:
    """Resolve a path without ever raising; the caller detects the problem via ``exists()``."""
    try:
        return Path(value).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        try:
            return Path(value).expanduser().absolute()
        except (OSError, RuntimeError, ValueError):
            return Path(str(value))


def workspace_root(root: Path | None = None) -> Path:
    """The MatFlow project root: explicit argument, ``MATFLOW_DATA_ROOT``'s parent, or default."""
    if root is not None:
        return _safe_resolve(root)
    import os

    configured = os.getenv("MATFLOW_FLOWVIEW_ROOT")
    if configured:
        return _safe_resolve(configured)
    return ROOT


def data_root(root: Path | None = None) -> Path:
    """The runtime data directory (``data/`` by default, ``MATFLOW_DATA_ROOT`` when set)."""
    import os

    configured = os.getenv("MATFLOW_DATA_ROOT")
    if configured:
        return _safe_resolve(configured)
    return workspace_root(root) / "data"


def default_graph_path(root: Path | None = None) -> Path:
    return data_root(root) / "graph_state.json"


def default_summary_path(root: Path | None = None) -> Path:
    return data_root(root) / "audit" / "task_summaries.jsonl"


def default_upload_dir(root: Path | None = None) -> Path:
    return data_root(root) / "uploads"


def _timestamp(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
    except OSError:
        return None


def probe_sources(root: Path | None = None) -> tuple[SourceStatus, ...]:
    """Probe every audited runtime location without creating or modifying anything."""
    project = workspace_root(root)
    candidates: Sequence[tuple[str, Path]] = (
        ("graph state", default_graph_path(root)),
        ("task summaries", default_summary_path(root)),
        ("uploads", default_upload_dir(root)),
        ("settings", data_root(root) / "settings.json"),
        ("graph history", data_root(root) / "graph_state.json"),
        ("backend package", project / "backend" / "workspace_runtime.py"),
    )
    seen: set[Path] = set()
    statuses: list[SourceStatus] = []
    for name, path in candidates:
        if path in seen:
            continue
        seen.add(path)
        exists = path.exists()
        readable = False
        size: int | None = None
        detail: str | None = None
        if exists:
            try:
                if path.is_dir():
                    entries = sum(1 for _ in path.iterdir())
                    readable = True
                    detail = f"directory with {entries} entries"
                else:
                    with path.open("rb") as handle:
                        handle.read(1)
                    readable = True
                    size = path.stat().st_size
            except OSError as exc:
                detail = str(exc)
        else:
            detail = "not created yet"
        statuses.append(
            SourceStatus(
                name=name,
                path=str(path),
                exists=exists,
                readable=readable,
                bytes=size,
                modified=_timestamp(path) if exists else None,
                detail=detail,
            )
        )
    return tuple(statuses)


def read_text_file(path: Path, *, code: str) -> tuple[str | None, FlowIssue | None]:
    """Read a UTF-8 text file with a byte cap, converting every failure into an issue.

    Beyond ordinary I/O errors this handles the two failures that would otherwise escape as
    tracebacks: a symlink loop (``RuntimeError`` on modern Python) and an ACL/permission denial
    (``PermissionError``), each of which gets its own code and hint. A directory is diagnosed as a
    directory, not as a permission problem.
    """
    try:
        is_directory = Path(path).is_dir()
    except (OSError, RuntimeError, ValueError):
        is_directory = False
    if is_directory:
        return None, FlowIssue(
            severity="error",
            code=f"{code}.is_directory",
            message=f"Expected a file but {path} is a directory.",
            where=str(path),
            hint="Pass the file itself (for example graph_state.json), not the folder that holds it.",
        )
    for attempt, action in ((_stat_size, "stat"), (_read_text_bytes, "read")):
        try:
            result = attempt(path)
        except PermissionError as exc:
            return None, FlowIssue(
                severity="error",
                code=f"{code}.permission_denied",
                message=f"FlowView is not allowed to {action} {path}: permission denied.",
                where=str(path),
                hint="Grant read access to the file, or copy it somewhere readable and pass that path.",
                detail=describe_exception(exc),
            )
        except RuntimeError as exc:
            # A symlink loop surfaces as RuntimeError, not OSError.
            return None, FlowIssue(
                severity="error",
                code=f"{code}.symlink_loop",
                message=f"Cannot {action} {path}: {exc}",
                where=str(path),
                hint="Replace the self-referential symlink with a real file, then retry.",
                detail=describe_exception(exc),
            )
        except Exception as exc:  # noqa: BLE001 - reading must never raise out of the loader
            return None, FlowIssue(
                severity="error",
                code=f"{code}.unreadable",
                message=f"Cannot {action} {path}: {describe_exception(exc)}",
                where=str(path),
                hint="Check the path, or run flowview doctor.",
                detail=describe_exception(exc),
            )
        if attempt is _stat_size:
            size = result
            if size > MAX_READ_BYTES:
                return None, FlowIssue(
                    severity="error",
                    code=f"{code}.too_large",
                    message=f"{path} is {size} bytes, above the {MAX_READ_BYTES}-byte reader cap.",
                    where=str(path),
                    hint="Point --graph-file at a smaller export, or split the file.",
                )
            continue
        try:
            return result.decode("utf-8-sig"), None
        except UnicodeDecodeError as exc:
            return None, FlowIssue(
                severity="error",
                code=f"{code}.undecodable",
                message=f"Cannot decode {path} as UTF-8 text: {exc}",
                where=str(path),
                hint="Re-export the file as UTF-8, then retry.",
                detail=describe_exception(exc),
            )
        except Exception as exc:  # noqa: BLE001
            return None, FlowIssue(
                severity="error",
                code=f"{code}.undecodable",
                message=f"Cannot decode {path} as text: {describe_exception(exc)}",
                where=str(path),
                hint="Re-export the file as UTF-8, then retry.",
                detail=describe_exception(exc),
            )
    return None, FlowIssue(
        severity="error",
        code=f"{code}.unreadable",
        message=f"Could not read {path}.",
        where=str(path),
    )


def _stat_size(path: Path) -> int:
    return path.stat().st_size


def _read_text_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _read_text(path: Path, *, code: str) -> tuple[str | None, FlowIssue | None]:
    """Backwards-compatible alias for :func:`read_text_file`."""
    return read_text_file(path, code=code)


def parse_json_text(text: str, *, code: str, where: str | None = None) -> tuple[Any, FlowIssue | None]:
    """Parse JSON, reporting a position-annotated issue instead of raising.

    ``RecursionError`` is caught as well: ``json`` recurses per nesting level, so a hostile or
    accidentally pathological document can blow the interpreter stack rather than raise a
    ``JSONDecodeError``.
    """
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        return None, FlowIssue(
            severity="error",
            code=f"{code}.invalid_json",
            message=f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}",
            where=where,
            hint="Fix the JSON syntax, or run flowview doctor to check the source.",
            detail=str(exc),
        )
    except ValueError as exc:
        # ``json.JSONDecodeError`` is a ``ValueError``; the remaining cases are bodies Python refuses
        # to parse at all (an integer beyond the 4300-digit string limit, for instance), which must
        # become this same readable diagnosis rather than an internal error.
        return None, FlowIssue(
            severity="error",
            code=f"{code}.invalid_json",
            message="The JSON document contains a value Python refuses to parse.",
            where=where,
            hint="Re-export the file; a number outside the interpreter's limits cannot be mirrored.",
            detail=describe_exception(exc),
        )
    except RecursionError as exc:
        return None, FlowIssue(
            severity="error",
            code=f"{code}.too_deep",
            message="The JSON document is nested too deeply to parse.",
            where=where,
            hint="Re-export the file with less nesting; FlowView refuses to risk the interpreter stack.",
            detail=describe_exception(exc),
        )
    except (ValueError, TypeError, MemoryError) as exc:
        return None, FlowIssue(
            severity="error",
            code=f"{code}.invalid_json",
            message=f"The file could not be parsed as JSON: {describe_exception(exc)}",
            where=where,
            hint="Check the file, or run flowview doctor.",
            detail=describe_exception(exc),
        )


def graph_from_payload(
    payload: Any, *, source: str = "", full: bool = False, issue: FlowIssue | None = None
) -> FlowGraph:
    """Mirror a raw ``graph_state.json`` payload, flagging anything it cannot trust.

    ``issue`` carries an upstream failure (a JSON syntax error, for instance) so the caller does
    not have to invent a second, less precise diagnosis for the same problem.
    """
    issues: list[FlowIssue] = [issue] if issue is not None else []
    truncated: list[str] = []
    if not isinstance(payload, Mapping):
        if issue is None:
            issues.append(
                FlowIssue(
                    severity="error",
                    code="graph.not_an_object",
                    message="Graph payload is not a JSON object.",
                    where=source or None,
                    hint="graph_state.json must contain {\"graph_id\": ..., \"nodes\": [...], \"edges\": [...]}.",
                )
            )
        return FlowGraph(source=source, issues=tuple(issues))

    raw_nodes = payload.get("nodes")
    raw_edges = payload.get("edges")
    if raw_nodes is None:
        issues.append(
            FlowIssue(
                severity="warning",
                code="graph.nodes_missing",
                message="Graph payload has no 'nodes' key; treating the graph as empty.",
                where=source or None,
            )
        )
        raw_nodes = []
    if raw_edges is None:
        issues.append(
            FlowIssue(
                severity="warning",
                code="graph.edges_missing",
                message="Graph payload has no 'edges' key; treating the graph as unconnected.",
                where=source or None,
            )
        )
        raw_edges = []
    if not isinstance(raw_nodes, list):
        issues.append(
            FlowIssue(
                severity="error",
                code="graph.nodes_not_a_list",
                message=f"Graph 'nodes' must be a list, got {type(raw_nodes).__name__}.",
                where=source or None,
            )
        )
        raw_nodes = []
    if not isinstance(raw_edges, list):
        issues.append(
            FlowIssue(
                severity="error",
                code="graph.edges_not_a_list",
                message=f"Graph 'edges' must be a list, got {type(raw_edges).__name__}.",
                where=source or None,
            )
        )
        raw_edges = []

    if not full:
        if len(raw_nodes) > MAX_NODES:
            truncated.append(f"nodes>{MAX_NODES}")
            raw_nodes = raw_nodes[:MAX_NODES]
        if len(raw_edges) > MAX_EDGES:
            truncated.append(f"edges>{MAX_EDGES}")
            raw_edges = raw_edges[:MAX_EDGES]

    nodes: list[FlowNode] = []
    self_issues: list[FlowIssue] = []
    for index, raw in enumerate(raw_nodes):
        node, node_issues = _mirror_node(raw, index=index, source=source)
        if node is None:
            issues.extend(node_issues)
            continue
        # Findings that are *about one node* belong on that node; the graph keeps only the
        # findings that are about the graph as a whole.
        attached = tuple(issue for issue in node_issues if issue.where == node.id)
        self_issues.extend(issue for issue in node_issues if issue.where != node.id)
        nodes.append(
            FlowNode(
                id=node.id,
                label=node.label,
                tool_id=node.tool_id,
                tool_version=node.tool_version,
                category=node.category,
                status=node.status,
                params=node.params,
                input_ports=node.input_ports,
                output_ports=node.output_ports,
                error=node.error,
                issues=attached,
                position=node.position,
                known_tool=node.known_tool,
                review_after_run=node.review_after_run,
            )
        )
    issues.extend(self_issues)

    edges: list[FlowEdge] = []
    for index, raw in enumerate(raw_edges):
        edge, edge_issues = _mirror_edge(raw, index=index, source=source)
        issues.extend(edge_issues)
        if edge is not None:
            edges.append(edge)

    version_raw = payload.get("version", 0)
    version = version_raw if isinstance(version_raw, int) and not isinstance(version_raw, bool) else 0
    if not isinstance(version_raw, int) or isinstance(version_raw, bool):
        issues.append(
            FlowIssue(
                severity="warning",
                code="graph.bad_version",
                message=f"Graph version is not an integer: {version_raw!r}; assuming 0.",
                where=source or None,
            )
        )
    graph = FlowGraph(
        graph_id=payload.get("graph_id") if isinstance(payload.get("graph_id"), str) else "local-default",
        version=version,
        nodes=tuple(nodes),
        edges=tuple(edges),
        source=source,
        issues=tuple(issues),
        truncated=tuple(truncated),
    )
    if graph.empty and not graph.issues:
        graph = FlowGraph(
            graph_id=graph.graph_id,
            version=graph.version,
            nodes=graph.nodes,
            edges=graph.edges,
            source=graph.source,
            issues=(
                FlowIssue(
                    severity="info",
                    code="graph.empty",
                    message="The workspace graph has no nodes yet.",
                    where=source or None,
                    hint="Upload a dataset and let the agent build a workflow, then re-run flowview graph.",
                ),
            ),
            truncated=graph.truncated,
        )
    return _with_health(graph)


def _mirror_node(raw: Any, *, index: int, source: str) -> tuple[FlowNode | None, list[FlowIssue]]:
    issues: list[FlowIssue] = []
    if not isinstance(raw, Mapping):
        issues.append(
            FlowIssue(
                severity="error",
                code="graph.node_not_an_object",
                message=f"Node at index {index} is {type(raw).__name__}, not a JSON object; skipped.",
                where=source or None,
                hint="Inspect data/graph_state.json; the file is not a valid GraphState.",
            )
        )
        return None, issues

    raw_id = raw.get("id")
    single_id = raw_id if isinstance(raw_id, str) and raw_id else ""
    if not single_id:
        single_id = f"node-{index}"
        issues.append(
            FlowIssue(
                severity="warning",
                code="graph.node_missing_id",
                message=f"Node at index {index} has no usable id; using '{single_id}'.",
                where=source or None,
            )
        )

    tool_id = raw.get("tool_id")
    node_type = raw.get("type")
    registry_id = tool_id if isinstance(tool_id, str) and tool_id else (node_type if isinstance(node_type, str) and node_type else None)
    if registry_id and isinstance(node_type, str) and isinstance(tool_id, str) and node_type != tool_id:
        issues.append(
            FlowIssue(
                severity="warning",
                code="graph.node_identity_mismatch",
                message=f"Node {single_id} declares type={node_type!r} but tool_id={tool_id!r}.",
                where=single_id,
                hint="The backend rejects this; only one of them is authoritative.",
            )
        )

    label = raw.get("label")
    display = label if isinstance(label, str) and label.strip() else (registry_id or single_id)

    raw_status = raw.get("status")
    status: str = raw_status if isinstance(raw_status, str) else "unknown"
    if status not in BACKEND_NODE_STATUSES:
        if raw_status is None:
            issues.append(
                FlowIssue(
                    severity="warning",
                    code="graph.node_status_missing",
                    message=f"Node {single_id} has no status; showing 'unknown' rather than assuming success.",
                    where=single_id,
                )
            )
        else:
            issues.append(
                FlowIssue(
                    severity="warning",
                    code="graph.node_status_unknown",
                    message=f"Node {single_id} has unrecognised status {raw_status!r}; showing 'unknown'.",
                    where=single_id,
                )
            )
        status = "unknown"

    params = raw.get("params")
    position: tuple[float, float] | None = None
    raw_position = raw.get("position")
    if isinstance(raw_position, Mapping):
        x, y = raw_position.get("x"), raw_position.get("y")
        if isinstance(x, (int, float)) and isinstance(y, (int, float)) and not isinstance(x, bool) and not isinstance(y, bool):
            try:
                # float() overflows on an integer too large to convert; a position is decoration, so
                # it is simply omitted rather than allowed to break the whole read.
                position = (float(x), float(y))
            except (OverflowError, ValueError):
                position = None

    review_policy = raw.get("review_policy")
    review_after_run = bool(isinstance(review_policy, Mapping) and review_policy.get("after_run"))

    error_text: str | None = None
    output = raw.get("output")
    if isinstance(output, Mapping) and isinstance(output.get("error"), str):
        error_text = output["error"]
    if status == "error" and not error_text:
        error_text = "Node status is 'error' but no error text was recorded."
        issues.append(
            FlowIssue(
                severity="warning",
                code="graph.node_error_without_message",
                message=f"Node {single_id} is in error state with no recorded message.",
                where=single_id,
                hint="Check the backend log or the task summary for this node.",
            )
        )

    return (
        FlowNode(
            id=single_id,
            label=display,
            tool_id=registry_id,
            tool_version=raw.get("tool_version") if isinstance(raw.get("tool_version"), str) else None,
            category=None,
            status=status,  # type: ignore[arg-type]
            params=dict(params) if isinstance(params, Mapping) else {},
            input_ports=(),
            output_ports=(),
            error=error_text,
            issues=tuple(),
            position=position,
            known_tool=None,
            review_after_run=review_after_run,
        ),
        issues,
    )


def _mirror_edge(raw: Any, *, index: int, source: str) -> tuple[FlowEdge | None, list[FlowIssue]]:
    if not isinstance(raw, Mapping):
        return None, [
            FlowIssue(
                severity="error",
                code="graph.edge_not_an_object",
                message=f"Edge at index {index} is {type(raw).__name__}, not a JSON object; skipped.",
                where=source or None,
            )
        ]
    edge_id = raw.get("id") if isinstance(raw.get("id"), str) and raw.get("id") else f"edge-{index}"
    source_id = raw.get("source") if isinstance(raw.get("source"), str) else ""
    target_id = raw.get("target") if isinstance(raw.get("target"), str) else ""
    issues: list[FlowIssue] = []
    if not source_id or not target_id:
        issues.append(
            FlowIssue(
                severity="error",
                code="graph.edge_missing_endpoint",
                message=f"Edge {edge_id} is missing a source or target; skipped.",
                where=source or None,
            )
        )
        return None, issues
    return (
        FlowEdge(
            id=edge_id,
            source=source_id,
            target=target_id,
            source_port=raw.get("source_port") if isinstance(raw.get("source_port"), str) else None,
            target_port=raw.get("target_port") if isinstance(raw.get("target_port"), str) else None,
            data_type=None,
            dangling=False,
            duplicate_input=False,
        ),
        issues,
    )


def _with_health(graph: FlowGraph) -> FlowGraph:
    """Add the consistency findings a graph source is not required to carry itself."""
    extra = edge_health(graph)
    if not extra:
        return graph
    return FlowGraph(
        graph_id=graph.graph_id,
        version=graph.version,
        nodes=graph.nodes,
        edges=graph.edges,
        source=graph.source,
        issues=tuple((*graph.issues, *extra)),
        truncated=graph.truncated,
    )


def build_graph_document(graph: FlowGraph, *, title: str | None = None) -> FlowDocument:
    """Wrap a mirrored graph in the canonical document shape."""
    return build_document(
        title=title or f"Workspace graph: {graph.graph_id}",
        source=graph.source or "(in-memory)",
        graph=graph,
    )


def resolve_path(path: Path | str) -> tuple[Path | None, FlowIssue | None]:
    """Resolve a user-supplied path, turning a symlink loop or bad path into an issue.

    ``Path.resolve()`` can raise ``RuntimeError`` for a self-referential symlink and ``OSError``
    for a malformed path, both of which would otherwise escape as a traceback.
    """
    try:
        return Path(path).expanduser().resolve(), None
    except RuntimeError as exc:
        return None, FlowIssue(
            severity="error",
            code="path.symlink_loop",
            message=f"Cannot resolve {path}: {exc}",
            where=str(path),
            hint="Replace the self-referential symlink or junction with a real file, then retry.",
            detail=describe_exception(exc),
        )
    except (OSError, ValueError) as exc:
        return None, FlowIssue(
            severity="error",
            code="path.invalid",
            message=f"Cannot resolve {path}: {describe_exception(exc)}",
            where=str(path),
            hint="Check the path for invalid characters or a broken link.",
            detail=describe_exception(exc),
        )


def read_graph(path: Path | None = None, *, full: bool = False) -> FlowDocument:
    """Read the workspace graph.

    A never-created ``graph_state.json`` is a normal, healthy state, so it yields an empty graph
    with an ``info`` issue rather than an error. A path the caller *explicitly* asked for and that
    does not exist is a different thing: that is a mistake and is reported as one.
    """
    explicit = path is not None
    if explicit:
        resolved, path_issue = resolve_path(path)
    else:
        resolved, path_issue = resolve_path(default_graph_path())
    if resolved is None:
        graph = FlowGraph(source=str(path or default_graph_path()), issues=(path_issue,) if path_issue else ())
        return build_document(
            title="Workspace graph (unresolvable path)",
            source=str(path or default_graph_path()),
            graph=graph,
            meta={"exists": "false", "explicit": "true" if explicit else "false"},
        )
    if not resolved.exists():
        if explicit:
            graph = FlowGraph(
                source=str(resolved),
                issues=(
                    FlowIssue(
                        severity="error",
                        code="graph.missing_file",
                        message=f"The graph file requested with --graph-file does not exist: {resolved}",
                        where=str(resolved),
                        hint="Check the path, or omit --graph-file to read the workspace graph.",
                    ),
                ),
            )
            return build_document(
                title=f"Workspace graph: {resolved.name} (missing)",
                source=str(resolved),
                graph=graph,
                meta={"resolved_path": str(resolved), "exists": "false", "explicit": "true"},
            )
        graph = FlowGraph(
            source=str(resolved),
            issues=(
                FlowIssue(
                    severity="info",
                    code="graph.missing_file",
                    message=f"No graph state file yet: {resolved}",
                    where=str(resolved),
                    hint="Start the backend and create a workflow, or pass --graph-file with an exported file.",
                ),
            ),
        )
        return build_document(
            title=f"Workspace graph: {resolved.name} (absent)",
            source=str(resolved),
            graph=graph,
            meta={"resolved_path": str(resolved), "exists": "false"},
        )
    if resolved.is_dir():
        graph = FlowGraph(
            source=str(resolved),
            issues=(
                FlowIssue(
                    severity="error",
                    code="graph.is_directory",
                    message=f"Expected a file but found a directory: {resolved}",
                    where=str(resolved),
                    hint="Pass the graph_state.json file path.",
                ),
            ),
        )
        return build_document(title=f"Workspace graph: {resolved.name}", source=str(resolved), graph=graph, meta={"resolved_path": str(resolved), "exists": "true"})

    text, issue = _read_text(resolved, code="graph")
    if text is None:
        graph = FlowGraph(source=str(resolved), issues=(issue,) if issue else ())
        return build_document(title=f"Workspace graph: {resolved.name}", source=str(resolved), graph=graph)
    payload, parse_issue = parse_json_text(text, code="graph", where=str(resolved))
    graph = graph_from_payload(payload, source=str(resolved), full=full, issue=parse_issue)
    return build_document(
        title=f"Workspace graph: {resolved.name}",
        source=str(resolved),
        graph=graph,
        meta={"resolved_path": str(resolved), "exists": "true", "modified": _timestamp(resolved) or ""},
    )


def read_state(path: Path | None = None) -> FlowDocument:
    """Alias for :func:`read_graph`, kept because ``state`` is the API's own word for it."""
    return read_graph(path)


def split_json_documents(text: str) -> tuple[list[Any], list[FlowIssue]]:
    """Parse a JSON document, a JSON array of documents, or JSON Lines — in that order."""
    issues: list[FlowIssue] = []
    stripped = text.strip()
    if not stripped:
        return [], [
            FlowIssue(
                severity="error",
                code="trace.empty_file",
                message="The file is empty; there are no events to print.",
                hint="Record a task first, or pass a file that contains events.",
            )
        ]
    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            payload = json.loads(stripped)
        except ValueError:
            payload = None
        if payload is not None:
            if isinstance(payload, list):
                return list(payload), issues
            return [payload], issues
    documents: list[Any] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            documents.append(json.loads(line))
        except ValueError as exc:
            issues.append(
                FlowIssue(
                    severity="warning",
                    code="trace.bad_jsonl_line",
                    message=f"Ignored unparsable JSONL line {number}: {exc}",
                    where=f"line {number}",
                    hint="Each line of a JSONL file must be one complete JSON object.",
                )
            )
    if not documents and not issues:
        issues.append(
            FlowIssue(
                severity="error",
                code="trace.no_documents",
                message="No JSON document could be read from this file.",
            )
        )
    return documents, issues


__all__ = [
    "MAX_EDGES",
    "MAX_NODES",
    "MAX_READ_BYTES",
    "build_graph_document",
    "data_root",
    "default_graph_path",
    "default_summary_path",
    "default_upload_dir",
    "graph_from_payload",
    "parse_json_text",
    "probe_sources",
    "read_graph",
    "read_state",
    "read_trace",
    "read_task",
    "split_json_documents",
    "workspace_root",
    "FlowSourceError",
]


def read_trace(path: Path, *, fmt: str | None = None, full: bool = False) -> FlowDocument:
    """Read a recorded runtime trace produced by ``trace.py``'s writer or by ``/api/chat``."""
    from .trace import document_from_trace_payload

    resolved_candidate, path_issue = resolve_path(path)
    if resolved_candidate is None:
        raise FlowSourceError(
            path_issue.message if path_issue else f"Cannot resolve {path}",
            code=path_issue.code if path_issue else "path.invalid",
            where=str(path),
            hint=path_issue.hint if path_issue else None,
        )
    resolved = resolved_candidate
    if not resolved.exists():
        raise FlowSourceError(
            f"Trace file not found: {resolved}",
            code="trace.missing_file",
            where=str(resolved),
            hint="Pass an existing file, or run flowview run-flow --blueprint to see the phase map.",
        )
    text, issue = _read_text(resolved, code="trace")
    if text is None:
        raise FlowSourceError(
            issue.message if issue else f"Cannot read {resolved}",
            code=issue.code if issue else "trace.unreadable",
            where=str(resolved),
            hint=issue.hint if issue else None,
        )
    payloads, issues = split_json_documents(text)
    if not payloads:
        raise FlowSourceError(
            "The trace file contains no readable JSON document.",
            code="trace.no_document",
            where=str(resolved),
            hint="Check the file with python -m flowview doctor.",
            detail=issues[0].message if issues else None,
        )
    return document_from_trace_payload(payloads, source=str(resolved), issues=issues, full=full)


def read_task(path_or_id: str, *, full: bool = False) -> FlowDocument:
    """Read one recorded task summary by file path or by task id from the audit JSONL."""
    from .tasks import load_task_document, load_task_summaries

    candidate = Path(path_or_id).expanduser()
    if candidate.exists() and candidate.is_file():
        return load_task_document(candidate)
    summaries_path = default_summary_path()
    if not summaries_path.exists():
        raise FlowSourceError(
            f"No task summaries recorded at {summaries_path}",
            code="task.no_summary_log",
            where=str(summaries_path),
            hint="Task summaries are persisted by the backend; enable config/observability.json task_summaries.",
        )
    for document in load_task_summaries(summaries_path):
        if document.meta.get("task_id") == path_or_id or document.source.endswith(path_or_id):
            return document
    raise FlowSourceError(
        f"No recorded task summary matches: {path_or_id}",
        code="task.not_found",
        where=str(summaries_path),
        hint="Run python -m flowview summary to list recorded task ids.",
    )

"""FlowView's zero-dependency mirror of the MatFlow flow model.

This module is intentionally ignorant of ``backend``: it re-declares the small amount of
structure FlowView needs so the printer keeps working when backend logic is broken. Backend
objects are adapted into these types at the edge, never passed through.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
import math
from typing import Any, Literal, Mapping, TypeVar

NodeStatus = Literal["ready", "running", "completed", "waiting", "error", "cancelled", "unknown"]
StepStatus = Literal["pending", "running", "completed", "waiting", "error", "skipped", "unknown"]
IssueSeverity = Literal["info", "warning", "error"]

NODE_STATUSES: tuple[NodeStatus, ...] = (
    "ready", "running", "completed", "waiting", "error", "cancelled", "unknown",
)
STEP_STATUSES: tuple[StepStatus, ...] = (
    "pending", "running", "completed", "waiting", "error", "skipped", "unknown",
)
ISSUE_SEVERITIES: tuple[IssueSeverity, ...] = ("info", "warning", "error")
NODE_STATUS_VOCABULARY: tuple[str, ...] = NODE_STATUSES

_FALLBACK_NODE_STATUS: NodeStatus = "unknown"
_FALLBACK_STEP_STATUS: StepStatus = "unknown"
_FALLBACK_SEVERITY: IssueSeverity = "warning"

T = TypeVar("T")

_MAX_TEXT = 2000
_INT_LIMIT = 2**63


def safe_text(value: Any, default: str = "") -> str:
    """``str(value)`` that cannot raise.

    CPython refuses to stringify an integer above 4300 digits (``sys.set_int_max_str_digits``), and a
    hostile or broken payload can carry one; ``json.dumps`` of such an integer raises for the same
    reason. Every reader funnels payload numbers through here, so such a value becomes readable text
    instead of an unexpected internal error.
    """
    try:
        return str(value)
    except (ValueError, OverflowError):
        return default or "(number too large to print)"


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return safe_text(value, default)
    return default


def _bounded_text(value: Any, default: str = "") -> str:
    text = _as_str(value, default)
    if len(text) <= _MAX_TEXT:
        return text
    return text[: _MAX_TEXT - 1] + "\u2026"


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return safe_text(value) or None
    return None


def _as_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        # A version or count outside 64 bits is not a number this document can carry: ``json.dumps``
        # would fail on it later, so it becomes the default here.
        return value if -_INT_LIMIT < value < _INT_LIMIT else default
    if isinstance(value, float):
        if not math.isfinite(value):
            return default
        return int(value)
    if isinstance(value, str):
        try:
            parsed = int(value.strip())
        except ValueError:
            return default
        return parsed if -_INT_LIMIT < parsed < _INT_LIMIT else default
    return default


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            number = float(value)
        except (OverflowError, ValueError):
            return None
        # JSON has no NaN/Infinity: letting one through would either break the "always valid JSON"
        # promise or need a non-standard encoder.
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        try:
            number = float(value.strip())
        except (ValueError, OverflowError):
            return None
        return number if math.isfinite(number) else None
    return None


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): _json_normalize(item) for key, item in value.items()}
    return {}


def _json_normalize(value: Any) -> Any:
    """Normalise a decoded JSON value so a dict→JSON→dict round trip is stable.

    ``json`` has no tuple, so a tuple read back from JSON is a list; normalising tuples to
    lists on the way in keeps ``FlowNode.to_dict()``/``from_dict`` symmetric. Numbers that JSON
    cannot carry back out (NaN, Infinity, integers beyond 64 bits, integers too long to print) become
    their textual form here, so no later ``json.dumps`` can fail on a hostile payload.
    """
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_normalize(item) for item in value]
    if isinstance(value, Mapping):
        return {safe_text(key): _json_normalize(item) for key, item in value.items()}
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int):
        return value if -_INT_LIMIT < value < _INT_LIMIT else safe_text(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else safe_text(value)
    return value


def _as_sequence(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, (str, bytes, Mapping)):
        return []
    if value is None:
        return []
    try:
        return list(value)
    except TypeError:
        return []


def _status_of(value: Any, allowed: tuple[str, ...], fallback: str) -> Any:
    text = _as_str(value).strip().lower()
    return text if text in allowed else fallback


def _dict_payload(value: Any) -> dict[str, Any]:
    """``to_dict`` body shared by every model type: field order is the JSON key order."""
    payload: dict[str, Any] = {}
    for item in fields(value):
        raw = getattr(value, item.name)
        payload[item.name] = _to_json(raw)
    return payload


def _to_json(value: Any) -> Any:
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_to_json(item) for item in value]
    if isinstance(value, Mapping):
        return {safe_text(key): _to_json(item) for key, item in value.items()}
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int):
        return value if -_INT_LIMIT < value < _INT_LIMIT else safe_text(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else safe_text(value)
    return _as_str(value)


@dataclass(frozen=True, slots=True)
class FlowIssue:
    """One diagnostic. FlowView never raises for bad input; it files one of these."""

    severity: IssueSeverity
    code: str
    message: str
    where: str | None = None
    hint: str | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _dict_payload(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | Any) -> "FlowIssue":
        data = _as_mapping(payload)
        return cls(
            severity=_status_of(data.get("severity"), ISSUE_SEVERITIES, _FALLBACK_SEVERITY),
            code=_as_str(data.get("code"), "flowview.issue"),
            message=_bounded_text(data.get("message"), "Unspecified FlowView issue."),
            where=_as_optional_str(data.get("where")),
            hint=_as_optional_str(data.get("hint")),
            detail=_bounded_text(data.get("detail")) or None,
        )

    def render(self) -> str:
        """One-line human form: ``severity code: message (where)``."""
        parts = [f"{self.severity} {self.code}: {self.message}"]
        if self.where:
            parts.append(f"[{self.where}]")
        if self.hint:
            parts.append(f"-> {self.hint}")
        return " ".join(parts)


@dataclass(frozen=True, slots=True)
class FlowPort:
    """A named port with its declared data type, when it is known offline."""

    name: str
    data_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _dict_payload(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | Any) -> "FlowPort":
        data = _as_mapping(payload)
        return cls(
            name=_as_str(data.get("name"), "?"),
            data_type=_as_optional_str(data.get("data_type")),
        )


@dataclass(frozen=True, slots=True)
class FlowNode:
    """A mirror of one graph node, including FlowView's own findings about it."""

    id: str
    label: str
    tool_id: str | None = None
    tool_version: str | None = None
    category: str | None = None
    status: NodeStatus = "unknown"
    params: Mapping[str, Any] = field(default_factory=dict)
    input_ports: tuple[FlowPort, ...] = ()
    output_ports: tuple[FlowPort, ...] = ()
    error: str | None = None
    issues: tuple[FlowIssue, ...] = ()
    position: tuple[float, float] | None = None
    known_tool: bool | None = None
    review_after_run: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _dict_payload(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | Any) -> "FlowNode":
        data = _as_mapping(payload)
        node_id = _as_str(data.get("id"), "?")
        return cls(
            id=node_id,
            label=_bounded_text(data.get("label"), node_id),
            tool_id=_as_optional_str(data.get("tool_id")),
            tool_version=_as_optional_str(data.get("tool_version")),
            category=_as_optional_str(data.get("category")),
            status=_status_of(data.get("status"), NODE_STATUSES, _FALLBACK_NODE_STATUS),
            params=_as_mapping(data.get("params")),
            input_ports=tuple(FlowPort.from_dict(item) for item in _as_sequence(data.get("input_ports"))),
            output_ports=tuple(FlowPort.from_dict(item) for item in _as_sequence(data.get("output_ports"))),
            error=_bounded_text(data.get("error")) or None,
            issues=tuple(FlowIssue.from_dict(item) for item in _as_sequence(data.get("issues"))),
            position=_position_of(data.get("position")),
            known_tool=_optional_bool(data.get("known_tool")),
            review_after_run=_as_bool(data.get("review_after_run")),
        )

    @property
    def display(self) -> str:
        """Label for diagrams; always non-empty and distinct enough for Mermaid ids."""
        return self.label.strip() or self.id

    @property
    def registry_id(self) -> str:
        return self.tool_id or self.id


def _position_of(value: Any) -> tuple[float, float] | None:
    if isinstance(value, Mapping):
        x, y = _as_float(value.get("x")), _as_float(value.get("y"))
    elif isinstance(value, (list, tuple)) and len(value) >= 2:
        x, y = _as_float(value[0]), _as_float(value[1])
    else:
        return None
    if x is None or y is None:
        return None
    return (x, y)


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    return None


def _normalise_node_params(node: FlowNode) -> FlowNode:
    """Rebuild a node with JSON-normalised ``params`` so round-tripping is stable."""
    normalised = _json_normalize(node.params)
    if normalised == node.params:
        return node
    return FlowNode(
        id=node.id,
        label=node.label,
        tool_id=node.tool_id,
        tool_version=node.tool_version,
        category=node.category,
        status=node.status,
        params=normalised,
        input_ports=node.input_ports,
        output_ports=node.output_ports,
        error=node.error,
        issues=node.issues,
        position=node.position,
        known_tool=node.known_tool,
        review_after_run=node.review_after_run,
    )


@dataclass(frozen=True, slots=True)
class FlowEdge:
    """An edge, flagged when its endpoints or input port are already inconsistent."""

    id: str
    source: str
    target: str
    source_port: str | None = None
    target_port: str | None = None
    data_type: str | None = None
    dangling: bool = False
    duplicate_input: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _dict_payload(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | Any) -> "FlowEdge":
        data = _as_mapping(payload)
        return cls(
            id=_as_str(data.get("id"), "?"),
            source=_as_str(data.get("source"), "?"),
            target=_as_str(data.get("target"), "?"),
            source_port=_as_optional_str(data.get("source_port")),
            target_port=_as_optional_str(data.get("target_port")),
            data_type=_as_optional_str(data.get("data_type")),
            dangling=_as_bool(data.get("dangling")),
            duplicate_input=_as_bool(data.get("duplicate_input")),
        )

    @property
    def sort_key(self) -> tuple[str, str, str, str]:
        return (self.source, self.source_port or "", self.target, self.target_port or "")


@dataclass(frozen=True, slots=True)
class FlowGraph:
    """The mirrored workspace graph plus every offline consistency finding."""

    graph_id: str = "local-default"
    version: int = 0
    nodes: tuple[FlowNode, ...] = ()
    edges: tuple[FlowEdge, ...] = ()
    source: str = ""
    issues: tuple[FlowIssue, ...] = ()
    truncated: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _dict_payload(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | Any) -> "FlowGraph":
        data = _as_mapping(payload)
        # `params` is free-form JSON: normalise it so a dict->JSON->dict round trip is stable.
        nodes = tuple(
            FlowNode.from_dict(item) for item in _as_sequence(data.get("nodes"))
        )
        return cls(
            graph_id=_as_str(data.get("graph_id"), "local-default"),
            version=_as_int(data.get("version"), 0),
            nodes=tuple(_normalise_node_params(node) for node in nodes),
            edges=tuple(FlowEdge.from_dict(item) for item in _as_sequence(data.get("edges"))),
            source=_as_str(data.get("source")),
            issues=tuple(FlowIssue.from_dict(item) for item in _as_sequence(data.get("issues"))),
            truncated=tuple(_as_str(item) for item in _as_sequence(data.get("truncated"))),
        )

    @property
    def node_ids(self) -> tuple[str, ...]:
        return tuple(node.id for node in self.nodes)

    def node(self, node_id: str) -> FlowNode | None:
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    @property
    def sorted_edges(self) -> tuple[FlowEdge, ...]:
        return tuple(sorted(self.edges, key=lambda edge: edge.sort_key))

    @property
    def empty(self) -> bool:
        return not self.nodes


@dataclass(frozen=True, slots=True)
class FlowStep:
    """One observable backend step inside a phase, with its backend seam in ``detail``."""

    name: str
    status: StepStatus = "unknown"
    detail: str | None = None
    error: str | None = None
    node_id: str | None = None
    tools: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _dict_payload(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | Any) -> "FlowStep":
        data = _as_mapping(payload)
        return cls(
            name=_as_str(data.get("name"), "?"),
            status=_status_of(data.get("status"), STEP_STATUSES, _FALLBACK_STEP_STATUS),
            detail=_bounded_text(data.get("detail")) or None,
            error=_bounded_text(data.get("error")) or None,
            node_id=_as_optional_str(data.get("node_id")),
            tools=tuple(_as_str(item) for item in _as_sequence(data.get("tools"))),
        )


@dataclass(frozen=True, slots=True)
class FlowPhase:
    """A named stage of the backend flow, with the steps observed or expected in it."""

    name: str
    title: str
    steps: tuple[FlowStep, ...] = ()
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _dict_payload(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | Any) -> "FlowPhase":
        data = _as_mapping(payload)
        name = _as_str(data.get("name"), "?")
        return cls(
            name=name,
            title=_as_str(data.get("title"), name),
            steps=tuple(FlowStep.from_dict(item) for item in _as_sequence(data.get("steps"))),
            error=_bounded_text(data.get("error")) or None,
        )

    @property
    def status(self) -> StepStatus:
        """Fold step statuses: error > running > waiting > completed > pending."""
        from .analysis import phase_status

        return phase_status(self)


@dataclass(frozen=True, slots=True)
class FlowEvent:
    """One recorded runtime event, already normalised into a phase and a status."""

    index: int
    phase: str
    name: str
    status: StepStatus = "unknown"
    detail: str | None = None
    error: str | None = None
    node_id: str | None = None
    tool_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _dict_payload(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | Any) -> "FlowEvent":
        data = _as_mapping(payload)
        return cls(
            index=_as_int(data.get("index"), 0),
            phase=_as_str(data.get("phase"), "unknown"),
            name=_as_str(data.get("name"), "event"),
            status=_status_of(data.get("status"), STEP_STATUSES, _FALLBACK_STEP_STATUS),
            detail=_bounded_text(data.get("detail")) or None,
            error=_bounded_text(data.get("error")) or None,
            node_id=_as_optional_str(data.get("node_id")),
            tool_id=_as_optional_str(data.get("tool_id")),
        )


@dataclass(frozen=True, slots=True)
class FlowTrace:
    """A recorded task lifecycle: events plus the phase order they belong to."""

    events: tuple[FlowEvent, ...] = ()
    task_id: str | None = None
    trace_id: str | None = None
    source: str = ""
    phases: tuple[FlowPhase, ...] = ()
    issues: tuple[FlowIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _dict_payload(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | Any) -> "FlowTrace":
        data = _as_mapping(payload)
        return cls(
            events=tuple(FlowEvent.from_dict(item) for item in _as_sequence(data.get("events"))),
            task_id=_as_optional_str(data.get("task_id")),
            trace_id=_as_optional_str(data.get("trace_id")),
            source=_as_str(data.get("source")),
            phases=tuple(FlowPhase.from_dict(item) for item in _as_sequence(data.get("phases"))),
            issues=tuple(FlowIssue.from_dict(item) for item in _as_sequence(data.get("issues"))),
        )

    @property
    def ordered_events(self) -> tuple[FlowEvent, ...]:
        return tuple(sorted(self.events, key=lambda event: event.index))

    @property
    def failed_events(self) -> tuple[FlowEvent, ...]:
        return tuple(event for event in self.ordered_events if event.status == "error")


@dataclass(frozen=True, slots=True)
class FlowDocument:
    """The single renderer input: a graph, a trace, or a written-down phase blueprint."""

    title: str
    source: str
    graph: FlowGraph | None = None
    trace: FlowTrace | None = None
    phases: tuple[FlowPhase, ...] = ()
    issues: tuple[FlowIssue, ...] = ()
    meta: Mapping[str, str] = field(default_factory=dict)
    truncated: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _dict_payload(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | Any) -> "FlowDocument":
        data = _as_mapping(payload)
        graph = data.get("graph")
        trace = data.get("trace")
        return cls(
            title=_as_str(data.get("title"), "MatFlow flow"),
            source=_as_str(data.get("source")),
            graph=FlowGraph.from_dict(graph) if isinstance(graph, Mapping) else None,
            trace=FlowTrace.from_dict(trace) if isinstance(trace, Mapping) else None,
            phases=tuple(FlowPhase.from_dict(item) for item in _as_sequence(data.get("phases"))),
            issues=tuple(FlowIssue.from_dict(item) for item in _as_sequence(data.get("issues"))),
            meta={str(key): _as_str(value) for key, value in _as_mapping(data.get("meta")).items()},
            truncated=tuple(_as_str(item) for item in _as_sequence(data.get("truncated"))),
        )

    def all_issues(self) -> tuple[FlowIssue, ...]:
        """Every distinct issue on the document and its parts, in a stable order."""
        from .analysis import collect_issues

        return collect_issues(self)

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.all_issues() if issue.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.all_issues() if issue.severity == "warning")


@dataclass(frozen=True, slots=True)
class SourceStatus:
    """A probe result for one audited runtime location, used by ``doctor`` and ``--list``."""

    name: str
    path: str
    exists: bool
    readable: bool
    bytes: int | None = None
    modified: str | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _dict_payload(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | Any) -> "SourceStatus":
        data = _as_mapping(payload)
        return cls(
            name=_as_str(data.get("name"), "?"),
            path=_as_str(data.get("path")),
            exists=_as_bool(data.get("exists")),
            readable=_as_bool(data.get("readable")),
            bytes=_as_int(data["bytes"]) if data.get("bytes") is not None else None,
            modified=_as_optional_str(data.get("modified")),
            detail=_bounded_text(data.get("detail")) or None,
        )

    @property
    def healthy(self) -> bool:
        return self.exists and self.readable

"""Mermaid rendering: deterministic flowcharts, sequence diagrams and state diagrams."""
from __future__ import annotations

import unicodedata
from typing import Any, ClassVar, Mapping, Sequence

from . import analysis
from .model import NODE_STATUSES, STEP_STATUSES
from .style import strip_ansi, truncate

_MAX_COMMENT = 200
_DIRECTIONS = ("TD", "TB", "BT", "LR", "RL")

# Every label goes through this map, character by character, so escaping cannot double-apply.
# Mermaid renders `#quot;` / `#35;` back to the original character.
_ESCAPE_MAP: dict[str, str] = {
    '"': "#quot;",
    "#": "#35;",
    "`": "#96;",
    "[": "#91;",
    "]": "#93;",
    "{": "#123;",
    "}": "#125;",
    "(": "#40;",
    ")": "#41;",
    "|": "#124;",
    "<": "&lt;",
    ">": "&gt;",
    "&": "&amp;",
    "\t": " ",
}
_DROP_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn"})

# Shape per status word: status stays readable even when the diagram is rendered without colour.
_STATUS_SHAPES: dict[str, str] = {
    "ready": "rect",
    "running": "round",
    "completed": "stadium",
    "waiting": "rhombus",
    "error": "hexagon",
    "cancelled": "subroutine",
    "unknown": "cylinder",
    "pending": "rect",
    "skipped": "subroutine",
}
_STATUS_CLASSDEFS: dict[str, str] = {
    "ready": "fill:#e8f1fb,stroke:#3b6ea5,color:#102a43",
    "running": "fill:#fff4d6,stroke:#a5761b,color:#3d2c00",
    "completed": "fill:#e3f6e8,stroke:#2f7d43,color:#0f3319",
    "waiting": "fill:#fdf1dc,stroke:#a5761b,color:#3d2c00",
    "error": "fill:#fbe3e3,stroke:#a32020,color:#4a0f0f",
    "cancelled": "fill:#f0e8f8,stroke:#6b4b9a,color:#2a1040",
    "unknown": "fill:#eceff3,stroke:#8792a2,color:#2b3038",
    "pending": "fill:#f3f4f6,stroke:#8792a2,color:#2b3038",
    "skipped": "fill:#f0e8f8,stroke:#6b4b9a,color:#2a1040",
}
_CLASSDEF_ORDER: tuple[str, ...] = tuple(NODE_STATUSES) + tuple(
    status for status in STEP_STATUSES if status not in NODE_STATUSES
)

_PLACEHOLDER_FALLBACK = "flowchart TD\n    %% FlowView could not render this document at all."


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return str(value)
    except Exception:  # noqa: BLE001 - rendering must never raise for odd values
        return ""


def _is_drop(ch: str) -> bool:
    try:
        return unicodedata.category(ch) in _DROP_CATEGORIES
    except Exception:  # noqa: BLE001
        return False


def _is_control(ch: str) -> bool:
    """C0/C1 control characters that Mermaid cannot carry and a reader cannot see."""
    return ch < " " or ch == "\x7f" or "\x80" <= ch <= "\x9f"


def _escape_control(ch: str) -> str:
    """A visible stand-in for a control character, so nothing disappears silently."""
    if ch == "\x1b":
        return "\\e"
    return f"\\x{ord(ch):02x}" if ord(ch) < 256 else f"\\u{ord(ch):04x}"


def _one_line(value: Any, *, limit: int = _MAX_COMMENT) -> str:
    """Collapse ``value`` into one sanitised line safe for a Mermaid comment or alias."""
    text = strip_ansi(_as_text(value))
    kept: list[str] = []
    for ch in text:
        if ch in "\r\n\t":
            kept.append(" ")
        elif _is_control(ch):
            kept.append(_escape_control(ch))
        elif _is_drop(ch):
            continue
        else:
            kept.append(ch)
    collapsed = " ".join("".join(kept).split())
    if limit > 0 and len(collapsed) > limit:
        collapsed = collapsed[: limit - 1].rstrip() + "\u2026"
    return collapsed


def _escape_text(value: Any, *, keep_breaks: bool = True) -> str:
    """Escape one Mermaid label: quotes, brackets, pipes, entities, and control characters."""
    text = strip_ansi(_as_text(value))
    out: list[str] = []
    for ch in text:
        if ch == "\n":
            out.append("<br/>" if keep_breaks else " ")
            continue
        if ch == "\r":
            continue
        mapped = _ESCAPE_MAP.get(ch)
        if mapped is not None:
            out.append(mapped)
            continue
        if _is_control(ch):
            out.append(_escape_control(ch))
            continue
        if _is_drop(ch):
            continue
        out.append(ch)
    return "".join(out)


def _sanitize_id_part(value: Any) -> str:
    """ASCII, Mermaid-safe id fragment (empty when nothing usable is left)."""
    text = strip_ansi(_as_text(value)).strip()
    cleaned = "".join(ch if (ch.isascii() and (ch.isalnum() or ch in "_-")) else "_" for ch in text)
    return cleaned.strip("_")


def _status_word(value: Any) -> str:
    """A recognised status word; anything else is reported as ``unknown`` (never as success)."""
    text = _as_text(value).strip().lower()
    return text if text in _STATUS_SHAPES else "unknown"


def _class_name(status: Any) -> str:
    word = _status_word(status)
    return f"flowview_{word}" if word in _STATUS_CLASSDEFS else "flowview_unknown"


def _shape(node_id: str, label: str, shape: str) -> str:
    """One node declaration in the shape that encodes the status."""
    if shape == "round":
        return f'{node_id}("{label}")'
    if shape == "stadium":
        return f'{node_id}(["{label}"])'
    if shape == "rhombus":
        return f'{node_id}{{"{label}"}}'
    if shape == "hexagon":
        return f'{node_id}{{{{"{label}"}}}}'
    if shape == "subroutine":
        return f'{node_id}[["{label}"]]'
    if shape == "cylinder":
        return f'{node_id}[("{label}")]'
    return f'{node_id}["{label}"]'


def _edge_key(edge: Any) -> tuple[str, str, str, str]:
    return (
        _as_text(getattr(edge, "source", "")),
        _as_text(getattr(edge, "source_port", "") or ""),
        _as_text(getattr(edge, "target", "")),
        _as_text(getattr(edge, "target_port", "") or ""),
    )


def _phase_status(phase: Any) -> str:
    try:
        return _status_word(analysis.phase_status(phase))
    except Exception:  # noqa: BLE001 - a malformed phase degrades to `unknown`
        return "unknown"


class _IdMap:
    """Deterministic, collision-free Mermaid ids, memoised per original identifier."""

    __slots__ = ("_prefix", "_map", "_taken")

    def __init__(self, prefix: str = "n") -> None:
        self._prefix = prefix
        self._map: dict[str, str] = {}
        self._taken: set[str] = set()

    def ensure(self, raw: Any) -> str:
        key = _as_text(raw)
        existing = self._map.get(key)
        if existing is not None:
            return existing
        base = _sanitize_id_part(key) or "node"
        candidate = f"{self._prefix}_{base}"
        index = 2
        while candidate in self._taken:
            candidate = f"{self._prefix}_{base}_{index}"
            index += 1
        self._taken.add(candidate)
        self._map[key] = candidate
        return candidate


class MermaidRenderer:
    """Render FlowView documents as Mermaid.

    Output is deterministic, always syntactically valid, and never contains ANSI escapes:
    the ``style`` argument is accepted for interface compatibility and deliberately unused.
    """

    format: ClassVar[str] = "mermaid"

    def __init__(
        self,
        *,
        direction: str = "TD",
        include_params: bool = False,
        max_label: int = 48,
        style: Any | None = None,
    ) -> None:
        chosen = _as_text(direction).strip().upper()
        self.direction = chosen if chosen in _DIRECTIONS else "TD"
        self.include_params = bool(include_params)
        try:
            self.max_label = int(max_label)
        except Exception:  # noqa: BLE001
            self.max_label = 48
        self.style = style  # kept for the shared renderer interface; never used for Mermaid

    # ------------------------------------------------------------------ public API

    def render_document(self, document: Any) -> str:
        """Pick the most informative view: graph, then trace, then the phase map."""
        try:
            graph = getattr(document, "graph", None)
            trace = getattr(document, "trace", None)
            phases = tuple(getattr(document, "phases", ()) or ())
            title = _as_text(getattr(document, "title", ""))
            source = _as_text(getattr(document, "source", ""))
            issues = list(getattr(document, "issues", ()) or ())
            events = tuple(getattr(trace, "events", ()) or ()) if trace is not None else ()
            if graph is not None:
                body = self._graph_flowchart(graph, title=title, source=source, issues=issues)
                if events:
                    body += (
                        "\n    %% NOTE: this document also carries a recorded trace; "
                        "call render_trace() for the sequence view."
                    )
                return body
            if trace is not None and (events or tuple(getattr(trace, "phases", ()) or ())):
                return self._sequence_diagram(trace, document_issues=issues)
            if phases:
                return self._phases_flowchart(phases, title=title, source=source, issues=issues)
            return self._placeholder(
                "document",
                "the document has no graph, trace, or phases to draw",
                extra=self._issue_comments(issues),
            )
        except Exception as exc:  # noqa: BLE001 - a renderer never crashes the CLI
            return self._placeholder("document", exc)

    def render_graph(self, graph: Any) -> str:
        """A ``flowchart`` of the graph: nodes in document order, edges sorted deterministically."""
        try:
            return self._graph_flowchart(graph)
        except Exception as exc:  # noqa: BLE001
            return self._placeholder("graph", exc)

    def render_trace(self, trace: Any) -> str:
        """A ``sequenceDiagram`` of one recorded task lifecycle."""
        try:
            return self._sequence_diagram(trace)
        except Exception as exc:  # noqa: BLE001
            return self._placeholder("trace", exc)

    def render_state(self, graph: Any) -> str:
        """A ``stateDiagram-v2`` view: transitions between the statuses nodes are in."""
        try:
            return self._state_diagram(graph)
        except Exception as exc:  # noqa: BLE001
            return self._placeholder("state view", exc)

    # ------------------------------------------------------------------ graph view

    def _graph_flowchart(
        self,
        graph: Any,
        *,
        title: str = "",
        source: str = "",
        issues: Sequence[Any] = (),
    ) -> str:
        nodes = self._nodes_of(graph)
        edges = self._edges_of(graph)
        ids = _IdMap("n")
        lines = [f"flowchart {self.direction}"]
        lines.append("    %% FlowView: workspace graph as a flowchart.")
        lines.append("    %% nodes are drawn in document order; edges are sorted by source, port, target, port.")
        if title:
            lines.append(f"    %% title: {_one_line(title)}")
        lines.append(
            "    %% graph_id: {graph_id}; version: {version}; nodes: {nodes}; edges: {edges}".format(
                graph_id=_one_line(getattr(graph, "graph_id", "")) or "local-default",
                version=_one_line(getattr(graph, "version", 0)) or "0",
                nodes=len(nodes),
                edges=len(edges),
            )
        )
        graph_source = _one_line(getattr(graph, "source", "")) or _one_line(source)
        if graph_source:
            lines.append(f"    %% source: {graph_source}")
        truncated = tuple(getattr(graph, "truncated", ()) or ())
        if truncated:
            caps = ", ".join(_one_line(item) for item in truncated)
            lines.append(f"    %% reader caps applied: {caps}")
        lines += self._issue_comments([*(getattr(graph, "issues", ()) or ()), *issues])

        if not nodes:
            lines.append("    %% Empty graph: no nodes were declared, so there is nothing to connect.")
            lines.append(
                f'    flowview_empty["(empty graph: 0 nodes, {len(edges)} edge(s))"]:::flowview_unknown'
            )
        else:
            for node in nodes:
                node_id = ids.ensure(getattr(node, "id", ""))
                status = _status_word(getattr(node, "status", ""))
                label = self._node_label(node)
                lines.append(
                    f"    {_shape(node_id, label, _STATUS_SHAPES.get(status, 'rect'))}:::{_class_name(status)}"
                )

        flagged = 0
        for edge in edges:
            source_id = ids.ensure(getattr(edge, "source", ""))
            target_id = ids.ensure(getattr(edge, "target", ""))
            is_flagged = bool(
                getattr(edge, "dangling", False) or getattr(edge, "duplicate_input", False)
            )
            flagged += 1 if is_flagged else 0
            arrow = "-.->" if is_flagged else "-->"
            label = self._edge_label(edge)
            if label:
                lines.append(f"    {source_id} {arrow}|{label}| {target_id}")
            else:
                lines.append(f"    {source_id} {arrow} {target_id}")

        known = {_as_text(getattr(node, "id", "")) for node in nodes}
        outside = sorted(
            {
                _as_text(endpoint)
                for edge in edges
                for endpoint in (getattr(edge, "source", ""), getattr(edge, "target", ""))
                if _as_text(endpoint) not in known
            }
        )
        if outside:
            shown = ", ".join(_one_line(item) for item in outside[:5])
            if len(outside) > 5:
                shown += f", ... (+{len(outside) - 5} more)"
            lines.append(
                f"    %% NOTE: {len(outside)} edge endpoint(s) are not declared nodes: {shown}"
            )
        if flagged:
            lines.append(
                f"    %% NOTE: {flagged} dotted edge(s) are flagged as dangling or duplicate input."
            )
        if nodes:
            lines += self._legend_block()
        lines += self._classdef_block()
        return "\n".join(lines)

    def _nodes_of(self, graph: Any) -> tuple[Any, ...]:
        try:
            return tuple(getattr(graph, "nodes", ()) or ())
        except Exception:  # noqa: BLE001
            return ()

    def _edges_of(self, graph: Any) -> tuple[Any, ...]:
        try:
            edges = tuple(getattr(graph, "edges", ()) or ())
        except Exception:  # noqa: BLE001
            return ()
        try:
            return tuple(sorted(edges, key=_edge_key))
        except Exception:  # noqa: BLE001
            return edges

    def _node_label(self, node: Any) -> str:
        raw = _as_text(getattr(node, "label", "")).strip() or _as_text(getattr(node, "id", ""))
        if self.include_params:
            params = self._params_text(getattr(node, "params", None))
            if params:
                raw = f"{raw} - {params}" if raw else params
        fallback = _as_text(getattr(node, "id", "")).strip() or "node"
        return self._label_text(raw, fallback)

    def _params_text(self, params: Any) -> str:
        if not isinstance(params, Mapping):
            return ""
        items = list(params.items())
        parts = [f"{_one_line(key)}={_one_line(value, limit=0)}" for key, value in items[:4]]
        text = ", ".join(parts)
        if len(items) > 4:
            text += f", ... (+{len(items) - 4} more)"
        return text

    def _label_text(self, raw: Any, fallback: Any) -> str:
        text = _as_text(raw).strip() or _as_text(fallback).strip() or "?"
        if self.max_label > 0 and len(text) > self.max_label:
            try:
                text = truncate(text, self.max_label) or text[: self.max_label]
            except Exception:  # noqa: BLE001
                text = text[: self.max_label]
        escaped = _escape_text(text)
        if not escaped:
            escaped = _escape_text(fallback) or "?"
        return escaped

    def _edge_label(self, edge: Any) -> str:
        parts: list[str] = []
        source_port = _as_text(getattr(edge, "source_port", "") or "")
        target_port = _as_text(getattr(edge, "target_port", "") or "")
        if source_port or target_port:
            parts.append(f"{source_port or '*'} -> {target_port or '*'}")
        data_type = _as_text(getattr(edge, "data_type", "") or "")
        if data_type:
            parts.append(f"type {data_type}")
        flags: list[str] = []
        if getattr(edge, "dangling", False):
            flags.append("dangling")
        if getattr(edge, "duplicate_input", False):
            flags.append("duplicate input")
        if flags:
            parts.append(", ".join(flags))
        text = " ".join(parts)
        if not text:
            return ""
        cap = self.max_label if self.max_label > 0 else 32
        cap = min(cap, 32)
        if len(text) > cap:
            try:
                text = truncate(text, cap) or text[:cap]
            except Exception:  # noqa: BLE001
                text = text[:cap]
        return _escape_text(text)

    def _legend_block(self) -> list[str]:
        lines = ['    subgraph flowview_legend["FlowView status legend (shape = status)"]']
        for status in NODE_STATUSES:
            name = f"flowview_legend_{status}"
            lines.append(f"        {_shape(name, status, _STATUS_SHAPES[status])}:::{_class_name(status)}")
        lines.append("    end")
        return lines

    def _classdef_block(self) -> list[str]:
        return [
            f"    classDef flowview_{status} {_STATUS_CLASSDEFS[status]};"
            for status in _CLASSDEF_ORDER
            if status in _STATUS_CLASSDEFS
        ]

    # ------------------------------------------------------------------ phase map view

    def _phases_flowchart(
        self,
        phases: Sequence[Any],
        *,
        title: str = "",
        source: str = "",
        issues: Sequence[Any] = (),
    ) -> str:
        """A flowchart of the runtime phase map: one subgraph per phase, one node per step."""
        lines = [f"flowchart {self.direction}"]
        lines.append("    %% FlowView: runtime phase map, one node per observable step.")
        if title:
            lines.append(f"    %% title: {_one_line(title)}")
        if source:
            lines.append(f"    %% source: {_one_line(source)}")
        lines.append(
            "    %% phases: {phases}; steps: {steps}".format(
                phases=len(phases),
                steps=sum(len(tuple(getattr(phase, "steps", ()) or ())) for phase in phases),
            )
        )
        lines += self._issue_comments(issues)

        phase_ids = _IdMap("pg")
        step_ids = _IdMap("n")
        if not phases:
            lines.append("    %% No phases were provided, so there is nothing to draw.")
            lines.append('    flowview_empty["(no phases to draw)"]:::flowview_unknown')
            lines += self._classdef_block()
            return "\n".join(lines)

        previous_last: str | None = None
        for index, phase in enumerate(phases):
            name = _as_text(getattr(phase, "name", "")).strip() or f"phase{index + 1}"
            phase_title = _as_text(getattr(phase, "title", "")).strip() or name
            status = _phase_status(phase)
            heading = f"{phase_title} ({name}) [{status}]" if phase_title != name else f"{phase_title} [{status}]"
            lines.append(
                f'    subgraph {phase_ids.ensure(name)}["{_escape_text(heading, keep_breaks=False)}"]'
            )
            steps = tuple(getattr(phase, "steps", ()) or ())
            first: str | None = None
            last: str | None = None
            for step_index, step in enumerate(steps):
                step_id = step_ids.ensure(
                    f"{name}\u0000{step_index}\u0000{_as_text(getattr(step, 'name', ''))}"
                )
                step_status = _status_word(getattr(step, "status", ""))
                lines.append(
                    "        {node}:::{klass}".format(
                        node=_shape(
                            step_id,
                            self._step_label(step),
                            _STATUS_SHAPES.get(step_status, "rect"),
                        ),
                        klass=_class_name(step_status),
                    )
                )
                if first is None:
                    first = step_id
                last = step_id
            if not steps:
                lines.append("        %% (no steps recorded in this phase)")
            lines.append("    end")
            if first is not None and last is not None:
                if previous_last is not None:
                    lines.append(f"    {previous_last} --> {first}")
                previous_last = last
        lines += self._classdef_block()
        return "\n".join(lines)

    def _step_label(self, step: Any) -> str:
        name = _as_text(getattr(step, "name", "")).strip() or "(unnamed step)"
        detail = _one_line(getattr(step, "detail", "") or "")
        raw = f"{name} - {detail}" if detail else name
        status = _status_word(getattr(step, "status", ""))
        return f"{self._label_text(raw, '(unnamed step)')}<br/>{status}"

    # ------------------------------------------------------------------ trace view

    def _events_of(self, trace: Any) -> tuple[Any, ...]:
        try:
            events = tuple(getattr(trace, "events", ()) or ())
        except Exception:  # noqa: BLE001
            return ()

        def index_of(event: Any) -> int:
            try:
                return int(getattr(event, "index", 0))
            except Exception:  # noqa: BLE001
                return 0

        try:
            return tuple(sorted(events, key=index_of))
        except Exception:  # noqa: BLE001
            return events

    def _phases_of(self, trace: Any) -> tuple[Any, ...]:
        try:
            derived = analysis.derive_phases(trace)
            if derived:
                return tuple(derived)
        except Exception:  # noqa: BLE001
            pass
        try:
            return tuple(getattr(trace, "phases", ()) or ())
        except Exception:  # noqa: BLE001
            return ()

    def _sequence_alias(self, value: Any) -> str:
        text = _one_line(value).replace(";", ",").replace(":", " -")
        return _escape_text(text, keep_breaks=False) or "phase"

    def _sequence_text(self, value: Any) -> str:
        text = _one_line(value, limit=0).replace(";", ",")
        return _escape_text(text, keep_breaks=False) or "(empty)"

    def _event_text(self, event: Any) -> str:
        name = _one_line(getattr(event, "name", "")) or "(unnamed event)"
        status = _status_word(getattr(event, "status", ""))
        text = f"{name} [{status}]"
        tool = _one_line(getattr(event, "tool_id", "") or "")
        if tool:
            text += f" ({tool})"
        detail = _one_line(getattr(event, "detail", "") or "", limit=80)
        if detail:
            text += f" - {detail}"
        return self._sequence_text(text)

    def _sequence_diagram(self, trace: Any, *, document_issues: Sequence[Any] = ()) -> str:
        events = self._events_of(trace)
        phases = self._phases_of(trace)
        order: list[str] = []
        titles: dict[str, str] = {}
        for phase in phases:
            name = _as_text(getattr(phase, "name", "")).strip() or "unknown"
            if name not in titles:
                order.append(name)
                titles[name] = _as_text(getattr(phase, "title", "")).strip() or name
        for event in events:
            name = _as_text(getattr(event, "phase", "")).strip() or "unknown"
            if name not in titles:
                order.append(name)
                titles[name] = name

        lines = ["sequenceDiagram"]
        lines.append("    %% FlowView: recorded runtime trace, in recorded event order.")
        lines.append(
            "    %% task_id: {task}; trace_id: {trace_id}; events: {events}; phases: {phases}".format(
                task=_one_line(getattr(trace, "task_id", "")) or "(none)",
                trace_id=_one_line(getattr(trace, "trace_id", "")) or "(none)",
                events=len(events),
                phases=len(order),
            )
        )
        source = _one_line(getattr(trace, "source", ""))
        if source:
            lines.append(f"    %% source: {source}")
        lines += self._issue_comments([
            *(getattr(trace, "issues", ()) or ()),
            *document_issues,
        ])

        if not order:
            lines.append("    %% The trace is empty: no recorded events or phases.")
            lines.append("    participant flowview_empty as (no events)")
            lines.append("    Note over flowview_empty: No runtime events were recorded for this trace.")
            return "\n".join(lines)

        ids: dict[str, str] = {}
        for index, name in enumerate(order):
            lane = f"P{index}_{_sanitize_id_part(name) or 'phase'}"
            ids[name] = lane
            lines.append(f"    participant {lane} as {self._sequence_alias(titles[name])}")
        if events:
            lines.append("    autonumber")

        previous: str | None = None
        failures = 0
        for event in events:
            name = _as_text(getattr(event, "phase", "")).strip() or "unknown"
            lane = ids.get(name) or ids[order[0]]
            text = self._event_text(event)
            if previous is not None and previous != lane:
                lines.append(f"    {previous}->>{lane}: {text}")
            else:
                lines.append(f"    {lane}->>{lane}: {text}")
            previous = lane
            if _status_word(getattr(event, "status", "")) == "error":
                failures += 1
            error = _as_text(getattr(event, "error", "") or "")
            if error:
                lines.append(f"    Note over {lane}: error: {self._sequence_text(error)}")
        if failures:
            lines.append(
                f"    Note over {ids[order[-1]]}: {failures} event(s) failed in this trace."
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------ state view

    def _state_diagram(self, graph: Any) -> str:
        nodes = self._nodes_of(graph)
        lines = ["stateDiagram-v2"]
        lines.append("    %% FlowView: node statuses and the status transitions the edges imply.")
        graph_source = _one_line(getattr(graph, "source", ""))
        if graph_source:
            lines.append(f"    %% source: {graph_source}")
        lines.append(f"    %% nodes: {len(nodes)}")
        if not nodes:
            lines.append("    %% Empty graph: no node statuses to show.")
            lines.append("    [*] --> flowview_empty")
            lines.append("    flowview_empty : (empty graph: no nodes)")
            return "\n".join(lines)

        status_of: dict[str, str] = {}
        for node in nodes:
            status_of[_as_text(getattr(node, "id", ""))] = _status_word(getattr(node, "status", ""))
        present = [status for status in NODE_STATUSES if status in set(status_of.values())]
        incoming = {node_id: 0 for node_id in status_of}
        transitions: dict[tuple[str, str], int] = {}
        for edge in self._edges_of(graph):
            source_id = _as_text(getattr(edge, "source", ""))
            target_id = _as_text(getattr(edge, "target", ""))
            if source_id in status_of and target_id in status_of:
                incoming[target_id] += 1
                key = (status_of[source_id], status_of[target_id])
                transitions[key] = transitions.get(key, 0) + 1

        roots = [
            status
            for status in present
            if any(status_of[node_id] == status and incoming.get(node_id, 0) == 0 for node_id in status_of)
        ]
        if roots:
            for status in roots:
                lines.append(f"    [*] --> {status}")
        else:
            lines.append(
                f"    %% no root node (every node has an incoming edge); entry shown into {present[0]}"
            )
            lines.append(f"    [*] --> {present[0]}")
        for (from_status, to_status) in sorted(transitions):
            lines.append(
                f"    {from_status} --> {to_status} : {transitions[(from_status, to_status)]} edge(s)"
            )
        for status in present:
            members = [node_id for node_id in status_of if status_of[node_id] == status]
            shown = members[:8]
            text = ", ".join(shown)
            if len(members) > len(shown):
                text += f", ... (+{len(members) - len(shown)} more)"
            lines.append(
                f"    note right of {status} : {len(members)} node(s): {self._state_note(text)}"
            )
        return "\n".join(lines)

    def _state_note(self, value: Any) -> str:
        return self._sequence_text(value)

    # ------------------------------------------------------------------ shared bits

    def _issue_comments(self, issues: Sequence[Any], *, limit: int = 5) -> list[str]:
        seen: set[tuple[str, str, str, str]] = set()
        unique: list[Any] = []
        for issue in issues:
            key = (
                _one_line(getattr(issue, "severity", "")),
                _one_line(getattr(issue, "code", "")),
                _one_line(getattr(issue, "where", "")),
                _one_line(getattr(issue, "message", "")),
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(issue)
        lines: list[str] = []
        total = len(unique)
        for issue in unique[:limit]:
            severity = (_one_line(getattr(issue, "severity", "")) or "info").upper()
            code = _one_line(getattr(issue, "code", "")) or "flowview.issue"
            message = _one_line(getattr(issue, "message", ""))
            line = f"    %% ISSUE {severity} {code}: {message}"
            where = _one_line(getattr(issue, "where", ""))
            if where:
                line += f" [{where}]"
            lines.append(line)
        if total > limit:
            lines.append(f"    %% ... and {total - limit} more issue(s)")
        return lines

    def _placeholder(self, what: str, reason: Any, extra: Sequence[str] = ()) -> str:
        """A clearly-labelled, still-valid diagram for a document that could not be drawn."""
        try:
            text = _one_line(reason, limit=180) or "unknown reason"
            lines = ["flowchart TD"]
            lines.append(f"    %% FlowView could not render the {what}: {text}")
            for line in extra:
                lines.append(f"    %% {_one_line(line)}")
            lines.append(
                f'    flowview_render_error["FlowView could not render the {what}"]:::flowview_error'
            )
            lines.append(f"    classDef flowview_error {_STATUS_CLASSDEFS['error']};")
            return "\n".join(lines)
        except Exception:  # noqa: BLE001
            return _PLACEHOLDER_FALLBACK


__all__ = ["MermaidRenderer"]

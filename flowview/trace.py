"""Defensive parsers that turn recorded backend payloads into FlowView traces."""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .analysis import build_document
from .model import STEP_STATUSES, FlowDocument, FlowEvent, FlowIssue, FlowTrace

PHASE_INSPECT = "inspect"
PHASE_PATCH = "patch"
PHASE_EXECUTE = "execute"
PHASE_PROPOSE = "propose"
PHASE_OTHER = "other"

#: The documented tool -> phase table for agent tool calls (backend/main.py TOOL_SCHEMAS).
TOOL_PHASE_MAP: Mapping[str, str] = {
    "inspect_upload": PHASE_INSPECT,
    "get_graph": PHASE_INSPECT,
    "apply_graph_patch": PHASE_PATCH,
    "run_workflow": PHASE_EXECUTE,
    "propose_tool_recipe": PHASE_PROPOSE,
    "propose_node_revision": PHASE_PROPOSE,
    "add_skill_node": PHASE_PROPOSE,
}

MAX_EVENTS = 500


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return default


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def _phase_for(tool: str) -> str:
    return TOOL_PHASE_MAP.get(tool.strip(), PHASE_OTHER)


def _error_text(value: Any, limit: int = 500) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, Mapping):
        code = _text(value.get("code")).strip()
        message = _text(value.get("message")).strip()
        if code and message:
            return f"{code}: {message}"
        return code or message or None
    try:
        encoded = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        encoded = _text(value)
    encoded = encoded.strip()
    return encoded[:limit] if encoded else None


def _result_digest(result: Any) -> str | None:
    """A short, deterministic hint about what a tool call returned."""
    if result is None:
        return None
    if isinstance(result, Mapping):
        state = result.get("state")
        if isinstance(state, Mapping):
            version = state.get("version")
            if isinstance(version, (int, float)) and not isinstance(version, bool):
                return f"state version {int(version)}"
        kind = _text(result.get("kind")).strip()
        if kind:
            return f"result kind: {kind}"
        node_id = _text(result.get("node_id")).strip()
        if node_id:
            return f"node_id: {node_id}"
        return f"{len(result)} result key(s)"
    if isinstance(result, (list, tuple)):
        return f"{len(result)} item(s)"
    return None


def _event_from_tool(item: Any) -> tuple[FlowEvent | None, list[FlowIssue]]:
    """One ``/api/chat`` trace item: {"tool": ..., "ok": bool, "result"/"error": ...}."""
    data = _mapping(item)
    issues: list[FlowIssue] = []
    name = _text(data.get("tool")).strip() or _text(data.get("name")).strip()
    if not name:
        return None, [
            FlowIssue(
                severity="warning",
                code="trace.event_without_tool",
                message="A recorded event carries no tool name and was skipped.",
                where="flowview/trace.py",
            )
        ]

    ok = data.get("ok")
    error = _error_text(data.get("error"))
    if isinstance(ok, bool):
        status = "completed" if ok else "error"
    elif error:
        status = "error"
    else:
        status = "unknown"
        issues.append(
            FlowIssue(
                severity="warning",
                code="trace.event_missing_ok",
                message=f"The event for '{name}' carries no 'ok' flag; its status is reported as 'unknown'.",
                where=name,
                hint="Recorded /api/chat events always carry 'ok'.",
            )
        )

    digest = _result_digest(data.get("result"))
    if status == "completed":
        detail = f"ToolCall completed: {digest}" if digest else "ToolCall completed."
    elif status == "error":
        detail = "ToolCall failed."
    else:
        detail = "ToolCall outcome not recorded."
    if status == "error" and not error:
        error = "The tool call failed without an error message."

    node_id = _text(data.get("node_id")).strip() or None
    if node_id is None:
        node_id = _text(_mapping(data.get("result")).get("node_id")).strip() or None
    tool_id = _text(data.get("tool_id")).strip() or None
    return (
        FlowEvent(
            index=0,
            phase=_phase_for(name),
            name=name,
            status=status,
            detail=detail,
            error=error if status == "error" else None,
            node_id=node_id,
            tool_id=tool_id,
        ),
        issues,
    )


def _event_from_record(item: Any) -> tuple[FlowEvent | None, list[FlowIssue]]:
    """A FlowEvent-shaped mapping, e.g. one line written by :func:`write_trace`."""
    data = _mapping(item)
    if not data:
        return None, [
            FlowIssue(
                severity="warning",
                code="trace.invalid_event",
                message="A recorded event is not a JSON object and was skipped.",
                where="flowview/trace.py",
            )
        ]
    issues: list[FlowIssue] = []
    where = _text(data.get("name")).strip() or _text(data.get("phase")).strip() or None
    raw_status = _text(data.get("status")).strip().lower()
    if raw_status and raw_status not in STEP_STATUSES:
        issues.append(
            FlowIssue(
                severity="warning",
                code="trace.unknown_status",
                message=f"Unknown event status '{raw_status}' mapped to 'unknown'.",
                where=where,
                hint="Expected " + ", ".join(STEP_STATUSES) + ".",
            )
        )
    elif not raw_status:
        issues.append(
            FlowIssue(
                severity="info",
                code="trace.missing_status",
                message="A recorded event carries no status; it is reported as 'unknown'.",
                where=where,
            )
        )
    return FlowEvent.from_dict(data), issues


def _parse_item(item: Any, *, prefer_record: bool = False) -> tuple[FlowEvent | None, list[FlowIssue]]:
    if isinstance(item, Mapping):
        if prefer_record and ("phase" in item or "status" in item):
            return _event_from_record(item)
        if "tool" in item or "ok" in item:
            return _event_from_tool(item)
        if "phase" in item:
            return _event_from_record(item)
        return None, [
            FlowIssue(
                severity="warning",
                code="trace.invalid_event",
                message="A recorded event has neither 'tool' nor 'phase' and was skipped.",
                where="flowview/trace.py",
                detail="keys: " + ", ".join(sorted(str(key) for key in item)[:12]),
            )
        ]
    return None, [
        FlowIssue(
            severity="warning",
            code="trace.invalid_event",
            message=f"A recorded event of type {type(item).__name__} was skipped; events must be JSON objects.",
            where="flowview/trace.py",
        )
    ]


def _phases_to_events(phases: Sequence[Any]) -> tuple[tuple[FlowEvent, ...], list[FlowIssue]]:
    """Flatten a parsed task summary's phases into events (task-summary-shaped payloads)."""
    events: list[FlowEvent] = []
    issues: list[FlowIssue] = []
    for phase in phases:
        name = _text(getattr(phase, "name", "")).strip() or PHASE_OTHER
        for step in getattr(phase, "steps", ()) or ():
            tools = getattr(step, "tools", ()) or ()
            events.append(
                FlowEvent(
                    index=len(events),
                    phase=name,
                    name=_text(getattr(step, "name", "")).strip() or "step",
                    status=_text(getattr(step, "status", "")).strip() or "unknown",
                    detail=_text(getattr(step, "detail", "")).strip() or None,
                    error=_text(getattr(step, "error", "")).strip() or None,
                    node_id=_text(getattr(step, "node_id", "")).strip() or None,
                    tool_id=_text(tools[0]).strip() or None if tools else None,
                )
            )
    return tuple(events), issues


def _looks_like_task_summary(data: Mapping[str, Any]) -> bool:
    return bool(data) and "task_id" in data and (
        "decision" in data or "result" in data or "error_and_handling" in data
    ) and "events" not in data and "trace" not in data


def _renumber(events: Sequence[FlowEvent]) -> tuple[FlowEvent, ...]:
    return tuple(dataclasses.replace(event, index=index) for index, event in enumerate(events))


def parse_trace_payload(payload: Any) -> tuple[tuple[FlowEvent, ...], tuple[FlowIssue, ...]]:
    """Turn one recorded payload into events plus issues; never raises, never guesses silently.

    Recognised shapes: a ``/api/chat`` result object (with a ``trace`` list), a list of
    ``{"tool", "ok", "result"|"error"}`` events, a ``FlowTrace``-shaped mapping (``{"events": [...]}``),
    a single ``FlowEvent``-shaped mapping, and a task-summary-shaped mapping.
    """
    events: list[FlowEvent] = []
    issues: list[FlowIssue] = []

    if isinstance(payload, (list, tuple)):
        for item in payload:
            event, item_issues = _parse_item(item)
            issues.extend(item_issues)
            if event is not None:
                events.append(event)
        return _renumber(events), tuple(issues)

    data = _mapping(payload)
    if not data:
        issues.append(
            FlowIssue(
                severity="warning",
                code="trace.unknown_payload",
                message=f"The payload of type {type(payload).__name__} is not a recognised trace shape.",
                where="flowview/trace.py",
                hint="Expected a /api/chat result, a list of tool events, a FlowTrace mapping or a task summary.",
            )
        )
        return (), tuple(issues)

    if isinstance(data.get("events"), (list, tuple)):
        for item in _sequence(data.get("events")):
            event, item_issues = _parse_item(item, prefer_record=True)
            issues.extend(item_issues)
            if event is not None:
                events.append(event)
        return _renumber(events), tuple(issues)

    if isinstance(data.get("trace"), (list, tuple)):
        for item in _sequence(data.get("trace")):
            event, item_issues = _parse_item(item)
            issues.extend(item_issues)
            if event is not None:
                events.append(event)
        return _renumber(events), tuple(issues)

    if _looks_like_task_summary(data):
        from .tasks import parse_task_summary

        document = parse_task_summary(data)
        issues.extend(document.issues)
        derived, derived_issues = _phases_to_events(document.phases)
        issues.extend(derived_issues)
        events.extend(derived)
        return _renumber(events), tuple(issues)

    if "tool" in data or "ok" in data:
        event, item_issues = _event_from_tool(data)
        issues.extend(item_issues)
        if event is not None:
            events.append(event)
        return _renumber(events), tuple(issues)

    if "phase" in data:
        event, item_issues = _event_from_record(data)
        issues.extend(item_issues)
        if event is not None:
            events.append(event)
        return _renumber(events), tuple(issues)

    issues.append(
        FlowIssue(
            severity="warning",
            code="trace.unknown_payload",
            message="The mapping is not a recognised trace shape and produced no events.",
            where="flowview/trace.py",
            detail="keys: " + ", ".join(sorted(data)[:12]),
            hint="Expected 'trace', 'events', 'tool' or a task summary with 'task_id'.",
        )
    )
    return (), tuple(issues)


def parse_trace_jsonl(text: str) -> tuple[tuple[FlowEvent, ...], tuple[FlowIssue, ...]]:
    """Read a JSONL trace: one payload per line, blank lines skipped, bad lines reported."""
    if not isinstance(text, str) or not text.strip():
        return (), (
            FlowIssue(
                severity="info",
                code="trace.empty_input",
                message="The trace text is empty; there is nothing to replay.",
                where="flowview/trace.py",
            ),
        )

    events: list[FlowEvent] = []
    issues: list[FlowIssue] = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except (ValueError, TypeError) as exc:
            issues.append(
                FlowIssue(
                    severity="warning",
                    code="trace.bad_line",
                    message=f"Trace line {number} is not valid JSON and was skipped.",
                    where=f"line {number}",
                    detail=f"{type(exc).__name__}: {exc}",
                    hint="The remaining lines were still read.",
                )
            )
            continue
        parsed, parsed_issues = parse_trace_payload(payload)
        events.extend(parsed)
        issues.extend(parsed_issues)
    return _renumber(events), tuple(issues)


def trace_from_chat_result(result: Mapping[str, Any]) -> FlowTrace:
    """The ``POST /api/chat`` response: its ``trace`` array plus task/trace correlation ids."""
    data = _mapping(result)
    events, issues = parse_trace_payload(data)
    collected = list(issues)
    error_text = _error_text(data.get("error"))
    if error_text:
        collected.append(
            FlowIssue(
                severity="warning",
                code="trace.chat_error",
                message="The agent runtime reported an error for this conversation.",
                where=_text(data.get("task_id")).strip() or None,
                detail=error_text,
            )
        )
        events = (
            *events,
            FlowEvent(
                index=len(events),
                phase=PHASE_OTHER,
                name="chat error",
                status="error",
                detail="The agent runtime reported an error.",
                error=error_text,
            ),
        )
    if not data:
        collected.append(
            FlowIssue(
                severity="warning",
                code="trace.unknown_payload",
                message="The chat result is empty or not a JSON object.",
                where="flowview/trace.py",
            )
        )
    return FlowTrace(
        events=_renumber(events),
        task_id=_text(data.get("task_id")).strip() or None,
        trace_id=_text(data.get("trace_id")).strip() or None,
        source="POST /api/chat",
        phases=(),
        issues=tuple(collected),
    )


def _payload_id(payload: Any, key: str) -> str | None:
    if isinstance(payload, Mapping):
        return _text(payload.get(key)).strip() or None
    return None


def document_from_trace_payload(
    payloads: Sequence[Any],
    *,
    source: str,
    issues: Sequence[FlowIssue] = (),
    full: bool = False,
) -> FlowDocument:
    """Merge every payload into one trace document, capped at :data:`MAX_EVENTS` unless ``full``."""
    source_text = source if isinstance(source, str) else _text(source)
    collected: list[FlowIssue] = [item for item in (issues or ()) if isinstance(item, FlowIssue)]
    items = payloads if isinstance(payloads, (list, tuple)) else [payloads]

    events: list[FlowEvent] = []
    task_id: str | None = None
    trace_id: str | None = None
    for payload in items:
        parsed, parsed_issues = parse_trace_payload(payload)
        events.extend(parsed)
        collected.extend(parsed_issues)
        if task_id is None:
            task_id = _payload_id(payload, "task_id")
        if trace_id is None:
            trace_id = _payload_id(payload, "trace_id")

    truncated: list[str] = []
    total = len(events)
    if not full and total > MAX_EVENTS:
        events = events[:MAX_EVENTS]
        truncated.append(f"events>{MAX_EVENTS}")
    if not events:
        collected.append(
            FlowIssue(
                severity="info",
                code="trace.no_events",
                message="No trace event was found in the given payload(s).",
                where=source_text or None,
                hint="Check the file with python -m flowview doctor.",
            )
        )

    # The parse findings belong on the document, not on both the document and the trace:
    # ``build_document`` already folds trace.issues into document.issues, while
    # ``FlowDocument.all_issues()`` (what the CLI prints) re-adds trace.issues, which would
    # show every warning twice.
    trace = FlowTrace(
        events=_renumber(events),
        task_id=task_id,
        trace_id=trace_id,
        source=source_text,
        phases=(),
        issues=(),
    )
    title = "MatFlow recorded trace" + (f" ({task_id})" if task_id else "")
    document = build_document(
        title=title,
        source=source_text,
        trace=trace,
        issues=tuple(collected),
        meta={"mode": "observed", "events_total": str(total)},
        modes=("observed",),
    )
    if truncated:
        document = dataclasses.replace(
            document,
            truncated=tuple(dict.fromkeys((*document.truncated, *truncated))),
        )
    return document


def write_trace(trace: FlowTrace, path: Path) -> Path:
    """Persist a trace as JSONL: an optional correlation header, then one line per event.

    The header line (written only when the trace carries a task id, trace id or source) keeps
    ``flowview flow --from-file`` able to report the correlation ids on read-back; the remaining
    lines are one :class:`FlowEvent` object each, in recorded order. Parent directories are
    created when missing.
    """
    target = Path(path).expanduser()
    parent = target.parent
    if str(parent):
        parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if isinstance(trace, FlowTrace):
        header: dict[str, Any] = {}
        if trace.task_id:
            header["task_id"] = trace.task_id
        if trace.trace_id:
            header["trace_id"] = trace.trace_id
        if trace.source:
            header["source"] = trace.source
        if header:
            header["events"] = []
            lines.append(json.dumps(header, ensure_ascii=False))
        events = trace.ordered_events
    else:
        events = ()
    lines.extend(json.dumps(event.to_dict(), ensure_ascii=False) for event in events)
    target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return target


__all__ = [
    "MAX_EVENTS",
    "PHASE_EXECUTE",
    "PHASE_INSPECT",
    "PHASE_OTHER",
    "PHASE_PATCH",
    "PHASE_PROPOSE",
    "TOOL_PHASE_MAP",
    "document_from_trace_payload",
    "parse_trace_jsonl",
    "parse_trace_payload",
    "trace_from_chat_result",
    "write_trace",
]

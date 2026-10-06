"""Defensive parsing of recorded MatFlow task summaries into FlowView documents."""
from __future__ import annotations

import dataclasses
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from .analysis import build_document, dedupe_issues, phase_status, summarize_steps
from .model import FlowDocument, FlowIssue, FlowPhase, FlowStep, safe_text

#: The status vocabulary backend/contracts.py TaskLogSummary allows.
TASK_STATUSES: tuple[str, ...] = (
    "routed",
    "waiting_for_confirmation",
    "completed",
    "waiting",
    "failed",
)

#: backend/contracts.py ExecutionResult.status values.
EXECUTION_STATUSES: tuple[str, ...] = ("completed", "waiting", "failed", "cancelled")

_TASK_STATUS_STEP: Mapping[str, str] = {
    "completed": "completed",
    "failed": "error",
    "waiting": "waiting",
    "waiting_for_confirmation": "waiting",
    "routed": "pending",
}

_EXECUTION_STATUS_STEP: Mapping[str, str] = {
    "completed": "completed",
    "waiting": "waiting",
    "failed": "error",
    # A cancelled run is stopped on purpose: it never completed, and it is not a failure.
    "cancelled": "skipped",
}

_NO_RESULT_STEP: Mapping[str, str] = {
    "routed": "pending",
    "waiting_for_confirmation": "pending",
    "waiting": "pending",
    "failed": "error",
}


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        # ``safe_text`` never raises: an integer above 4300 digits cannot be stringified by CPython.
        return safe_text(value, default)
    return default


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, (str, bytes, Mapping)) or value is None:
        return []
    try:
        return list(value)
    except TypeError:
        return []


def _short(value: Any, limit: int = 160) -> str:
    text = " ".join(_text(value).split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "\u2026"


def _confidence_text(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "not recorded"
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return "not recorded"
    return f"{number:.2f}" if math.isfinite(number) else "not recorded"


def _tool_label(value: Any) -> str:
    if isinstance(value, str):
        return value.strip() or "unknown tool"
    data = _mapping(value)
    for key in ("registered_id", "tool_id", "id", "label"):
        label = _text(data.get(key)).strip()
        if label:
            return label
    return "unknown tool"


def _tool_list(items: Sequence[Any], limit: int = 6) -> str:
    labels = [_tool_label(item) for item in items]
    if not labels:
        return "none"
    if len(labels) > limit:
        return ", ".join(labels[:limit]) + f" (+{len(labels) - limit} more)"
    return ", ".join(labels)


def _confirmation(decision: Mapping[str, Any], status: str) -> bool | None:
    """True/False when the record says so, otherwise inferred from the recorded status."""
    raw = decision.get("requires_human_confirmation")
    if isinstance(raw, bool):
        return raw
    if status == "waiting_for_confirmation":
        return True
    if status == "routed":
        # record_routing() writes "routed" only when no confirmation was required.
        return False
    return None


def _confirmation_text(value: bool | None) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "not recorded in this summary"


def _output_preview(value: Any, limit: int = 200) -> str:
    if value is None:
        return "no output recorded"
    if isinstance(value, Mapping):
        kind = _text(value.get("kind")).strip()
        encoded = json.dumps(value, ensure_ascii=False, default=str)
        preview = _short(encoded, limit)
        keys = ", ".join(list(value)[:8]) or "no keys"
        return f"output keys: {keys}; {preview}" if not kind else f"output kind: {kind}; {preview}"
    return _short(value, limit) or "output recorded"


def _route_phase(
    *,
    prompt: str,
    decision: Mapping[str, Any],
    status: str,
    issues: list[FlowIssue],
) -> FlowPhase:
    steps: list[FlowStep] = [
        FlowStep(
            name="prompt recorded",
            status="completed" if prompt else "unknown",
            detail=f'user prompt: "{_short(prompt)}"' if prompt else "no user prompt recorded",
        )
    ]
    if not decision:
        steps.append(
            FlowStep(
                name="no routing decision recorded",
                status="unknown",
                detail="the record carries no decision block, so no candidates or rationale are known",
            )
        )
        issues.append(
            FlowIssue(
                severity="warning",
                code="task.missing_decision",
                message="A task summary carries no routing decision block.",
                where="flowview/tasks.py",
                hint="Check the record in data/audit/task_summaries.jsonl.",
            )
        )
        return FlowPhase(name="route", title="Route", steps=tuple(steps))

    has_candidates = "candidate_tools" in decision
    candidates = _sequence(decision.get("candidate_tools"))
    selected = _sequence(decision.get("selected_tools"))
    confidence = decision.get("confidence")
    rationale = _text(decision.get("rationale"))
    confirmation = _confirmation(decision, status)

    if has_candidates:
        detail = (
            f"{len(candidates)} candidate tool(s) considered: {_tool_list(candidates)}"
            if candidates
            else "no active compatible tool matched the request"
        )
        steps.append(FlowStep(name="candidates considered", status="completed", detail=detail))
    else:
        steps.append(
            FlowStep(
                name="candidates considered",
                status="unknown",
                detail="the record does not carry a candidate_tools list",
            )
        )

    if selected:
        selected_name = f"selected {_tool_list(selected, limit=3)}"
        selected_status = "waiting" if confirmation is True else "completed"
    else:
        selected_name = "no tool selected"
        selected_status = "waiting" if confirmation is True else "unknown"
    steps.append(
        FlowStep(
            name=selected_name,
            status=selected_status,
            detail=(
                f"confidence {_confidence_text(confidence)}; "
                f"human confirmation required: {_confirmation_text(confirmation)}; "
                f"rationale: {_short(rationale) or 'not recorded'}"
            ),
            tools=tuple(_tool_label(item) for item in selected),
        )
    )

    opinions = _sequence(decision.get("model_opinions"))
    if opinions:
        profiles: list[str] = []
        for opinion in opinions:
            data = _mapping(opinion)
            label = _text(data.get("profile")).strip() or _text(data.get("model")).strip() or "unknown profile"
            picked = _text(data.get("selected_tool_id")).strip()
            profiles.append(f"{label} -> {picked or 'no selection'}")
        steps.append(
            FlowStep(
                name=f"{len(opinions)} model opinion(s)",
                status="completed",
                detail="; ".join(_short(item, 80) for item in profiles),
            )
        )
    return FlowPhase(name="route", title="Route", steps=tuple(steps))


def _error_info(
    error_and_handling: Mapping[str, Any],
    result: Mapping[str, Any],
    status: str,
) -> tuple[str, str] | None:
    """(code, message) when the record reports a failure, else None."""
    code = ""
    message = ""
    raw_error = error_and_handling.get("error")
    if isinstance(raw_error, Mapping):
        code = _text(raw_error.get("code")).strip()
        message = _text(raw_error.get("message")).strip()
    elif isinstance(raw_error, str):
        message = raw_error.strip()

    if not code:
        execution_status = _text(result.get("execution_status")).strip().lower()
        if execution_status == "failed":
            code = "execution_failed"
    if not message:
        output = result.get("output")
        if isinstance(output, Mapping):
            message = _text(output.get("error")).strip()
    if not code and not message and status == "failed":
        code = "task_failed"
    if not code and not message:
        return None
    if not message:
        message = f"The task reported '{code}'."
    return (code or "execution_failed", message)


def _execute_phase(
    *,
    result: Mapping[str, Any],
    error_and_handling: Mapping[str, Any],
    status: str,
    issues: list[FlowIssue],
) -> FlowPhase:
    steps: list[FlowStep] = []
    execution_status = _text(result.get("execution_status")).strip().lower()
    tool = result.get("executed_tool")
    schema_valid = result.get("output_schema_valid")
    output = result.get("output")

    if result:
        if execution_status and execution_status not in EXECUTION_STATUSES:
            issues.append(
                FlowIssue(
                    severity="warning",
                    code="task.unknown_execution_status",
                    message=(
                        f"Unknown execution status '{execution_status}' mapped to 'unknown'; "
                        "it is never reported as completed."
                    ),
                    where="flowview/tasks.py",
                    hint="Expected " + ", ".join(EXECUTION_STATUSES) + ".",
                )
            )
        steps.append(
            FlowStep(
                name=f"executed {_tool_label(tool)}" if tool else "execution recorded",
                status=_EXECUTION_STATUS_STEP.get(execution_status, "unknown"),
                detail=(
                    f"execution status: {execution_status or 'not recorded'}; "
                    f"tool version: {_text(_mapping(tool).get('version')).strip() or 'not recorded'}"
                ),
                tools=(_tool_label(tool),) if tool else (),
            )
        )
        if schema_valid is True:
            schema_status, schema_text = "completed", "true"
        elif schema_valid is False:
            schema_status, schema_text = "error", "false"
        else:
            schema_status, schema_text = "unknown", "not recorded"
        steps.append(
            FlowStep(
                name="output schema validated",
                status=schema_status,
                detail=f"output_schema_valid: {schema_text}",
            )
        )
        steps.append(
            FlowStep(
                name="output recorded",
                status="completed" if output is not None else "unknown",
                detail=_output_preview(output),
            )
        )
    else:
        steps.append(
            FlowStep(
                name="no execution recorded",
                status=_NO_RESULT_STEP.get(status, "unknown"),
                detail="the record carries result: null, so no tool output was observed",
            )
        )

    error_info = _error_info(error_and_handling, result, status)
    if error_info is not None:
        code, message = error_info
        steps.append(
            FlowStep(
                name=f"execution error: {code}",
                status="error",
                detail=message,
                error=message,
            )
        )
    return FlowPhase(name="execute", title="Execute", steps=tuple(steps))


def _outcome_phase(
    *,
    status: str,
    handling: str,
    error_info: tuple[str, str] | None,
) -> FlowPhase:
    steps: list[FlowStep] = [
        FlowStep(
            name=f"outcome: {status or 'not recorded'}",
            status=_TASK_STATUS_STEP.get(status, "unknown"),
            detail=f"handling: {_short(handling)}" if handling else "no handling sentence recorded",
            error=error_info[1] if (error_info is not None and status == "failed") else None,
        )
    ]
    if error_info is not None:
        code, message = error_info
        steps.append(
            FlowStep(
                name=f"reported error: {code}",
                status="error",
                detail=message,
                error=message,
            )
        )
    return FlowPhase(name="outcome", title="Outcome", steps=tuple(steps))


def parse_task_summary(payload: Mapping[str, Any]) -> FlowDocument:
    """Mirror one TaskLogSummary record as a route/execute/outcome FlowDocument."""
    issues: list[FlowIssue] = []
    data = _mapping(payload)
    if not data:
        issues.append(
            FlowIssue(
                severity="warning",
                code="task.empty_payload",
                message="The task summary payload is empty or not a JSON object.",
                where="flowview/tasks.py",
                hint="Pass one record from data/audit/task_summaries.jsonl.",
            )
        )

    task_id = _text(data.get("task_id")).strip() or "unknown-task"
    trace_id = _text(data.get("trace_id")).strip()
    status = _text(data.get("status")).strip().lower()
    if not status:
        issues.append(
            FlowIssue(
                severity="warning",
                code="task.missing_status",
                message="The task summary carries no status; the outcome is reported as 'unknown'.",
                where=task_id,
                hint="Expected " + ", ".join(TASK_STATUSES) + ".",
            )
        )
    elif status not in TASK_STATUSES:
        issues.append(
            FlowIssue(
                severity="warning",
                code="task.unknown_status",
                message=f"Unknown task status '{status}' mapped to 'unknown'; it is never reported as completed.",
                where=task_id,
                hint="Expected " + ", ".join(TASK_STATUSES) + ".",
            )
        )

    prompt = _text(data.get("user_prompt")).strip()
    decision = _mapping(data.get("decision"))
    result = _mapping(data.get("result"))
    error_and_handling = _mapping(data.get("error_and_handling"))
    handling = _text(error_and_handling.get("handling")).strip()
    error_info = _error_info(error_and_handling, result, status)

    phases = (
        _route_phase(prompt=prompt, decision=decision, status=status, issues=issues),
        _execute_phase(result=result, error_and_handling=error_and_handling, status=status, issues=issues),
        _outcome_phase(status=status, handling=handling, error_info=error_info),
    )

    meta: dict[str, str] = {
        "mode": "recorded",
        "task_id": task_id,
        "status": status or "unknown",
        "steps": str(sum(len(phase.steps) for phase in phases)),
    }
    if trace_id:
        meta["trace_id"] = trace_id
    recorded_at = _text(data.get("recorded_at")).strip() or _text(data.get("timestamp")).strip()
    if recorded_at:
        meta["recorded_at"] = recorded_at

    return build_document(
        title=f"task {task_id}",
        source=f"task summary {task_id}",
        phases=phases,
        issues=tuple(issues),
        meta=meta,
        modes=("recorded",),
    )


def _parse_json_line(line: str, path: Path, number: int) -> tuple[Any, FlowIssue | None]:
    try:
        return json.loads(line), None
    except (ValueError, TypeError) as exc:
        return None, FlowIssue(
            severity="warning",
            code="task.unparsable_line",
            message=f"Line {number} of {path.name} is not valid JSON and was skipped.",
            where=f"{path}:{number}",
            detail=f"{type(exc).__name__}: {exc}",
            hint="The remaining records were still read.",
        )


def load_task_summaries(path: Path) -> tuple[FlowDocument, ...]:
    """Read a JSONL log in file order; unparsable lines are skipped and reported as issues.

    The collected issues are attached to the first returned document so the CLI can print them.
    A missing or unreadable file returns ``()``. When a file exists but holds no usable record,
    one issue-only document is returned so the corruption stays visible instead of silent.
    """
    resolved = _path_or_none(path)
    if resolved is None:
        return ()
    try:
        text = resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ()

    documents: list[FlowDocument] = []
    collected: list[FlowIssue] = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        payload, issue = _parse_json_line(line, resolved, number)
        if issue is not None:
            collected.append(issue)
            continue
        if not isinstance(payload, Mapping):
            collected.append(
                FlowIssue(
                    severity="warning",
                    code="task.unparsable_line",
                    message=f"Line {number} of {resolved.name} is JSON but not an object and was skipped.",
                    where=f"{resolved}:{number}",
                )
            )
            continue
        documents.append(parse_task_summary(payload))

    if documents and collected:
        first = documents[0]
        documents[0] = dataclasses.replace(first, issues=tuple((*first.issues, *collected)))
    if not documents and collected:
        return (
            build_document(
                title=f"task summary log {resolved.name}",
                source=str(resolved),
                issues=tuple(collected),
                meta={"mode": "recorded", "records": "0"},
                modes=("recorded",),
            ),
        )
    return tuple(documents)


def _parse_documents(text: str, path: Path) -> tuple[list[Mapping[str, Any]], list[FlowIssue]]:
    """Split one file that may be a single JSON object, a JSON array, or JSONL."""
    issues: list[FlowIssue] = []
    try:
        whole = json.loads(text)
    except (ValueError, TypeError):
        whole = None
    if isinstance(whole, Mapping):
        return [whole], issues
    if isinstance(whole, list):
        records: list[Mapping[str, Any]] = []
        for index, item in enumerate(whole, 1):
            if isinstance(item, Mapping):
                records.append(item)
            else:
                issues.append(
                    FlowIssue(
                        severity="warning",
                        code="task.unparsable_line",
                        message=f"Array item {index} of {path.name} is not an object and was skipped.",
                        where=f"{path}#{index}",
                    )
                )
        return records, issues

    records = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        payload, issue = _parse_json_line(line, path, number)
        if issue is not None:
            issues.append(issue)
            continue
        if isinstance(payload, Mapping):
            records.append(payload)
        else:
            issues.append(
                FlowIssue(
                    severity="warning",
                    code="task.unparsable_line",
                    message=f"Line {number} of {path.name} is JSON but not an object and was skipped.",
                    where=f"{path}:{number}",
                )
            )
    return records, issues


def load_task_document(path: Path) -> FlowDocument:
    """Read one summary file (single JSON object, JSON array, or JSONL) and show its last record."""
    resolved = _path_or_none(path)
    shown = str(resolved) if resolved is not None else str(path)

    def _failure(code: str, message: str, *, hint: str | None = None, detail: str | None = None) -> FlowDocument:
        return build_document(
            title="task summary",
            source=shown,
            issues=(
                FlowIssue(
                    severity="error",
                    code=code,
                    message=message,
                    where=shown,
                    hint=hint,
                    detail=detail,
                ),
            ),
            meta={"mode": "recorded"},
            modes=("recorded",),
        )

    if resolved is None or not resolved.exists():
        return _failure(
            "task.missing_file",
            f"No task summary file exists at {shown}.",
            hint="Pass an existing JSON or JSONL file, or run python -m flowview summary.",
        )
    if resolved.is_dir():
        return _failure("task.not_a_file", f"{shown} is a directory, not a task summary file.")
    try:
        text = resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return _failure(
            "task.unreadable",
            f"Cannot read {shown}.",
            detail=f"{type(exc).__name__}: {exc}",
        )
    if not text.strip():
        return _failure("task.empty_file", f"{shown} is empty; there is no record to show.")

    payloads, issues = _parse_documents(text, resolved)
    if not payloads:
        issue = issues[0] if issues else FlowIssue(
            severity="error",
            code="task.empty_file",
            message=f"{shown} contains no readable task summary record.",
            where=shown,
        )
        return build_document(
            title="task summary",
            source=shown,
            issues=(*issues[:1],) if issues else (issue,),
            meta={"mode": "recorded"},
            modes=("recorded",),
        )

    document = parse_task_summary(payloads[-1])
    extra: list[FlowIssue] = list(issues)
    if len(payloads) > 1:
        extra.append(
            FlowIssue(
                severity="info",
                code="task.multiple_records",
                message=(
                    f"{shown} holds {len(payloads)} records for this task; the last one "
                    "(the latest recorded state) is shown."
                ),
                where=shown,
            )
        )
    if extra:
        document = dataclasses.replace(document, issues=tuple((*document.issues, *extra)))
    return dataclasses.replace(document, source=shown)


def latest_task_documents(path: Path, *, limit: int = 10) -> tuple[FlowDocument, ...]:
    """The newest ``limit`` documents by ``recorded_at`` when present, else the last in file order."""
    documents = load_task_summaries(path)
    if not documents:
        return ()
    try:
        wanted = int(limit)
    except (TypeError, ValueError):
        wanted = 10
    if wanted <= 0:
        return ()

    if any(document.meta.get("recorded_at") for document in documents):
        ordered = sorted(
            enumerate(documents),
            key=lambda pair: (pair[1].meta.get("recorded_at", ""), pair[0]),
        )
        documents = tuple(document for _, document in ordered)
    return tuple(documents[-wanted:])


def _phase_digest(phase: FlowPhase) -> str:
    counts = summarize_steps(phase.steps)
    summary = ", ".join(f"{count} {status}" for status, count in counts.items() if count)
    failures = [step for step in phase.steps if step.status == "error"]
    detail = f"{len(phase.steps)} step(s): {summary or 'none'}"
    if failures:
        first = failures[0]
        detail += f"; first error: {_short(first.error or first.name, 120)}"
    return detail


def _fold_phases(phases: Sequence[FlowPhase]) -> tuple[FlowStep, ...]:
    """Fold a task's phases into at most four steps, keeping every status visible."""
    items = [phase for phase in phases if isinstance(phase, FlowPhase)]
    if not items:
        return (FlowStep(name="no recorded phase", status="unknown", detail="this document carried no phases"),)
    steps = [
        FlowStep(name=phase.title or phase.name, status=phase_status(phase), detail=_phase_digest(phase))
        for phase in items
    ]
    if len(steps) > 4:
        head, tail = steps[:3], steps[3:]
        folded_status = phase_status(FlowPhase(name="folded", title="folded", steps=tuple(tail)))
        head.append(
            FlowStep(
                name=f"+{len(tail)} more phase(s)",
                status=folded_status,
                detail="; ".join(step.name for step in tail),
            )
        )
        steps = head
    return tuple(steps)


def summaries_document(
    documents: Sequence[FlowDocument],
    *,
    limit: int = 10,
    source: str = "",
) -> FlowDocument:
    """Fold recorded task documents into one timeline: one phase per task.

    The summary log is append-only, so a task id may appear several times; the newest record of
    each task is shown once (and phase names stay unique for the renderers). ``limit`` caps how
    many tasks appear; a cap is recorded in ``document.truncated``.
    """
    items = [document for document in documents if isinstance(document, FlowDocument)]
    records = len(items)

    # One phase per task: keep the newest record of every task id, ordered by last appearance.
    last_seen: dict[str, int] = {}
    for index, document in enumerate(items):
        last_seen[_task_key(document, index)] = index
    ordered = [items[index] for index in sorted(last_seen.values())]
    unique_total = len(ordered)

    try:
        wanted = int(limit)
    except (TypeError, ValueError):
        wanted = 10
    wanted = max(0, wanted)

    truncated: list[str] = []
    if wanted == 0 and unique_total:
        shown = []
        truncated.append("tasks>0")
    elif unique_total > wanted:
        shown = ordered[-wanted:]
        truncated.append(f"tasks>{wanted}")
    else:
        shown = ordered

    phases: list[FlowPhase] = []
    statuses: Counter[str] = Counter()
    failed = 0
    for document in shown:
        task_id = document.meta.get("task_id") or "unknown-task"
        status = document.meta.get("status") or "unknown"
        statuses[status] += 1
        steps = _fold_phases(document.phases)
        if any(step.status == "error" for step in steps):
            failed += 1
        phases.append(FlowPhase(name=task_id, title=f"task {task_id}", steps=steps))

    issues: list[FlowIssue] = []
    # Findings the loader attached to a record (a skipped, unparsable JSONL line, for instance)
    # must survive the fold; otherwise corruption in the log is silently dropped.
    for document in items:
        issues.extend(document.issues)
        if document.graph is not None:
            issues.extend(document.graph.issues)
        if document.trace is not None:
            issues.extend(document.trace.issues)
    if failed:
        issues.append(
            FlowIssue(
                severity="error",
                code="task.failed",
                message=f"{failed} of {len(shown)} displayed task(s) ended in a failed state.",
                where=source or None,
                hint="Run 'python -m flowview summary --task TASK_ID' to inspect one task.",
            )
        )
    issues = dedupe_issues(issues)

    meta: dict[str, str] = {
        "mode": "recorded",
        "tasks": str(len(shown)),
        "tasks_total": str(unique_total),
        "records": str(records),
        "failed": str(failed),
        "statuses": ", ".join(f"{status}={count}" for status, count in sorted(statuses.items())),
    }
    document = build_document(
        title="MatFlow task summary timeline",
        source=source or "recorded task summaries",
        phases=phases,
        issues=tuple(issues),
        meta=meta,
        modes=("recorded",),
    )
    if truncated:
        document = dataclasses.replace(
            document,
            truncated=tuple(dict.fromkeys((*document.truncated, *truncated))),
        )
    return document


def _path_or_none(path: Any) -> Path | None:
    if path is None:
        return None
    try:
        return Path(path)
    except (TypeError, ValueError, OSError):
        return None


def _task_key(document: FlowDocument, index: int) -> str:
    """Group records of the same task; documents without an id stay separate."""
    task_id = document.meta.get("task_id")
    if task_id:
        return task_id
    return f"anonymous:{document.source or index}"


__all__ = [
    "EXECUTION_STATUSES",
    "TASK_STATUSES",
    "latest_task_documents",
    "load_task_document",
    "load_task_summaries",
    "parse_task_summary",
    "summaries_document",
]

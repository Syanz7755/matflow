"""Live mode: read the flow from a *running* MatFlow backend over the versioned HTTP contract.

Offline is the default and stays the default. Nothing in this module runs unless the CLI was given
an explicit ``--http URL``: without that flag ``graph``, ``flow``, ``summary`` and ``doctor`` never
open a socket and behave exactly as they did before live mode existed.

Every function here returns a :class:`FlowDocument`. A server that is unreachable, speaks a
different contract, or answers with a payload FlowView cannot mirror becomes an **error** issue on
that document, so the command exits 3 with a readable explanation instead of printing a flow it did
not actually read. Nothing raises.

The one call in the whole package that makes the backend write anything lives here: ``POST
/api/route`` makes the backend record a routing summary in its own audit log, and the document it
produces says so. FlowView itself still writes nothing — no ``--http`` path opens a file for
writing, patches the graph, starts a server or touches ``data/``.
"""
from __future__ import annotations

import math
from dataclasses import replace
from typing import Any, Mapping, Sequence

from . import client
from .analysis import build_document
from .loader import graph_from_payload
from .model import FlowDocument, FlowIssue, FlowPhase, FlowStep, safe_text
from .tasks import parse_task_summary

MAX_TASK_MESSAGE = 4000
DEFAULT_TIMEOUT = client.DEFAULT_TIMEOUT
#: The routing request FlowView sends is a preview, so the task id says so and never collides with a
#: real chat task id.
PREVIEW_TASK_ID = "flowview-http-preview"
#: The same input context the offline preview declares (``backend_adapter.dry_route``). Keeping the
#: two identical means a live and an offline preview of one prompt differ by transport, not by
#: context; ``test_http_live`` pins this against the offline default so the two cannot drift.
DEFAULT_INPUT_TYPES: tuple[str, ...] = ("RawData", "TypedTable")


# ------------------------------------------------------------------------------------- helpers


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        # ``safe_text`` never raises: a payload integer above 4300 digits cannot be stringified.
        return safe_text(value, default)
    return default


def _label(value: Any, default: str = "unknown") -> str:
    text = _text(value).strip()
    return text or default


def _number_text(value: Any, missing: str) -> str:
    """``0.00``-style text for a score/confidence, or ``missing``.

    ``float()`` overflows on an integer too large to convert, and JSON's NaN/Infinity cannot be
    formatted as a comparable number: both become ``missing`` instead of an escaped exception.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return missing
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return missing
    return f"{number:.2f}" if math.isfinite(number) else missing


def _int(value: Any, default: int = 0) -> int:
    limit = 2**63
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        # A version outside 64 bits cannot be carried by the document's JSON later.
        return value if -limit < value < limit else default
    if isinstance(value, float):
        # JSON allows NaN and Infinity: int() raises ValueError/OverflowError on both, which would
        # escape as an unexpected internal error instead of a readable issue.
        if not math.isfinite(value):
            return default
        return int(value)
    if isinstance(value, str):
        try:
            parsed = int(value.strip() or default)
        except ValueError:
            return default
        return parsed if -limit < parsed < limit else default
    return default


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def _as_error(issue: FlowIssue) -> FlowIssue:
    """Promote ``issue`` to ``error``.

    A missing flow is not a note in the margin: when a live endpoint cannot be read there is no flow
    to print, so the command must exit 3 rather than 0 with a warning nobody reads.
    """
    if issue.severity == "error":
        return issue
    return FlowIssue(
        severity="error",
        code=issue.code,
        message=issue.message,
        where=issue.where,
        hint=issue.hint,
        detail=issue.detail,
    )


def _unreachable_issue(issue: FlowIssue, base: str) -> FlowIssue:
    """One code for one condition.

    The transport reports an unreachable server as ``<endpoint>.unreachable``; every live caller
    promotes that to the single documented ``http.unreachable``, keeping the original code in the
    detail so nothing is lost.
    """
    detail = f"reported by the transport as {issue.code}"
    if issue.detail:
        detail += f": {issue.detail}"
    return FlowIssue(
        severity="error",
        code="http.unreachable",
        message=issue.message,
        where=issue.where or base,
        hint=issue.hint,
        detail=detail,
    )


def resolve_base(explicit: str | None = None) -> str:
    """The origin ``--http`` asked for: its value, then ``MATFLOW_API_URL``, then the default."""
    return client.base_url(explicit or None)


def _origin(base: str) -> str:
    """The origin as it may be printed: a credentialed URL is withheld, never echoed.

    The CLI refuses such an origin before calling anything here, so this is defence in depth for
    direct API use; the transport applies the same rule to the URLs it reports.
    """
    return "(origin withheld)" if client.has_credentials(base) else base


def live_issue(url: str, *, action: str, status: int | None, trace_id: str | None, base: str) -> FlowIssue:
    """The info issue every live document carries: where this flow came from."""
    detail = f"HTTP {status}" if status is not None else "no HTTP status"
    if trace_id:
        detail += f", trace id {trace_id}"
    return FlowIssue(
        severity="info",
        code="http.live",
        message=f"This flow was read from a running backend at {_origin(base)} ({action}).",
        where=url,
        hint="Drop --http to read local files instead; offline mode needs no server.",
        detail=detail,
    )


def _probe(base: str, timeout: float) -> tuple[client.LiveProbe, FlowDocument | None]:
    """Check reachability and the API contract before reading anything.

    Returns ``(probe, document)``: a document means the caller must print that instead of a flow,
    because the backend is not reachable at all.
    """
    probed = client.probe(base=base, timeout=timeout)
    if probed.reachable:
        return probed, None
    issue = probed.issues[0] if probed.issues else FlowIssue(
        severity="error",
        code="http.unreachable",
        message=f"Cannot reach a MatFlow backend at {probed.base}.",
    )
    # Three different problems must not share one message. A mistyped origin, a server that is down,
    # and a server that answered HTTP 404 / invalid JSON are all "no probe", but saying "cannot
    # reach" about a server that just answered is a false diagnosis.
    if issue.code.endswith(".unreachable"):
        final, title = _unreachable_issue(issue, probed.base), "Live backend (unreachable)"
    elif issue.code.endswith(".invalid_url"):
        final, title = _as_error(issue), "Live backend (bad --http URL)"
    elif issue.code.endswith(".credentials_not_supported"):
        # Never echo a credentialed origin, and never call it reachable.
        final, title = _as_error(issue), "Live backend (origin refused)"
    else:
        final, title = _as_error(issue), "Live backend (unusable answer)"
    return probed, build_document(
        title=title,
        source=_origin(probed.base),
        issues=(final,),
        meta={
            "mode": "http",
            "transport": "http",
            "base": _origin(probed.base),
            "reachable": "false",
            "issue": final.code,
        },
        modes=("http",),
    )


def _failure(
    title: str,
    action: str,
    result: client.HttpResult,
    *,
    extra: Sequence[FlowIssue] = (),
    base: str = "",
) -> FlowDocument:
    """Turn a failed endpoint call into a document that explains itself and exits 3."""
    issue = result.issue or FlowIssue(
        severity="error",
        code="http.request_failed",
        message=f"The {action} request to {result.url} failed.",
        where=result.url,
        hint="Run 'python -m flowview doctor --http <url>' to diagnose the backend.",
    )
    return build_document(
        title=title,
        source=result.url,
        issues=tuple((*extra, _as_error(issue))),
        meta={
            "mode": "http",
            "transport": "http",
            "action": action,
            "base": base,
            "url": result.url,
            "http_status": "" if result.status is None else str(result.status),
        },
        modes=("http",),
    )


# ----------------------------------------------------------------------------------- endpoints


def graph_document(base: str, *, timeout: float = DEFAULT_TIMEOUT, full: bool = False) -> FlowDocument:
    """Mirror the live workspace graph from ``GET /api/state``."""
    probed, unreachable = _probe(base, timeout)
    if unreachable is not None:
        return unreachable
    result = client.state(base=base, timeout=timeout)
    if not result.ok:
        return _failure("Live workspace graph (unreadable)", "state", result, extra=probed.issues, base=base)
    state = _mapping(result.payload).get("state")
    if not isinstance(state, Mapping):
        return build_document(
            title="Live workspace graph (no state object)",
            source=result.url,
            issues=(
                *probed.issues,
                FlowIssue(
                    severity="error",
                    code="http.state_missing",
                    message="The /api/state response carried no 'state' object, so there is no graph to mirror.",
                    where=result.url,
                    hint="'GET /api/state' must answer {\"state\": {...}}; check the backend version.",
                ),
            ),
            meta={"mode": "http", "transport": "http", "base": base, "url": result.url},
            modes=("http",),
        )
    graph = graph_from_payload(state, source=result.url, full=full)
    return build_document(
        title=f"Live workspace graph: {graph.graph_id}",
        source=result.url,
        graph=graph,
        issues=(
            *probed.issues,
            live_issue(result.url, action="GET /api/state", status=result.status, trace_id=result.trace_id, base=base),
        ),
        meta={
            "mode": "http",
            "transport": "http",
            "base": base,
            "url": result.url,
            "http_status": "" if result.status is None else str(result.status),
        },
        modes=("http", "live"),
    )


def task_document(task_id: str, base: str, *, timeout: float = DEFAULT_TIMEOUT) -> FlowDocument:
    """Mirror one recorded task from ``GET /api/task-summaries/{task_id}``."""
    probed, unreachable = _probe(base, timeout)
    if unreachable is not None:
        return unreachable
    result = client.task_summary(task_id, base=base, timeout=timeout)
    if not result.ok:
        return _failure(f"task {task_id} (live)", "task-summary", result, extra=probed.issues, base=base)
    payload = result.payload
    if not isinstance(payload, Mapping):
        return build_document(
            title=f"task {task_id} (live)",
            source=result.url,
            issues=(
                *probed.issues,
                FlowIssue(
                    severity="error",
                    code="http.task_summary_not_an_object",
                    message="The task-summary response is not a JSON object, so there is no record to replay.",
                    where=result.url,
                ),
            ),
            meta={"mode": "recorded", "transport": "http", "base": base, "url": result.url, "task_id": task_id},
            modes=("recorded", "http"),
        )
    recorded = parse_task_summary(payload)
    return replace(
        recorded,
        source=result.url,
        issues=(
            *recorded.issues,
            *probed.issues,
            live_issue(result.url, action="GET /api/task-summaries", status=result.status, trace_id=result.trace_id, base=base),
        ),
        meta={
            **recorded.meta,
            "transport": "http",
            "base": base,
            "url": result.url,
            "http_status": "" if result.status is None else str(result.status),
        },
    )


def _route_request(
    prompt_text: str,
    base: str,
    timeout: float,
    requested_types: Sequence[str],
    probed: client.LiveProbe,
) -> tuple[dict[str, Any], int, list[FlowIssue]]:
    """Build the routing request the backend would receive, plus the issues that qualify it.

    The request carries only what the caller supplied: the prompt's own characters, the graph version
    read from ``/api/state``, and the input types the live backend actually reports. No marker,
    placeholder or summary text invented by FlowView ever enters ``user_message``.
    """
    issues = list(probed.issues)
    version = 0
    state_result = client.state(base=base, timeout=timeout)
    if state_result.ok:
        state = _mapping(state_result.payload).get("state")
        if isinstance(state, Mapping):
            version = max(0, _int(state.get("version")))
    else:
        issues.append(
            FlowIssue(
                severity="warning",
                code="http.graph_version_unknown",
                message="The current graph version could not be read, so the routing request declares version 0.",
                where=state_result.url,
                hint="The decision may differ from one made against the real graph version.",
                detail=state_result.error,
            )
        )
    reported = _mapping(probed.payload).get("data_types")
    known_types = {_text(item).strip() for item in _sequence(reported) if _text(item).strip()}
    accepted = [item for item in requested_types if not known_types or item in known_types]
    dropped = [item for item in requested_types if item not in accepted]
    if dropped:
        issues.append(
            FlowIssue(
                severity="warning",
                code="http.unknown_input_type",
                message="Ignored input type(s) the live backend does not report: " + ", ".join(sorted(set(dropped))),
                where=base,
                hint="Run 'python -m flowview doctor --http <url>' to see the data types the backend reports.",
            )
        )
    sent = prompt_text[:MAX_TASK_MESSAGE]
    if len(prompt_text) > MAX_TASK_MESSAGE:
        issues.append(
            FlowIssue(
                severity="warning",
                code="http.prompt_truncated_for_backend",
                message=(
                    f"The prompt is {len(prompt_text)} characters, above the backend's "
                    f"{MAX_TASK_MESSAGE}-character user_message limit, so the routing request carried the "
                    f"prompt's own first {MAX_TASK_MESSAGE} characters."
                ),
                where="backend.contracts.TaskState.user_message",
                hint=(
                    "The prompt printed in text and JSON mode is the full text you passed; a diagram label may "
                    "still be elided for display. Only characters you typed were sent: no marker, placeholder "
                    "or summary was added."
                ),
            )
        )
    task = {
        "task_id": PREVIEW_TASK_ID,
        "user_message": sent or "?",
        "graph_version": version,
        "available_input_types": accepted,
    }
    return task, version, issues


def route_document(
    prompt: str,
    base: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    available_input_types: Sequence[str] = DEFAULT_INPUT_TYPES,
) -> FlowDocument:
    """Print what the *running* backend decides for one request (``POST /api/route``)."""
    prompt_text = _text(prompt)
    if not prompt_text.strip():
        return build_document(
            title="Live routing preview (empty prompt)",
            source=client.api_url("api", "route", base=base),
            issues=(
                FlowIssue(
                    severity="error",
                    code="http.empty_prompt",
                    message="A live routing preview needs a non-empty prompt.",
                    where=base,
                    hint='Pass the request text, for example: --prompt "run basic EIS quality checks".',
                ),
            ),
            meta={"mode": "http", "transport": "http", "base": base},
            modes=("http",),
        )
    probed, unreachable = _probe(base, timeout)
    if unreachable is not None:
        return unreachable
    requested = tuple(_text(item).strip() for item in available_input_types if _text(item).strip())
    task, version, issues = _route_request(prompt_text, base, timeout, requested, probed)
    # ``client.route`` wraps the body as {"task": {...}} itself: passing a wrapper here would send
    # {"task": {"task": {...}}} and the backend would reject it as an invalid TaskState.
    result = client.route(task, base=base, timeout=timeout)
    if not result.ok:
        # Even a broken answer may have left a routing summary behind, so the side-effect disclosure
        # travels with the failure — but only if a request was really handed to the transport: a
        # body that could not be serialised (a lone surrogate) never left this process.
        extra: tuple[FlowIssue, ...] = tuple(issues)
        if _request_was_sent(result):
            extra = (
                *issues,
                _route_side_effect_issue(result.url, reached=result.status is not None, recorded_task=""),
            )
        return _failure("Live routing preview (unreadable)", "route", result, extra=extra, base=base)
    if not isinstance(result.payload, Mapping):
        return build_document(
            title="Live routing preview (invalid payload)",
            source=result.url,
            issues=(
                *issues,
                _route_side_effect_issue(result.url, reached=True, recorded_task=""),
                FlowIssue(
                    severity="error",
                    code="http.route_payload_invalid",
                    message="The /api/route response is not a JSON object, so there is no decision to print.",
                    where=result.url,
                ),
            ),
            meta={"mode": "http", "transport": "http", "base": base, "url": result.url},
            modes=("http",),
        )
    return _route_document(prompt_text, result.payload, base=base, version=version, result=result, issues=issues)


def _request_was_sent(result: client.HttpResult) -> bool:
    """Was the exchange actually handed to the transport?

    A body that cannot be serialised, or an origin the transport refuses outright, fails before any
    socket is opened; claiming afterwards that the backend "may have recorded something" would be a
    false disclosure about a request that never existed.
    """
    issue = result.issue
    if issue is None:
        return True
    pre_send = ("unserialisable_request", "invalid_url")
    return not any(issue.code.endswith(suffix) for suffix in pre_send)


def _route_side_effect_issue(url: str, *, reached: bool, recorded_task: str) -> FlowIssue:
    """Disclose that ``POST /api/route`` makes the backend record a routing summary.

    The disclosure must appear whenever the request was **sent**, not only when it succeeded: if the
    answer was unreadable the backend may still have recorded the decision, and a silent side effect
    is exactly what a read-only promise must not hide. When the outcome is unknown the issue is a
    warning, because an unverified side effect is not a neutral fact.
    """
    if recorded_task:
        return FlowIssue(
            severity="info",
            code="http.route_recorded",
            message=(
                "POST /api/route is a decision, not a mutation: the graph is untouched, but the backend "
                f"recorded this routing decision in its task summary log as task {recorded_task}."
            ),
            where=url,
            hint=(
                'Use flowview flow --prompt "..." without --http for a preview that persists nothing, or '
                "run 'flowview summary' afterwards to see the recorded entry."
            ),
        )
    if reached:
        return FlowIssue(
            severity="warning",
            code="http.route_recorded",
            message=(
                "The backend answered the POST /api/route request but the response did not carry the recorded "
                "task id, so whether it wrote a routing summary cannot be confirmed from here."
            ),
            where=url,
            hint="The backend records a routing summary for every accepted POST /api/route; check its task summary log.",
        )
    return FlowIssue(
        severity="warning",
        code="http.route_recorded",
        message=(
            "The POST /api/route request was sent but the backend never answered, so whether a routing summary "
            "was recorded is unknown."
        ),
        where=url,
        hint="Start the backend and re-run, or use offline 'flowview flow --prompt', which persists nothing.",
    )


def _candidate_step(candidate: Any) -> FlowStep:
    data = _mapping(candidate)
    tool_id = _label(data.get("tool_id"))
    score = data.get("score")
    score_text = _number_text(score, "not scored")
    reasons = _sequence(data.get("reasons"))
    reason_text = "; ".join(_text(item).strip() for item in reasons if _text(item).strip()) or "no reason recorded"
    return FlowStep(
        name=f"{tool_id} (candidate)",
        status="pending",
        detail=(
            f"candidate only, nothing executed; score {score_text}; "
            f"version {_label(data.get('version'))}; reasons: {reason_text}"
        ),
        tools=(tool_id,),
    )


def _route_document(
    prompt_text: str,
    payload: Mapping[str, Any],
    *,
    base: str,
    version: int,
    result: client.HttpResult,
    issues: Sequence[FlowIssue],
) -> FlowDocument:
    """Assemble the live routing document from the backend's own decision payload."""
    candidate_steps = [_candidate_step(item) for item in _sequence(payload.get("candidates"))]
    if not candidate_steps:
        candidate_steps.append(
            FlowStep(
                name="no candidate retrieved",
                status="unknown",
                detail="the backend's CandidateRetriever found no active compatible tool for this request",
            )
        )
    selected = [_mapping(item) for item in _sequence(payload.get("selected"))]
    confirmation = payload.get("requires_human_confirmation")
    if selected:
        selected_name = "selected " + ", ".join(_label(item.get("tool_id")) for item in selected)
        selected_status = "waiting" if confirmation is True else "completed"
    else:
        selected_name = "no tool selected"
        selected_status = "waiting" if confirmation is True else "unknown"
    confidence = payload.get("confidence")
    confidence_text = _number_text(confidence, "not recorded")
    rationale = _text(payload.get("rationale")).strip()
    model_decisions = _sequence(payload.get("model_decisions"))
    summary = _mapping(payload.get("summary"))
    recorded_task = _label(summary.get("task_id"), "")
    sent_characters = len(prompt_text[:MAX_TASK_MESSAGE])
    collected: list[FlowIssue] = list(issues)
    collected.append(_route_side_effect_issue(result.url, reached=True, recorded_task=recorded_task))
    if model_decisions:
        profiles = ", ".join(sorted({_label(_mapping(item).get("profile")) for item in model_decisions}))
        collected.append(
            FlowIssue(
                severity="info",
                code="http.model_router_used",
                message=f"The backend consulted a routing model ({profiles}); the offline preview never does.",
                where=result.url,
                hint="A model-mediated decision can differ from the deterministic offline preview.",
            )
        )
    collected.append(
        live_issue(result.url, action="POST /api/route", status=result.status, trace_id=result.trace_id, base=base)
    )
    phases = (
        FlowPhase(
            name="prompt",
            title="Prompt (input)",
            steps=(
                FlowStep(name="user prompt", status="completed", detail=prompt_text),
                FlowStep(
                    name="prompt size",
                    status="completed",
                    detail=(
                        f"{len(prompt_text)} character(s), {len(prompt_text.split())} whitespace-separated token(s); "
                        f"sent to the backend: {sent_characters} character(s); graph_version {version}"
                    ),
                ),
                FlowStep(
                    name="request",
                    status="completed",
                    detail=(
                        f"POST {result.url} -> HTTP {result.status}"
                        + (f"; trace id {result.trace_id}" if result.trace_id else "; no trace id returned")
                    ),
                ),
            ),
        ),
        FlowPhase(name="candidates", title="Candidates", steps=tuple(candidate_steps)),
        FlowPhase(
            name="decision",
            title="Decision",
            steps=(
                FlowStep(
                    name=selected_name,
                    status=selected_status,
                    detail=(
                        f"confidence {confidence_text}; human confirmation required: "
                        f"{'yes' if confirmation is True else 'no' if confirmation is False else 'not reported'}; "
                        f"rationale: {rationale or 'not recorded'}"
                    ),
                    tools=tuple(_label(item.get("tool_id")) for item in selected),
                ),
                FlowStep(
                    name="live decision",
                    status="completed",
                    detail=(
                        f"computed by the running backend at {base} through POST /api/route; the request declared "
                        f"graph_version {version}"
                        + (
                            " and the decision reports routing-model evidence"
                            if model_decisions
                            else "; the decision reports no routing-model evidence"
                        )
                    ),
                ),
            ),
        ),
    )
    return build_document(
        title="Live routing preview (backend decision)",
        source=result.url,
        phases=phases,
        issues=tuple(collected),
        meta={
            "mode": "http",
            "transport": "http",
            "base": base,
            "url": result.url,
            "http_status": "" if result.status is None else str(result.status),
            "graph_version": str(version),
            "candidates": str(len(candidate_steps)),
            "task_id": recorded_task,
        },
        modes=("http", "live"),
    )


def probe_document(base: str, *, timeout: float = DEFAULT_TIMEOUT) -> FlowDocument:
    """Diagnose the live backend: reachability and the versioned contract, nothing else."""
    probed = client.probe(base=base, timeout=timeout)
    payload = _mapping(probed.payload)
    operations = _mapping(payload.get("operations"))
    if not probed.reachable:
        issue = probed.issues[0] if probed.issues else FlowIssue(
            severity="error",
            code="http.unreachable",
            message=f"Cannot reach a MatFlow backend at {base}.",
        )
        # Keep the transport's own diagnosis and never claim a server answered when none did (or the
        # reverse): three conditions, three step pairs.
        code = issue.code
        if code.endswith(".unreachable"):
            issue = _unreachable_issue(issue, base)
            failure_steps = (
                FlowStep(name="reachable", status="error", detail=issue.message, error=issue.message),
                FlowStep(name="api_contract", status="unknown", detail="not checked: the backend did not answer"),
            )
        elif code.endswith(".invalid_url") or code.endswith(".credentials_not_supported"):
            # The transport refused the origin before opening a socket: nothing was reached, so the
            # step must not say the backend answered.
            issue = _as_error(issue)
            failure_steps = (
                FlowStep(name="reachable", status="error", detail=issue.message, error=issue.message),
                FlowStep(name="api_contract", status="unknown", detail="not checked: the origin was refused"),
            )
        else:
            # The server answered, just not with something usable: reachability is fine, the
            # capability answer is not.
            issue = _as_error(issue)
            failure_steps = (
                FlowStep(name="reachable", status="completed", detail=f"the backend answered at {_origin(base)}"),
                FlowStep(name="api_contract", status="error", detail=issue.message, error=issue.message),
            )
        return build_document(
            title=f"Live backend: {_origin(base)}",
            source=_origin(base),
            # Always a phase, even on failure: callers (doctor) print the steps and would otherwise
            # have to special-case an empty phase list.
            phases=(FlowPhase(name="live", title="Live backend (--http)", steps=failure_steps),),
            issues=(issue,),
            meta={
                "mode": "http",
                "transport": "http",
                "base": _origin(base),
                "reachable": "false",
                "contract_ok": "false",
            },
            modes=("http", "live"),
        )
    steps = (
        FlowStep(name="reachable", status="completed", detail=f"GET /api/capabilities answered ({_origin(base)})"),
        FlowStep(
            name="api_contract",
            status="completed" if probed.contract_ok else "error",
            detail=probed.contract_detail or "no contract reported",
        ),
        FlowStep(name="server_version", status="completed", detail=_label(payload.get("server_version"))),
        FlowStep(
            name="operations",
            status="completed",
            detail=f"{len(operations)} documented operation(s)" if operations else "none reported",
        ),
    )
    return build_document(
        title=f"Live backend: {_origin(base)}",
        source=_origin(base),
        phases=(FlowPhase(name="live", title="Live backend (--http)", steps=steps),),
        issues=tuple(probed.issues),
        meta={
            "mode": "http",
            "transport": "http",
            "base": _origin(base),
            "reachable": "true",
            "contract_ok": "true" if probed.contract_ok else "false",
        },
        modes=("http", "live"),
    )


__all__ = [
    "DEFAULT_INPUT_TYPES",
    "DEFAULT_TIMEOUT",
    "MAX_TASK_MESSAGE",
    "PREVIEW_TASK_ID",
    "graph_document",
    "live_issue",
    "probe_document",
    "resolve_base",
    "route_document",
    "task_document",
]

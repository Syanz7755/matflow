"""Optional read-only adapter that mirrors live backend state; zero import-time coupling."""
from __future__ import annotations

import dataclasses
import importlib
import importlib.util
import math
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .analysis import build_document, graph_phases
from .loader import graph_from_payload, workspace_root
from .model import (
    FlowDocument,
    FlowGraph,
    FlowIssue,
    FlowNode,
    FlowPhase,
    FlowPort,
    FlowStep,
    safe_text,
)

#: The one concrete next action FlowView can always suggest when the adapter fails.
BACKEND_HINT = "run 'python -m flowview doctor'"

_DEFAULT_INPUT_TYPES: tuple[str, ...] = ("RawData", "TypedTable")


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


def _label(value: Any, default: str = "unknown") -> str:
    text = _text(value).strip()
    return text or default


def _number_text(value: Any, missing: str) -> str:
    """``0.00``-style text for a score, or ``missing`` when it cannot be a finite number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return missing
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return missing
    return f"{number:.2f}" if math.isfinite(number) else missing


def _failure(
    message: str,
    *,
    detail: str | None = None,
    code: str = "backend.unavailable",
    where: str | None = None,
    hint: str | None = None,
    title: str = "MatFlow flowview (backend unavailable)",
) -> FlowDocument:
    """The only shape a failed adapter call returns: one error issue with a next action."""
    return build_document(
        title=title,
        source="flowview backend adapter",
        issues=(
            FlowIssue(
                severity="error",
                code=code,
                message=message,
                where=where,
                hint=hint or BACKEND_HINT,
                detail=detail,
            ),
        ),
        meta={"mode": "offline"},
    )


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def _backend_root(root: Path | None = None) -> Path:
    if root is None:
        return workspace_root()
    try:
        return Path(root).expanduser().resolve()
    except (TypeError, ValueError, OSError):
        return workspace_root()


def _import_module(name: str) -> Any:
    """Import one backend module lazily; the caller wraps this in a guard."""
    return importlib.import_module(name)


def _runtime_module() -> Any:
    return _import_module("backend.workspace_runtime")


def _configured_package_ids(root: Path) -> tuple[str, ...] | None:
    """The domain packages the backend app composes, read without changing the process env.

    ``backend/main.py`` reads ``MATFLOW_DOMAIN_PACKAGES`` (falling back to
    ``backend.domain_packages.REFERENCE_PACKAGE_IDS``) after loading ``.env``. FlowView mirrors
    that composition so the registry resolves the same types, but never calls ``os.environ``
    setters or ``load_local_env()``.
    """
    value = os.environ.get("MATFLOW_DOMAIN_PACKAGES")
    if value is None:
        try:
            lines = (root / ".env").read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            lines = []
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, raw_value = line.partition("=")
            if name.strip() == "MATFLOW_DOMAIN_PACKAGES":
                value = raw_value.strip().strip('"').strip("'")
                break
    if value is None:
        return None
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _package_ids(root: Path) -> tuple[str, ...]:
    configured = _configured_package_ids(root)
    if configured is not None:
        return configured
    try:
        reference = getattr(_import_module("backend.domain_packages"), "REFERENCE_PACKAGE_IDS", ())
    except BaseException:  # noqa: BLE001 - a missing reference composition means domain-free Core
        return ()
    return tuple(item for item in reference if isinstance(item, str))


def _runtime(root: Path | None = None) -> tuple[Any, Path]:
    """(WorkspaceRuntime instance, resolved root), composed like the backend app.

    Only reading happens here: constructing the runtime loads the same domain packages as
    ``backend/main.py`` and opens no file for writing.
    """
    base = _backend_root(root)
    module = _runtime_module()
    return module.WorkspaceRuntime(base, packages=_package_ids(base)), base


def backend_available() -> tuple[bool, str | None]:
    """(importable, human reason when not) for the optional read-only backend adapter."""
    try:
        base = _backend_root()
        marker = base / "backend" / "workspace_runtime.py"
        if not marker.exists():
            return False, f"no backend package found at {marker}"
        spec = importlib.util.find_spec("backend.workspace_runtime")
        if spec is None:
            return False, "the backend package exists on disk but is not importable from here"
        _runtime_module()
    except BaseException as exc:  # noqa: BLE001 - availability probing must never escape
        return False, _describe(exc)
    return True, None


def _ports(spec_ports: Any) -> tuple[FlowPort, ...]:
    ports = spec_ports if isinstance(spec_ports, Mapping) else {}
    result: list[FlowPort] = []
    for name, data_type in ports.items():
        result.append(FlowPort(name=_label(name, "?"), data_type=_label(data_type) or None))
    return tuple(result)


def live_graph_document(root: Path | None = None) -> FlowDocument:
    """Mirror ``WorkspaceRuntime.read_state()`` into a FlowDocument; never writes state."""
    try:
        workspace, base = _runtime(root)
        state = workspace.read_state()
        payload = state.model_dump() if hasattr(state, "model_dump") else state
        if not isinstance(payload, Mapping):
            raise TypeError("read_state() did not return a mapping payload")
        graph = graph_from_payload(dict(payload), source=f"live:{base}")
    except BaseException as exc:  # noqa: BLE001 - the adapter degrades, it never raises
        return _failure(
            "The workspace graph could not be read from the backend.",
            detail=_describe(exc),
            where="backend.workspace_runtime.WorkspaceRuntime.read_state",
        )
    return build_document(
        title="MatFlow live workspace graph",
        source=f"live:{base}",
        graph=graph,
        meta={"mode": "live"},
        modes=("live",),
    )


def schema_document(root: Path | None = None) -> FlowDocument:
    """Read-only view of the tool registry and data types, as a graph of tool nodes."""
    try:
        workspace, base = _runtime(root)
        registry = workspace.registry()
        specs: Mapping[str, Any] = registry.active()
        type_names = tuple(workspace.data_type_registry().names())
    except BaseException as exc:  # noqa: BLE001
        return _failure(
            "The tool registry and data types could not be read from the backend.",
            detail=_describe(exc),
            code="backend.schema_failed",
            where="backend.workspace_runtime.WorkspaceRuntime.registry",
        )

    nodes: list[FlowNode] = []
    categories: dict[str, int] = {}
    for tool_id, spec in specs.items():
        identifier = _label(getattr(spec, "tool_id", None), tool_id)
        category = _label(getattr(spec, "category", None))
        categories[category] = categories.get(category, 0) + 1
        nodes.append(
            FlowNode(
                id=identifier,
                label=_label(getattr(spec, "label", None), identifier),
                tool_id=identifier,
                tool_version=_label(getattr(spec, "version", None)) or None,
                category=category,
                status="ready",
                input_ports=_ports(getattr(spec, "inputs", None)),
                output_ports=_ports(getattr(spec, "outputs", None)),
                known_tool=True,
            )
        )

    category_text = ", ".join(f"{name}: {count}" for name, count in sorted(categories.items())) or "none"
    type_text = ", ".join(type_names) if type_names else "none reported"
    composition = FlowPhase(
        name="composition",
        title="Tool registry and data types",
        steps=(
            FlowStep(
                name="tool registry loaded",
                status="completed",
                detail=(
                    f"{len(nodes)} active registered tool(s) read from "
                    "WorkspaceRuntime.registry().active(); no write_state() call is made"
                ),
            ),
            FlowStep(name="categories", status="completed", detail=category_text, tools=tuple()),
            FlowStep(
                name="data types",
                status="completed" if type_names else "unknown",
                detail=type_text,
            ),
            FlowStep(
                name="read-only guarantee",
                status="completed",
                detail=(
                    "Only registry() and data_type_registry() are used: they read settings, "
                    "never mutate graph, settings or uploads"
                ),
            ),
        ),
    )
    graph = FlowGraph(
        graph_id="tool-registry",
        version=0,
        nodes=tuple(nodes),
        edges=(),
        source=f"registry:{base}",
    )
    return build_document(
        title="MatFlow tool registry and data types (read-only)",
        source=f"registry:{base}",
        graph=graph,
        phases=(composition,),
        meta={"mode": "schema", "tools": str(len(nodes)), "data_types": str(len(type_names))},
        modes=("schema",),
    )


def _prompt_token_diagnostic(prompt: str) -> tuple[int, int, int, str]:
    """Count what the retriever can actually see in a prompt, and explain anomalies.

    ``backend.routing._tokens`` keeps only ``[a-z0-9]+`` runs of length > 1 and returns them as a
    **set**, so the count reported here is the size of that set, not the number of occurrences — a
    repeated prompt must not look like a richer one than it is. CJK text contributes no tokens at
    all, which is worth surfacing instead of leaving the reader to guess why a route looks wrong.
    """
    import re

    occurrences = re.findall(r"[a-z0-9]+", prompt.lower())
    distinct = {token for token in occurrences if len(token) > 1}
    cjk = len(re.findall(r"[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff]", prompt))
    note = ""
    if cjk and not distinct:
        note = " -- every CJK character is invisible to the retriever, so no candidate can match"
    elif cjk > 20 * max(1, len(distinct)):
        note = " -- the prompt is overwhelmingly CJK: lexical matching sees almost none of it"
    elif not distinct:
        note = " -- no token of length > 1 survived tokenisation, so nothing can match"
    return len(occurrences), len(distinct), cjk, note


MAX_TASK_MESSAGE = 4000


def _route_preview_message(prompt: str, *, limit: int = MAX_TASK_MESSAGE) -> tuple[str, bool, tuple[str, ...]]:
    """Build the text the router will actually see from a prompt of any length.

    ``backend/contracts.py`` caps ``TaskState.user_message`` at :data:`MAX_TASK_MESSAGE` characters,
    so a longer prompt cannot be passed through as-is. The preview must contain **only the prompt's
    own tokens**: adding descriptive header text of our own would enter the query set and invent
    candidates that the real prompt never mentioned, which is worse than a refused request.

    The retriever scores with a *set* intersection, so the preview is the distinct ``[a-z0-9]+`` runs
    of the prompt (length > 1, first-appearance order). Returns the preview, whether it was
    shortened, and the tokens that had to be dropped when even the deduplicated set was too long.
    """
    if len(prompt) <= limit:
        return prompt, False, ()
    import re

    tokens: list[str] = []
    seen: set[str] = set()
    for token in re.findall(r"[a-z0-9]+", prompt.lower()):
        if len(token) > 1 and token not in seen:
            seen.add(token)
            tokens.append(token)

    # First pass: fit whole tokens. An oversized token is skipped, never used to consume the budget,
    # so the tokens after it still get their chance (they are often the ones naming a tool).
    kept: list[str] = []
    size = 0
    dropped: list[str] = []
    for token in tokens:
        if size + len(token) + 1 > limit:
            dropped.append(token)
            continue
        kept.append(token)
        size += len(token) + 1

    if not kept and dropped:
        # Nothing fit at all (one enormous token). Truncating a prefix of the prompt's OWN token
        # keeps the subset property: every character still comes from the user's text, so this can
        # never manufacture a token the prompt did not contain. The token is reported as dropped
        # because it was not routed whole.
        room = max(1, limit - 1)
        kept.append(dropped[0][:room])
        size = room + 1
    return " ".join(kept)[:limit], True, tuple(dropped)


def dry_route(
    prompt: str,
    root: Path | None = None,
    *,
    include_candidates: bool = True,
    available_input_types: Sequence[str] = _DEFAULT_INPUT_TYPES,
) -> FlowDocument:
    """Read-only routing preview: decide() with the lexical retriever, no JEV model, no persistence."""
    issues: list[FlowIssue] = []
    prompt_text = _text(prompt)
    if not prompt_text.strip():
        # Match the CLI's own rule: an empty request is a user mistake, not a route worth printing.
        return _failure(
            "A routing preview needs a non-empty prompt.",
            detail="empty prompt",
            code="route.empty_prompt",
            where="flowview dry-route",
            hint='Pass the request text, for example: --prompt "run basic EIS quality checks".',
            title="MatFlow routing preview (empty prompt)",
        )
    raw_tokens, usable_tokens, cjk_characters, token_note = _prompt_token_diagnostic(prompt_text)
    preview_text, shortened, dropped_tokens = _route_preview_message(prompt_text)
    preview_raw, preview_tokens, preview_cjk, _ = _prompt_token_diagnostic(preview_text)
    if shortened:
        dropped_text = ""
        if dropped_tokens:
            # A single pathological token can be enormous; never let it dominate the report.
            shown_drops = [token[:40] + ("…" if len(token) > 40 else "") for token in dropped_tokens[:12]]
            dropped_text = (
                f" {len(dropped_tokens)} distinct token(s) did not fit into the preview: "
                + ", ".join(shown_drops)
                + (" …" if len(dropped_tokens) > 12 else "")
            )
        no_tokens = preview_tokens == 0
        issues.append(
            FlowIssue(
                severity="info" if not dropped_tokens else "warning",
                code="route.prompt_shortened_for_routing",
                message=(
                    f"The prompt is {len(prompt_text)} characters, above the backend's "
                    f"{MAX_TASK_MESSAGE}-character user_message limit, so routing used a "
                    f"{len(preview_text)}-character preview built only from the prompt's own tokens."
                    + dropped_text
                ),
                where="backend.contracts.TaskState.user_message",
                hint=(
                    "The prompt printed in text and JSON mode is the full text; the preview carries the "
                    "prompt's own distinct [a-z0-9]+ tokens and nothing else, so no candidate can come from "
                    "words FlowView added."
                    + (
                        " Because tokens were dropped, both the route and its confidence were computed "
                        "over the preview rather than the whole request: treat the decision as incomplete."
                        if dropped_tokens
                        else ""
                    )
                    + (
                        " This prompt yields no ASCII token at all, so the router was given an empty "
                        "query and cannot select anything: the request needs a Latin keyword or the "
                        "model (JEV) router."
                        if no_tokens
                        else ""
                    )
                ),
            )
        )
    if shortened and preview_tokens == 0:
        issues.append(
            FlowIssue(
                severity="warning",
                code="route.no_retriever_tokens",
                message=(
                    f"The {len(prompt_text)}-character prompt contains no [a-z0-9]+ token longer than one "
                    "character, so the router received an empty query."
                ),
                where="backend/routing.py: _tokens()",
                hint=(
                    "No candidate can be selected from a prompt the tokeniser cannot see. Add a Latin "
                    "keyword (a tool id, a column name, a unit) or route through the model (JEV) router."
                ),
            )
        )
    if token_note:
        issues.append(
            FlowIssue(
                severity="warning",
                code="route.prompt_tokens_unusable",
                message="The retriever cannot see most of this prompt." + token_note,
                where="backend/routing.py: _tokens()",
                hint=(
                    "This is a routing limitation, not a FlowView one: the printer is showing exactly "
                    "what the backend decided. Add an English/Latin keyword to the request, or route "
                    "through the model (JEV) router, if a specific tool must be selected."
                ),
            )
        )
    try:
        workspace, base = _runtime(root)
        routing = _import_module("backend.routing")
        contracts = _import_module("backend.contracts")
        state = workspace.read_state()
        version = getattr(state, "version", 0)
        version_number = int(version) if isinstance(version, (int, float)) and not isinstance(version, bool) else 0
        registry = workspace.registry()

        known_types = {name for name in workspace.data_type_registry().names()}
        requested = [_text(item).strip() for item in available_input_types if isinstance(item, str)]
        accepted = [item for item in requested if item and item in known_types]
        dropped = [item for item in requested if item and item not in known_types]
        if dropped:
            issues.append(
                FlowIssue(
                    severity="warning",
                    code="route.unknown_input_type",
                    message="Ignored input type(s) the registry does not know: " + ", ".join(sorted(set(dropped))),
                    where="flowview dry-route",
                    hint="Pass a type listed by 'python -m flowview doctor'.",
                )
            )
        task = contracts.TaskState(
            task_id="dry-run",
            # TaskState requires 1..4000 characters. When the prompt yields no token at all the
            # router still gets the prompt's OWN first characters (never the `_label` placeholder,
            # which would put a `?` in the query that the user did not type); `_tokens` sees nothing
            # in either case, so no candidate can match.
            user_message=_label(preview_text or prompt_text[:MAX_TASK_MESSAGE], "?"),
            graph_version=max(0, version_number),
            available_input_types=accepted,
        )
        decision = routing.DecisionRouter().decide(task, registry)
    except BaseException as exc:  # noqa: BLE001
        return _failure(
            "Read-only routing could not be computed from the backend.",
            detail=_describe(exc),
            code="backend.route_failed",
            where="backend.routing.DecisionRouter.decide",
        )

    candidates = list(getattr(decision, "candidates", ()) or ())
    selected = list(getattr(decision, "selected", ()) or ())
    confidence = getattr(decision, "confidence", None)
    rationale = _text(getattr(decision, "rationale", None)).strip()
    confirmation = getattr(decision, "requires_human_confirmation", None)

    candidate_steps: list[FlowStep] = []
    if include_candidates:
        for candidate in candidates:
            tool_id = _label(getattr(candidate, "tool_id", None))
            score = getattr(candidate, "score", None)
            score_text = _number_text(score, "not scored")
            reasons = getattr(candidate, "reasons", ()) or ()
            reason_text = "; ".join(_text(item).strip() for item in reasons if _text(item).strip()) or "no reason recorded"
            candidate_steps.append(
                FlowStep(
                    name=f"{tool_id} (candidate)",
                    status="pending",
                    detail=(
                        f"candidate only, nothing executed; score {score_text}; "
                        f"version {_label(getattr(candidate, 'version', None))}; reasons: {reason_text}"
                    ),
                    tools=(tool_id,),
                )
            )
        if not candidate_steps:
            candidate_steps.append(
                FlowStep(
                    name="no candidate retrieved",
                    status="unknown",
                    detail="CandidateRetriever found no active compatible tool for this prompt",
                )
            )
    else:
        candidate_steps.append(
            FlowStep(
                name=f"{len(candidates)} candidate(s) considered",
                status="pending",
                detail="the candidate list was omitted because include_candidates=False",
            )
        )

    if selected:
        selected_name = "selected " + ", ".join(_label(getattr(item, "tool_id", None)) for item in selected)
        selected_status = "waiting" if confirmation is True else "completed"
    else:
        selected_name = "no tool selected"
        selected_status = "waiting" if confirmation is True else "unknown"

    confidence_text = _number_text(confidence, "not recorded")
    decision_steps = [
        FlowStep(
            name=selected_name,
            status=selected_status,
            detail=(
                f"confidence {confidence_text}; human confirmation required: "
                f"{'yes' if confirmation is True else 'no' if confirmation is False else 'not reported'}; "
                f"rationale: {rationale or 'not recorded'}"
            ),
            tools=tuple(_label(getattr(item, "tool_id", None)) for item in selected),
        ),
        FlowStep(
            name="dry run guarantee",
            status="completed",
            detail=(
                "DecisionRouter() ran without the JEV/model router: record_routing() was not called "
                "and no graph, settings or summary file was written"
            ),
        ),
    ]

    phases = (
        FlowPhase(
            name="prompt",
            title="Prompt (input)",
            steps=(
                FlowStep(
                    name="user prompt",
                    status="completed",
                    detail=prompt_text,
                ),
                FlowStep(
                    name="prompt size",
                    status="completed",
                    detail=(
                        f"{len(prompt_text)} character(s), {len(prompt_text.split())} whitespace-separated token(s); "
                        f"available input types: {', '.join(accepted) if accepted else '(none)'}"
                        + (
                            f"; routing consumed a {len(preview_text)}-character preview "
                            f"with {preview_tokens} of the prompt's {usable_tokens} distinct token(s)"
                            if shortened
                            else ""
                        )
                    ),
                ),
                FlowStep(
                    name="retriever tokenisation",
                    status="waiting" if (token_note or dropped_tokens) else "completed",
                    detail=(
                        f"backend/routing.py _tokens() keeps the distinct [a-z0-9]+ runs longer than one character. "
                        f"The {len(prompt_text)}-character prompt yields {raw_tokens} occurrence(s) / "
                        f"{usable_tokens} distinct token(s) and {cjk_characters} CJK character(s); "
                        f"the router was given {preview_tokens} distinct token(s) "
                        f"({preview_raw} occurrence(s), {preview_cjk} CJK character(s))"
                        + (" [shortened]" if shortened else " [verbatim]")
                        + f"{token_note}"
                    ),
                ),
            ),
        ),
        FlowPhase(name="candidates", title="Candidates", steps=tuple(candidate_steps)),
        FlowPhase(name="decision", title="Decision", steps=tuple(decision_steps)),
    )
    issues.append(
        FlowIssue(
            severity="info",
            code="route.dry_run",
            message="This route was computed read-only: nothing was persisted to the task summary log.",
            where=f"dry-route:{base}",
        )
    )
    return build_document(
        title="MatFlow routing preview (read-only)",
        source=f"dry-route:{base}",
        phases=phases,
        issues=tuple(issues),
        meta={
            "mode": "dry-run",
            "graph_version": str(max(0, version_number)),
            "candidates": str(len(candidates)),
            "confirmation": "yes" if confirmation is True else "no" if confirmation is False else "unknown",
            "prompt_characters": str(len(prompt_text)),
            "prompt": prompt_text,
            "retriever_tokens": str(usable_tokens),
            "routing_tokens": str(preview_tokens),
            "retriever_tokens_dropped": str(len(dropped_tokens)),
            "cjk_characters": str(cjk_characters),
            "routing_preview": "shortened" if shortened else "verbatim",
        },
        modes=("dry-run",),
    )


def graph_document_merged(root: Path | None = None) -> FlowDocument:
    """The live graph annotated with registry knowledge (which tools are known)."""
    try:
        workspace, base = _runtime(root)
        state = workspace.read_state()
        payload = state.model_dump() if hasattr(state, "model_dump") else state
        if not isinstance(payload, Mapping):
            raise TypeError("read_state() did not return a mapping payload")
        graph = graph_from_payload(dict(payload), source=f"live+registry:{base}")
        known = set(workspace.registry().active())
    except BaseException as exc:  # noqa: BLE001
        return _failure(
            "The live graph could not be merged with the tool registry.",
            detail=_describe(exc),
            where="backend.workspace_runtime.WorkspaceRuntime.read_state",
        )

    nodes = tuple(
        dataclasses.replace(node, known_tool=(node.tool_id or node.id) in known)
        for node in graph.nodes
    )
    merged = dataclasses.replace(graph, nodes=nodes)
    return build_document(
        title="MatFlow live graph with registry knowledge",
        source=f"live+registry:{base}",
        graph=merged,
        phases=graph_phases(merged),
        meta={"mode": "live+registry", "known_tools": str(len(known))},
        modes=("live", "registry"),
    )


__all__ = [
    "BACKEND_HINT",
    "backend_available",
    "dry_route",
    "graph_document_merged",
    "live_graph_document",
    "schema_document",
]

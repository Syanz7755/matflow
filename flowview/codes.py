"""FlowView error taxonomy, exit codes, and exception-to-issue conversion."""
from __future__ import annotations

import functools
from typing import Any, Callable, Iterable, Mapping, Sequence

from .model import FlowIssue, IssueSeverity

EXIT_OK = 0
EXIT_INTERNAL = 1
EXIT_USAGE = 2
EXIT_SOURCE = 3

EXIT_CODES: Mapping[int, str] = {
    EXIT_OK: "success",
    EXIT_INTERNAL: "unexpected internal error",
    EXIT_USAGE: "usage error",
    EXIT_SOURCE: "input or backend problem",
}


class FlowViewError(Exception):
    """Base class for every expected FlowView failure.

    Carrying a :class:`FlowIssue` (not just a message) is what lets the CLI print a
    readable diagnosis instead of a traceback.
    """

    exit_code = EXIT_INTERNAL

    def __init__(
        self,
        message: str,
        *,
        code: str = "flowview.error",
        where: str | None = None,
        hint: str | None = None,
        detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.issue = FlowIssue(
            severity="error",
            code=code,
            message=message,
            where=where,
            hint=hint,
            detail=detail,
        )


class FlowUsageError(FlowViewError):
    """The caller asked for something the CLI cannot express."""

    exit_code = EXIT_USAGE


class FlowSourceError(FlowViewError):
    """A required input (file, stream, or backend) is missing or unusable."""

    exit_code = EXIT_SOURCE


class FlowBackendError(FlowSourceError):
    """The optional backend adapter could not be used."""


class FlowRenderError(FlowViewError):
    """Rendering was asked for a document that cannot produce that format."""

    exit_code = EXIT_INTERNAL


class FlowCycleError(FlowSourceError):
    """The graph is unusable because it contains a cycle."""

    def __init__(self, cycles: Sequence[Sequence[str]], *, where: str | None = None) -> None:
        rendered = ", ".join(" -> ".join(cycle) for cycle in cycles) or "(unknown cycle)"
        super().__init__(
            f"The graph is not acyclic: {rendered}",
            code="graph.cycle",
            where=where,
            hint="Repair the graph with apply_graph_patch, then re-run flowview graph.",
        )
        self.cycles = tuple(tuple(cycle) for cycle in cycles)


def describe_exception(exc: BaseException) -> str:
    """A stable, redaction-safe one-line description of an exception."""
    text = str(exc).strip() or exc.__class__.__name__
    return f"{exc.__class__.__name__}: {text}"


def issue_from_exception(
    exc: BaseException,
    *,
    code: str,
    where: str | None = None,
    severity: IssueSeverity = "error",
    hint: str | None = None,
    message: str | None = None,
) -> FlowIssue:
    """Convert any exception into a FlowIssue without leaking a traceback upward."""
    if isinstance(exc, FlowViewError):
        issue = exc.issue
        return FlowIssue(
            severity=severity if severity != "error" else issue.severity,
            code=code or issue.code,
            message=message or issue.message,
            where=where or issue.where,
            hint=hint or issue.hint,
            detail=issue.detail or describe_exception(exc),
        )
    return FlowIssue(
        severity=severity,
        code=code,
        message=message or f"{exc.__class__.__name__}: {str(exc).strip() or 'no detail provided'}",
        where=where,
        hint=hint,
        detail=describe_exception(exc),
    )


def guard(
    code: str,
    *,
    where: str | None = None,
    severity: IssueSeverity = "warning",
    hint: str | None = None,
    default: Any = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator converting unexpected exceptions into an issue instead of a crash.

    On failure the wrapper attaches the issue to the returned value when that value has a
    mutable ``issues`` list, and always records it on ``__flowview_issues__``.
    """

    def decorate(function: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(function)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return function(*args, **kwargs)
            except FlowViewError:
                raise
            except Exception as exc:  # noqa: BLE001 - the whole point of the guard
                issue = issue_from_exception(exc, code=code, where=where, severity=severity, hint=hint)
                result = default
                collected = list(getattr(wrapper, "__flowview_issues__", ()))
                collected.append(issue)
                wrapper.__flowview_issues__ = collected  # type: ignore[attr-defined]
                if hasattr(result, "issues"):
                    try:
                        result.issues = tuple(result.issues) + (issue,)  # type: ignore[attr-defined]
                    except Exception:  # noqa: BLE001 - degraded-but-not-fatal
                        pass
                return result

        wrapper.__flowview_issues__ = []  # type: ignore[attr-defined]
        return wrapper

    return decorate


def worst_severity(issues: Iterable[FlowIssue]) -> IssueSeverity | None:
    """The most severe severity present, or ``None`` when there are no issues."""
    order: Mapping[IssueSeverity, int] = {"info": 0, "warning": 1, "error": 2}
    worst: IssueSeverity | None = None
    for issue in issues:
        if worst is None or order[issue.severity] > order[worst]:
            worst = issue.severity
    return worst


def exit_code_for(issues: Iterable[FlowIssue], *, strict: bool = False) -> int:
    """Map an issue collection to the documented CLI exit code."""
    severity = worst_severity(issues)
    if severity == "error":
        return EXIT_SOURCE
    if severity == "warning" and strict:
        return EXIT_SOURCE
    return EXIT_OK

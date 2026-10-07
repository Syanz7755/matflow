"""The workspace error taxonomy.

One place decides how a failure is *classified*: a stable machine-readable
``code`` plus the HTTP status it deserves.  The HTTP adapter turns this into
the wire envelope; the runtime raises it without knowing about HTTP.

Documented codes (clients branch on these, never on message text):

``not_found``              an identified resource does not exist
``invalid_request``        the request or its payload is malformed
``invalid_parameters``     node parameters are unsupported or fail the tool schema
``unknown_tool``           a graph references a tool the registry does not provide
``invalid_tool_schema``    a loaded tool declares a schema that cannot be used
``missing_dependency``     a required input port is not connected
``graph_version_conflict`` a write was based on a stale graph version
``conflict``               a write conflicts with the current workspace state
``execution_failed``       a node or workflow failed while executing
"""
from __future__ import annotations

from typing import Any

#: Failure codes that are *not* a 422, for errors raised by third-party code
#: (pydantic validators, executors) that only carry a ``code`` attribute.
STATUS_BY_CODE: dict[str, int] = {
    "not_found": 404,
    "graph_version_conflict": 409,
    "conflict": 409,
    "node_already_running": 409,
    "execution_failed": 424,
    "workflow_failed": 424,
    "unreadable_dataset": 422,
}


class WorkspaceError(ValueError):
    """A rejection that carries a stable code and the HTTP status it deserves.

    Subclasses :class:`ValueError` so every existing ``except ValueError`` seam
    keeps working; the code and status are additive information.
    """

    code: str = "invalid_request"
    status_code: int = 422

    def __init__(self, message: str, *, code: str | None = None, details: dict[str, Any] | None = None):
        super().__init__(message)
        if code is not None:
            self.code = code
        self.details: dict[str, Any] = dict(details or {})


class NotFoundError(WorkspaceError):
    """The identified resource does not exist."""

    code = "not_found"
    status_code = 404


class ConflictError(WorkspaceError):
    """The write conflicts with the current workspace state."""

    code = "conflict"
    status_code = 409


class GraphVersionConflict(ConflictError):
    """A graph write was based on a stale version."""

    code = "graph_version_conflict"


class ExecutionFailed(WorkspaceError):
    """A node or workflow failed while executing."""

    code = "execution_failed"
    status_code = 424


def error_detail(code: str, message: str, **extra: Any) -> dict[str, Any]:
    """The canonical error payload: always an object, never a bare string."""
    return {"code": code, "message": message, **extra}


def status_for(exc: BaseException, default: int = 422) -> int:
    """Resolve the HTTP status for any exception, by attribute or by code."""
    explicit = getattr(exc, "status_code", None)
    if isinstance(explicit, int):
        return explicit
    code = getattr(exc, "code", None)
    if isinstance(code, str):
        return STATUS_BY_CODE.get(code, default)
    return default


def code_for(exc: BaseException, default: str = "invalid_request") -> str:
    """Resolve the stable failure code for any exception."""
    code = getattr(exc, "code", None)
    return code if isinstance(code, str) and code else default


def details_for(exc: BaseException) -> dict[str, Any]:
    """Extra machine-readable fields an error wants to publish."""
    details = getattr(exc, "details", None)
    return dict(details) if isinstance(details, dict) else {}

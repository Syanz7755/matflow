"""Minimal, dependency-free HTTP client for the optional live mode.

The project rule is that clients talk to the backend only over the versioned HTTP API, so this
module is how FlowView reaches a *running* server: read-only ``GET`` calls plus ``POST /api/route``,
which the backend itself treats as a pure decision step. Nothing here writes graph state.

Every failure is returned, never raised, so ``flowview`` can print the flow it could observe and
explain the rest.
"""
from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib import error as urlerror
from urllib import request as urlrequest

from .codes import describe_exception
from .model import FlowIssue

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT = 5.0
MAX_BODY_BYTES = 8 * 1024 * 1024
EXPECTED_CONTRACT = "matflow-http"


@dataclass(frozen=True, slots=True)
class HttpResult:
    """One HTTP exchange, successful or not."""

    ok: bool
    status: int | None = None
    payload: Any = None
    trace_id: str | None = None
    url: str = ""
    error: str | None = None
    issue: FlowIssue | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "url": self.url,
            "trace_id": self.trace_id,
            "error": self.error,
            "payload": self.payload,
        }

    @property
    def unavailable(self) -> bool:
        """True when the server could not be reached at all (as opposed to answering badly)."""
        return not self.ok and self.status is None


def base_url(explicit: str | None = None) -> str:
    """Resolve the backend origin: explicit argument, ``MATFLOW_API_URL``, then the default."""
    value = explicit or os.getenv("MATFLOW_API_URL") or os.getenv("MATFLOW_BACKEND_URL") or DEFAULT_BASE_URL
    return value.rstrip("/")


def api_url(*parts: str, base: str | None = None) -> str:
    root = base_url(base).rstrip("/")
    suffix = "/".join(part.strip("/") for part in parts if part.strip("/"))
    return f"{root}/{suffix}" if suffix else root


def _is_http_url(url: str) -> bool:
    """``--http`` takes an origin a user can mistype, so refuse anything that is not http(s).

    Without this check ``urlopen`` raises ``ValueError("unknown url type")`` for a bare word, which
    would escape as an unexpected internal error (exit 1) instead of a readable diagnosis.
    """
    scheme = url.split("://", 1)[0].strip().lower() if "://" in url else ""
    return scheme in ("http", "https")


def has_credentials(url: str) -> bool:
    """True when the origin embeds ``user:password@``.

    FlowView prints the origin it reads from, so a credential would be copied into reports, ``--out``
    files and issue messages; several HTTP stacks also bypass the loopback proxy rules for a URL with
    userinfo and would forward the secret. A credential therefore fails the command before any
    request is made, and this is checked by the CLI as well as by :func:`request_json`.
    """
    if "@" not in url:
        return False
    authority = url.split("://", 1)[1].split("/", 1)[0] if "://" in url else url.split("/", 1)[0]
    return "@" in authority


class _NoRedirect(urlrequest.HTTPRedirectHandler):
    """A redirect handler that refuses every hop.

    A flow has to come from the origin the user named. Following a redirect would let any hop decide
    what FlowView reads, would attribute a proxy's or a third party's answer to the backend, and
    would walk straight past the credential check above when the target embeds userinfo (the same
    request that bypasses the loopback proxy rules). Returning ``None`` makes urllib raise the
    redirect as an ``HTTPError``, which becomes the documented ``http_error`` issue.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


_OPENER = urlrequest.build_opener(_NoRedirect)


def request_json(
    method: str,
    url: str,
    *,
    payload: Mapping[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    trace_id: str | None = None,
    code: str = "http.request_failed",
) -> HttpResult:
    """Perform one JSON request and turn every failure mode into a :class:`HttpResult`."""
    if has_credentials(url):
        issue = FlowIssue(
            severity="error",
            code=f"{code}.credentials_not_supported",
            message="This URL embeds credentials (user:password@host); FlowView refuses to send it.",
            where="(origin withheld)",
            hint="Configure the backend without embedded credentials: FlowView prints the origin it reads from.",
        )
        return HttpResult(ok=False, url="(origin withheld)", error=issue.message, issue=issue)
    if not _is_http_url(url):
        issue = FlowIssue(
            severity="error",
            code=f"{code}.invalid_url",
            message=f"Not an http(s) URL: {url!r}",
            where=url,
            hint="--http takes an origin such as http://127.0.0.1:8000 (or use bare --http for the default).",
        )
        return HttpResult(ok=False, url=url, error=issue.message, issue=issue)
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        try:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        except RecursionError as exc:
            issue = FlowIssue(
                severity="error",
                code="http.unserialisable_request",
                message="Request payload is nested too deeply to serialise.",
                where=url,
                detail=describe_exception(exc),
            )
            return HttpResult(ok=False, url=url, error=issue.message, issue=issue)
        except (TypeError, ValueError) as exc:
            issue = FlowIssue(
                severity="error",
                code="http.unserialisable_request",
                message=f"Request payload is not JSON-serialisable: {describe_exception(exc)}",
                where=url,
            )
            return HttpResult(ok=False, url=url, error=issue.message, issue=issue)
        headers["Content-Type"] = "application/json"
    if trace_id:
        headers["X-Trace-ID"] = trace_id
    request = urlrequest.Request(url, data=body, headers=headers, method=method.upper())
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            raw = response.read(MAX_BODY_BYTES)
            status = getattr(response, "status", None)
            returned_trace = response.headers.get("X-Trace-ID") if response.headers else None
    except urlerror.HTTPError as exc:
        try:
            detail = json.loads(exc.read(MAX_BODY_BYTES) or b"null")
        except (ValueError, RecursionError, OSError):
            detail = None
        answer_code = getattr(exc, "code", None)
        redirect = isinstance(answer_code, int) and 300 <= answer_code < 400
        return HttpResult(
            ok=False,
            status=answer_code,
            payload=detail,
            url=url,
            error=f"HTTP {answer_code if answer_code is not None else '?'}: {getattr(exc, 'reason', '')}".strip(),
            issue=FlowIssue(
                severity="error",
                code=f"{code}.http_error",
                message=(
                    f"The backend answered HTTP {answer_code if answer_code is not None else '?'} for {url}."
                    + (" FlowView does not follow redirects." if redirect else "")
                ),
                where=url,
                hint=(
                    "Point --http at the origin that serves the API directly: a redirect would come from a hop, "
                    "not from the backend, and FlowView refuses to follow it."
                    if redirect
                    else "Check the backend log; the response body is included in the JSON output. "
                    "A proxy in front of the backend can also answer instead of it."
                ),
                detail=str(detail)[:400] if detail is not None else None,
            ),
        )
    except (urlerror.URLError, socket.timeout, TimeoutError, OSError) as exc:
        return HttpResult(
            ok=False,
            url=url,
            error=describe_exception(exc),
            issue=FlowIssue(
                severity="warning",
                code=f"{code}.unreachable",
                message=f"Cannot reach the MatFlow backend at {url}.",
                where=url,
                hint="Start it with 'python -m backend.cli serve', or use offline mode (the default).",
                detail=describe_exception(exc),
            ),
        )
    except Exception as exc:  # noqa: BLE001 - a transport hiccup must never escape as a traceback
        return HttpResult(
            ok=False,
            url=url,
            error=describe_exception(exc),
            issue=FlowIssue(
                severity="error",
                code=f"{code}.request_failed",
                message=f"The {method.upper()} request to {url} failed before an answer arrived.",
                where=url,
                hint="Check the URL and the backend log; offline mode needs no server.",
                detail=describe_exception(exc),
            ),
        )
    try:
        decoded = json.loads(raw) if raw else None
    except RecursionError as exc:
        # ``json.loads`` recurses per nesting level: a 5000-deep body raises RecursionError, which is
        # not a ValueError and would otherwise escape the reader as an unexpected internal error.
        return HttpResult(
            ok=False,
            status=status,
            url=url,
            error="Response is nested too deeply to parse",
            issue=FlowIssue(
                severity="error",
                code=f"{code}.invalid_json",
                message=f"The backend response from {url} is nested too deeply to parse safely.",
                where=url,
                hint="The response is malformed or hostile; the flow it describes cannot be read.",
                detail=describe_exception(exc),
            ),
        )
    except json.JSONDecodeError as exc:
        return HttpResult(
            ok=False,
            status=status,
            url=url,
            error=f"Invalid JSON response: {exc.msg}",
            issue=FlowIssue(
                severity="error",
                code=f"{code}.invalid_json",
                message=f"The backend response from {url} is not valid JSON.",
                where=url,
                detail=f"{exc.msg} at line {exc.lineno}, column {exc.colno}",
            ),
        )
    except (UnicodeDecodeError, ValueError) as exc:
        # ``json.loads`` raises more than JSONDecodeError: a body that is not UTF-8 (a gzip stream, a
        # binary proxy answer) raises UnicodeDecodeError, and an integer beyond CPython's 4300-digit
        # string limit raises a plain ValueError. Both must become one readable diagnosis.
        if isinstance(exc, UnicodeDecodeError):
            reason = "is not decodable JSON"
            hint = "The body is not UTF-8 JSON; a compressing or rewriting proxy in front of the backend can cause this."
        else:
            reason = "contains a number Python refuses to parse"
            hint = "CPython limits integer conversion to 4300 digits, so the body cannot be mirrored."
        return HttpResult(
            ok=False,
            status=status,
            url=url,
            error=f"Unusable response: {describe_exception(exc)}",
            issue=FlowIssue(
                severity="error",
                code=f"{code}.invalid_json",
                message=f"The backend response from {url} {reason}.",
                where=url,
                hint=hint,
                detail=describe_exception(exc),
            ),
        )
    return HttpResult(ok=True, status=status, payload=decoded, url=url, trace_id=returned_trace)


def capabilities(*, base: str | None = None, timeout: float = DEFAULT_TIMEOUT) -> HttpResult:
    """Read ``/api/capabilities`` — the contract endpoint a client must check at startup."""
    return request_json("GET", api_url("api", "capabilities", base=base), timeout=timeout, code="http.capabilities")


def health(*, base: str | None = None, timeout: float = DEFAULT_TIMEOUT) -> HttpResult:
    """Cheap reachability probe. Any answer at all means the server is up."""
    return request_json("GET", api_url("api", "capabilities", base=base), timeout=min(timeout, 2.0), code="http.health")


def contract_status(result: HttpResult) -> tuple[bool, str]:
    """Compare an observed capability payload with the contract FlowView understands."""
    if not result.ok or not isinstance(result.payload, Mapping):
        return False, "no capability payload"
    contract = result.payload.get("api_contract")
    if not isinstance(contract, Mapping):
        return False, "capability payload has no api_contract"
    name = contract.get("name")
    version = contract.get("version")
    if name != EXPECTED_CONTRACT:
        return False, f"unexpected contract name: {name!r}"
    major = str(version).split(".")[0] if version is not None else ""
    if major and major != "1":
        return False, f"incompatible contract major version: {version!r}"
    return True, f"{name} {version}"


def state(*, base: str | None = None, timeout: float = DEFAULT_TIMEOUT) -> HttpResult:
    return request_json("GET", api_url("api", "state", base=base), timeout=timeout, code="http.state")


def task_summary(task_id: str, *, base: str | None = None, timeout: float = DEFAULT_TIMEOUT) -> HttpResult:
    if not task_id.strip():
        return HttpResult(
            ok=False,
            url=api_url("api", "task-summaries", base=base),
            error="A task id is required.",
            issue=FlowIssue(severity="error", code="http.task_id_required", message="A task id is required for a task summary request."),
        )
    return request_json(
        "GET",
        api_url("api", "task-summaries", task_id.strip(), base=base),
        timeout=timeout,
        code="http.task_summary",
    )


def route(task: Mapping[str, Any], *, base: str | None = None, timeout: float = DEFAULT_TIMEOUT) -> HttpResult:
    """``POST /api/route``: the backend returns a decision and records a routing summary.

    FlowView only ever calls this for an explicit ``--live`` request; the response contains the
    full decision, which is exactly what ``flowview flow --live`` prints.
    """
    return request_json(
        "POST",
        api_url("api", "route", base=base),
        payload={"task": dict(task)},
        timeout=timeout,
        code="http.route",
    )


@dataclass(frozen=True, slots=True)
class LiveProbe:
    """The result of one live-mode reachability check."""

    base: str
    reachable: bool
    contract_ok: bool
    contract_detail: str
    issues: tuple[FlowIssue, ...] = field(default_factory=tuple)
    #: The ``/api/capabilities`` payload when the check succeeded, so callers that need the reported
    #: data types or operations do not have to fetch the same endpoint twice.
    payload: Any = None


def probe(*, base: str | None = None, timeout: float = DEFAULT_TIMEOUT) -> LiveProbe:
    """Check the running backend without changing anything."""
    origin = base_url(base)
    result = capabilities(base=origin, timeout=timeout)
    if not result.ok:
        issue = result.issue or FlowIssue(
            severity="warning",
            code="http.capabilities.unreachable",
            message=f"No MatFlow backend at {origin}.",
        )
        return LiveProbe(base=origin, reachable=False, contract_ok=False, contract_detail=result.error or "", issues=(issue,))
    ok, detail = contract_status(result)
    issues: list[FlowIssue] = []
    if not ok:
        issues.append(
            FlowIssue(
                severity="warning",
                code="http.contract_mismatch",
                message=f"The backend contract is not the expected one: {detail}",
                where=result.url,
                hint="Update FlowView or the backend; offline mode is unaffected.",
            )
        )
    return LiveProbe(
        base=origin,
        reachable=True,
        contract_ok=ok,
        contract_detail=detail,
        issues=tuple(issues),
        payload=result.payload,
    )

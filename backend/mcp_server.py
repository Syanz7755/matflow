"""MCP adapter for the transport-neutral MatFlow workspace runtime."""
from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib import request as urlrequest
from urllib.parse import urlparse

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel

from .contracts import GraphPatch, TaskState
from .workspace_runtime import WorkspaceRuntime


class OpenAIFile(BaseModel):
    """ChatGPT file-param shape; optional fields must remain declared but optional."""

    download_url: str
    file_id: str
    mime_type: str | None = None
    file_name: str | None = None


def _validate_public_https(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("File download_url must be a public HTTPS URL")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise ValueError("File download host could not be resolved") from exc
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("File download_url cannot target a private or local address")


class _SafeRedirects(urlrequest.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_public_https(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _download_file(file: OpenAIFile) -> bytes:
    _validate_public_https(file.download_url)
    opener = urlrequest.build_opener(_SafeRedirects())
    request = urlrequest.Request(file.download_url, headers={"User-Agent": "MatFlow/0.3"})
    with opener.open(request, timeout=30) as response:
        declared = response.headers.get("Content-Length")
        if declared and int(declared) > 25 * 1024 * 1024:
            raise ValueError("File exceeds the 25 MB MatFlow limit")
        content = response.read(25 * 1024 * 1024 + 1)
    if len(content) > 25 * 1024 * 1024:
        raise ValueError("File exceeds the 25 MB MatFlow limit")
    return content


def _ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data, "error": None}


def _call(operation):
    try:
        return _ok(operation())
    except Exception as exc:
        return {"ok": False, "data": None, "error": {"code": "matflow_error", "message": str(exc), "retryable": False}}


def create_mcp_server(runtime: WorkspaceRuntime) -> FastMCP:
    server = FastMCP(
        "MatFlow",
        instructions="Use MatFlow to inspect datasets and build audited materials workflows. Read tools are safe; request user approval before write or execution tools.",
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        max_request_body_size=36 * 1024 * 1024,
    )

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True))
    def get_workspace_state() -> dict[str, Any]:
        """Read the current graph, registered tools, data types, and feature flags."""
        return _call(runtime.workspace_snapshot)

    @server.tool(
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False),
        meta={"openai/fileParams": ["file"]},
    )
    def import_dataset(file: OpenAIFile) -> dict[str, Any]:
        """Import a ChatGPT/MCP file object. Ask the user before calling this write tool."""
        return _call(lambda: runtime.import_dataset(file.file_name or file.file_id, _download_file(file), file.mime_type or "application/octet-stream"))

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True))
    def inspect_dataset(upload_id: str) -> dict[str, Any]:
        """Inspect an imported dataset's shape, columns, types, and bounded preview."""
        return _call(lambda: runtime.inspect_dataset(upload_id))

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True))
    def route_research_task(task: dict[str, Any]) -> dict[str, Any]:
        """Select compatible registered tools without changing or executing the graph."""
        return _call(lambda: runtime.route_task(TaskState.model_validate(task)))

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True))
    def validate_graph_patch(patch: dict[str, Any]) -> dict[str, Any]:
        """Validate a proposed graph patch without changing workspace state."""
        return _call(lambda: runtime.validate_graph_patch(GraphPatch.model_validate(patch)))

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False))
    def apply_graph_patch(patch: dict[str, Any]) -> dict[str, Any]:
        """Apply a validated, version-checked graph patch. Ask the user before calling."""
        return _call(lambda: {"state": runtime.apply_graph_patch(GraphPatch.model_validate(patch)).model_dump()})

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False))
    def execute_workflow() -> dict[str, Any]:
        """Execute ready graph nodes until completion, error, or a human-decision pause. Ask first."""
        return _call(runtime.execute_workflow)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False))
    def submit_human_decision(node_id: str, decision: str) -> dict[str, Any]:
        """Resolve a waiting human-decision node. Ask the user before calling."""
        return _call(lambda: runtime.submit_human_decision(node_id, decision))

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True))
    def get_task_summary(task_id: str) -> dict[str, Any]:
        """Read the latest persisted routing/execution summary for a task."""
        return _call(lambda: runtime.task_summary(task_id) or (_ for _ in ()).throw(ValueError("No task summary exists for this task_id")))

    return server

"""JSON rendering: exactly one stable, ASCII-safe JSON document, with no other output."""
from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any, ClassVar

from . import analysis
from .model import FlowDocument, FlowIssue

_SCHEMA = "1.0"
_MAX_DEPTH = 64

_HARD_FALLBACK = json.dumps(
    {
        "flowview_schema": "1.0",
        "document": None,
        "phases": [],
        "issues": [
            {
                "severity": "error",
                "code": "render.json_failed",
                "message": "FlowView could not serialise this document.",
                "where": None,
                "hint": "Re-run with -v to see the traceback.",
                "detail": None,
            }
        ],
        "exit_code_hint": 3,
    },
    separators=(",", ":"),
    ensure_ascii=True,
)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return str(value)
    except Exception:  # noqa: BLE001 - serialisation must never raise
        return ""


def _json_safe(value: Any, depth: int = 0) -> Any:
    """Convert any value into something ``json.dumps`` accepts, without raising."""
    if depth > _MAX_DEPTH:
        return _text(value)
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else _text(value)
    if isinstance(value, Mapping):
        return {_text(key): _json_safe(item, depth + 1) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        ordered = sorted(value, key=_text)
        return [_json_safe(item, depth + 1) for item in ordered]
    if isinstance(value, (list, tuple)):
        return [_json_safe(item, depth + 1) for item in value]
    converter = getattr(value, "to_dict", None)
    if callable(converter):
        try:
            return _json_safe(converter(), depth + 1)
        except Exception:  # noqa: BLE001
            pass
    return _text(value)


class JsonRenderer:
    """Render FlowView documents as a single JSON document.

    The document shape is :func:`flowview.analysis.document_payload`: ``flowview_schema``,
    ``document`` (title, source, meta, graph, trace), ``phases``, ``issues`` and
    ``exit_code_hint``, plus ``graph_stats``/``trace_summary`` when those parts exist.
    Output is pure ASCII so any console encoding carries a valid document.
    """
    format: ClassVar[str] = "json"

    def __init__(self, *, indent: int | None = 2) -> None:
        self.indent = self._normalise_indent(indent)

    @staticmethod
    def _normalise_indent(indent: Any) -> int | None:
        if indent is None:
            return None
        if isinstance(indent, bool):
            return 2
        try:
            value = int(indent)
        except Exception:  # noqa: BLE001
            return 2
        return value if value >= 0 else 0

    # ------------------------------------------------------------------ public API

    def render_document(self, document: Any) -> str:
        """One JSON document, and nothing else on the stream."""
        try:
            payload = analysis.document_payload(document)
        except Exception as exc:  # noqa: BLE001 - degrade to a labelled minimal payload
            payload = self._fallback_payload(document, exc)
        # Lead addition: the expected process exit code travels with the document, so a consumer
        # piping FlowView into a JSON tool can act on the diagnosis without parsing stderr.
        try:
            if isinstance(payload, dict):
                payload["exit_code_hint"] = analysis.expected_exit_code(document)
        except Exception:  # noqa: BLE001 - the hint is advisory
            pass
        try:
            return self._dumps(_json_safe(payload))
        except Exception as exc:  # noqa: BLE001
            try:
                return self._dumps(_json_safe(self._fallback_payload(document, exc)))
            except Exception:  # noqa: BLE001
                return _HARD_FALLBACK

    def render_graph(self, graph: Any) -> str:
        """The same document shape for a bare graph."""
        document = self._document_for_graph(graph)
        return self.render_document(document)

    # ------------------------------------------------------------------ helpers

    def _document_for_graph(self, graph: Any) -> Any:
        graph_id = _text(getattr(graph, "graph_id", "")) or "local-default"
        source = _text(getattr(graph, "source", "")) or "(in-memory)"
        try:
            return analysis.build_document(
                title=f"Workspace graph: {graph_id}",
                source=source,
                graph=graph,
            )
        except Exception:  # noqa: BLE001
            return FlowDocument(title=f"Workspace graph: {graph_id}", source=source, graph=graph)

    def _fallback_payload(self, document: Any, exc: BaseException) -> dict[str, Any]:
        try:
            document_payload = _json_safe(document.to_dict())
        except Exception:  # noqa: BLE001
            document_payload = {
                "title": _text(getattr(document, "title", "")),
                "source": _text(getattr(document, "source", "")),
                "graph": None,
                "trace": None,
                "phases": [],
                "issues": [],
                "meta": {},
                "truncated": [],
            }
        issue = FlowIssue(
            severity="error",
            code="render.json_failed",
            message=(
                "JSON rendering fell back to a minimal payload: "
                f"{exc.__class__.__name__}: {_text(exc).strip() or 'no detail'}"
            ),
            where=_text(getattr(document, "source", "")) or None,
            hint="Re-run with -v to see the traceback, or use --format text.",
            detail=exc.__class__.__name__,
        )
        phases: list[Any] = []
        try:
            phases = [_json_safe(phase.to_dict()) for phase in tuple(getattr(document, "phases", ()) or ())]
        except Exception:  # noqa: BLE001
            phases = []
        return {
            "flowview_schema": _SCHEMA,
            "document": document_payload,
            "phases": phases,
            "issues": [issue.to_dict()],
            "exit_code_hint": 3,
        }

    def _dumps(self, payload: Any) -> str:
        if self.indent is None:
            return json.dumps(
                payload,
                indent=None,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            )
        return json.dumps(
            payload,
            indent=self.indent,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=False,
        )


__all__ = ["JsonRenderer"]

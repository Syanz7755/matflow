"""Structured, redacted lifecycle logging with request-level trace correlation."""
from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from typing import Any

_trace_id: ContextVar[str] = ContextVar("matflow_trace_id", default="untraced")
LOGGER = logging.getLogger("matflow")


def set_trace_id(trace_id: str):
    return _trace_id.set(trace_id)


def reset_trace_id(token: Any) -> None:
    _trace_id.reset(token)


def current_trace_id() -> str:
    return _trace_id.get()


def audit(event: str, **context: Any) -> None:
    """Write one machine-readable lifecycle event without exposing secret values."""
    payload = {"event": event, "trace_id": current_trace_id(), **context}
    LOGGER.info(json.dumps(payload, ensure_ascii=False, default=str))

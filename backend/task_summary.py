"""Build and persist one concise, registry-aware task-lifecycle summary.

Callers use the small ``TaskSummaryService`` interface.  It hides view shaping,
safe output truncation, JSONL persistence, and merging routing with execution.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contracts import ExecutionResult, RegisteredToolReference, RouterCandidate, RouterDecision, TaskLogSummary, TaskState
from .observability import current_trace_id
from .tool_registry import ToolRegistry

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "config" / "observability.json"


def _load_log_path(config_path: Path = DEFAULT_CONFIG_PATH) -> Path | None:
    """Read the tracked logging configuration; disabled means no persistence."""
    if not config_path.exists():
        return None
    config = json.loads(config_path.read_text(encoding="utf-8"))
    summaries = config.get("task_summaries", {})
    if not summaries.get("enabled", False):
        return None
    location = summaries.get("jsonl_path")
    if not isinstance(location, str) or not location:
        raise ValueError("observability.task_summaries.jsonl_path must be a non-empty string")
    path = (ROOT / location).resolve()
    if ROOT not in path.parents:
        raise ValueError("task summary log path must stay inside the MatFlow project")
    return path


def _tool_reference(registry: ToolRegistry, candidate: RouterCandidate) -> dict[str, Any]:
    spec = registry.get(candidate.tool_id)
    return RegisteredToolReference(
        registered_id=spec.tool_id,
        version=spec.version,
        label=spec.label,
        category=spec.category,
    ).model_dump() | {"retrieval_score": candidate.score, "reasons": candidate.reasons}


def _bounded(value: Any, limit: int = 5000) -> Any:
    """Keep a summary usable without silently discarding the output shape."""
    encoded = json.dumps(value, ensure_ascii=False, default=str)
    if len(encoded) <= limit:
        return value
    return {"truncated": True, "preview": encoded[:limit], "original_characters": len(encoded)}


class TaskSummaryService:
    """Deep module for route/execute summary snapshots at one stable seam."""

    def __init__(self, log_path: Path | None = None):
        self._log_path = log_path if log_path is not None else _load_log_path()

    def record_routing(self, task: TaskState, decision: RouterDecision, registry: ToolRegistry) -> TaskLogSummary:
        selected = [_tool_reference(registry, candidate) for candidate in decision.selected]
        needs_confirmation = decision.requires_human_confirmation
        summary = TaskLogSummary(
            task_id=task.task_id,
            trace_id=current_trace_id(),
            status="waiting_for_confirmation" if needs_confirmation else "routed",
            user_prompt=task.user_message,
            input_context={
                "graph_version": task.graph_version,
                "available_input_types": task.available_input_types,
                "assumptions": task.assumptions,
            },
            decision={
                "decision_id": decision.decision_id,
                "candidate_tools": [_tool_reference(registry, candidate) for candidate in decision.candidates],
                "selected_tools": selected,
                "confidence": decision.confidence,
                "rationale": decision.rationale,
                "model_opinions": [item.model_dump() for item in decision.model_decisions],
            },
            error_and_handling=(
                {"error": None, "handling": "No automatic execution. Human confirmation is required before continuing."}
                if needs_confirmation
                else {"error": None, "handling": "No exception. The selected registered tool may proceed to execution."}
            ),
        )
        return self._append(summary)

    def record_execution(self, task_id: str, execution: ExecutionResult, registry: ToolRegistry) -> TaskLogSummary | None:
        previous = self.get(task_id)
        if previous is None:
            return None
        spec = registry.get(execution.tool_id)
        tool = RegisteredToolReference(
            registered_id=spec.tool_id, version=spec.version, label=spec.label, category=spec.category
        ).model_dump()
        if execution.status == "failed":
            status = "failed"
            handling = {"error": execution.error.model_dump() if execution.error else {"code": "execution_failed", "message": "Execution failed."}, "handling": "Execution stopped safely. Correct the reported issue and retry after review."}
        elif execution.status == "waiting":
            status = "waiting"
            handling = {"error": None, "handling": "Execution paused for a human decision; no subsequent tool was run."}
        else:
            status = "completed"
            handling = {"error": None, "handling": "No exception. Execution completed."}
        summary = previous.model_copy(update={
            "trace_id": execution.trace_id,
            "status": status,
            "result": {
                "execution_id": execution.execution_id,
                "executed_tool": tool,
                "execution_status": execution.status,
                "output_schema_valid": execution.output_schema_valid,
                "output": _bounded(execution.output),
            },
            "error_and_handling": handling,
        })
        return self._append(summary)

    def get(self, task_id: str) -> TaskLogSummary | None:
        if self._log_path is None or not self._log_path.exists():
            return None
        latest: TaskLogSummary | None = None
        for line in self._log_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                parsed = TaskLogSummary.model_validate_json(line)
                if parsed.task_id == task_id:
                    latest = parsed
        return latest

    def _append(self, summary: TaskLogSummary) -> TaskLogSummary:
        if self._log_path is not None:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            payload = summary.model_dump() | {"recorded_at": datetime.now(timezone.utc).isoformat()}
            with self._log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        return summary

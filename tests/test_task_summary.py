import tempfile
import unittest
from pathlib import Path

from backend.contracts import ExecutionError, ExecutionResult, RouterCandidate, RouterDecision, TaskState
from backend.task_summary import TaskSummaryService
from backend.tool_registry import ToolRegistry


class TaskSummaryTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.service = TaskSummaryService(log_path=Path(self.tempdir.name) / "task_summaries.jsonl")
        self.registry = ToolRegistry()
        self.task = TaskState(
            task_id="summary-eis",
            user_message="请对这份 EIS 数据做基础质检，并报告异常。",
            graph_version=4,
            available_input_types=["TypedTable"],
        )
        self.candidate = RouterCandidate(
            tool_id="eis_basic_qc", version="1.0.0", score=0.91, reasons=["matches: eis", "input ports are compatible"]
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def test_route_summary_keeps_prompt_and_registry_identity(self):
        decision = RouterDecision(
            task_id=self.task.task_id, graph_version=4, candidates=[self.candidate], selected=[self.candidate],
            confidence=0.91, rationale="Selected EIS Basic Analysis.",
        )
        summary = self.service.record_routing(self.task, decision, self.registry)

        self.assertEqual(summary.user_prompt, self.task.user_message)
        selected = summary.decision["selected_tools"][0]
        self.assertEqual(selected["registered_id"], "eis_basic_qc")
        self.assertEqual(selected["label"], "EIS Basic Analysis")
        self.assertEqual(self.service.get(self.task.task_id).task_id, self.task.task_id)

    def test_failed_execution_is_merged_with_safe_handling(self):
        decision = RouterDecision(
            task_id=self.task.task_id, graph_version=4, candidates=[self.candidate], selected=[self.candidate],
            confidence=0.91, rationale="Selected EIS Basic Analysis.",
        )
        self.service.record_routing(self.task, decision, self.registry)
        execution = ExecutionResult(
            node_id="eis-1", tool_id="eis_basic_qc", tool_version="1.0.0", status="failed", trace_id="trace-test",
            error=ExecutionError(code="missing_input", message="The data input is not connected.", retryable=True),
        )
        summary = self.service.record_execution(self.task.task_id, execution, self.registry)

        self.assertEqual(summary.status, "failed")
        self.assertEqual(summary.result["executed_tool"]["registered_id"], "eis_basic_qc")
        self.assertEqual(summary.error_and_handling["error"]["code"], "missing_input")

    def test_confirmation_is_explicitly_recorded(self):
        decision = RouterDecision(
            task_id=self.task.task_id, graph_version=4, candidates=[], selected=[], confidence=0,
            rationale="No active compatible tool matched the request.", requires_human_confirmation=True,
        )
        summary = self.service.record_routing(self.task, decision, self.registry)

        self.assertEqual(summary.status, "waiting_for_confirmation")
        self.assertIn("Human confirmation", summary.error_and_handling["handling"])

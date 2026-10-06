"""`run-flow --blueprint` and `summary`: the recorded/blueprint side of the task lifecycle."""
from __future__ import annotations

import json
import unittest

from flowview.tests.support import FlowViewTestCase

BLUEPRINT_PHASES = ("request", "route", "confirm", "patch", "execute", "review", "persist")


def task_record(task_id: str, status: str = "completed", **extra) -> dict:
    record = {
        "task_id": task_id,
        "trace_id": f"trace-{task_id}",
        "status": status,
        "user_prompt": "Measure the band gap of the uploaded structure",
        "decision": {"action": "run_workflow"},
        "result": {"ok": status == "completed"},
        "recorded_at": "2024-01-01T00:00:00+00:00",
    }
    record.update(extra)
    return record


class BlueprintFlowTests(FlowViewTestCase, unittest.TestCase):
    def test_blueprint_json_exposes_the_canonical_phase_order(self):
        proc = self.run_cli("flow", "--format", "json", "--blueprint")
        self.assert_exit(proc, 0)
        payload = json.loads(proc.stdout)
        names = [phase["name"] for phase in payload["phases"]]
        self.assertEqual(names, list(BLUEPRINT_PHASES))

    def test_run_flow_alias_supports_the_flow_options(self):
        """CONTRACT.md documents `run-flow` as an alias for `flow`, options included."""
        proc = self.run_cli("run-flow", "--format", "json", "--blueprint")
        self.assert_exit(proc, 0)
        payload = json.loads(proc.stdout)
        self.assertEqual([phase["name"] for phase in payload["phases"]], list(BLUEPRINT_PHASES))

    def test_blueprint_is_available_in_every_format(self):
        for fmt in ("text", "mermaid", "json"):
            with self.subTest(fmt=fmt):
                proc = self.run_cli("flow", "--format", fmt, "--blueprint")
                self.assert_exit(proc, 0)
                self.assert_no_traceback(proc)
                self.assertTrue(proc.stdout.strip())

    def test_phase_blueprint_steps_carry_a_backend_seam(self):
        from flowview.phases import phase_blueprint

        phases = phase_blueprint()
        self.assertEqual([phase.name for phase in phases], list(BLUEPRINT_PHASES))
        for phase in phases:
            with self.subTest(phase=phase.name):
                self.assertTrue(phase.steps, f"{phase.name} must document at least one step")
                self.assertTrue(
                    any(step.detail for step in phase.steps),
                    f"{phase.name} steps must record their backend seam in `detail`",
                )


class SummaryTests(FlowViewTestCase, unittest.TestCase):
    def write_summaries(self, *records: dict) -> None:
        path = self.summary_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")

    def test_one_recorded_task_prints_a_timeline_and_exits_0(self):
        self.write_summaries(task_record("t1"))
        proc = self.run_cli("summary", "--format", "json")
        self.assert_exit(proc, 0)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["document"]["meta"]["tasks"], "1")
        self.assertEqual([phase["name"] for phase in payload["phases"]], ["t1"])

    def test_limit_keeps_only_the_newest_tasks_and_records_the_cap(self):
        self.write_summaries(task_record("t1"), task_record("t2"), task_record("t3"))
        proc = self.run_cli("summary", "--format", "json", "--limit", "1")
        self.assert_exit(proc, 0)
        payload = json.loads(proc.stdout)
        self.assertEqual([phase["name"] for phase in payload["phases"]], ["t3"])
        self.assertIn("tasks>1", payload["document"]["truncated"])

    def test_summary_task_replays_one_recorded_task(self):
        self.write_summaries(task_record("t1"), task_record("t2"))
        proc = self.run_cli("summary", "--format", "json", "--task", "t1")
        self.assert_exit(proc, 0)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["document"]["meta"]["task_id"], "t1")

    def test_summary_file_option_reads_an_explicit_log(self):
        other = self.tmp / "elsewhere" / "summaries.jsonl"
        other.parent.mkdir(parents=True, exist_ok=True)
        other.write_text(json.dumps(task_record("elsewhere")) + "\n", encoding="utf-8")
        proc = self.run_cli("summary", "--format", "json", "--file", str(other))
        self.assert_exit(proc, 0)
        payload = json.loads(proc.stdout)
        self.assertEqual([phase["name"] for phase in payload["phases"]], ["elsewhere"])

    def test_a_failed_recorded_task_makes_the_summary_non_zero(self):
        self.write_summaries(task_record("t-ok"), task_record("t-bad", status="failed", error_and_handling={"handling": "aborted", "message": "boom"}))
        proc = self.run_cli("summary", "--format", "json")
        self.assert_exit(proc, 3)
        payload = json.loads(proc.stdout)
        self.assertIn("task.failed", [issue["code"] for issue in payload["issues"]])

    def test_broken_summary_line_is_a_warning_not_a_crash(self):
        path = self.summary_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(task_record("t1")) + "\n" + "{ broken line\n", encoding="utf-8")
        proc = self.run_cli("summary", "--format", "json")
        self.assert_exit(proc, 0)
        self.assert_no_traceback(proc)
        payload = json.loads(proc.stdout)
        self.assertIn("task.unparsable_line", [issue["code"] for issue in payload["issues"]])

    def test_flow_can_replay_a_recorded_task_by_id(self):
        self.write_summaries(task_record("t1"))
        proc = self.run_cli("flow", "--format", "json", "--task", "t1")
        self.assert_exit(proc, 0)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["document"]["meta"]["task_id"], "t1")

    def test_summary_text_output_is_never_wider_than_the_width(self):
        from flowview.tests.support import display_width

        self.write_summaries(task_record("t1"), task_record("t2"))
        proc = self.run_cli("summary", "--format", "text", "--width", "72")
        self.assert_exit(proc, 0)
        offenders = [line for line in proc.stdout.splitlines() if display_width(line) > 72]
        self.assertEqual(offenders, [], offenders[:3])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

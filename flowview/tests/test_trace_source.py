"""Malformed trace inputs for ``run-flow --from-file`` / ``flow --from``.

A trace is a *recorded* file, so it may be a JSON document, a JSON array, or JSON Lines. Every
failure mode below must become a readable issue with a documented exit code, never a traceback.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from flowview.tests.support import FlowViewTestCase

EVENT = {"index": 0, "phase": "request", "name": "request.received", "status": "completed"}
EVENT_2 = {"index": 1, "phase": "execute", "name": "execute.node", "status": "running"}


class TraceSourceTests(FlowViewTestCase, unittest.TestCase):
    def trace(self, name: str = "trace.jsonl") -> Path:
        return self.data_dir / name

    def run_trace(self, *args: str, path: Path | None = None, command: str = "flow"):
        proc = self.run_cli(command, "--format", "json", "--from-file", str(path or self.trace()), *args)
        self.assert_no_traceback(proc)
        return proc

    # -- missing / unreadable ------------------------------------------------------------
    def test_missing_trace_file_is_exit_3_with_a_code(self):
        proc = self.run_trace()
        self.assert_exit(proc, 3)
        self.assert_stderr_code(proc, "trace.missing_file")

    def test_zero_byte_trace_is_reported_and_exits_3(self):
        self.write_file("trace.jsonl", "")
        proc = self.run_trace()
        self.assert_exit(proc, 3)
        self.assert_stderr_code(proc, "trace.no_document")

    def test_whitespace_only_trace_is_reported_and_exits_3(self):
        self.write_file("trace.jsonl", "   \n\t\n  \n")
        proc = self.run_trace()
        self.assert_exit(proc, 3)
        self.assert_stderr_code(proc, "trace.no_document")

    def test_undecodable_trace_is_exit_3_with_a_code(self):
        self.write_raw("trace.jsonl", b'{"index": 0, "phase": "\xff\xfe\xfa"}')
        proc = self.run_trace()
        self.assert_exit(proc, 3)
        self.assert_stderr_code(proc, "trace.undecodable")

    def test_trace_path_that_is_a_directory_is_exit_3(self):
        directory = self.data_dir / "trace-dir"
        directory.mkdir(parents=True, exist_ok=True)
        proc = self.run_trace(path=directory)
        self.assert_exit(proc, 3)
        # In JSON mode a failed source still produces one valid error document, so a consumer
        # piping FlowView into jq never has to handle an empty stream.
        payload = self.load_stdout_json(proc)
        self.assertEqual(payload["flowview_schema"], "1.0")
        self.assertTrue(payload["issues"], "the failure must be reported inside the document")
        self.assertIsNone(payload["document"]["trace"])

    # -- content shape -------------------------------------------------------------------
    def test_valid_single_document_trace_prints_json_and_exits_0(self):
        self.write_file("trace.jsonl", json.dumps({"task_id": "t1", "events": [EVENT, EVENT_2]}))
        proc = self.run_trace()
        self.assert_exit(proc, 0, )
        payload = self.load_stdout_json(proc)
        self.assertIn("flowview_schema", payload)
        self.assertIsNotNone(payload["document"]["trace"])

    def test_jsonl_with_one_broken_line_warns_and_still_reports(self):
        text = "\n".join([json.dumps(EVENT), "{ this line is not json", json.dumps(EVENT_2)])
        self.write_file("trace.jsonl", text)
        proc = self.run_trace()
        self.assert_exit(proc, 0)
        payload = self.load_stdout_json(proc)
        self.assert_issue_code(payload, "trace.bad_jsonl_line")
        trace = payload["document"]["trace"]
        self.assertTrue(trace["events"], "the readable events must still be printed")
        self.assertEqual(len(trace["events"]), 2)

    def test_jsonl_broken_line_is_exit_3_under_strict(self):
        self.write_file("trace.jsonl", "\n".join([json.dumps(EVENT), "{ broken"]))
        proc = self.run_trace("--strict")
        self.assert_exit(proc, 3)
        payload = self.load_stdout_json(proc)
        self.assert_issue_code(payload, "trace.bad_jsonl_line")

    def test_valid_json_that_is_not_an_event_list_is_diagnosed_not_crashed(self):
        """A file that parses but carries no events is a healthy-but-empty replay: exit 0 with
        ``trace.unknown_payload`` warnings and an info ``trace.no_events``, and exit 3 under
        ``--strict`` (the documented promotion of warnings)."""
        self.write_file("trace.jsonl", json.dumps([1, 2, 3]))
        proc = self.run_trace()
        self.assert_no_traceback(proc)
        self.assert_exit(proc, 0)
        payload = self.load_stdout_json(proc)
        self.assert_issue_code(payload, "trace.unknown_payload")
        self.assert_issue_code(payload, "trace.no_events")
        self.assertEqual(payload["document"]["trace"]["events"], [])

        strict = self.run_trace("--strict")
        self.assert_exit(strict, 3)

    def test_events_list_with_non_objects_reports_invalid_events(self):
        self.write_file("trace.jsonl", json.dumps({"events": [1, "two", EVENT]}))
        proc = self.run_trace()
        self.assert_no_traceback(proc)
        self.assert_exit(proc, 0)
        payload = self.load_stdout_json(proc)
        self.assert_issue_code(payload, "trace.invalid_event")
        self.assertEqual(len(payload["document"]["trace"]["events"]), 1)

    def test_json_object_without_events_is_diagnosed_not_crashed(self):
        self.write_file("trace.jsonl", json.dumps({"unrelated": {"nested": True}}))
        proc = self.run_trace()
        self.assert_no_traceback(proc)
        self.assert_exit(proc, 0)
        payload = self.load_stdout_json(proc)
        self.assert_issue_code(payload, "trace.unknown_payload")
        self.assert_issue_code(payload, "trace.no_events")

    # -- unit level ----------------------------------------------------------------------
    def test_split_json_documents_reports_empty_file_code(self):
        from flowview.loader import split_json_documents

        documents, issues = split_json_documents("")
        self.assertEqual(documents, [])
        self.assertEqual([issue.code for issue in issues], ["trace.empty_file"])

    def test_split_json_documents_keeps_readable_jsonl_lines(self):
        from flowview.loader import split_json_documents

        documents, issues = split_json_documents("\n".join([json.dumps(EVENT), "oops", json.dumps(EVENT_2)]))
        self.assertEqual(len(documents), 2)
        self.assertEqual([issue.code for issue in issues], ["trace.bad_jsonl_line"])

    def test_read_trace_raises_flow_source_error_with_a_code(self):
        from flowview.codes import FlowSourceError
        from flowview.loader import read_trace

        with self.assertRaises(FlowSourceError) as caught:
            read_trace(self.trace())
        self.assertEqual(caught.exception.exit_code, 3)
        self.assertEqual(caught.exception.issue.code, "trace.missing_file")

    # -- aliases -------------------------------------------------------------------------
    def test_flow_and_run_flow_are_the_same_command(self):
        self.write_file("trace.jsonl", json.dumps({"events": [EVENT]}))
        flow = self.run_cli("flow", "--format", "text", "--from-file", str(self.trace()))
        alias = self.run_cli("run-flow", "--format", "text", "--from-file", str(self.trace()))
        self.assert_exit(flow, 0)
        self.assert_exit(alias, 0)
        self.assertEqual(flow.stdout, alias.stdout)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

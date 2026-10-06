"""Regression guards for FlowView's hostile-input hardening.

Each test here pins a defect that was found by adversarial verification and then fixed. They are
grouped by the failure the defect caused, because the important property is not the shape of the
fix but that the printer keeps printing:

* a pathological document must not exhaust the interpreter stack;
* a pathological path must not escape as an unexpected internal error;
* a cycle must be visible without being fatal;
* JSON mode must always yield exactly one JSON document, even when everything else fails.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from .support import FlowViewTestCase, display_width, edge, graph_payload, node


def make_symlink(link: Path, target: Path, *, directory: bool = False) -> bool:
    """Create a self-referential symlink, falling back to ``mklink`` on Windows.

    ``os.symlink`` needs a privilege Windows does not grant by default, but ``mklink`` works from
    an elevated shell, so the path-hardening tests actually run instead of silently skipping.
    """
    try:
        os.symlink(target, link, target_is_directory=directory)
        return True
    except (OSError, NotImplementedError, AttributeError):
        pass
    if sys.platform != "win32":
        return False
    flag = "/D" if directory else ""
    result = subprocess.run(
        ["cmd", "/c", "mklink", flag, str(link), str(target)],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and os.path.lexists(link)


class PathologicalDocumentTests(FlowViewTestCase, unittest.TestCase):
    """Deep nesting and huge graphs: the walk and the parser must both be bounded."""

    def test_deeply_nested_json_is_a_diagnosed_error_not_a_recursion_crash(self):
        # 5000 levels of arrays: json.loads recurses once per level.
        self.write_graph("[" * 5000 + "]" * 5000)
        proc, payload = self.graph_json()
        self.assert_exit(proc, 3)
        self.assert_no_traceback(proc)
        self.assert_issue_code(payload, "graph.too_deep")

    def test_deeply_nested_json_works_in_text_and_mermaid_modes_too(self):
        self.write_graph("[" * 5000 + "]" * 5000)
        for fmt in ("text", "mermaid"):
            proc = self.run_cli("--format", fmt, "graph")
            self.assert_exit(proc, 3)
            self.assert_no_traceback(proc)

    def test_a_long_chain_survives_every_format_with_full(self):
        # A recursive cycle walk overflowed the stack here (depth == longest path).
        self.write_graph(graph_payload(
            [node(f"n{index}", status="completed") for index in range(3000)],
            [edge(f"e{index}", f"n{index}", f"n{index + 1}") for index in range(2999)],
        ))
        for fmt in ("text", "mermaid", "json"):
            proc = self.run_cli("--format", fmt, "graph", "--full")
            self.assert_exit(proc, 0, )
            self.assert_no_traceback(proc)
            self.assertNotIn("RecursionError", proc.combined)

    def test_a_long_cycle_is_detected_without_recursing(self):
        count = 1200
        nodes = [node(f"n{index}", status="ready") for index in range(count)]
        edges = [edge(f"e{index}", f"n{index}", f"n{index + 1}") for index in range(count - 1)]
        edges.append(edge("e-close", f"n{count - 1}", "n0"))
        self.write_graph(graph_payload(nodes, edges))
        proc, payload = self.graph_json("--full")
        self.assert_exit(proc, 0)
        self.assert_issue_code(payload, "graph.cycle")
        # The reported cycle repeats its entry node to show the closure, so a 1200-node loop is
        # 1201 entries long.
        lengths = sorted(len(cycle) for cycle in payload["graph_stats"]["cycles"])
        self.assertEqual(lengths, [count + 1])


class CycleVisibilityTests(FlowViewTestCase, unittest.TestCase):
    """A cycle is a warning everywhere: visible, and fatal only under --strict."""

    def _cycle(self):
        self.write_graph(graph_payload(
            [node("a"), node("b")],
            [edge("e1", "a", "b"), edge("e2", "b", "a")],
        ))

    def test_cycle_is_reported_in_every_format(self):
        self._cycle()
        for fmt in ("text", "mermaid", "json"):
            proc = self.run_cli("--format", fmt, "graph")
            self.assert_exit(proc, 0)
            self.assertIn("cycle", proc.stdout.lower())

    def test_cycle_exit_code_is_zero_without_strict_and_three_with_it(self):
        self._cycle()
        self.assert_exit(self.run_cli("graph"), 0)
        self.assert_exit(self.run_cli("graph", "--strict"), 3)

    def test_self_loop_is_a_cycle(self):
        self.write_graph(graph_payload([node("a")], [edge("e", "a", "a")]))
        proc, payload = self.graph_json()
        self.assert_exit(proc, 0)
        self.assert_issue_code(payload, "graph.cycle")


class PathologicalPathTests(FlowViewTestCase, unittest.TestCase):
    """A broken path is user input, never an unexpected internal error."""

    def test_graph_path_that_is_a_symlink_loop_is_diagnosed(self):
        loop = self.data_dir / "loop.json"
        if not make_symlink(loop, loop):
            self.skipTest("this platform cannot create a self-referential symlink")
        proc = self.run_cli("graph", "--graph-file", str(loop))
        self.assert_exit(proc, 3)
        self.assert_no_traceback(proc)
        self.assertIn("path.symlink_loop", proc.stderr + proc.stdout)

    def test_data_root_that_is_a_symlink_loop_is_diagnosed(self):
        loop = self.tmp / "dataloop"
        if not make_symlink(loop, loop, directory=True):
            self.skipTest("this platform cannot create a self-referential directory symlink")
        for command in ("graph", "doctor", "summary"):
            proc = self.run_cli(command, "--data-root", str(loop))
            self.assert_exit(proc, 3)
            self.assert_no_traceback(proc)
            self.assertIn("--data-root", proc.stderr)

    def test_out_into_a_broken_path_reports_a_source_error(self):
        blocker = self.tmp / "blocker"
        blocker.write_text("not a directory", encoding="utf-8")
        proc = self.run_cli("graph", "--out", str(blocker / "nested" / "out.json"))
        self.assert_exit(proc, 3)
        self.assert_no_traceback(proc)
        self.assertIn("cannot write", proc.stderr)

    def test_explicitly_missing_graph_file_is_an_error_but_the_default_is_not(self):
        explicit = self.run_cli("graph", "--graph-file", str(self.data_dir / "nope.json"))
        self.assert_exit(explicit, 3)
        self.assertIn("graph.missing_file", explicit.stderr + explicit.stdout)

        default = self.run_cli("graph")
        self.assert_exit(default, 0, )


class JsonAlwaysAnswersTests(FlowViewTestCase, unittest.TestCase):
    """In JSON mode stdout is one valid document, on success and on failure alike."""

    def test_hard_source_errors_still_emit_one_json_document(self):
        cases = (
            ("run-flow", "--from-file", str(self.data_dir / "missing.jsonl")),
            ("summary", "--task", "does-not-exist"),
            ("summary", "--file", str(self.data_dir / "missing-summaries.jsonl")),
        )
        for case in cases:
            proc = self.run_cli("--format", "json", *case)
            self.assert_exit(proc, 3)
            self.assert_no_traceback(proc)
            payload = json.loads(proc.stdout)  # must not raise
            self.assertEqual(payload["flowview_schema"], "1.0")
            self.assertTrue(payload["issues"], f"{case}: the failure must travel inside the document")

    def test_text_mode_keeps_stdout_empty_for_a_source_error(self):
        proc = self.run_cli("run-flow", "--format", "text", "--from-file", str(self.data_dir / "missing.jsonl"))
        self.assert_exit(proc, 3)
        self.assertFalse(proc.stdout.strip())

    def test_exit_code_hint_matches_the_process_exit_code(self):
        # A consumer parsing JSON should be able to read the diagnosis without watching stderr.
        self.write_graph(graph_payload([node("a", status="ready")], []))
        healthy = self.run_cli("--format", "json", "graph")
        self.assert_exit(healthy, 0)
        self.assertEqual(json.loads(healthy.stdout)["exit_code_hint"], 0)

        broken = self.run_cli("--format", "json", "graph", "--graph-file", str(self.data_dir / "nope.json"))
        self.assert_exit(broken, 3)
        self.assertEqual(json.loads(broken.stdout)["exit_code_hint"], 3)

    def test_a_blank_trace_file_is_diagnosed(self):
        self.write_file("blank.jsonl", "\n\n   \n")
        proc = self.run_cli("--format", "json", "run-flow", "--from-file", str(self.data_dir / "blank.jsonl"))
        self.assert_exit(proc, 3)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["issues"])

    def test_a_directory_given_as_a_trace_is_not_called_a_permission_problem(self):
        directory = self.data_dir / "trace-dir"
        directory.mkdir(parents=True, exist_ok=True)
        proc = self.run_cli("--format", "json", "run-flow", "--from-file", str(directory))
        self.assert_exit(proc, 3)
        self.assert_no_traceback(proc)
        codes = [issue["code"] for issue in json.loads(proc.stdout)["issues"]]
        self.assertIn("trace.is_directory", codes)
        self.assertNotIn("trace.permission_denied", codes)

    def test_doctor_format_json_is_json(self):
        proc = self.run_cli("doctor", "--format", "json")
        self.assert_exit(proc, 0)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["document"]["meta"]["mode"], "doctor")
        phase_names = [phase["name"] for phase in payload["phases"]]
        self.assertIn("sources", phase_names)
        self.assertIn("renderers", phase_names)

    def test_a_broken_data_root_still_emits_one_json_document(self):
        blocker = self.tmp / "data-root-blocker"
        blocker.write_text("not a directory", encoding="utf-8")
        proc = self.run_cli("--format", "json", "graph", "--data-root", str(blocker / "nested"))
        self.assert_exit(proc, 0)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["flowview_schema"], "1.0")

    def test_an_unresolvable_data_root_emits_one_json_document(self):
        loop = self.tmp / "dataloop-json"
        if not make_symlink(loop, loop, directory=True):
            self.skipTest("this platform cannot create a self-referential directory symlink")
        proc = self.run_cli("--format", "json", "graph", "--data-root", str(loop))
        self.assert_exit(proc, 3)
        self.assert_no_traceback(proc)
        payload = json.loads(proc.stdout)  # must not raise: no empty stream in JSON mode
        self.assertEqual(payload["flowview_schema"], "1.0")
        self.assertTrue(payload["issues"])


class FilterVocabularyTests(FlowViewTestCase, unittest.TestCase):
    """A filter that matches nothing must say why instead of silently showing nothing."""

    def test_unknown_status_value_is_reported(self):
        self.write_graph(graph_payload([node("a", status="ready")], []))
        proc, payload = self.graph_json("--status", "teleported")
        self.assert_exit(proc, 0)
        self.assert_issue_code(payload, "filter.unknown_status")

    def test_known_status_value_is_not_reported(self):
        self.write_graph(graph_payload([node("a", status="ready")], []))
        proc, payload = self.graph_json("--status", "ready")
        self.assert_exit(proc, 0)
        self.assert_no_issue_code(payload, "filter.unknown_status")

    def test_limit_below_one_is_clamped_and_reported(self):
        record = {
            "schema_version": "1.0",
            "task_id": "t1",
            "trace_id": "tr1",
            "status": "routed",
            "user_prompt": "do the thing",
            "input_context": {},
            "decision": {"selected_tools": [], "candidate_tools": [], "confidence": 1.0, "rationale": "r"},
            "result": None,
            "error_and_handling": {"error": None, "handling": "none"},
        }
        path = self.summary_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        proc = self.run_cli("--format", "json", "summary", "--limit", "0")
        self.assert_exit(proc, 0)
        payload = json.loads(proc.stdout)
        self.assert_issue_code(payload, "cli.limit_clamped")


class WidthFloorTests(FlowViewTestCase, unittest.TestCase):
    """--width is honoured down to a floor, and the floor is announced rather than hidden."""

    def test_narrow_widths_are_bounded_and_announced(self):
        self.write_graph(graph_payload(
            [node("a", status="exploded"), node("b", status="error")],
            [edge("e1", "a", "b")],
        ))
        for requested in (1, 5, 10, 15):
            proc = self.run_cli("graph", "--format", "text", "--width", str(requested))
            self.assert_exit(proc, 0)
            offending = [
                line for line in proc.stdout.splitlines()
                if display_width(line) > 20
            ]
            self.assertEqual(offending, [], f"--width {requested}: {offending[:2]!r}")
            self.assertIn("minimum", proc.stderr)

    def test_width_at_or_above_the_floor_is_exact(self):
        self.write_graph(graph_payload(
            [node("a", status="error"), node("b")],
            [edge("e1", "a", "b")],
        ))
        for requested in (20, 30, 45, 60):
            proc = self.run_cli("graph", "--format", "text", "--width", str(requested))
            self.assert_exit(proc, 0)
            offending = [
                (display_width(line), line)
                for line in proc.stdout.splitlines()
                if display_width(line) > requested
            ]
            self.assertEqual(offending, [], f"--width {requested}: {offending[:2]!r}")

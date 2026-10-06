"""The CLI surface frozen by CONTRACT.md: help, version, exit codes, caps and stream safety."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest

from flowview.tests.support import CLI_MODULE, FlowViewTestCase, edge, graph_payload, node

BROKEN_PIPE_BODY = """
import sys


class BrokenStdout:
    \"\"\"A stdout whose every write fails the way a closed downstream pipe does.\"\"\"

    encoding = "utf-8"

    def write(self, text):
        raise BrokenPipeError(32, "Broken pipe")

    def flush(self):
        # A no-op: this models a closed downstream pipe, and raising here would make the
        # interpreter's own shutdown flush print an unrelated "Exception ignored" notice.
        return None

    def isatty(self):
        return False


from flowview.cli import main

sys.stdout = BrokenStdout()
raise SystemExit(main(["graph", "--format", "text"]))
"""


class HelpAndUsageTests(FlowViewTestCase, unittest.TestCase):
    def test_help_exits_0_and_lists_every_subcommand(self):
        proc = self.run_cli("--help")
        self.assert_exit(proc, 0)
        for command in ("graph", "flow", "run-flow", "summary", "doctor"):
            with self.subTest(command=command):
                self.assertIn(command, proc.stdout)

    def test_every_subcommand_accepts_help(self):
        for command in ("graph", "flow", "run-flow", "summary", "doctor"):
            with self.subTest(command=command):
                proc = self.run_cli(command, "--help")
                self.assert_exit(proc, 0)
                self.assertTrue(proc.stdout.strip())

    def test_version_exits_0(self):
        proc = self.run_cli("--version")
        self.assert_exit(proc, 0)
        self.assertIn("FlowView", proc.stdout)
        self.assertRegex(proc.stdout, r"\d+\.\d+")

    def test_no_subcommand_is_a_usage_error(self):
        proc = self.run_cli()
        self.assert_exit(proc, 2)

    def test_unknown_subcommand_is_a_usage_error_without_traceback(self):
        proc = self.run_cli("frobnicate")
        self.assert_exit(proc, 2)
        self.assert_no_traceback(proc)

    def test_unknown_option_is_a_usage_error(self):
        proc = self.run_cli("--not-an-option", "graph")
        self.assert_exit(proc, 2)

    def test_bad_format_choice_is_a_usage_error(self):
        proc = self.run_cli("--format", "yaml", "graph")
        self.assert_exit(proc, 2)

    def test_bad_width_value_is_a_usage_error(self):
        proc = self.run_cli("--format", "text", "graph", "--width", "wide")
        self.assert_exit(proc, 2)

    def test_common_options_after_the_subcommand(self):
        """Regression guard: `graph --format json` is the documented user-facing spelling."""
        self.write_graph(graph_payload([node("a")], []))
        proc = self.run_cli("graph", "--format", "json")
        self.assert_exit(proc, 0)
        json.loads(proc.stdout)

    def test_common_options_before_the_subcommand_are_honoured(self):
        """CONTRACT.md documents `python -m flowview [--format ...] <command> ...`.

        Regression guard for the argparse pitfall where subparser defaults clobber values the
        top-level parser already parsed.
        """
        self.write_graph(graph_payload([node("a")], []))
        proc = self.run_cli("--format", "json", "graph")
        self.assert_exit(proc, 0)
        payload = json.loads(proc.stdout)
        self.assertIn("flowview_schema", payload)

    def test_strict_before_the_subcommand_is_honoured(self):
        self.write_graph(graph_payload([node("a", status="exploded")], []))
        proc = self.run_cli("--strict", "graph", "--format", "json")
        self.assert_exit(proc, 3)

    def test_out_before_the_subcommand_is_honoured(self):
        self.write_graph(graph_payload([node("a")], []))
        target = self.tmp / "pre-placement" / "graph.json"
        proc = self.run_cli("graph", "--out", str(target), "--format", "json")
        self.assert_exit(proc, 0)
        self.assertTrue(target.is_file(), "--out before the subcommand was ignored")

    def test_no_color_works_in_both_placements(self):
        self.write_graph(graph_payload([node("a")], []))
        for args in (("graph", "--no-color"), ("--no-color", "graph")):
            with self.subTest(args=args):
                proc = self.run_cli(*args)
                self.assert_exit(proc, 0)
                self.assertNotIn("\x1b", proc.stdout)


class OptionPlacementEquivalenceTests(FlowViewTestCase, unittest.TestCase):
    """Before and after the subcommand must be interchangeable for every common option.

    CONTRACT.md documents both `python -m flowview [--format json] graph` and
    `python -m flowview graph --format json`; argparse makes it easy to define both spellings
    while letting the subparser defaults clobber the pre-subcommand value, so this class pins
    byte-for-byte equivalence of stdout and the exit code.
    """

    def setUp(self):
        super().setUp()
        self.write_graph(
            graph_payload([node("a", "completed"), node("b", "running")], [edge("e1", "a", "b"), edge("e2", "b", "a")])
        )
        log = self.summary_path()
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(json.dumps({"task_id": "t1", "status": "completed", "user_prompt": "p"}) + "\n", encoding="utf-8")
        self.trace_path = self.data_dir / "trace.jsonl"
        self.trace_path.write_text(
            json.dumps({"index": 0, "phase": "request", "name": "request.received", "status": "completed"}) + "\n",
            encoding="utf-8",
        )

    def both_placements(self, before, command, after=()):
        pre = self.run_cli(*before, command, *after)
        post = self.run_cli(command, *before, *after)
        return pre, post

    def test_every_common_option_is_equivalent_in_both_placements(self):
        scenarios = (
            ("json", ("--format", "json"), "graph", ()),
            ("mermaid", ("--format", "mermaid"), "graph", ()),
            ("width", ("--format", "text", "--width", "60"), "graph", ()),
            ("no-color", ("--no-color", "--format", "text", "--width", "100"), "graph", ()),
            ("full", ("--full", "--format", "json"), "graph", ()),
            ("verbose", ("-v", "--format", "json"), "graph", ()),
            ("blueprint", ("--format", "json"), "flow", ("--blueprint",)),
            ("from-file", ("--format", "json"), "flow", ("--from-file", str(self.trace_path))),
            ("summary", ("--format", "json"), "summary", ()),
            ("doctor", ("--format", "text"), "doctor", ()),
        )
        for label, before, command, after in scenarios:
            with self.subTest(scenario=label):
                pre, post = self.both_placements(before, command, after)
                self.assertEqual(pre.returncode, post.returncode, (label, pre.stderr, post.stderr))
                self.assertEqual(pre.stdout, post.stdout, f"{label}: placements produced different output")

    def test_out_option_is_equivalent_in_both_placements(self):
        pre_target = self.tmp / "pre" / "graph.json"
        post_target = self.tmp / "post" / "graph.json"
        pre = self.run_cli("--out", str(pre_target), "--format", "json", "graph")
        post = self.run_cli("graph", "--out", str(post_target), "--format", "json")
        self.assertEqual(pre.returncode, post.returncode)
        self.assertTrue(pre_target.is_file(), "--out before the subcommand was ignored")
        self.assertTrue(post_target.is_file(), "--out after the subcommand was ignored")
        self.assertEqual(pre_target.read_text(encoding="utf-8"), post_target.read_text(encoding="utf-8"))

    def test_strict_is_equivalent_in_both_placements_on_warnings(self):
        self.write_graph(graph_payload([node("a", status="exploded")], []))
        pre, post = self.both_placements(("--strict", "--format", "json"), "graph")
        self.assertEqual(pre.returncode, 3, pre.stderr)
        self.assertEqual(post.returncode, 3, post.stderr)
        self.assertEqual(pre.stdout, post.stdout)

    def test_no_strict_is_equivalent_in_both_placements_on_warnings(self):
        self.write_graph(graph_payload([node("a", status="exploded")], []))
        pre, post = self.both_placements(("--format", "json"), "graph")
        self.assertEqual(pre.returncode, 0, pre.stderr)
        self.assertEqual(post.returncode, 0, post.stderr)
        self.assertEqual(pre.stdout, post.stdout)


class SourceFailureTests(FlowViewTestCase, unittest.TestCase):
    def test_unusable_trace_source_is_exit_3_without_a_traceback(self):
        proc = self.run_cli("run-flow", "--format", "json", "--from-file", str(self.data_dir / "missing.jsonl"))
        self.assert_exit(proc, 3)
        self.assert_no_traceback(proc)
        # JSON mode reports the failure as a document, never as an empty stream.
        payload = self.load_stdout_json(proc)
        self.assertEqual(payload["flowview_schema"], "1.0")
        self.assertTrue(payload["issues"])
        self.assertIn("mode", payload["document"]["meta"])

    def test_unusable_trace_source_prints_nothing_in_text_mode(self):
        proc = self.run_cli("run-flow", "--format", "text", "--from-file", str(self.data_dir / "missing.jsonl"))
        self.assert_exit(proc, 3)
        self.assert_no_traceback(proc)
        self.assertFalse(proc.stdout.strip(), "a text-mode source error belongs on stderr, not stdout")

    def test_summary_without_any_recorded_summaries_is_exit_3(self):
        proc = self.run_cli("summary", "--format", "text")
        self.assert_exit(proc, 3)
        self.assert_no_traceback(proc)
        self.assertRegex(proc.stderr, r"(?i)summar")

    def test_summary_with_an_empty_summary_log_is_exit_3(self):
        path = self.summary_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        proc = self.run_cli("summary", "--format", "text")
        self.assert_exit(proc, 3)
        self.assert_no_traceback(proc)

    def test_summary_task_that_does_not_exist_is_exit_3(self):
        proc = self.run_cli("flow", "--format", "text", "--task", "no-such-task")
        self.assert_exit(proc, 3)
        self.assert_no_traceback(proc)

    def test_verbose_flag_keeps_the_documented_exit_code(self):
        proc = self.run_cli("flow", "-v", "--from-file", str(self.data_dir / "missing.jsonl"))
        self.assert_exit(proc, 3)


class StrictModeTests(FlowViewTestCase, unittest.TestCase):
    def warnings_only_graph(self):
        return graph_payload([node("a", status="exploded")], [])

    def test_warnings_only_exit_0_without_strict(self):
        self.write_graph(self.warnings_only_graph())
        proc = self.run_cli("graph", "--format", "json")
        self.assert_exit(proc, 0)

    def test_warnings_only_exit_3_with_strict(self):
        self.write_graph(self.warnings_only_graph())
        proc = self.run_cli("graph", "--strict", "--format", "json")
        self.assert_exit(proc, 3)

    def test_strict_does_not_change_info_only_documents(self):
        proc = self.run_cli("graph", "--strict", "--format", "json")
        self.assert_exit(proc, 0)


class OutputTargetTests(FlowViewTestCase, unittest.TestCase):
    def test_out_creates_missing_parent_directories(self):
        self.write_graph(graph_payload([node("a")], []))
        target = self.tmp / "reports" / "deeply" / "nested" / "flow.json"
        proc = self.run_cli("graph", "--out", str(target), "--format", "json")
        self.assert_exit(proc, 0)
        self.assertTrue(target.is_file(), f"--out did not create {target}")
        payload = json.loads(target.read_text(encoding="utf-8"))
        self.assertIn("flowview_schema", payload)

    def test_out_writes_the_document_even_when_the_source_is_corrupt(self):
        self.write_graph("{ not json")
        target = self.tmp / "out" / "corrupt.json"
        proc = self.run_cli("graph", "--out", str(target), "--format", "json")
        self.assert_exit(proc, 3)
        payload = json.loads(target.read_text(encoding="utf-8"))
        self.assertIn("graph.invalid_json", [issue["code"] for issue in payload["issues"]])

    def test_out_keeps_stdout_free_of_the_document(self):
        self.write_graph(graph_payload([node("a")], []))
        target = self.tmp / "out" / "graph.json"
        proc = self.run_cli("graph", "--out", str(target), "--format", "json")
        self.assert_exit(proc, 0)
        self.assertNotIn("flowview_schema", proc.stdout)
        self.assertRegex(proc.stdout, r"(?i)wrote")


class BrokenPipeTests(FlowViewTestCase, unittest.TestCase):
    def test_broken_pipe_returns_success_without_a_traceback(self):
        self.write_graph(graph_payload([node("a", "completed"), node("b", "running")], []))
        proc = self.run_bootstrap(BROKEN_PIPE_BODY)
        self.assert_no_traceback(proc)
        self.assertNotEqual(proc.returncode, 1, proc)
        self.assertEqual(proc.returncode, 0, proc)

    def test_closed_real_stdout_pipe_is_not_an_internal_error(self):
        """The same guarantee, but with the operating system closing the pipe for real."""
        self.write_graph(graph_payload([node(f"n{index}") for index in range(50)], []))
        process = subprocess.Popen(
            [sys.executable, "-m", CLI_MODULE, "graph", "--format", "text", "--width", "120"],
            cwd=str(support_root()),
            env=self.env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        try:
            assert process.stdout is not None and process.stderr is not None
            process.stdout.close()
            stderr = process.stderr.read()
            process.stderr.close()
            process.wait(timeout=60)
        finally:
            if process.poll() is None:  # pragma: no cover - defensive
                process.kill()
        self.assertNotEqual(process.returncode, 1, stderr)
        self.assertNotIn("Traceback (most recent call last)", stderr or "")
        self.assertNotIn("unexpected internal error", stderr or "")


def support_root():
    from flowview.tests import support

    return support.REPO_ROOT


class DoctorTests(FlowViewTestCase, unittest.TestCase):
    def test_doctor_reports_healthy_sources_and_exits_0(self):
        proc = self.run_cli("doctor")
        self.assert_exit(proc, 0)
        self.assert_no_traceback(proc)
        self.assertIn("FlowView", proc.stdout)

    def test_doctor_list_shows_audited_files(self):
        proc = self.run_cli("doctor", "--list")
        self.assert_exit(proc, 0)
        # Compare resolved paths: on Windows a temp directory can come back as an 8.3 short name
        # while the CLI prints the long form (or the other way round).
        self.assertIn(str(self.data_dir.resolve()), proc.stdout)

    def test_doctor_does_not_import_backend_into_its_verdict(self):
        proc = self.run_cli("doctor")
        self.assert_exit(proc, 0)
        self.assertRegex(proc.stdout, r"(?i)offline|backend")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

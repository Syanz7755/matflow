"""Renderer contract, asserted on the real stdout of real subprocesses where possible.

Mermaid output must be syntactically usable and escape-free-looking; JSON must be exactly one
document; text must respect ``--width`` and keep spelling statuses out in words.
"""
from __future__ import annotations

import json
import re
import unittest

from flowview.model import FlowEdge, FlowEvent, FlowGraph, FlowNode, FlowTrace
from flowview.tests.support import FlowViewTestCase, display_width, graph_payload, node, edge

ALL_STATUSES = ("ready", "running", "completed", "waiting", "error", "cancelled", "unknown")

LABEL_GRAPH = FlowGraph(
    graph_id="labels",
    version=1,
    source="(fixture)",
    nodes=(
        FlowNode(id="quoted", label='He said "hi"'),
        FlowNode(id="multiline", label="first line\nsecond line"),
        FlowNode(id="empty-label-node", label=""),
    ),
    edges=(FlowEdge(id="e1", source="quoted", target="multiline"),),
)

CYCLE_GRAPH = FlowGraph(
    graph_id="cycle",
    version=1,
    source="(fixture)",
    nodes=(FlowNode(id="a", label="A", status="completed"), FlowNode(id="b", label="B", status="running")),
    edges=(
        FlowEdge(id="e1", source="a", target="b"),
        FlowEdge(id="e2", source="b", target="a"),
    ),
)


def status_graph() -> FlowGraph:
    return FlowGraph(
        graph_id="statuses",
        version=2,
        source="(fixture)",
        nodes=tuple(FlowNode(id=f"n-{status}", label=f"Node {status}", status=status, tool_id=f"tool.{status}") for status in ALL_STATUSES),
    )


def rich_graph() -> FlowGraph:
    """A graph wide enough that a 60-column table has to wrap or truncate."""
    nodes = [
        FlowNode(
            id=f"pipeline-step-{index:02d}",
            label=f"Pipeline step {index:02d} with a deliberately long descriptive label",
            status=ALL_STATUSES[index % len(ALL_STATUSES)],
            tool_id=f"tool.pipeline.step.{index}",
            error="boom: the recorded error text is long enough to need wrapping" if index % 5 == 0 else None,
        )
        for index in range(12)
    ]
    edges = tuple(
        FlowEdge(id=f"e{index}", source=f"pipeline-step-{index:02d}", target=f"pipeline-step-{index + 1:02d}", target_port="in")
        for index in range(11)
    )
    return FlowGraph(graph_id="rich", version=4, source="(fixture)", nodes=tuple(nodes), edges=edges)


class MermaidRendererTests(FlowViewTestCase, unittest.TestCase):
    def renderer(self):
        from flowview.mermaid import MermaidRenderer

        return MermaidRenderer()

    def test_mermaid_graph_starts_with_a_diagram_keyword(self):
        proc = self.run_cli("graph", "--format", "mermaid")
        self.assert_exit(proc, 0)
        first = next(line for line in proc.stdout.splitlines() if line.strip())
        self.assertRegex(first.strip(), r"^(flowchart\s+(TD|TB|LR|RL|BT)|graph\s+(TD|TB|LR|RL|BT))")

    def test_mermaid_outputs_never_contain_ansi(self):
        self.write_graph(graph_payload([node("a", "completed"), node("b", "running")], [edge("e", "a", "b")]))
        for fmt in ("mermaid", "text", "json"):
            with self.subTest(fmt=fmt):
                proc = self.run_cli("graph", "--format", fmt)
                self.assertNotIn("\x1b", proc.stdout)

    def test_label_with_double_quote_is_escaped(self):
        rendered = self.renderer().render_graph(LABEL_GRAPH)
        self.assertIn("#quot;", rendered)
        self.assertIn("He said", rendered)
        self.assertNotIn('"hi"', rendered)

    def test_label_with_newline_becomes_a_break_not_a_raw_newline(self):
        rendered = self.renderer().render_graph(LABEL_GRAPH)
        self.assertIn("<br/>", rendered)
        self.assertNotIn("first line\n", rendered)
        self.assertIn("first line<br/>second line", rendered)

    def test_empty_label_falls_back_to_the_node_id(self):
        rendered = self.renderer().render_graph(LABEL_GRAPH)
        self.assertIn("empty-label-node", rendered)

    def test_empty_graph_is_still_valid_and_mentions_emptiness(self):
        rendered = self.renderer().render_graph(FlowGraph(graph_id="empty", source="(fixture)"))
        self.assertTrue(rendered.strip(), "an empty graph must still print something")
        first = next(line for line in rendered.splitlines() if line.strip())
        self.assertRegex(first.strip(), r"^(flowchart|graph|%%|flowchart\s+TD)")
        self.assertRegex(rendered, r"(?i)empty|no nodes")

    def test_empty_graph_through_the_cli_mentions_emptiness(self):
        self.write_graph({"graph_id": "empty", "version": 0, "nodes": [], "edges": []})
        proc = self.run_cli("graph", "--format", "mermaid")
        self.assert_exit(proc, 0)
        self.assertRegex(proc.stdout, r"(?i)empty|no nodes")

    def test_mermaid_is_deterministic(self):
        self.write_graph(graph_payload([node("b"), node("a")], [edge("e2", "a", "b"), edge("e1", "a", "b")]))
        first = self.run_cli("graph", "--format", "mermaid")
        second = self.run_cli("graph", "--format", "mermaid")
        self.assertEqual(first.stdout, second.stdout)

    def test_render_trace_is_a_sequence_diagram(self):
        trace = FlowTrace(
            events=(
                FlowEvent(index=0, phase="request", name="request.received", status="completed"),
                FlowEvent(index=1, phase="execute", name="execute.node", status="running"),
            ),
            task_id="t1",
            trace_id="tr1",
            source="(fixture)",
        )
        rendered = self.renderer().render_trace(trace)
        self.assertTrue(rendered.strip().startswith("sequenceDiagram"), rendered[:120])
        self.assertNotIn("\x1b", rendered)

    def test_render_state_is_a_state_diagram(self):
        rendered = self.renderer().render_state(status_graph())
        self.assertTrue(rendered.strip().startswith("stateDiagram"), rendered[:120])

    def test_long_label_is_truncated_with_an_ellipsis(self):
        node_long = FlowNode(id="long", label="x" * 200)
        rendered = self.renderer().render_graph(FlowGraph(nodes=(node_long,)))
        self.assertIn("\u2026", rendered)
        self.assertNotIn("x" * 120, rendered)


class JsonRendererTests(FlowViewTestCase, unittest.TestCase):
    def assert_single_document(self, proc):
        json.loads(proc.stdout)  # raises when it is not valid JSON at all
        document, end = json.JSONDecoder().raw_decode(proc.stdout)
        self.assertEqual(proc.stdout[end:].strip(), "", "JSON mode must print nothing but the document")
        return document

    def test_payload_has_the_documented_keys_and_nothing_else_on_stdout(self):
        self.write_graph(graph_payload([node("a"), node("b")], [edge("e", "a", "b")]))
        proc = self.run_cli("graph", "--format", "json")
        self.assert_exit(proc, 0)
        payload = self.assert_single_document(proc)
        for key in ("flowview_schema", "document", "phases", "issues"):
            self.assertIn(key, payload)
        self.assertTrue(payload["flowview_schema"])
        self.assertIsInstance(payload["phases"], list)
        self.assertIsInstance(payload["issues"], list)
        self.assertEqual(payload["document"]["graph"]["graph_id"], "test-graph")
        self.assertEqual(len(payload["document"]["graph"]["nodes"]), 2)

    def test_json_mode_prints_nothing_else_even_with_issues(self):
        self.write_graph(graph_payload([node("a", status="bogus")], []))
        proc = self.run_cli("graph", "--format", "json")
        self.assert_exit(proc, 0)
        payload = self.assert_single_document(proc)
        self.assertIn("graph.node_status_unknown", [issue["code"] for issue in payload["issues"]])

    def test_corrupt_source_still_emits_valid_json_and_exit_3(self):
        self.write_graph("{ this is not json")
        proc = self.run_cli("graph", "--format", "json")
        self.assert_exit(proc, 3)
        payload = self.assert_single_document(proc)
        self.assertIn("graph.invalid_json", [issue["code"] for issue in payload["issues"]])

    def test_blueprint_json_is_a_single_valid_document(self):
        proc = self.run_cli("flow", "--format", "json", "--blueprint")
        self.assert_exit(proc, 0)
        payload = self.assert_single_document(proc)
        self.assertTrue(payload["phases"], "the blueprint must expose its phases")


class TextRendererTests(FlowViewTestCase, unittest.TestCase):
    def text_renderer(self, **kwargs):
        from flowview.text import TextRenderer

        return TextRenderer(**kwargs)

    def test_width_60_is_never_exceeded(self):
        """The whole command's stdout, including the trailing status/issue block cli._announce adds."""
        self.write_graph(graph_payload(
            [node(f"n{index}", status=ALL_STATUSES[index % len(ALL_STATUSES)]) for index in range(10)],
            [edge(f"e{index}", f"n{index}", f"n{index + 1}") for index in range(9)],
        ))
        proc = self.run_cli("graph", "--format", "text", "--width", "60")
        self.assert_exit(proc, 0)
        offenders = [(display_width(line), line) for line in proc.stdout.splitlines() if display_width(line) > 60]
        self.assertEqual(offenders, [], f"lines wider than 60 display columns: {offenders[:5]!r}")

    def test_rich_graph_under_width_60_is_never_exceeded(self):
        """The renderer alone must honour the width (the CLI status block is checked above)."""
        rendered = self.text_renderer(width=60).render_graph(rich_graph())
        offenders = [(display_width(line), line) for line in rendered.splitlines() if display_width(line) > 60]
        self.assertEqual(offenders, [], f"lines wider than 60 display columns: {offenders[:5]!r}")

    def test_every_status_appears_as_a_word(self):
        self.write_graph(graph_payload([node(f"n-{status}", status=status) for status in ALL_STATUSES], []))
        proc = self.run_cli("graph", "--format", "text", "--width", "100")
        self.assert_exit(proc, 0)
        for status in ALL_STATUSES:
            with self.subTest(status=status):
                self.assertRegex(proc.stdout, re.compile(re.escape(status), re.IGNORECASE))

    def test_no_color_output_contains_no_ansi(self):
        self.write_graph(graph_payload([node("a", "error"), node("b", "completed")], []))
        proc = self.run_cli("graph", "--no-color", "--format", "text", "--width", "100")
        self.assert_exit(proc, 0)
        self.assertNotIn("\x1b", proc.stdout)

    def test_forced_color_keeps_every_status_word(self):
        from flowview.style import Style

        graph = status_graph()
        plain = self.text_renderer(width=100, color=False, style=Style(enabled=False)).render_graph(graph)
        colored = self.text_renderer(width=100, color=True, style=Style(enabled=True)).render_graph(graph)
        self.assertNotIn("\x1b", plain)
        self.assertIn("\x1b", colored, "forced colour must actually emit ANSI codes")
        for status in ALL_STATUSES:
            with self.subTest(status=status):
                self.assertRegex(plain, re.compile(re.escape(status), re.IGNORECASE))
                self.assertRegex(colored, re.compile(re.escape(status), re.IGNORECASE))

    def test_cycle_is_reported_as_a_cycle_not_a_crash(self):
        rendered = self.text_renderer(width=100).render_graph(CYCLE_GRAPH)
        self.assertRegex(rendered, r"(?i)cycle")

    def test_empty_graph_mentions_emptiness(self):
        rendered = self.text_renderer(width=100).render_graph(FlowGraph(graph_id="empty", source="(fixture)"))
        self.assertRegex(rendered, r"(?i)empty|no nodes")

    def test_issue_table_renders_every_issue(self):
        from flowview.model import FlowIssue

        issues = (
            FlowIssue(severity="error", code="graph.invalid_json", message="Invalid JSON at line 1, column 1"),
            FlowIssue(severity="warning", code="graph.dangling_edge", message="Edge e1 points outside the graph"),
            FlowIssue(severity="info", code="graph.missing_file", message="No graph state file yet"),
        )
        rendered = self.text_renderer(width=100).render_issue_table(issues)
        for issue in issues:
            with self.subTest(code=issue.code):
                self.assertIn(issue.code, rendered)

    def test_wide_unicode_labels_respect_the_display_width(self):
        graph = FlowGraph(
            nodes=(
                FlowNode(id="wide", label="\u65e5\u672c\u8a9e\u306e\u30e9\u30d9\u30eb\u3067\u3059\u304c\u5206\u5272\u3055\u308c\u307e\u3059", status="ready"),
                FlowNode(id="plain", label="plain", status="completed"),
            )
        )
        rendered = self.text_renderer(width=40).render_graph(graph)
        offenders = [line for line in rendered.splitlines() if display_width(line) > 40]
        self.assertEqual(offenders, [], offenders[:3])


class StyleHelperTests(unittest.TestCase):
    def test_display_width_counts_east_asian_characters_as_two_columns(self):
        from flowview.style import display_width as style_width

        self.assertEqual(style_width("abc"), 3)
        self.assertEqual(style_width("\u65e5\u672c\u8a9e"), 6)
        self.assertEqual(style_width("\x1b[31mred\x1b[0m"), 3)

    def test_color_enabled_respects_the_override(self):
        from flowview.style import color_enabled

        self.assertFalse(color_enabled(None, override=False))
        self.assertTrue(color_enabled(None, override=True))

    def test_pad_and_truncate_are_width_aware(self):
        from flowview.style import display_width as style_width
        from flowview.style import pad, truncate

        self.assertEqual(style_width(pad("ab", 6)), 6)
        self.assertLessEqual(style_width(truncate("\u65e5\u672c\u8a9e\u306e\u30c6\u30ad\u30b9\u30c8", 6)), 6)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

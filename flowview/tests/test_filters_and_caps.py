"""`--focus`, `--status`, `--tool`, `--search` and `--layers`: filters must reduce the node set.

Assertions read the ``--format json`` payload, so they test the data the renderers receive, not
a substring of a table.
"""
from __future__ import annotations

import unittest

from flowview.tests.support import FlowViewTestCase, edge, graph_payload

NODES = (
    {"id": "ingest", "label": "Ingest dataset", "tool_id": "tool.ingest", "status": "completed"},
    {"id": "clean", "label": "Clean dataset", "tool_id": "tool.clean", "status": "running"},
    {"id": "analyze", "label": "Analyze spectra", "tool_id": "tool.analyze", "status": "error"},
    {"id": "review", "label": "Review results", "tool_id": "tool.review", "status": "waiting"},
    {"id": "export", "label": "Export report", "tool_id": "tool.export", "status": "ready"},
    {"id": "archive", "label": "Archive run", "tool_id": "tool.archive", "status": "unknown"},
)

EDGES = (
    edge("e1", "ingest", "clean"),
    edge("e2", "clean", "analyze"),
    edge("e3", "analyze", "review"),
    edge("e4", "review", "export"),
    edge("e5", "export", "archive"),
)


class FilterTests(FlowViewTestCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.write_graph(graph_payload(NODES, EDGES))

    def graph_json(self, *args):
        proc = self.run_cli("graph", "--format", "json", *args)
        self.assert_no_traceback(proc)
        payload = self.load_stdout_json(proc)
        return proc, payload

    def edge_pairs(self, payload):
        graph = payload["document"]["graph"]
        return sorted((item["source"], item["target"]) for item in graph["edges"])

    # -- --status ------------------------------------------------------------------------
    def test_status_filter_keeps_only_matching_nodes(self):
        proc, payload = self.graph_json("--status", "error")
        self.assert_exit(proc, 0)
        self.assertEqual(self.node_ids(payload), ["analyze"])

    def test_status_filter_is_repeatable(self):
        proc, payload = self.graph_json("--status", "completed", "--status", "error")
        self.assert_exit(proc, 0)
        self.assertEqual(sorted(self.node_ids(payload)), ["analyze", "ingest"])

    def test_status_filter_reports_how_many_nodes_were_hidden(self):
        proc, payload = self.graph_json("--status", "error")
        self.assert_issue_code(payload, "filter.applied")

    # -- --tool --------------------------------------------------------------------------
    def test_tool_filter_matches_the_registry_id(self):
        proc, payload = self.graph_json("--tool", "tool.clean")
        self.assert_exit(proc, 0)
        self.assertEqual(self.node_ids(payload), ["clean"])

    def test_tool_filter_is_repeatable(self):
        proc, payload = self.graph_json("--tool", "tool.clean", "--tool", "tool.export")
        self.assert_exit(proc, 0)
        self.assertEqual(sorted(self.node_ids(payload)), ["clean", "export"])

    # -- --search ------------------------------------------------------------------------
    def test_search_matches_labels(self):
        proc, payload = self.graph_json("--search", "spectra")
        self.assert_exit(proc, 0)
        self.assertEqual(self.node_ids(payload), ["analyze"])

    def test_search_is_case_insensitive_and_matches_several_nodes(self):
        proc, payload = self.graph_json("--search", "DATASET")
        self.assert_exit(proc, 0)
        self.assertEqual(sorted(self.node_ids(payload)), ["clean", "ingest"])

    def test_search_with_no_match_yields_an_empty_graph_not_an_error(self):
        proc, payload = self.graph_json("--search", "no-such-text-anywhere")
        self.assert_exit(proc, 0)
        self.assertEqual(self.node_ids(payload), [])

    # -- --focus -------------------------------------------------------------------------
    def test_focus_radius_1_keeps_the_node_and_its_neighbours(self):
        proc, payload = self.graph_json("--focus", "analyze", "--radius", "1")
        self.assert_exit(proc, 0)
        self.assertEqual(sorted(self.node_ids(payload)), ["analyze", "clean", "review"])

    def test_focus_radius_0_keeps_only_the_node(self):
        proc, payload = self.graph_json("--focus", "analyze", "--radius", "0")
        self.assert_exit(proc, 0)
        self.assertEqual(self.node_ids(payload), ["analyze"])

    def test_focus_radius_2_reaches_two_hops(self):
        proc, payload = self.graph_json("--focus", "analyze", "--radius", "2")
        self.assert_exit(proc, 0)
        self.assertEqual(sorted(self.node_ids(payload)), ["analyze", "clean", "export", "ingest", "review"])

    def test_focus_on_an_unknown_node_warns(self):
        proc, payload = self.graph_json("--focus", "ghost")
        self.assert_exit(proc, 0)
        self.assert_issue_code(payload, "focus.unknown_node")

    def test_focus_on_an_unknown_node_is_exit_3_under_strict(self):
        proc = self.run_cli("graph", "--strict", "--format", "json", "--focus", "ghost")
        self.assert_exit(proc, 3)

    # -- edge consistency ----------------------------------------------------------------
    def test_filters_drop_edges_whose_endpoints_are_filtered_out(self):
        proc, payload = self.graph_json("--status", "error")
        self.assert_exit(proc, 0)
        self.assertEqual(self.edge_pairs(payload), [])

    def test_focus_keeps_only_edges_inside_the_neighbourhood(self):
        proc, payload = self.graph_json("--focus", "analyze", "--radius", "1")
        self.assertEqual(self.edge_pairs(payload), [("analyze", "review"), ("clean", "analyze")])

    def test_combined_filters_intersect(self):
        proc, payload = self.graph_json("--tool", "tool.clean", "--search", "dataset")
        self.assert_exit(proc, 0)
        self.assertEqual(self.node_ids(payload), ["clean"])

    # -- --layers ------------------------------------------------------------------------
    def test_layers_flag_groups_text_output_without_crashing(self):
        proc = self.run_cli("graph", "--format", "text", "--layers", "--width", "100")
        self.assert_exit(proc, 0)
        self.assert_no_traceback(proc)
        self.assertRegex(proc.stdout, r"(?i)layer")

    def test_text_filtered_output_still_respects_the_width(self):
        from flowview.tests.support import display_width

        proc = self.run_cli("graph", "--format", "text", "--status", "error", "--width", "60")
        self.assert_exit(proc, 0)
        offenders = [line for line in proc.stdout.splitlines() if display_width(line) > 60]
        self.assertEqual(offenders, [], offenders[:3])

    # -- non-mutation --------------------------------------------------------------------
    def test_filtering_does_not_touch_the_source_file(self):
        path = self.data_dir / "graph_state.json"
        before = path.read_bytes()
        self.graph_json("--status", "error")
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

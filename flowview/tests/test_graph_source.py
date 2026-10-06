"""Malformed ``graph_state.json`` handling: every case asserts an issue code *and* an exit code.

The exit codes come from the frozen table in ``flowview/CONTRACT.md``:

* ``0`` success (warnings and info are still success without ``--strict``),
* ``2`` usage error,
* ``3`` input/backend problem (any ``error`` issue, or any warning under ``--strict``).
"""
from __future__ import annotations

import json
import unittest

from flowview.loader import MAX_NODES
from flowview.tests.support import FlowViewTestCase, chain_payload, edge, graph_payload, node


class GraphSourceTests(FlowViewTestCase, unittest.TestCase):
    # -- helpers -------------------------------------------------------------------------
    def issue(self, payload, code):
        for item in payload.get("issues", []):
            if item.get("code") == code:
                return item
        return None

    def graph(self, payload):
        return payload["document"]["graph"]

    # -- syntax and shape ----------------------------------------------------------------
    def test_invalid_json_reports_graph_invalid_json_and_exit_3(self):
        self.write_graph('{"graph_id": "x", "nodes": [')
        proc, payload = self.graph_json()
        self.assert_exit(proc, 3)
        self.assert_issue_code(payload, "graph.invalid_json")
        self.assert_no_issue_code(payload, "graph.not_an_object")
        self.assertEqual(self.issue(payload, "graph.invalid_json")["severity"], "error")

    def test_top_level_array_is_not_an_object_and_exits_3(self):
        proc, payload = self.graph_json(graph=[])
        self.assert_exit(proc, 3)
        self.assert_issue_code(payload, "graph.not_an_object")
        self.assertEqual(self.issue(payload, "graph.not_an_object")["severity"], "error")

    def test_top_level_string_is_not_an_object_and_exits_3(self):
        proc, payload = self.graph_json(graph=json.dumps("not-a-graph"))
        self.assert_exit(proc, 3)
        self.assert_issue_code(payload, "graph.not_an_object")

    def test_nodes_of_wrong_type_is_an_error_and_exits_3(self):
        proc, payload = self.graph_json(graph={"nodes": "x"})
        self.assert_exit(proc, 3)
        self.assert_issue_code(payload, "graph.nodes_not_a_list")
        self.assertEqual(self.issue(payload, "graph.nodes_not_a_list")["severity"], "error")

    def test_edges_of_wrong_type_is_an_error_and_exits_3(self):
        proc, payload = self.graph_json(graph={"nodes": [], "edges": 7})
        self.assert_exit(proc, 3)
        self.assert_issue_code(payload, "graph.edges_not_a_list")

    def test_node_that_is_not_an_object_is_skipped_with_an_error(self):
        proc, payload = self.graph_json(graph={"nodes": [42, node("good")], "edges": []})
        self.assert_exit(proc, 3)
        self.assert_issue_code(payload, "graph.node_not_an_object")
        self.assertEqual(self.node_ids(payload), ["good"])

    def test_missing_nodes_and_edges_keys_are_warnings_and_exit_0(self):
        proc, payload = self.graph_json(graph={"graph_id": "x", "version": 1})
        self.assert_exit(proc, 0)
        self.assert_issue_code(payload, "graph.nodes_missing")
        self.assert_issue_code(payload, "graph.edges_missing")
        self.assertEqual(self.issue(payload, "graph.nodes_missing")["severity"], "warning")

    # -- node-level findings -------------------------------------------------------------
    def test_node_without_id_gets_a_synthetic_id_and_a_warning(self):
        proc, payload = self.graph_json(graph={"nodes": [{"label": "anonymous", "status": "ready"}], "edges": []})
        self.assert_exit(proc, 0)
        self.assert_issue_code(payload, "graph.node_missing_id")
        self.assertEqual(self.node_ids(payload), ["node-0"])

    def test_unknown_status_becomes_unknown_with_a_warning_never_completed(self):
        proc, payload = self.graph_json(graph={"nodes": [node("a", status="exploded")], "edges": []})
        self.assert_exit(proc, 0)
        self.assert_issue_code(payload, "graph.node_status_unknown")
        statuses = self.statuses(payload)
        self.assertEqual(statuses["a"], "unknown")
        self.assertNotEqual(statuses["a"], "completed")
        self.assertEqual(self.issue(payload, "graph.node_status_unknown")["severity"], "warning")

    def test_unknown_status_is_exit_3_under_strict(self):
        self.write_graph(graph_payload([node("a", status="exploded")], []))
        proc = self.run_cli("graph", "--format", "json", "--strict")
        self.assert_exit(proc, 3)
        payload = self.load_stdout_json(proc)
        self.assert_issue_code(payload, "graph.node_status_unknown")

    def test_missing_status_becomes_unknown_with_a_warning(self):
        proc, payload = self.graph_json(graph={"nodes": [{"id": "a", "label": "A"}], "edges": []})
        self.assert_exit(proc, 0)
        self.assert_issue_code(payload, "graph.node_status_missing")
        self.assertEqual(self.statuses(payload)["a"], "unknown")

    def test_error_node_without_message_carries_a_warning(self):
        payload_in = {"nodes": [{"id": "a", "label": "A", "status": "error"}], "edges": []}
        proc, payload = self.graph_json(graph=payload_in)
        self.assert_exit(proc, 0)
        self.assert_issue_code(payload, "graph.node_error_without_message")
        graph_node = self.graph(payload)["nodes"][0]
        self.assertTrue(graph_node["error"], "an error node must still show some error text")

    def test_type_and_tool_id_mismatch_is_reported(self):
        payload_in = {"nodes": [{"id": "a", "label": "A", "type": "tool.x", "tool_id": "tool.y", "status": "ready"}], "edges": []}
        proc, payload = self.graph_json(graph=payload_in)
        self.assert_exit(proc, 0)
        self.assert_issue_code(payload, "graph.node_identity_mismatch")

    def test_bad_version_is_a_warning_and_exits_0(self):
        proc, payload = self.graph_json(graph={"graph_id": "x", "version": "three", "nodes": [], "edges": []})
        self.assert_exit(proc, 0)
        self.assert_issue_code(payload, "graph.bad_version")

    # -- edge-level findings -------------------------------------------------------------
    def test_dangling_edge_is_a_warning_and_exits_0(self):
        payload_in = graph_payload([node("a")], [edge("e1", "a", "missing")])
        proc, payload = self.graph_json(graph=payload_in)
        self.assert_exit(proc, 0)
        self.assert_issue_code(payload, "graph.dangling_edge")
        self.assertEqual(self.issue(payload, "graph.dangling_edge")["severity"], "warning")

    def test_edge_without_endpoint_is_an_error_and_exits_3(self):
        payload_in = graph_payload([node("a")], [{"id": "e1", "target": "a"}])
        proc, payload = self.graph_json(graph=payload_in)
        self.assert_exit(proc, 3)
        self.assert_issue_code(payload, "graph.edge_missing_endpoint")

    def test_edge_that_is_not_an_object_is_an_error_and_exits_3(self):
        payload_in = graph_payload([node("a")], ["nope"])
        proc, payload = self.graph_json(graph=payload_in)
        self.assert_exit(proc, 3)
        self.assert_issue_code(payload, "graph.edge_not_an_object")

    def test_duplicate_node_id_is_an_error_and_exits_3(self):
        payload_in = graph_payload([node("dup"), node("dup")], [])
        proc, payload = self.graph_json(graph=payload_in)
        self.assert_exit(proc, 3)
        self.assert_issue_code(payload, "graph.duplicate_node")
        self.assertEqual(self.issue(payload, "graph.duplicate_node")["severity"], "error")

    def test_duplicate_edge_id_is_a_warning_and_exits_0(self):
        payload_in = graph_payload(
            [node("a"), node("b"), node("c")],
            [edge("same", "a", "b"), edge("same", "b", "c")],
        )
        proc, payload = self.graph_json(graph=payload_in)
        self.assert_exit(proc, 0)
        self.assert_issue_code(payload, "graph.duplicate_edge")

    def test_two_edges_into_one_input_port_is_a_warning(self):
        payload_in = graph_payload(
            [node("a"), node("b"), node("c")],
            [
                edge("e1", "a", "c", target_port="in"),
                edge("e2", "b", "c", target_port="in"),
            ],
        )
        proc, payload = self.graph_json(graph=payload_in)
        self.assert_exit(proc, 0)
        self.assert_issue_code(payload, "graph.multiple_edges_into_port")

    # -- cycles --------------------------------------------------------------------------
    def test_self_loop_is_reported_as_a_cycle_not_a_crash(self):
        self.write_graph(graph_payload([node("a")], [edge("e", "a", "a")]))
        text = self.run_cli("graph", "--format", "text", "--width", "80")
        self.assert_no_traceback(text)
        self.assertEqual(text.returncode, 0, text)
        self.assertIn("cycl", text.stdout.lower())
        proc, payload = self.graph_json()
        self.assert_exit(proc, 0)
        cycles = payload["graph_stats"]["cycles"]
        self.assertTrue(cycles, "a self-loop must be reported as a cycle")

    def test_two_node_cycle_is_reported_as_a_cycle_not_a_crash(self):
        payload_in = graph_payload(
            [node("a"), node("b")],
            [edge("e1", "a", "b"), edge("e2", "b", "a")],
        )
        self.write_graph(payload_in)
        text = self.run_cli("graph", "--format", "text", "--width", "80")
        self.assert_no_traceback(text)
        self.assertEqual(text.returncode, 0, text)
        self.assertIn("cycl", text.stdout.lower())
        proc, payload = self.graph_json()
        self.assert_exit(proc, 0)
        cycles = [tuple(cycle) for cycle in payload["graph_stats"]["cycles"]]
        self.assertTrue(any(set(cycle) == {"a", "b"} for cycle in cycles), cycles)

    # -- caps ----------------------------------------------------------------------------
    def test_two_thousand_node_graph_truncates_and_records_the_cap(self):
        proc, payload = self.graph_json(graph=chain_payload(2000))
        self.assert_exit(proc, 0)
        self.assertEqual(len(self.node_ids(payload)), MAX_NODES)
        truncated = payload["document"]["truncated"]
        self.assertIn(f"nodes>{MAX_NODES}", truncated)

    def test_full_flag_keeps_every_node_of_a_large_graph(self):
        self.write_graph(chain_payload(600))
        proc = self.run_cli("graph", "--format", "json")
        self.assert_exit(proc, 0)
        payload = self.load_stdout_json(proc)
        self.assertEqual(len(self.node_ids(payload)), 500)
        self.assertIn(f"nodes>{MAX_NODES}", payload["document"]["truncated"])

        proc_full = self.run_cli("graph", "--full", "--format", "json")
        self.assert_exit(proc_full, 0)
        payload_full = self.load_stdout_json(proc_full)
        self.assertEqual(len(self.node_ids(payload_full)), 600)
        self.assertEqual(payload_full["document"]["truncated"], [])

    # -- missing / unusable source -------------------------------------------------------
    def test_missing_graph_file_is_info_and_exit_0(self):
        """A workspace that never ran is healthy, not broken."""
        proc, payload = self.graph_json()
        self.assert_exit(proc, 0)
        self.assert_issue_code(payload, "graph.missing_file")
        info = self.issue(payload, "graph.missing_file")
        self.assertEqual(info["severity"], "info")
        self.assertEqual(self.node_ids(payload), [])

    def test_graph_path_that_is_a_directory_is_an_error_and_exit_3(self):
        (self.data_dir / "graph_state.json").mkdir(parents=True, exist_ok=True)
        proc, payload = self.graph_json()
        self.assert_exit(proc, 3)
        self.assert_issue_code(payload, "graph.is_directory")

    def test_empty_graph_is_info_and_still_prints_json(self):
        proc, payload = self.graph_json(graph={"graph_id": "empty", "version": 0, "nodes": [], "edges": []})
        self.assert_exit(proc, 0)
        self.assert_issue_code(payload, "graph.empty")
        self.assertEqual(self.issue(payload, "graph.empty")["severity"], "info")
        self.assertEqual(self.node_ids(payload), [])

    def test_caps_are_disclosed_and_never_silent(self):
        proc, payload = self.graph_json(graph=chain_payload(2000))
        self.assert_exit(proc, 0)
        self.assertTrue(payload["document"]["truncated"], "a cap must be recorded in `truncated`")
        rendered = self.run_cli("graph", "--format", "text", "--width", "100")
        self.assert_no_traceback(rendered)
        self.assertIn("truncat", rendered.stdout.lower())

    def test_graph_file_option_reads_an_explicit_path(self):
        explicit = self.tmp / "elsewhere" / "exported_graph.json"
        explicit.parent.mkdir(parents=True, exist_ok=True)
        explicit.write_text(json.dumps(graph_payload([node("only")], [])), encoding="utf-8")
        proc = self.run_cli("graph", "--format", "json", "--graph-file", str(explicit))
        self.assert_exit(proc, 0)
        payload = self.load_stdout_json(proc)
        self.assertEqual(self.node_ids(payload), ["only"])
        self.assertNotIn("graph.missing_file", [item["code"] for item in payload["issues"]])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

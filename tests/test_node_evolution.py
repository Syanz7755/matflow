import json
import tempfile
import unittest
from pathlib import Path

from backend.contracts import Edge, GraphState, Node
from backend.preview import build_preview
from backend.tool_registry import ToolRegistry
from backend.workspace_runtime import WorkspaceRuntime


def safe_revision(messages, tools, **kwargs):
    return {"content": json.dumps({
        "label": "Revised import",
        "description": "Imports a selected table with a clearer label.",
        "params": {"file_name": "measurement.csv", "upload_id": ""},
        "preview_spec": {"version": "1.0", "outputs": {"raw": {"renderer": "table_head", "max_rows": 5}}},
        "generated_code": None,
    })}


class NodeEvolutionTests(unittest.TestCase):
    def test_proposal_is_isolated_and_apply_reconnects_exact_ports_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = WorkspaceRuntime(Path(directory), model_complete=safe_revision)
            runtime.write_state(GraphState(nodes=[
                Node(id="input", type="raw_file_import"),
                Node(id="map", type="normalize_columns"),
            ], edges=[Edge(id="input-map", source="input", source_port="raw", target="map", target_port="raw")]))

            proposal = runtime.create_revision_proposal("input", "Give this node a clearer purpose", "local_litellm", "qwen")
            before = runtime.read_state()
            self.assertEqual(before.version, 0)
            self.assertEqual(before.nodes[0].type, "raw_file_import")
            self.assertEqual(proposal["edge_plan"][0]["status"], "exact")

            applied = runtime.apply_revision_proposal(proposal["proposal_id"], {})
            self.assertEqual(applied.version, 1)
            self.assertNotEqual(applied.nodes[0].type, "raw_file_import")
            self.assertEqual(applied.edges[0].source_port, "raw")
            self.assertEqual(runtime.get_revision_proposal(proposal["proposal_id"])["status"], "applied")

    def test_port_changing_proposal_cannot_activate_without_an_installed_executor(self):
        def port_revision(messages, tools, **kwargs):
            return {"content": json.dumps({"inputs": {}, "outputs": {"table": "TypedTable"}, "generated_code": "def run(): pass"})}

        with tempfile.TemporaryDirectory() as directory:
            runtime = WorkspaceRuntime(Path(directory), model_complete=port_revision)
            runtime.write_state(GraphState(nodes=[Node(id="input", type="raw_file_import")]))
            proposal = runtime.create_revision_proposal("input", "Return a typed table", "local_litellm", "qwen")
            self.assertTrue(proposal["requires_code_review"])
            with self.assertRaisesRegex(ValueError, "reviewed executor"):
                runtime.apply_revision_proposal(proposal["proposal_id"], {})

    def test_review_after_run_builds_preview_and_blocks_until_continue(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = WorkspaceRuntime(Path(directory))
            upload = runtime.import_dataset("sample.csv", b"frequency_hz,z_real,z_imag\n100,5,-1\n", "text/csv")
            runtime.write_state(GraphState(nodes=[Node(
                id="input", type="raw_file_import", params={"file_name": "sample.csv", "upload_id": upload["id"]},
                review_policy={"after_run": True, "prompt": "Check the imported rows."},
            )]))

            outcome = runtime.execute_workflow(restart=True)
            node = outcome["state"]["nodes"][0]
            self.assertEqual(node["status"], "waiting")
            self.assertEqual(node["review_state"]["status"], "pending")
            self.assertEqual(node["preview"]["kind"], "table")
            continued = runtime.submit_node_review("input", "continue")
            self.assertEqual(continued["state"]["nodes"][0]["status"], "completed")

    def test_preview_bounds_untrusted_json(self):
        spec = ToolRegistry().get("eis_basic_qc")
        preview = build_preview({"kind": "EISQCReport", "values": list(range(100))}, spec)
        self.assertEqual(preview["kind"], "json_tree")
        self.assertLess(len(preview["data"]["values"]), 100)


if __name__ == "__main__":
    unittest.main()

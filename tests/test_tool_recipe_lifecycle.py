import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main
from backend.analysis_recipes import reference_recipe, reference_tool_definition
from backend.contracts import Edge, GraphState, Node
from backend.workspace_runtime import WorkspaceRuntime
from examples.generate_analysis_fixtures import generate_fixture_set


class ToolRecipeLifecycleTests(unittest.TestCase):
    def test_chat_creates_a_draft_recipe_proposal_without_activating_it(self):
        recipe = reference_recipe("xrd").model_copy(update={
            "recipe_id": "generated_xrd_candidate", "status": "draft",
        }).model_dump()
        reply = {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "proposal-call",
                "type": "function",
                "function": {"name": "propose_tool_recipe", "arguments": json.dumps({
                    "label": "Generated XRD analysis",
                    "description": "Find peaks and match a declared reference set.",
                    "recipe": recipe,
                })},
            }],
        }
        final = {"role": "assistant", "content": "A draft is ready for review."}

        with tempfile.TemporaryDirectory() as directory:
            runtime = WorkspaceRuntime(Path(directory))
            with patch.object(main, "workspace", runtime), patch.object(
                main, "model_completion", side_effect=[reply, final]
            ):
                response = TestClient(main.app).post("/api/chat", json={
                    "message": "Build an XRD analysis tool.",
                    "attachments": [{"upload_id": "contract-fixture", "name": "pattern.csv"}],
                })

            self.assertEqual(response.status_code, 200)
            proposal = response.json()["tool_proposals"][0]
            self.assertEqual(proposal["status"], "draft")
            self.assertTrue(proposal["requires_human_review"])
            self.assertNotIn("generated_xrd_candidate", runtime.registry().active())

    def test_published_reference_recipe_executes_through_the_runtime_interface(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = generate_fixture_set(root / "fixtures")
            fixture = next(item for item in manifest["fixtures"] if item["fixture_id"] == "xrd_20260930")
            runtime = WorkspaceRuntime(root)
            settings = runtime.read_settings()
            settings["custom_nodes"] = {"reference_xrd_phase_identification": reference_tool_definition("xrd")}
            runtime.write_settings(settings)
            content = (root / "fixtures" / fixture["path"]).read_bytes()
            upload = runtime.import_dataset("xrd.csv", content, "text/csv")
            runtime.write_state(GraphState(nodes=[
                Node(id="input", type="raw_file_import", params={"file_name": "xrd.csv", "upload_id": upload["id"]}),
                Node(id="analysis", type="reference_xrd_phase_identification"),
            ], edges=[Edge(id="input-analysis", source="input", source_port="raw", target="analysis", target_port="data")]))

            outcome = runtime.execute_workflow(restart=True)

            analysis = next(node for node in outcome["state"]["nodes"] if node["id"] == "analysis")
            self.assertEqual(analysis["status"], "completed")
            self.assertEqual(analysis["output"]["data"]["dominant_phase"], "anatase_tio2")


if __name__ == "__main__":
    unittest.main()

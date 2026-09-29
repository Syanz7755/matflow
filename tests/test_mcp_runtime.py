import asyncio
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import app
from backend.mcp_server import create_mcp_server
from backend.workspace_runtime import WorkspaceRuntime


class WorkspaceRuntimeTests(unittest.TestCase):
    def test_import_and_inspect_share_the_transport_neutral_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = WorkspaceRuntime(Path(directory))
            record = runtime.import_dataset("sample.csv", b"x,y\n1,2\n3,4\n", "text/csv")
            inspected = runtime.inspect_dataset(record["id"])
            self.assertEqual(inspected["kind"], "table")
            self.assertEqual(inspected["rows"], 2)
            self.assertEqual([item["name"] for item in inspected["columns"]], ["x", "y"])
            self.assertEqual(runtime.list_datasets()[0]["id"], record["id"])

    def test_upload_id_cannot_escape_upload_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = WorkspaceRuntime(Path(directory))
            with self.assertRaisesRegex(ValueError, "Unknown upload"):
                runtime.inspect_dataset("../settings.json")


class McpAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_catalog_has_stable_tools_and_mutation_annotations(self):
        with tempfile.TemporaryDirectory() as directory:
            server = create_mcp_server(WorkspaceRuntime(Path(directory)))
            tools = {tool.name: tool for tool in await server.list_tools()}
            self.assertEqual(
                set(tools),
                {
                    "get_workspace_state", "import_dataset", "inspect_dataset",
                    "route_research_task", "validate_graph_patch", "apply_graph_patch",
                    "execute_workflow", "submit_human_decision", "submit_node_review", "get_task_summary",
                    "create_data_type", "update_data_type_inheritance",
                },
            )
            self.assertTrue(tools["get_workspace_state"].annotations.readOnlyHint)
            self.assertTrue(tools["apply_graph_patch"].annotations.destructiveHint)
            self.assertEqual(tools["import_dataset"].meta["openai/fileParams"], ["file"])
            file_schema = tools["import_dataset"].inputSchema["$defs"]["OpenAIFile"]
            self.assertEqual(set(file_schema["properties"]), {"download_url", "file_id", "mime_type", "file_name"})
            self.assertEqual(set(file_schema["required"]), {"download_url", "file_id"})


class LegacyChatTests(unittest.TestCase):
    def test_built_in_chat_is_retired_by_default(self):
        response = TestClient(app).post("/api/chat", json={"message": "hello"})
        self.assertEqual(response.status_code, 410)
        self.assertIn("/mcp", response.json()["detail"])

    def test_http_dataset_inventory_is_available_to_the_control_plane(self):
        response = TestClient(app).get("/api/uploads")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json()["files"], list)

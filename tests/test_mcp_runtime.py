import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import app
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


class LegacyChatTests(unittest.TestCase):
    def test_built_in_chat_is_retired_by_default(self):
        response = TestClient(app).post("/api/chat", json={"message": "hello"})
        self.assertEqual(response.status_code, 410)
        self.assertIn("matflow-frontend MCP bridge", response.json()["detail"])

    def test_backend_no_longer_mounts_mcp(self):
        response = TestClient(app).post("/mcp", json={})
        self.assertEqual(response.status_code, 404)

    def test_http_dataset_inventory_is_available_to_the_control_plane(self):
        response = TestClient(app).get("/api/uploads")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json()["files"], list)

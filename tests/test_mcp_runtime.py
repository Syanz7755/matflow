import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main
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


class ChatContractTests(unittest.TestCase):
    def test_chat_is_the_stable_user_message_interface(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = WorkspaceRuntime(Path(directory))
            with patch.object(main, "workspace", runtime), patch("backend.main.model_completion", return_value={"role": "assistant", "content": "Ready."}):
                response = TestClient(app).post("/api/chat", json={
                    "message": "Create an EIS quality-control workflow.",
                    "task_id": "chat-task-1",
                    "conversation_id": "conversation-1",
                    "attachments": [{"upload_id": "contract-fixture", "name": "sample.csv"}],
                })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["task_id"], "chat-task-1")
        self.assertEqual(payload["conversation_id"], "conversation-1")
        self.assertEqual(payload["message"], "Ready.")
        self.assertEqual(payload["status"], "completed")
        self.assertIn("state", payload)
        self.assertIn("trace", payload)
        self.assertIn("tool_proposals", payload)

    def test_capabilities_publish_the_chat_interface(self):
        payload = TestClient(app).get("/api/capabilities").json()
        self.assertEqual(payload["server_version"], "1.1.0")
        self.assertEqual(payload["operations"]["chat"], "POST /api/chat")

    def test_chat_round_limit_becomes_human_confirmation_instead_of_transport_failure(self):
        repeated = {"role": "assistant", "content": "", "tool_calls": [{
            "id": "read-again", "type": "function",
            "function": {"name": "get_graph", "arguments": "{}"},
        }]}
        with tempfile.TemporaryDirectory() as directory:
            runtime = WorkspaceRuntime(Path(directory))
            settings = runtime.read_settings()
            settings["agent"]["max_tool_rounds"] = 2
            runtime.write_settings(settings)
            with patch.object(main, "workspace", runtime), patch.object(main, "model_completion", return_value=repeated):
                response = TestClient(app).post("/api/chat", json={
                    "message": "Plan an unsupported refinement.",
                    "attachments": [{"upload_id": "fixture", "name": "pattern.xy"}],
                })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "waiting_for_confirmation")
        self.assertEqual(response.json()["state"]["nodes"], [])

    def test_read_only_reply_for_an_unmatched_capability_waits_for_confirmation(self):
        reply = {"role": "assistant", "content": "Please provide the missing structural model."}
        with tempfile.TemporaryDirectory() as directory:
            runtime = WorkspaceRuntime(Path(directory))
            with patch.object(main, "workspace", runtime), patch.object(main, "model_completion", return_value=reply):
                response = TestClient(app).post("/api/chat", json={
                    "message": "Run an unsupported refinement.",
                    "attachments": [{"upload_id": "fixture", "name": "pattern.xy"}],
                })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "waiting_for_confirmation")
        self.assertEqual(response.json()["tool_proposals"], [])

    def test_backend_no_longer_mounts_mcp(self):
        response = TestClient(app).post("/mcp", json={})
        self.assertEqual(response.status_code, 404)

    def test_http_dataset_inventory_is_available_to_the_control_plane(self):
        response = TestClient(app).get("/api/uploads")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json()["files"], list)

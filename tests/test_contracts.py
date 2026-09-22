import unittest

from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.contracts import GraphPatch, Node, Operation, ToolSpec
from backend.main import app
from backend.tool_registry import ToolRegistry


class ToolSpecContractTests(unittest.TestCase):
    def test_active_tool_requires_executor_reference(self):
        with self.assertRaises(ValidationError):
            ToolSpec(tool_id="demo_tool", label="Demo", category="Test", description="Test tool", outputs={"result": "Artifact"})

    def test_generated_tool_requires_review_before_activation(self):
        with self.assertRaises(ValidationError):
            ToolSpec(tool_id="demo_tool", label="Demo", category="Test", description="Test tool", outputs={"result": "Artifact"}, executor_ref="builtin:demo", provenance={"kind": "generated"})

    def test_registry_exposes_versioned_active_tools(self):
        spec = ToolRegistry().get("eis_basic_qc")
        self.assertEqual(spec.version, "1.0.0")
        self.assertEqual(spec.executor_ref, "builtin:eis_basic_qc")
        self.assertEqual(spec.status, "active")


class GraphContractTests(unittest.TestCase):
    def test_legacy_node_gets_explicit_tool_identity(self):
        node = Node(id="qc-1", type="eis_basic_qc")
        self.assertEqual(node.tool_id, "eis_basic_qc")
        self.assertEqual(node.tool_version, "1.0.0")

    def test_patch_requires_operation_payload(self):
        with self.assertRaises(ValidationError):
            GraphPatch(base_version=0, operations=[Operation(op="add_node")])


class RuntimeIntegrationTests(unittest.TestCase):
    def test_state_exposes_versioned_registry_and_trace_id(self):
        response = TestClient(app).get("/api/state")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["x-trace-id"])
        self.assertEqual(response.json()["state"]["graph_id"], "local-default")
        self.assertEqual(response.json()["registry"]["eis_basic_qc"]["version"], "1.0.0")
        self.assertFalse(response.json()["features"]["tool_manager_build"])

    def test_route_selects_compatible_eis_tool_with_auditable_decision(self):
        response = TestClient(app).post("/api/route", json={"task": {"task_id": "route-eis", "user_message": "Run basic EIS quality checks", "graph_version": 0, "available_input_types": ["TypedTable"]}})
        self.assertEqual(response.status_code, 200)
        decision = response.json()
        self.assertEqual(decision["selected"][0]["tool_id"], "eis_basic_qc")
        self.assertFalse(decision["requires_human_confirmation"])

    def test_route_returns_confirmation_when_no_tool_matches(self):
        response = TestClient(app).post("/api/route", json={"task": {"task_id": "route-unknown", "user_message": "Perform quantum diffraction tomography", "graph_version": 0, "available_input_types": ["TypedTable"]}})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["selected"], [])
        self.assertTrue(response.json()["requires_human_confirmation"])

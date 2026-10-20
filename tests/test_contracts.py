import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.contracts import Edge, GraphPatch, GraphState, Node, Operation, ToolSpec
from backend import main
from backend.jev_routing import JevConfig, JevDecisionRouter
from backend.main import app
from backend.tool_registry import ToolRegistry
from backend.validator import GraphValidator
from tests.reference_composition import registry as reference_registry
from tests.reference_composition import workspace as reference_workspace


class ToolSpecContractTests(unittest.TestCase):
    def test_active_tool_requires_executor_reference(self):
        with self.assertRaises(ValidationError):
            ToolSpec(tool_id="demo_tool", label="Demo", category="Test", description="Test tool", outputs={"result": "Artifact"})

    def test_generated_tool_requires_review_before_activation(self):
        with self.assertRaises(ValidationError):
            ToolSpec(tool_id="demo_tool", label="Demo", category="Test", description="Test tool", outputs={"result": "Artifact"}, executor_ref="builtin:demo", provenance={"kind": "generated"})

    def test_registry_exposes_versioned_active_tools(self):
        spec = reference_registry().get("eis_basic_qc")
        self.assertEqual(spec.version, "1.0.0")
        self.assertEqual(spec.executor_ref, "builtin:eis_basic_qc")
        self.assertEqual(spec.status, "active")
        self.assertNotIn("human_decision", reference_registry().active())


class GraphContractTests(unittest.TestCase):
    def test_legacy_node_gets_explicit_tool_identity(self):
        node = Node(id="qc-1", type="eis_basic_qc")
        self.assertEqual(node.tool_id, "eis_basic_qc")
        self.assertEqual(node.tool_version, "1.0.0")

    def test_patch_requires_operation_payload(self):
        with self.assertRaises(ValidationError):
            GraphPatch(base_version=0, operations=[Operation(op="add_node")])

    def test_validator_rejects_a_directed_cycle(self):
        registry = ToolRegistry(custom_nodes={
            "loop_node": {
                "label": "Loop Node",
                "category": "Test",
                "description": "A test-only node with matching input and output types.",
                "inputs": {"value": "Artifact"},
                "outputs": {"value": "Artifact"},
                "params": {},
            },
        })
        state = GraphState(nodes=[
            Node(id="a", type="loop_node"),
            Node(id="b", type="loop_node"),
        ], edges=[
            Edge(id="forward", source="a", source_port="value", target="b", target_port="value"),
        ])
        patch = GraphPatch(base_version=0, operations=[Operation(
            op="connect",
            edge=Edge(id="back", source="b", source_port="value", target="a", target_port="value"),
        )])

        with self.assertRaisesRegex(ValueError, "Graph must be acyclic"):
            GraphValidator().validate(state, patch, registry)

    def test_validator_rejects_two_edges_for_one_input_port(self):
        state = GraphState(nodes=[
            Node(id="import-a", type="raw_file_import"),
            Node(id="import-b", type="raw_file_import"),
            Node(id="normalize", type="normalize_columns"),
        ], edges=[
            Edge(id="first", source="import-a", source_port="raw", target="normalize", target_port="raw"),
        ])
        patch = GraphPatch(base_version=0, operations=[Operation(
            op="connect",
            edge=Edge(id="second", source="import-b", source_port="raw", target="normalize", target_port="raw"),
        )])

        with self.assertRaisesRegex(ValueError, "Input port already connected"):
            GraphValidator().validate(state, patch, ToolRegistry())

    def test_validator_accepts_safe_node_label_and_position_changes(self):
        state = GraphState(nodes=[Node(id="input", type="raw_file_import")])
        patch = GraphPatch(base_version=0, operations=[Operation(
            op="update_node",
            node_id="input",
            changes={"label": "Experiment input", "position": {"x": 220, "y": 90}},
        )])

        GraphValidator().validate(state, patch, ToolRegistry())

    def test_validator_rejects_runtime_state_changes_through_graph_patch(self):
        state = GraphState(nodes=[Node(id="input", type="raw_file_import")])
        patch = GraphPatch(base_version=0, operations=[Operation(
            op="update_node",
            node_id="input",
            changes={"status": "completed"},
        )])

        with self.assertRaisesRegex(ValueError, "Unsupported node change"):
            GraphValidator().validate(state, patch, ToolRegistry())


class RuntimeIntegrationTests(unittest.TestCase):
    def test_state_exposes_versioned_registry_and_trace_id(self):
        response = TestClient(app).get("/api/state")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["x-trace-id"])
        self.assertEqual(response.json()["state"]["graph_id"], "local-default")
        self.assertEqual(response.json()["registry"]["eis_basic_qc"]["version"], "1.0.0")
        self.assertFalse(response.json()["features"]["tool_manager_build"])

    def test_model_provider_endpoint_never_returns_secret_values(self):
        response = TestClient(app).get("/api/model-providers")
        self.assertEqual(response.status_code, 200)
        encoded = response.text
        self.assertIn("api_key_env", encoded)
        self.assertNotIn("sk-matflow-local-gateway", encoded)

    def test_capabilities_exposes_future_client_operations_without_frontend(self):
        response = TestClient(app).get("/api/capabilities")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["api_contract"], {"name": "matflow-http", "version": "1.0"})
        self.assertEqual(payload["server_version"], "1.1.0")
        self.assertEqual(payload["registry"]["eis_basic_qc"]["version"], "1.0.0")
        self.assertEqual(payload["operations"]["route"], "POST /api/route")
        self.assertEqual(payload["operations"]["chat"], "POST /api/chat")
        self.assertEqual(payload["operations"]["execute_node"], "POST /api/execute")
        self.assertEqual(payload["operations"]["execute_workflow"], "POST /api/workflow/execute")
        self.assertEqual(payload["operations"]["validate_graph_patch"], "POST /api/patch/validate")

    def test_stale_patch_returns_stable_conflict(self):
        response = TestClient(app).post("/api/patch/validate", json={"base_version": 999, "operations": [{"op": "add_node", "node": {"id": "stale-test", "type": "raw_file_import"}}]})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "graph_version_conflict")

    def _route(self, task, llm_answer):
        """POST /api/route on a private workspace with a scripted LLM and Jev disabled."""
        reply = {"role": "assistant", "content": json.dumps(llm_answer)}
        with tempfile.TemporaryDirectory() as directory:
            runtime = reference_workspace(Path(directory), model_complete=main._runtime_model_adapter)
            with patch.object(main, "workspace", runtime),                     patch.object(main, "model_completion", return_value=reply) as model,                     patch("backend.workspace_runtime.JevDecisionRouter", lambda: JevDecisionRouter(JevConfig.model_validate({"version": 1, "router": {"enabled": False}, "profiles": {}}))):
                response = TestClient(app).post("/api/route", json={"task": task})
                summary = TestClient(app).get(f"/api/task-summaries/{task['task_id']}")
        return response, summary, model

    def test_route_selects_compatible_eis_tool_with_auditable_decision(self):
        task = {"task_id": "route-eis", "user_message": "Run basic EIS quality checks", "graph_version": 0, "available_input_types": ["TypedTable"]}
        response, read_summary, model = self._route(task, {"tool_id": "eis_basic_qc", "confidence": 0.9, "rationale": "EIS quality checks on a typed table."})
        self.assertEqual(response.status_code, 200)
        decision = response.json()
        self.assertEqual(decision["selected"][0]["tool_id"], "eis_basic_qc")
        self.assertFalse(decision["requires_human_confirmation"])
        self.assertEqual(decision["model_decisions"][-1]["profile"], "llm")
        model.assert_called_once()
        summary = decision["summary"]
        self.assertEqual(summary["user_prompt"], "Run basic EIS quality checks")
        self.assertEqual(summary["decision"]["selected_tools"][0]["registered_id"], "eis_basic_qc")
        self.assertEqual(read_summary.status_code, 200)
        self.assertEqual(read_summary.json()["user_prompt"], "Run basic EIS quality checks")

    def test_route_returns_confirmation_when_no_tool_matches(self):
        task = {"task_id": "route-unknown", "user_message": "Perform quantum electron tomography", "graph_version": 0, "available_input_types": ["TypedTable"]}
        response, _, _ = self._route(task, {"tool_id": None, "confidence": 0.95, "rationale": "No candidate performs tomography."})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["selected"], [])
        self.assertTrue(response.json()["requires_human_confirmation"])

    def test_route_never_selects_by_keyword_overlap(self):
        # The request repeats the EIS tool's own words, yet the model's choice
        # decides; candidates carry no lexical score at all.
        task = {"task_id": "route-words", "user_message": "eis basic qc eis basic analysis nyquist bode quality checks", "graph_version": 0, "available_input_types": ["TypedTable"]}
        response, _, _ = self._route(task, {"tool_id": "xrd_peak_extraction", "confidence": 0.8, "rationale": "scripted"})
        decision = response.json()
        self.assertEqual(decision["selected"][0]["tool_id"], "xrd_peak_extraction")
        self.assertTrue(all(candidate["score"] == 0.0 for candidate in decision["candidates"]))

    def test_route_without_any_model_selects_nothing(self):
        from backend.routing import DecisionRouter
        from backend.contracts import TaskState

        decision = DecisionRouter().decide(
            TaskState(user_message="Run basic EIS quality checks", graph_version=0, available_input_types=["TypedTable"]),
            reference_registry(),
        )
        self.assertEqual(decision.selected, [])
        self.assertTrue(decision.requires_human_confirmation)
        self.assertIn("keyword matching is disabled", decision.rationale)

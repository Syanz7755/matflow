"""The matflow-http v1.1 contract at the HTTP seam.

Every test builds its own temporary workspace, so the contract is proven instead
of borrowed from the repository's live `data/` directory.

What is locked here:

* one error envelope (``{"detail": {"code", "message", ...}}``) and honest status
  codes, including 404-vs-422 consistency for the same missing resource;
* a failed workflow or chat must not arrive as HTTP 200;
* ``GraphState.revision`` advances on every persisted write while ``version``
  stays the structural (patch) version clients send as ``base_version``;
* the operation catalogue is derived from the live route table;
* the dataset byte-delivery channel, with an ETag;
* every agent-selectable tool declared in code states its parameters.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from backend import main
from backend.contracts import Edge, GraphPatch, Node, Operation, ToolSpec
from backend.tool_registry import ToolRegistry
from tests.reference_composition import registry as reference_registry
from tests.reference_composition import workspace as reference_workspace


class WorkspaceHttpTestCase(unittest.TestCase):
    """A test client whose routes see a private temporary workspace."""

    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.runtime = reference_workspace(Path(self._directory.name))
        self._workspace_patch = patch.object(main, "workspace", self.runtime)
        self._workspace_patch.start()
        self.client = TestClient(main.app)

    def tearDown(self):
        self._workspace_patch.stop()
        self._directory.cleanup()

    def add_node(self, node_id: str = "import-1", node_type: str = "raw_file_import", params: dict | None = None) -> str:
        state = self.runtime.read_state()
        self.runtime.apply_graph_patch(GraphPatch(
            base_version=state.version,
            operations=[Operation(op="add_node", node=Node(id=node_id, type=node_type, params=params or {}))],
        ))
        return node_id


class OperationCatalogueTests(unittest.TestCase):
    def test_every_live_api_route_has_a_stable_operation_id(self):
        payload = TestClient(main.app).get("/api/capabilities").json()

        self.assertEqual(payload["operations_unmapped"], [])
        self.assertEqual(payload["operations_stale"], [])
        self.assertGreaterEqual(len(payload["operations"]), 35)

    def test_the_catalogue_covers_endpoints_the_hand_written_list_omitted(self):
        operations = TestClient(main.app).get("/api/capabilities").json()["operations"]

        self.assertEqual(operations["inspect_dataset"], "GET /api/uploads/{upload_id}")
        self.assertEqual(operations["read_dataset_content"], "GET /api/uploads/{upload_id}/content")
        self.assertEqual(operations["read_settings"], "GET /api/settings")
        self.assertEqual(operations["reset_workspace"], "POST /api/reset")
        self.assertEqual(operations["chat"], "POST /api/chat")

    def test_the_contract_names_the_same_version_everywhere(self):
        payload = TestClient(main.app).get("/api/capabilities").json()

        self.assertEqual(payload["api_contract"], {"name": "matflow-http", "version": "1.0"})
        self.assertEqual(payload["server_version"], "1.1.0")


class ErrorEnvelopeTests(WorkspaceHttpTestCase):
    def test_a_validation_failure_uses_the_same_envelope(self):
        response = self.client.post("/api/route", json={"task": {"user_message": ""}})

        self.assertEqual(response.status_code, 422)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "invalid_request")
        self.assertIsInstance(detail["message"], str)
        self.assertIsInstance(detail["errors"], list)

    def test_an_unknown_node_is_not_found_not_unprocessable(self):
        response = self.client.post("/api/execute", json={"node_id": "does-not-exist"})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"]["code"], "not_found")

    def test_an_unknown_upload_is_not_found_with_a_code(self):
        response = self.client.get("/api/uploads/missing.csv")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"]["code"], "not_found")

    def test_a_stale_patch_reports_the_current_version(self):
        response = self.client.post("/api/patch/validate", json={
            "base_version": 99,
            "operations": [{"op": "add_node", "node": {"id": "stale", "type": "raw_file_import"}}],
        })

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "graph_version_conflict")
        self.assertEqual(response.json()["detail"]["current_version"], 0)

    def test_the_same_missing_proposal_is_not_found_on_every_route(self):
        self.assertEqual(self.client.get("/api/node-revisions/proposals/nope").status_code, 404)
        self.assertEqual(self.client.post("/api/node-revisions/proposals/nope/review-code", json={"approved": True}).status_code, 404)
        self.assertEqual(self.client.post("/api/node-revisions/proposals/nope/apply", json={}).status_code, 404)

    def test_reviewing_a_node_that_is_not_waiting_is_a_conflict(self):
        node_id = self.add_node()

        response = self.client.post("/api/workflow/decision", json={"node_id": node_id, "decision": "continue"})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "conflict")

    def test_an_unsupported_decision_is_still_a_validation_error(self):
        node_id = self.add_node()
        state = self.runtime.read_state()
        node = next(item for item in state.nodes if item.id == node_id)
        node.status = "waiting"
        node.review_state.status = "pending"
        self.runtime.write_state(state)

        response = self.client.post("/api/workflow/decision", json={"node_id": node_id, "decision": "maybe"})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "invalid_request")


class HonestFailureStatusTests(WorkspaceHttpTestCase):
    def test_a_failed_workflow_is_not_http_200(self):
        self.add_node(params={"upload_id": "missing.csv"})

        response = self.client.post("/api/workflow/execute", json={})

        self.assertEqual(response.status_code, 424)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["errors"][0]["node_id"], "import-1")
        self.assertIn("state", body)

    def test_a_successful_workflow_still_reports_ok(self):
        upload = self.runtime.import_dataset("a.csv", b"x,y\n1,2\n", "text/csv")
        self.add_node(params={"upload_id": upload["id"]})

        response = self.client.post("/api/workflow/execute", json={})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["errors"], [])

    def test_a_failed_chat_is_not_http_200(self):
        replies = [
            {"role": "assistant", "content": "", "tool_calls": [{
                "id": "call-1", "type": "function",
                "function": {"name": "inspect_upload", "arguments": json.dumps({"upload_id": "missing.csv"})},
            }]},
            {"role": "assistant", "content": "I could not read the file."},
        ]
        with patch.object(main, "model_completion", side_effect=replies):
            response = self.client.post("/api/chat", json={
                "message": "Analyse the attached data.",
                "attachments": [{"upload_id": "missing.csv", "name": "a.csv"}],
            })

        self.assertEqual(response.status_code, 424)
        payload = response.json()
        self.assertEqual(payload["status"], "failed")
        self.assertIsNotNone(payload["error"])
        self.assertIn("state", payload)

    def test_an_unreadable_dataset_is_not_silently_ok(self):
        with patch.object(self.runtime, "inspect_dataset", return_value={"upload_id": "x.csv", "name": "x.csv", "kind": "unreadable", "error": "boom"}):
            response = self.client.get("/api/uploads/x.csv")

        self.assertEqual(response.status_code, 422)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "unreadable_dataset")
        self.assertEqual(detail["inspection"]["kind"], "unreadable")

    def test_a_binary_dataset_is_still_a_valid_answer(self):
        with patch.object(self.runtime, "inspect_dataset", return_value={"upload_id": "x.png", "name": "x.png", "kind": "binary"}):
            response = self.client.get("/api/uploads/x.png")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["kind"], "binary")


class RevisionTests(WorkspaceHttpTestCase):
    def test_revision_moves_on_execution_while_version_stays_structural(self):
        node_id = self.add_node()
        after_patch = self.runtime.read_state()

        upload = self.runtime.import_dataset("a.csv", b"x,y\n1,2\n", "text/csv")
        self.runtime.apply_graph_patch(GraphPatch(
            base_version=after_patch.version,
            operations=[Operation(op="update_node", node_id=node_id, params={"upload_id": upload["id"]})],
        ))
        before_execution = self.runtime.read_state()

        response = self.client.post("/api/execute", json={"node_id": node_id})
        self.assertEqual(response.status_code, 200)
        after_execution = self.runtime.read_state()

        self.assertEqual(after_execution.version, before_execution.version)
        self.assertGreater(after_execution.revision, before_execution.revision)
        self.assertIsNotNone(after_execution.updated_at)

    def test_revision_moves_on_a_review_decision(self):
        node_id = self.add_node()
        state = self.runtime.read_state()
        node = next(item for item in state.nodes if item.id == node_id)
        node.status = "waiting"
        node.review_state.status = "pending"
        self.runtime.write_state(state)
        before = self.runtime.read_state()

        response = self.client.post("/api/workflow/decision", json={"node_id": node_id, "decision": "stop"})

        self.assertEqual(response.status_code, 200)
        self.assertGreater(self.runtime.read_state().revision, before.revision)

    def test_state_exposes_the_revision_to_clients(self):
        self.add_node()

        payload = self.client.get("/api/state").json()

        self.assertEqual(payload["state"]["revision"], self.runtime.read_state().revision)
        self.assertGreaterEqual(payload["state"]["revision"], 1)

    def test_a_running_node_cannot_be_started_twice(self):
        node_id = self.add_node()
        state = self.runtime.read_state()
        next(item for item in state.nodes if item.id == node_id).status = "running"
        self.runtime.write_state(state)

        response = self.client.post("/api/execute", json={"node_id": node_id})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "node_already_running")


class ReviewContinueTests(WorkspaceHttpTestCase):
    """The editor's exact sequence: run to a review gate, continue, downstream runs."""

    def build_gated_eis_workflow(self) -> str:
        upload = self.runtime.import_dataset(
            "sample-eis.csv",
            b"frequency_hz,z_real,z_imag\n1000,5,-1\n100,8,-3\n10,12,-5\n",
            "text/csv",
        )
        self.runtime.apply_graph_patch(GraphPatch(
            base_version=self.runtime.read_state().version,
            operations=[
                Operation(op="add_node", node=Node(
                    id="source", type="raw_file_import",
                    params={"upload_id": upload["id"]},
                    review_policy={"after_run": True, "prompt": "Review the imported data."},
                )),
                Operation(op="add_node", node=Node(
                    id="normalize", type="normalize_columns",
                    params={"frequency_column": "frequency_hz", "real_column": "z_real", "imag_column": "z_imag"},
                )),
                Operation(op="add_node", node=Node(
                    id="qc", type="eis_basic_qc", params={"min_frequency_hz": 10, "fit_model": "None"},
                )),
                Operation(op="connect", edge=Edge(id="e1", source="source", source_port="raw", target="normalize", target_port="raw")),
                Operation(op="connect", edge=Edge(id="e2", source="normalize", source_port="table", target="qc", target_port="data")),
            ],
            rationale="Contract test: a review gate followed by downstream execution.",
        ))
        return "source"

    def test_continuing_a_review_runs_the_downstream_nodes(self):
        source_id = self.build_gated_eis_workflow()

        run = self.client.post("/api/workflow/execute", json={})
        self.assertEqual(run.status_code, 200)
        self.assertTrue(run.json()["ok"])
        self.assertEqual(next(node for node in run.json()["state"]["nodes"] if node["id"] == source_id)["status"], "waiting")

        decision = self.client.post("/api/workflow/decision", json={"node_id": source_id, "decision": "continue"})

        self.assertEqual(decision.status_code, 200)
        body = decision.json()
        self.assertTrue(body["ok"])
        nodes = {node["id"]: node for node in body["state"]["nodes"]}
        self.assertEqual(nodes[source_id]["status"], "completed")
        self.assertEqual(nodes["normalize"]["status"], "completed")
        self.assertEqual(nodes["qc"]["status"], "completed")
        self.assertEqual(nodes["qc"]["output"]["kind"], "EISQCReport")

    def test_stopping_a_review_leaves_the_downstream_nodes_alone(self):
        source_id = self.build_gated_eis_workflow()
        self.client.post("/api/workflow/execute", json={})

        decision = self.client.post("/api/workflow/decision", json={"node_id": source_id, "decision": "stop"})

        self.assertEqual(decision.status_code, 200)
        nodes = {node["id"]: node for node in decision.json()["state"]["nodes"]}
        self.assertEqual(nodes[source_id]["status"], "cancelled")
        self.assertEqual(nodes["qc"]["status"], "ready")


class DatasetContentTests(WorkspaceHttpTestCase):
    def test_a_numeric_table_preview_is_native_json(self):
        """Regression: pandas can hand back numpy scalars, which JSON rejects."""
        upload = self.runtime.import_dataset("numbers.csv", b"n,ratio,label\n1,0.5,a\n2,,\n", "text/csv")

        response = self.client.get(f"/api/uploads/{upload['id']}")

        self.assertEqual(response.status_code, 200)
        preview = response.json()["preview"]
        self.assertEqual(len(preview), 2)
        for row in preview:
            for value in row.values():
                self.assertIsInstance(value, (int, float, str, bool, type(None)), row)

    def test_stored_bytes_can_be_read_back_with_an_etag(self):
        upload = self.runtime.import_dataset("a.csv", b"x,y\n1,2\n", "text/csv")

        response = self.client.get(f"/api/uploads/{upload['id']}/content")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"x,y\n1,2\n")
        self.assertTrue(response.headers["etag"])
        self.assertTrue(response.headers["content-type"].startswith("text/csv"))

    def test_a_matching_etag_returns_not_modified(self):
        upload = self.runtime.import_dataset("a.csv", b"x,y\n1,2\n", "text/csv")
        first = self.client.get(f"/api/uploads/{upload['id']}/content")

        second = self.client.get(f"/api/uploads/{upload['id']}/content", headers={"If-None-Match": first.headers["etag"]})

        self.assertEqual(second.status_code, 304)

    def test_the_content_route_rejects_unknown_and_traversing_ids(self):
        self.assertEqual(self.client.get("/api/uploads/missing.csv/content").status_code, 404)
        self.assertEqual(self.client.get("/api/uploads/../settings.json/content").status_code, 404)


class ParameterContractTests(unittest.TestCase):
    def test_every_agent_selectable_tool_states_its_parameters(self):
        registry = reference_registry()

        checked = 0
        for tool_id, spec in registry.active().items():
            if not spec.agent_selectable:
                continue
            schema = spec.parameter_schema
            Draft202012Validator.check_schema(schema)
            self.assertEqual(schema.get("type"), "object", tool_id)
            self.assertIn("properties", schema, tool_id)
            self.assertIn("additionalProperties", schema, tool_id)
            if not spec.open_params:
                self.assertIs(schema["additionalProperties"], False, tool_id)
            else:
                self.assertIs(schema["additionalProperties"], True, tool_id)
            checked += 1
        self.assertGreaterEqual(checked, 12)

    def test_a_declared_tool_without_a_parameter_contract_is_rejected(self):
        undeclared = ToolSpec(
            tool_id="undeclared_tool", label="Undeclared", category="Test",
            description="Declares no parameter contract.", outputs={"value": "Artifact"},
            executor_ref="custom:undeclared_tool",
        )

        with self.assertRaisesRegex(ValueError, "must declare an explicit parameter_schema"):
            ToolRegistry(package_specs={"undeclared_tool": undeclared})

    def test_a_custom_node_is_exempt_so_the_user_library_still_loads(self):
        registry = ToolRegistry(custom_nodes={
            "my_node": {
                "label": "My Node", "category": "Test", "description": "A user-authored node.",
                "inputs": {}, "outputs": {"value": "Artifact"}, "params": {},
            },
        })

        self.assertIn("my_node", registry.active())


if __name__ == "__main__":
    unittest.main()

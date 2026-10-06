from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.contracts import Edge, GraphPatch, GraphState, Node, TaskState, ToolSpec
from backend.domain_packages import DomainPackage, DomainPackageLoader, DomainPackageManifest
from backend.domain_packages.qe_demo import build_demo_patch, qe_replay_stdout
from backend.executors import ExecutorRegistry, NodeExecution, ToolExecutionError
from backend.routing import DecisionRouter
from backend.validator import GraphValidator
from backend.workspace_runtime import WorkspaceRuntime


class QEDomainPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.runtime = WorkspaceRuntime(Path(self.temp.name), packages=("qe", "qe_demo"))

    def tearDown(self):
        self.temp.cleanup()

    def test_demo_generates_pw_input_and_replays_a_converged_result(self):
        patch = build_demo_patch(0, "对纯 MgO 2x2x2 结构生成 QE SCF 输入并报告收敛和总能")
        self.runtime.apply_graph_patch(patch)
        outcome = self.runtime.execute_workflow(restart=True)
        nodes = {node["id"]: node for node in outcome["state"]["nodes"]}
        generated = nodes["qe-demo-input"]["output"]["input_text"]
        self.assertIn("&CONTROL", generated)
        self.assertIn("ATOMIC_SPECIES", generated)
        self.assertIn("ATOMIC_POSITIONS crystal", generated)
        self.assertIn("K_POINTS automatic", generated)
        self.assertEqual(nodes["qe-demo-input"]["output"]["atom_count"], 64)
        result = nodes["qe-demo-result"]["output"]
        self.assertEqual(result["convergence"], "converged")
        self.assertEqual(result["iterations"], 14)
        self.assertAlmostEqual(result["energy"]["value"], -2417.17683284)
        self.assertEqual(result["provenance"], "historical_output_replay")

    def test_schema_rejects_invalid_kmesh_and_missing_pseudopotential(self):
        state = GraphState(nodes=[Node(id="structure", type="qe_structure", params={
            "cell": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "cell_unit": "angstrom",
            "positions": [{"element": "Mg", "coordinates": [0, 0, 0]}], "position_unit": "crystal",
            "pseudopotentials": {},
        })])
        with self.assertRaisesRegex(ValueError, "Invalid parameters.*pseudopotentials"):
            GraphValidator().validate_state(state, self.runtime.registry())

        valid = build_demo_patch(0, "MgO SCF").operations
        pw_node = next(op.node for op in valid if op.node and op.node.type == "qe_pw_input")
        pw_node.params["k_points"] = [0, 3, 3, 0, 0, 0]
        structure_node = next(op.node for op in valid if op.node and op.node.type == "qe_structure")
        edge = Edge(id="input-edge", source=structure_node.id, source_port="structure", target=pw_node.id, target_port="structure")
        invalid = GraphState(nodes=[structure_node, pw_node], edges=[edge])
        with self.assertRaisesRegex(ValueError, "Invalid parameters.*k_points"):
            GraphValidator().validate_state(invalid, self.runtime.registry())

    def test_workflow_rejects_missing_required_dependency(self):
        spec = self.runtime.registry().get("qe_pw_input")
        node = Node(id="input", type="qe_pw_input", params=spec.params)
        with self.assertRaisesRegex(ValueError, "Missing required dependency.*structure"):
            GraphValidator().validate_state(GraphState(nodes=[node]), self.runtime.registry())

    def test_workflow_reports_unknown_tool_type_mismatch_and_cycle(self):
        with self.assertRaisesRegex(ValueError, "Unknown registry node: missing_tool"):
            GraphValidator().validate_state(GraphState(nodes=[Node(id="bad", type="missing_tool")]), self.runtime.registry())
        structure = Node(id="structure", type="qe_structure", params=self.runtime.registry().get("qe_structure").params)
        parser = Node(id="parser", type="qe_parse_output")
        wrong_type = GraphState(nodes=[structure, parser], edges=[Edge(id="wrong", source="structure", source_port="structure", target="parser", target_port="stdout")])
        with self.assertRaisesRegex(ValueError, "Type mismatch"):
            GraphValidator().validate_state(wrong_type, self.runtime.registry())
        cast_params = {"source_type": "RawData", "target_type": "RawData"}
        cycle = GraphState(nodes=[Node(id="a", type="type_cast", params=cast_params), Node(id="b", type="type_cast", params=cast_params)], edges=[
            Edge(id="ab", source="a", source_port="value", target="b", target_port="value"),
            Edge(id="ba", source="b", source_port="value", target="a", target_port="value"),
        ])
        with self.assertRaisesRegex(ValueError, "acyclic"):
            GraphValidator().validate_state(cycle, self.runtime.registry())

    def _parse_from_text(self, output: str) -> ToolExecutionError:
        state = GraphState(nodes=[
            Node(id="input", type="qe_pw_input", status="completed", output={"kind": "QEInput"}),
            Node(id="stdout", type="qe_replay_stdout", status="completed", output={"kind": "QEStdout", "text": output, "source": "test"}),
            Node(id="parse", type="qe_parse_output"),
        ], edges=[
            Edge(id="e1", source="input", source_port="input", target="parse", target_port="input"),
            Edge(id="e2", source="stdout", source_port="stdout", target="parse", target_port="stdout"),
        ])
        self.runtime.write_state(state)
        with self.assertRaises(ToolExecutionError) as caught:
            self.runtime.execute_node("parse")
        return caught.exception

    def test_parser_distinguishes_missing_output_from_nonconvergence(self):
        missing = self._parse_from_text("")
        self.assertEqual(missing.code, "qe_output_missing")
        nonconverged = self._parse_from_text("! total energy = -1.0 Ry\nJOB DONE")
        self.assertEqual(nonconverged.code, "qe_not_converged")

    def test_missing_archived_output_file_has_its_own_error(self):
        node = Node(id="fixture", type="qe_replay_stdout")
        context = NodeExecution(runtime=self.runtime, state=GraphState(), node=node, spec=self.runtime.registry().get("qe_replay_stdout"))
        with patch.object(Path, "read_text", side_effect=FileNotFoundError("missing")):
            with self.assertRaises(ToolExecutionError) as caught:
                qe_replay_stdout(context)
        self.assertEqual(caught.exception.code, "qe_output_missing")

    def test_demo_fixture_is_not_a_router_candidate(self):
        registry = self.runtime.registry()
        self.assertIn("qe_replay_stdout", registry.active())
        self.assertNotIn("qe_replay_stdout", registry.agent_selectable())
        decision = DecisionRouter().decide(
            TaskState(user_message="Replay archived QE output", graph_version=0, available_input_types=[]),
            registry,
        )
        self.assertNotIn("qe_replay_stdout", [item.tool_id for item in decision.candidates])

    def test_agent_patch_cannot_add_the_demo_fixture_tool(self):
        import backend.main as main

        previous = main.workspace
        try:
            main.workspace = self.runtime
            patch = build_demo_patch(0, "MgO SCF")
            with self.assertRaisesRegex(ValueError, "not available for agent selection"):
                main.run_agent_tool("apply_graph_patch", {"patch": patch.model_dump()})
        finally:
            main.workspace = previous

    def test_slurm_failure_keeps_its_stable_error_code(self):
        spec = ToolSpec(tool_id="fake_slurm", label="Fake Slurm", category="test", description="Failure injection", outputs={"result": "Artifact"}, params={}, parameter_schema={"type": "object", "properties": {}, "additionalProperties": False}, executor_ref="test:slurm")
        package = DomainPackage(manifest=DomainPackageManifest(package_id="test_slurm", version="1.0.0", label="Test Slurm", description="Failure test"), tool_specs={"fake_slurm": spec})
        loader = DomainPackageLoader({"test_slurm": lambda: package})
        executors = ExecutorRegistry.platform()
        def fail(_ctx):
            raise ToolExecutionError("slurm_failed", "sbatch rejected the job")
        executors.register("test:slurm", fail)
        runtime = WorkspaceRuntime(Path(self.temp.name) / "slurm", packages=("test_slurm",), package_loader=loader, executors=executors)
        runtime.write_state(GraphState(nodes=[Node(id="submit", type="fake_slurm")]))
        with self.assertRaises(ToolExecutionError) as caught:
            runtime.execute_node("submit")
        self.assertEqual(caught.exception.code, "slurm_failed")
        self.assertEqual(runtime.read_state().nodes[0].output["error"]["code"], "slurm_failed")

    def test_qe_demo_http_endpoint_builds_workflow_without_external_model(self):
        import backend.main as main
        from fastapi.testclient import TestClient

        previous = main.workspace
        try:
            main.workspace = WorkspaceRuntime(Path(self.temp.name) / "http-demo", packages=("qe", "qe_demo"))
            response = TestClient(main.app).post("/api/qe/demo", json={"message": "For pristine MgO SCF, generate QE input and report energy."})
            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertEqual(payload["execution_mode"], "historical_output_replay")
            self.assertFalse(payload["slurm_submitted"])
            self.assertEqual(payload["results"][-1]["result"]["kind"], "QEResult")
        finally:
            main.workspace = previous


if __name__ == "__main__":
    unittest.main()

"""Generic control semantics: Join, Aggregate, QualityReport and ConditionalGate.

None of these nodes carry scientific vocabulary, and the same graph shape must
work for a plain cast artifact and for an artifact produced by the EIS package.
That reuse is the evidence the platform milestone asks for.
"""
import tempfile
import unittest
from pathlib import Path

from backend.contracts import Edge, GraphState, Node
from backend.validator import GraphValidator
from backend.workspace_runtime import WorkspaceRuntime
from tests.reference_composition import PACKAGES

EIS_CSV = b"frequency_hz,z_real_ohm,z_imag_ohm\n1000,5.0,-1.5\n100,10.0,-5.0\n10,20.0,-12.0\n1,40.0,-30.0\n"


class GenericControlNodeTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.runtime = WorkspaceRuntime(Path(self.tempdir.name), packages=PACKAGES)

    def tearDown(self):
        self.tempdir.cleanup()

    def _nodes(self) -> dict[str, Node]:
        return {node.id: node for node in self.runtime.read_state().nodes}

    def test_join_and_aggregate_accept_several_upstream_artifacts(self):
        first = self.runtime.import_dataset("a.csv", b"value\n1\n2\n", "text/csv")
        second = self.runtime.import_dataset("b.csv", b"value\n3\n", "text/csv")
        self.runtime.write_state(
            GraphState(
                nodes=[
                    Node(id="input_a", type="raw_file_import", params={"upload_id": first["id"]}),
                    Node(id="input_b", type="raw_file_import", params={"upload_id": second["id"]}),
                    Node(id="cast_a", type="type_cast", params={"source_type": "RawData", "target_type": "Artifact"}),
                    Node(id="cast_b", type="type_cast", params={"source_type": "RawData", "target_type": "Artifact"}),
                    Node(id="join", type="join", params={"label": "batch"}),
                    Node(id="summary", type="aggregate", params={"group_key": "batch"}),
                ],
                edges=[
                    Edge(id="e1", source="input_a", source_port="raw", target="cast_a", target_port="value"),
                    Edge(id="e2", source="input_b", source_port="raw", target="cast_b", target_port="value"),
                    Edge(id="e3", source="cast_a", source_port="value", target="join", target_port="items"),
                    Edge(id="e4", source="cast_b", source_port="value", target="join", target_port="items"),
                    Edge(id="e5", source="join", source_port="combined", target="summary", target_port="items"),
                ],
            )
        )

        GraphValidator().validate_state(self.runtime.read_state(), self.runtime.registry())
        outcome = self.runtime.execute_workflow()
        self.assertEqual([item for item in outcome["results"] if "error" in item], [])

        nodes = self._nodes()
        self.assertEqual(nodes["join"].output["join"]["count"], 2)
        self.assertEqual(nodes["join"].output["join"]["sources"], ["cast_a", "cast_b"])
        self.assertEqual(nodes["join"].output["join"]["label"], "batch")
        self.assertEqual(len(nodes["join"].output["items"]), 2)
        self.assertEqual(nodes["summary"].output["aggregate"]["count"], 1)
        self.assertEqual(nodes["summary"].output["aggregate"]["numeric"]["join.count"]["max"], 2.0)

    def test_single_occupancy_still_holds_for_ordinary_input_ports(self):
        upload = self.runtime.import_dataset("a.csv", b"value\n1\n", "text/csv")
        state = GraphState(
            nodes=[
                Node(id="input", type="raw_file_import", params={"upload_id": upload["id"]}),
                Node(id="other", type="raw_file_import", params={"upload_id": upload["id"]}),
                Node(id="cast", type="type_cast", params={"source_type": "RawData", "target_type": "Artifact"}),
            ],
            edges=[
                Edge(id="e1", source="input", source_port="raw", target="cast", target_port="value"),
                Edge(id="e2", source="other", source_port="raw", target="cast", target_port="value"),
            ],
        )
        with self.assertRaisesRegex(ValueError, "Input port already connected"):
            GraphValidator().validate_state(state, self.runtime.registry())

    def test_failing_quality_report_stops_downstream_work(self):
        upload = self.runtime.import_dataset("a.csv", b"value\n1\n2\n", "text/csv")
        self.runtime.write_state(
            GraphState(
                nodes=[
                    Node(id="input", type="raw_file_import", params={"upload_id": upload["id"]}),
                    Node(id="cast", type="type_cast", params={"source_type": "RawData", "target_type": "Artifact"}),
                    Node(
                        id="report",
                        type="quality_report",
                        params={"required_keys": ["rows"], "metric_key": "rows", "minimum": 5, "maximum": None},
                    ),
                    Node(id="gate", type="conditional_gate", params={"on_fail": "stop"}),
                    Node(id="summary", type="aggregate", params={"group_key": ""}),
                ],
                edges=[
                    Edge(id="e1", source="input", source_port="raw", target="cast", target_port="value"),
                    Edge(id="e2", source="cast", source_port="value", target="report", target_port="data"),
                    Edge(id="e3", source="cast", source_port="value", target="gate", target_port="data"),
                    Edge(id="e4", source="report", source_port="report", target="gate", target_port="report"),
                    Edge(id="e5", source="gate", source_port="data", target="summary", target_port="items"),
                ],
            )
        )

        outcome = self.runtime.execute_workflow()
        self.assertTrue(outcome["stopped"])

        nodes = self._nodes()
        self.assertIs(nodes["report"].output["passed"], False)
        self.assertEqual(nodes["report"].output["checks"][1]["check"], "metric_range")
        self.assertEqual(nodes["gate"].status, "cancelled")
        self.assertEqual(nodes["gate"].output["decision"], "stop")
        self.assertEqual(nodes["summary"].status, "ready")

    def test_passing_quality_report_lets_downstream_work_run(self):
        upload = self.runtime.import_dataset("a.csv", b"value\n1\n2\n", "text/csv")
        self.runtime.write_state(
            GraphState(
                nodes=[
                    Node(id="input", type="raw_file_import", params={"upload_id": upload["id"]}),
                    Node(id="cast", type="type_cast", params={"source_type": "RawData", "target_type": "Artifact"}),
                    Node(
                        id="report",
                        type="quality_report",
                        params={"required_keys": ["rows"], "metric_key": "rows", "minimum": 1, "maximum": None},
                    ),
                    Node(id="gate", type="conditional_gate", params={"on_fail": "stop"}),
                    Node(id="summary", type="aggregate", params={"group_key": ""}),
                ],
                edges=[
                    Edge(id="e1", source="input", source_port="raw", target="cast", target_port="value"),
                    Edge(id="e2", source="cast", source_port="value", target="report", target_port="data"),
                    Edge(id="e3", source="cast", source_port="value", target="gate", target_port="data"),
                    Edge(id="e4", source="report", source_port="report", target="gate", target_port="report"),
                    Edge(id="e5", source="gate", source_port="data", target="summary", target_port="items"),
                ],
            )
        )

        outcome = self.runtime.execute_workflow()
        self.assertNotIn("stopped", outcome)

        nodes = self._nodes()
        self.assertIs(nodes["report"].output["passed"], True)
        self.assertEqual(nodes["gate"].status, "completed")
        self.assertEqual(nodes["gate"].output["decision"], "continue")
        self.assertEqual(nodes["summary"].output["aggregate"]["count"], 1)

    def test_the_same_generic_gate_reused_over_an_eis_package_artifact(self):
        upload = self.runtime.import_dataset("eis_spectrum.csv", EIS_CSV, "text/csv")
        self.runtime.write_state(
            GraphState(
                nodes=[
                    Node(id="input", type="raw_file_import", params={"upload_id": upload["id"]}),
                    Node(
                        id="map",
                        type="normalize_columns",
                        params={
                            "frequency_column": "frequency_hz",
                            "real_column": "z_real_ohm",
                            "imag_column": "z_imag_ohm",
                        },
                    ),
                    Node(id="qc", type="eis_basic_qc", params={"min_frequency_hz": 10, "fit_model": "None"}),
                    Node(
                        id="report",
                        type="quality_report",
                        params={"required_keys": ["rows_valid"], "metric_key": "rows_valid", "minimum": 4, "maximum": None},
                    ),
                    Node(id="gate", type="conditional_gate", params={"on_fail": "stop"}),
                    Node(id="summary", type="aggregate", params={"group_key": "eis"}),
                ],
                edges=[
                    Edge(id="e1", source="input", source_port="raw", target="map", target_port="raw"),
                    Edge(id="e2", source="map", source_port="table", target="qc", target_port="data"),
                    Edge(id="e3", source="qc", source_port="report", target="report", target_port="data"),
                    Edge(id="e4", source="qc", source_port="report", target="gate", target_port="data"),
                    Edge(id="e5", source="report", source_port="report", target="gate", target_port="report"),
                    Edge(id="e6", source="gate", source_port="data", target="summary", target_port="items"),
                ],
            )
        )

        outcome = self.runtime.execute_workflow()
        self.assertNotIn("stopped", outcome)

        nodes = self._nodes()
        self.assertEqual(nodes["qc"].output["kind"], "EISQCReport")
        self.assertIs(nodes["report"].output["passed"], True)
        self.assertEqual(nodes["gate"].output["decision"], "continue")
        self.assertIn("rows_valid", nodes["summary"].output["aggregate"]["numeric"])

    def test_a_cancelling_gate_is_recorded_as_cancelled_not_completed(self):
        upload = self.runtime.import_dataset("a.csv", b"value\n1\n2\n", "text/csv")
        self.runtime.write_state(
            GraphState(
                nodes=[
                    Node(id="input", type="raw_file_import", params={"upload_id": upload["id"]}),
                    Node(id="cast", type="type_cast", params={"source_type": "RawData", "target_type": "Artifact"}),
                    Node(
                        id="report",
                        type="quality_report",
                        params={"required_keys": ["rows"], "metric_key": "rows", "minimum": 5, "maximum": None},
                    ),
                    Node(id="gate", type="conditional_gate", params={"on_fail": "stop"}),
                ],
                edges=[
                    Edge(id="e1", source="input", source_port="raw", target="cast", target_port="value"),
                    Edge(id="e2", source="cast", source_port="value", target="report", target_port="data"),
                    Edge(id="e3", source="cast", source_port="value", target="gate", target_port="data"),
                    Edge(id="e4", source="report", source_port="report", target="gate", target_port="report"),
                ],
            )
        )

        for node_id in ("input", "cast", "report"):
            self.runtime.execute_node(node_id)
        outcome = self.runtime.execute_node("gate")

        self.assertEqual(outcome["execution"]["status"], "cancelled")
        self.assertEqual(outcome["execution"]["output"]["decision"], "stop")
        self.assertEqual(outcome["state"]["nodes"][-1]["status"], "cancelled")

    def test_the_gate_declares_only_the_port_it_writes(self):
        spec = self.runtime.registry().get("conditional_gate")
        self.assertEqual(spec.outputs, {"data": "Artifact"})
        self.assertNotIn("decision", spec.outputs)

    def test_a_multi_input_port_must_be_read_with_the_multi_input_accessor(self):
        first = self.runtime.import_dataset("a.csv", b"value\n1\n", "text/csv")
        second = self.runtime.import_dataset("b.csv", b"value\n2\n", "text/csv")
        self.runtime.write_state(
            GraphState(
                nodes=[
                    Node(id="input_a", type="raw_file_import", params={"upload_id": first["id"]}),
                    Node(id="input_b", type="raw_file_import", params={"upload_id": second["id"]}),
                    Node(id="cast_a", type="type_cast", params={"source_type": "RawData", "target_type": "Artifact"}),
                    Node(id="cast_b", type="type_cast", params={"source_type": "RawData", "target_type": "Artifact"}),
                    Node(id="join", type="join", params={"label": "batch"}),
                ],
                edges=[
                    Edge(id="e1", source="input_a", source_port="raw", target="cast_a", target_port="value"),
                    Edge(id="e2", source="input_b", source_port="raw", target="cast_b", target_port="value"),
                    Edge(id="e3", source="cast_a", source_port="value", target="join", target_port="items"),
                    Edge(id="e4", source="cast_b", source_port="value", target="join", target_port="items"),
                ],
            )
        )
        with self.assertRaisesRegex(ValueError, "use the multi-input accessor"):
            self.runtime.node_input(self.runtime.read_state(), "join", "items")

    def test_declaring_no_check_fails_closed(self):
        upload = self.runtime.import_dataset("a.csv", b"value\n1\n", "text/csv")
        self.runtime.write_state(
            GraphState(
                nodes=[
                    Node(id="input", type="raw_file_import", params={"upload_id": upload["id"]}),
                    Node(id="cast", type="type_cast", params={"source_type": "RawData", "target_type": "Artifact"}),
                    Node(id="report", type="quality_report", params={"required_keys": [], "metric_key": "", "minimum": None, "maximum": None}),
                ],
                edges=[Edge(id="e1", source="input", source_port="raw", target="cast", target_port="value"),
                       Edge(id="e2", source="cast", source_port="value", target="report", target_port="data")],
            )
        )

        self.runtime.execute_workflow()
        self.assertIs(self._nodes()["report"].output["passed"], False)


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from backend.contracts import Edge, GraphPatch, GraphState, Node, Operation, TaskState
from backend.data_types import DataTypeRegistry
from backend.routing import CandidateRetriever
from backend.tool_registry import ToolRegistry
from backend.validator import GraphValidator
from backend.workspace_runtime import WorkspaceRuntime


class DataTypeRegistryTests(unittest.TestCase):
    def test_multiple_inheritance_uses_c3_and_allows_parent_output_to_child_input(self):
        types = DataTypeRegistry({
            "Measurement": {"parents": []},
            "SpectralData": {"parents": ["Measurement"]},
            "CalibratedData": {"parents": ["Measurement"]},
            "CalibratedSpectrum": {"parents": ["SpectralData", "CalibratedData"]},
        })

        self.assertEqual(
            types.linearization("CalibratedSpectrum"),
            ("CalibratedSpectrum", "SpectralData", "CalibratedData", "Measurement"),
        )
        self.assertTrue(types.can_flow("Measurement", "CalibratedSpectrum"))
        self.assertFalse(types.can_flow("CalibratedSpectrum", "Measurement"))

    def test_rejects_cycles_unknown_parents_and_inconsistent_c3_order(self):
        with self.assertRaisesRegex(ValueError, "cycle"):
            DataTypeRegistry({"A": {"parents": ["B"]}, "B": {"parents": ["A"]}})
        with self.assertRaisesRegex(ValueError, "unknown parent"):
            DataTypeRegistry({"A": {"parents": ["Missing"]}})
        with self.assertRaisesRegex(ValueError, "Inconsistent multiple inheritance"):
            DataTypeRegistry({
                "A": {"parents": []}, "B": {"parents": []},
                "X": {"parents": ["A", "B"]}, "Y": {"parents": ["B", "A"]},
                "Z": {"parents": ["X", "Y"]},
            })


class TypeAwareGraphTests(unittest.TestCase):
    def setUp(self):
        self.types = DataTypeRegistry({
            "Measurement": {"parents": []},
            "EISMeasurement": {"parents": ["Measurement"]},
        })
        self.registry = ToolRegistry({
            "measurement_source": {
                "label": "Measurement Source", "category": "Test", "description": "source",
                "inputs": {}, "outputs": {"value": "Measurement"}, "params": {},
            },
            "eis_sink": {
                "label": "EIS Sink", "category": "Test", "description": "sink",
                "inputs": {"value": "EISMeasurement"}, "outputs": {"result": "Artifact"}, "params": {},
            },
            "eis_source": {
                "label": "EIS Source", "category": "Test", "description": "source",
                "inputs": {}, "outputs": {"value": "EISMeasurement"}, "params": {},
            },
            "measurement_sink": {
                "label": "Measurement Sink", "category": "Test", "description": "sink",
                "inputs": {"value": "Measurement"}, "outputs": {"result": "Artifact"}, "params": {},
            },
        }, self.types)

    def test_graph_accepts_parent_to_child_and_rejects_child_to_parent(self):
        parent_to_child = GraphState(nodes=[
            Node(id="source", type="measurement_source"), Node(id="sink", type="eis_sink"),
        ])
        patch = GraphPatch(base_version=0, operations=[Operation(
            op="connect", edge=Edge(id="flow", source="source", source_port="value", target="sink", target_port="value"),
        )])
        GraphValidator().validate(parent_to_child, patch, self.registry)

        child_to_parent = GraphState(nodes=[
            Node(id="source", type="eis_source"), Node(id="sink", type="measurement_sink"),
        ])
        with self.assertRaisesRegex(ValueError, "Type mismatch"):
            GraphValidator().validate(child_to_parent, patch, self.registry)

    def test_abstract_cast_resolves_instance_specific_ports(self):
        state = GraphState(nodes=[
            Node(id="source", type="measurement_source"),
            Node(id="cast", type="type_cast", params={"source_type": "EISMeasurement", "target_type": "Plot"}),
        ])
        patch = GraphPatch(base_version=0, operations=[Operation(
            op="connect", edge=Edge(id="cast-in", source="source", source_port="value", target="cast", target_port="value"),
        )])
        GraphValidator().validate(state, patch, self.registry)

    def test_router_uses_the_same_parent_to_child_rule(self):
        task = TaskState(user_message="EIS Sink", graph_version=0, available_input_types=["Measurement"])
        candidates = CandidateRetriever().retrieve(task, self.registry)
        self.assertIn("eis_sink", [candidate.tool_id for candidate in candidates])


class DataTypeActionTests(unittest.TestCase):
    def test_create_and_update_are_atomic_and_reject_a_cycle(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = WorkspaceRuntime(Path(directory))
            created = runtime.create_data_type({"name": "Measurement", "parents": [], "description": "Base"})
            self.assertEqual(created["name"], "Measurement")
            runtime.create_data_type({"name": "EISMeasurement", "parents": ["Measurement"]})

            with self.assertRaisesRegex(ValueError, "cycle"):
                runtime.update_data_type_inheritance("Measurement", ["EISMeasurement"])

            self.assertEqual(runtime.data_type_registry().get("Measurement").parents, [])

    def test_inheritance_update_cannot_invalidate_the_saved_graph(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = WorkspaceRuntime(Path(directory))
            runtime.create_data_type({"name": "Measurement", "parents": []})
            runtime.create_data_type({"name": "EISMeasurement", "parents": ["Measurement"]})
            settings = runtime.read_settings()
            settings["custom_nodes"] = {
                "measurement_source": {
                    "label": "Measurement Source", "category": "Test", "description": "source",
                    "inputs": {}, "outputs": {"value": "Measurement"}, "params": {},
                },
                "eis_sink": {
                    "label": "EIS Sink", "category": "Test", "description": "sink",
                    "inputs": {"value": "EISMeasurement"}, "outputs": {"result": "Artifact"}, "params": {},
                },
            }
            runtime.write_settings(settings)
            runtime.write_state(GraphState(nodes=[
                Node(id="source", type="measurement_source"), Node(id="sink", type="eis_sink"),
            ], edges=[
                Edge(id="flow", source="source", source_port="value", target="sink", target_port="value"),
            ]))

            with self.assertRaisesRegex(ValueError, "Type mismatch"):
                runtime.update_data_type_inheritance("EISMeasurement", [])

            self.assertEqual(runtime.data_type_registry().get("EISMeasurement").parents, ["Measurement"])

    def test_abstract_cast_executes_as_a_typed_pass_through(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = WorkspaceRuntime(Path(directory))
            upload = runtime.import_dataset("sample.csv", b"x,y\n1,2\n", "text/csv")
            runtime.write_state(GraphState(nodes=[
                Node(id="input", type="raw_file_import", params={"file_name": "sample.csv", "upload_id": upload["id"]}),
                Node(id="cast", type="type_cast", params={"source_type": "RawData", "target_type": "Artifact"}),
            ], edges=[
                Edge(id="input-cast", source="input", source_port="raw", target="cast", target_port="value"),
            ]))

            result = runtime.execute_workflow()

            cast = next(node for node in result["state"]["nodes"] if node["id"] == "cast")
            self.assertEqual(cast["output"]["kind"], "Artifact")
            self.assertEqual(cast["output"]["cast"]["from"], "RawData")


if __name__ == "__main__":
    unittest.main()

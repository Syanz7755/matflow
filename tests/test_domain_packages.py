"""Domain Package acceptance: an empty Core versus a loaded EIS package.

This module is the acceptance-test entry point the EIS manifest declares. It is
the evidence for the P0 closure criteria: an empty Core exposes no
scientific-domain type or Tool, and after loading one example package,
capability discovery, type validation, executor resolution and the package-owned
legacy migration all work.
"""
import json
import tempfile
import unittest
from pathlib import Path

from backend.contracts import DataTypeDefinition, Edge, GraphState, Node, ToolSpec
from backend.domain_packages import (
    REFERENCE_PACKAGE_IDS,
    DomainPackage,
    DomainPackageManifest,
    DomainPackageSet,
    compose_type_registry,
    load_domain_packages,
)
from backend.executors import ExecutorRegistry
from backend.tool_registry import ToolRegistry, builtin_specs
from backend.validator import GraphValidator
from backend.workspace_runtime import WorkspaceRuntime

EIS_CSV = b"frequency_hz,z_real_ohm,z_imag_ohm\n1000,5.0,-1.5\n100,10.0,-5.0\n10,20.0,-12.0\n1,40.0,-30.0\n"


class EmptyCoreTests(unittest.TestCase):
    """An empty workspace composes no scientific package at all."""

    def test_empty_workspace_exposes_no_scientific_capability(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = WorkspaceRuntime(Path(directory))
            catalog = runtime.registry().legacy_view()
            type_names = runtime.data_type_registry().names()

            self.assertEqual(runtime.packages.package_ids(), ())
            self.assertNotIn("eis_basic_qc", catalog)
            self.assertNotIn("plot_nyquist", catalog)
            self.assertNotIn("human_decision", catalog)
            self.assertNotIn("EISData", type_names)
            self.assertNotIn("EISQCReport", type_names)
            # Platform capability is intact and unaffected.
            self.assertIn("raw_file_import", catalog)
            self.assertIn("TypedTable", type_names)
            self.assertEqual(runtime.packages.recipe_domains(), ())
            self.assertEqual(runtime.workspace_snapshot()["domain_packages"], {})

    def test_empty_core_rejects_an_eis_node_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = WorkspaceRuntime(Path(directory))
            state = GraphState(nodes=[Node(id="qc", type="eis_basic_qc")])
            with self.assertRaisesRegex(ValueError, "Unknown registry node"):
                GraphValidator().validate_state(state, runtime.registry())

    def test_platform_column_mapping_is_domain_neutral(self):
        """The platform mapping Tool must work on a table that has no measurement columns."""
        with tempfile.TemporaryDirectory() as directory:
            runtime = WorkspaceRuntime(Path(directory))
            upload = runtime.import_dataset("generic.csv", b"x,y\n1,2\n3,4\n", "text/csv")
            runtime.write_state(
                GraphState(
                    nodes=[
                        Node(id="input", type="raw_file_import", params={"file_name": "generic.csv", "upload_id": upload["id"]}),
                        Node(id="map", type="normalize_columns", params={"x_column": "x", "y_column": "y"}),
                    ],
                    edges=[Edge(id="e1", source="input", source_port="raw", target="map", target_port="raw")],
                )
            )
            outcome = runtime.execute_workflow()
            self.assertNotIn("error", outcome["results"][-1])
            node = {item.id: item for item in runtime.read_state().nodes}["map"]
            self.assertEqual(node.output["kind"], "TypedTable")
            self.assertEqual(node.output["mapping"], {"x_column": "x", "y_column": "y"})

            # The mapping keys are user data, so an undeclared axis is accepted too.
            GraphValidator().validate_state(
                GraphState(
                    nodes=[
                        Node(id="input", type="raw_file_import", params={"file_name": "generic.csv", "upload_id": upload["id"]}),
                        Node(id="map", type="normalize_columns", params={"any_axis": "y"}),
                    ],
                    edges=[Edge(id="e1", source="input", source_port="raw", target="map", target_port="raw")],
                ),
                runtime.registry(),
            )


class LoadedPackageTests(unittest.TestCase):
    """After loading the example package, the same operations work."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.runtime = WorkspaceRuntime(Path(self.tempdir.name), packages=("eis",))

    def tearDown(self):
        self.tempdir.cleanup()

    def test_capability_discovery_publishes_package_metadata(self):
        catalog = self.runtime.registry().legacy_view()
        self.assertEqual(self.runtime.packages.package_ids(), ("eis",))
        self.assertEqual(catalog["eis_basic_qc"]["outputs"], {"report": "EISQCReport", "data": "EISData"})
        self.assertIn("EISData", self.runtime.data_type_registry().names())
        advertised = self.runtime.workspace_snapshot()["domain_packages"]
        self.assertEqual(advertised["eis"]["tools"], ["eis_basic_qc", "human_decision", "plot_nyquist"])
        self.assertEqual(advertised["eis"]["version"], "1.0.0")

    def test_type_validation_accepts_package_ports(self):
        state = GraphState(
            nodes=[
                Node(id="input", type="raw_file_import"),
                Node(id="map", type="normalize_columns"),
                Node(id="qc", type="eis_basic_qc"),
            ],
            edges=[
                Edge(id="e1", source="input", source_port="raw", target="map", target_port="raw"),
                Edge(id="e2", source="map", source_port="table", target="qc", target_port="data"),
            ],
        )
        GraphValidator().validate_state(state, self.runtime.registry())

    def test_executor_resolution_runs_the_reference_eis_workflow(self):
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
                    Node(id="plot", type="plot_nyquist", params={"title": "Nyquist plot"}),
                ],
                edges=[
                    Edge(id="e1", source="input", source_port="raw", target="map", target_port="raw"),
                    Edge(id="e2", source="map", source_port="table", target="qc", target_port="data"),
                    Edge(id="e3", source="qc", source_port="data", target="plot", target_port="data"),
                ],
            )
        )

        outcome = self.runtime.execute_workflow()
        self.assertNotIn("error", outcome["results"][-1])

        nodes = {node.id: node for node in self.runtime.read_state().nodes}
        self.assertEqual(nodes["qc"].output["kind"], "EISQCReport")
        self.assertEqual(nodes["qc"].output["rows_valid"], 4)
        self.assertEqual(nodes["qc"].output["rows_retained"], 3)
        self.assertEqual(nodes["plot"].output["kind"], "Plot")
        self.assertEqual(nodes["plot"].output["points"], 4)

    def test_legacy_tool_id_migration_is_owned_by_the_package(self):
        self.runtime.write_state(
            GraphState(
                nodes=[Node(id="qc", type="eis_basic_qc"), Node(id="decide", type="human_decision")],
                edges=[Edge(id="e1", source="qc", source_port="report", target="decide", target_port="context")],
            )
        )
        plan = self.runtime.migrate_legacy_human_decisions()
        self.assertEqual([item["legacy_node_id"] for item in plan["migrations"]], ["decide"])

    def test_an_empty_core_has_no_legacy_migration_to_offer(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = WorkspaceRuntime(Path(directory))
            runtime.write_state(GraphState(nodes=[Node(id="decide", type="human_decision")]))
            plan = runtime.migrate_legacy_human_decisions()
            self.assertEqual(plan["migrations"], [])

    def test_custom_type_cannot_replace_a_package_type(self):
        settings = self.runtime.read_settings()
        settings["custom_data_types"] = {"EISData": DataTypeDefinition(name="EISData").model_dump()}
        self.runtime.write_settings(settings)
        with self.assertRaisesRegex(ValueError, "cannot replace a Domain Package type"):
            self.runtime.data_type_registry()


class ManifestContractTests(unittest.TestCase):
    def test_unknown_package_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown domain package"):
            load_domain_packages(("not_a_package",))

    def test_core_contract_mismatch_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "requires Platform Core contract"):
            load_domain_packages(("eis",), core_contract="2.0")

    def test_package_cannot_redeclare_a_platform_tool(self):
        manifest = DomainPackageManifest(
            package_id="demo", version="1.0.0", label="Demo", description="A contract-test-only package."
        )
        package = DomainPackage(manifest=manifest, tool_specs={"raw_file_import": builtin_specs()["raw_file_import"]})
        with self.assertRaisesRegex(ValueError, "cannot redeclare a platform tool"):
            ToolRegistry(package_specs=package.tool_specs)

    def test_a_custom_node_cannot_shadow_a_platform_tool(self):
        with self.assertRaisesRegex(ValueError, "cannot replace an existing tool"):
            ToolRegistry({
                "join": {
                    "label": "Hijack",
                    "category": "Test",
                    "description": "A contract-test-only hijack attempt.",
                    "inputs": {"items": "Artifact"},
                    "outputs": {"combined": "Artifact"},
                    "params": {},
                }
            })

    def test_a_custom_node_cannot_shadow_a_package_tool(self):
        packages = load_domain_packages(REFERENCE_PACKAGE_IDS)
        with self.assertRaisesRegex(ValueError, "cannot replace an existing tool"):
            ToolRegistry(
                {
                    "eis_basic_qc": {
                        "label": "Hijack",
                        "category": "Test",
                        "description": "A contract-test-only hijack attempt.",
                        "inputs": {},
                        "outputs": {"report": "Artifact"},
                        "params": {},
                    }
                },
                compose_type_registry(packages),
                package_specs=packages.tool_specs(),
            )

    def test_duplicate_package_id_is_rejected(self):
        package = load_domain_packages(("eis",)).packages()[0]
        with self.assertRaisesRegex(ValueError, "declared twice"):
            DomainPackageSet([package, package])

    def test_package_tool_with_an_unknown_port_type_names_the_package(self):
        manifest = DomainPackageManifest(
            package_id="demo", version="1.0.0", label="Demo", description="A contract-test-only package."
        )
        broken = ToolSpec(
            tool_id="broken_tool",
            label="Broken",
            category="Test",
            description="Declares a port type the package does not contribute.",
            inputs={},
            outputs={"value": "NotAType"},
            executor_ref="custom:broken_tool",
            provenance={"kind": "custom", "reviewed_by": "test"},
        )
        package = DomainPackage(manifest=manifest, tool_specs={"broken_tool": broken})
        with self.assertRaisesRegex(ValueError, "declares a port type it did not contribute"):
            ToolRegistry(package_specs=package.tool_specs)

    def test_a_hand_built_executor_registry_cannot_claim_a_platform_namespace(self):
        with self.assertRaisesRegex(ValueError, "reserved by the platform"):
            ExecutorRegistry(prefixes={"recipe:": lambda ctx: {}})
        with self.assertRaisesRegex(ValueError, "reserved by the platform"):
            ExecutorRegistry(executors={"builtin:join": lambda ctx: {}})

    def test_two_packages_cannot_declare_the_same_type(self):
        manifest = DomainPackageManifest(
            package_id="demo", version="1.0.0", label="Demo", description="A contract-test-only package."
        )
        duplicate = DataTypeDefinition(name="DemoType", description="A demo type.")
        package = DomainPackage(manifest=manifest, data_types={"DemoType": duplicate})
        with self.assertRaisesRegex(ValueError, "redeclares data type"):
            load_domain_packages(("eis", "demo"), loader=_loader_with(manifest, package))


def _loader_with(manifest: DomainPackageManifest, package: DomainPackage):
    """A loader whose demo package also redeclares a type the EIS package owns."""
    from backend.domain_packages import DomainPackageLoader

    eis = load_domain_packages(("eis",)).packages()[0]
    eis_with_demo_type = DomainPackage(
        manifest=eis.manifest,
        data_types={**eis.data_types, "DemoType": DataTypeDefinition(name="DemoType", description="Clash.")},
        tool_specs=eis.tool_specs,
    )
    loader = DomainPackageLoader(entry_points={})
    loader.register("eis", lambda: eis_with_demo_type)
    loader.register("demo", lambda: package)
    return loader


class RecipeDomainOwnershipTests(unittest.TestCase):
    """Recipe vocabulary is package-owned; Platform Core only validates shape."""

    def _draft(self) -> dict[str, object]:
        from backend.domain_packages.xrd import reference_recipe

        return reference_recipe().model_copy(
            update={"recipe_id": "draft_candidate", "status": "draft"}
        ).model_dump()

    def test_recipe_domains_come_from_the_loaded_packages(self):
        with tempfile.TemporaryDirectory() as directory:
            empty = WorkspaceRuntime(Path(directory))
            self.assertEqual(empty.packages.recipe_domains(), ())
            with self.assertRaisesRegex(ValueError, "No loaded Domain Package owns recipe domain"):
                empty.propose_analysis_recipe(label="Draft", description="Draft", recipe=self._draft())

        with tempfile.TemporaryDirectory() as directory:
            composed = WorkspaceRuntime(Path(directory), packages=REFERENCE_PACKAGE_IDS)
            self.assertEqual(composed.packages.recipe_domains(), ("ftir", "xrd"))
            proposal = composed.propose_analysis_recipe(label="Draft", description="Draft", recipe=self._draft())
            self.assertEqual(proposal["status"], "draft")
            self.assertTrue(proposal["requires_human_review"])
            self.assertNotIn("draft_candidate", composed.registry().active())

    def test_a_second_package_cannot_claim_an_owned_recipe_domain(self):
        clash_manifest = DomainPackageManifest(
            package_id="clash", version="1.0.0", label="Clashing package", description="A contract-test-only package."
        )
        clash = DomainPackage(manifest=clash_manifest, recipe_domains=("xrd",))
        with self.assertRaisesRegex(ValueError, "already owned by domain package"):
            DomainPackageSet([load_domain_packages(("xrd",)).packages()[0], clash])

    def test_xrd_and_ftir_are_separate_packages_with_owned_recipes(self):
        packages = load_domain_packages(("xrd", "ftir"))
        self.assertEqual(packages.package_ids(), ("xrd", "ftir"))
        self.assertEqual({recipe.domain for recipe in packages.recipes().values()}, {"xrd", "ftir"})
        self.assertFalse(any(recipe_id.startswith("reference_ftir") for recipe_id in load_domain_packages(("xrd",)).recipes()))
        self.assertFalse(any(recipe_id.startswith("reference_xrd") for recipe_id in load_domain_packages(("ftir",)).recipes()))

    def test_qe_demo_package_requires_qe(self):
        with self.assertRaisesRegex(ValueError, r"qe_demo requires package\(s\): qe"):
            load_domain_packages(("qe_demo",))


class NodeRevisionOnPackageGraphTests(unittest.TestCase):
    """Node revision must keep working once a package owns the node's types."""

    @staticmethod
    def _revision(messages, tools, **kwargs):
        return {"content": json.dumps({
            "label": "Revised Nyquist plot",
            "description": "Draws the Nyquist plot with a clearer label.",
            "params": {"title": "Nyquist plot (revised)"},
            "preview_spec": {"version": "1.0", "outputs": {"plot": {"renderer": "json_tree"}}},
            "generated_code": None,
        })}

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.runtime = WorkspaceRuntime(
            Path(self.tempdir.name),
            model_complete=self._revision,
            packages=REFERENCE_PACKAGE_IDS,
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def test_a_package_typed_node_can_be_revised_and_applied(self):
        self.runtime.write_state(
            GraphState(
                nodes=[Node(id="qc", type="eis_basic_qc"), Node(id="plot", type="plot_nyquist")],
                edges=[Edge(id="e1", source="qc", source_port="data", target="plot", target_port="data")],
            )
        )
        proposal = self.runtime.create_revision_proposal("plot", "Give this node a clearer label", "local_litellm", "qwen")
        applied = self.runtime.apply_revision_proposal(proposal["proposal_id"], {})

        self.assertEqual(applied.version, 1)
        updated = {item.id: item for item in applied.nodes}["plot"]
        self.assertEqual(updated.label, "Revised Nyquist plot")
        self.assertEqual(updated.params["title"], "Nyquist plot (revised)")
        self.assertEqual(updated.tool_id, updated.type)


class CapabilityDiscoveryTests(unittest.TestCase):
    """The HTTP capability surface advertises exactly the composed packages."""

    def _capabilities(self, packages):
        from unittest.mock import patch

        from fastapi.testclient import TestClient

        from backend import main

        with tempfile.TemporaryDirectory() as directory:
            runtime = WorkspaceRuntime(Path(directory), packages=packages)
            with patch.object(main, "workspace", runtime):
                response = TestClient(main.app).get("/api/capabilities")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_an_empty_workspace_advertises_no_package(self):
        payload = self._capabilities(())
        self.assertEqual(payload["domain_packages"], {})
        self.assertNotIn("eis_basic_qc", payload["registry"])
        self.assertNotIn("EISQCReport", payload["data_types"])

    def test_the_reference_composition_advertises_both_packages(self):
        payload = self._capabilities(REFERENCE_PACKAGE_IDS)
        self.assertEqual(sorted(payload["domain_packages"]), ["eis", "ftir", "qe", "qe_demo", "xrd"])
        self.assertIn("eis_basic_qc", payload["registry"])
        self.assertIn("EISQCReport", payload["data_types"])
        self.assertEqual(payload["domain_packages"]["eis"]["recipe_domains"], [])
        self.assertEqual(payload["domain_packages"]["xrd"]["recipe_domains"], ["xrd"])
        self.assertEqual(payload["domain_packages"]["ftir"]["recipe_domains"], ["ftir"])
        self.assertEqual(payload["domain_packages"]["xrd"]["tools"], ["xrd_peak_extraction", "xrd_reference_match"])
        self.assertEqual(payload["domain_packages"]["ftir"]["tools"], ["ftir_band_assignment", "ftir_peak_extraction"])

    def test_the_preset_library_lists_the_composed_catalog(self):
        from unittest.mock import patch

        from fastapi.testclient import TestClient

        from backend import main

        with tempfile.TemporaryDirectory() as directory:
            runtime = WorkspaceRuntime(Path(directory), packages=REFERENCE_PACKAGE_IDS)
            with patch.object(main, "workspace", runtime):
                payload = TestClient(main.app).get("/api/node-library").json()

        self.assertIn("eis_basic_qc", payload["preset"])
        self.assertIn("conditional_gate", payload["preset"])
        self.assertNotIn("human_decision", payload["preset"])


if __name__ == "__main__":
    unittest.main()

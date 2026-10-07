"""Offline contract tests for prompt -> workflow planning.

The LLM is scripted: decomposition answers are fixed JSON, and tool selection
answers come from a table keyed by action id. That keeps every assertion about
*mechanics* — decomposition, per-action routing, port binding, validation —
deterministic. Whether a real model plans long prompts well is measured by
``tests/test_prompt_to_workflow_online.py``.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main
from backend.jev_routing import JevConfig, JevDecisionRouter
from backend.planner import BIND_SYSTEM_PROMPT, DECOMPOSE_SYSTEM_PROMPT
from backend.routing import SELECT_SYSTEM_PROMPT
from tests.reference_composition import workspace as reference_workspace

ROOT = Path(__file__).parents[1]
EIS = ROOT / "examples" / "data" / "01_eis_basic_qc" / "eis_spectrum.csv"
XRD = ROOT / "examples" / "data" / "02_xrd_anatase_identification" / "xrd_anatase.csv"
FTIR = ROOT / "examples" / "data" / "06_ftir_functional_group_assignment" / "ftir_spectrum.csv"

DISABLED_JEV = {"version": 1, "router": {"enabled": False}, "profiles": {}}


def jev(config=None, transport=None):
    return lambda: JevDecisionRouter(JevConfig.model_validate(config or DISABLED_JEV), transport=transport)


class ScriptedLLM:
    """Answers the planner's two kinds of request from fixed scripts."""

    def __init__(self, decompositions, routes, bindings=None):
        self.decompositions = list(decompositions)
        self.routes = routes
        self.bindings = bindings or {}
        self.decompose_requests = []
        self.route_requests = []
        self.bind_requests = []

    def __call__(self, messages, tools, **_kwargs):
        system = messages[0]["content"]
        if system == DECOMPOSE_SYSTEM_PROMPT:
            self.decompose_requests.append(list(messages))
            answer = self.decompositions.pop(0)
            return {"role": "assistant", "content": answer if isinstance(answer, str) else "```json\n" + json.dumps(answer) + "\n```"}
        if system == SELECT_SYSTEM_PROMPT:
            payload = json.loads(messages[1]["content"])
            self.route_requests.append(payload)
            goal = payload["work"]["action"]["goal"]
            tool_id, params = self.routes[goal]
            offered = [card["tool_id"] for card in payload["candidates"]]
            if tool_id is not None and tool_id not in offered:
                tool_id = None
            return {"role": "assistant", "content": json.dumps({"tool_id": tool_id, "confidence": 0.9, "rationale": f"scripted for {goal}", "params": params})}
        if system == BIND_SYSTEM_PROMPT:
            self.bind_requests.append(json.loads(messages[1]["content"]))
            return {"role": "assistant", "content": json.dumps({"params": self.bindings})}
        raise AssertionError(f"unexpected model request: {system[:60]}")


def action(action_id, goal, depends_on=(), input_files=(), parameters=None):
    return {"id": action_id, "goal": goal, "depends_on": list(depends_on), "input_files": list(input_files), "parameters": parameters or {}}


EIS_PLAN = {"status": "plan", "actions": [
    action("a1", "import eis", input_files=["eis_spectrum.csv"]),
    action("a2", "map eis columns", ["a1"]),
    action("a3", "eis quality check", ["a2"], parameters={"min_frequency_hz": 1}),
    action("a4", "nyquist plot", ["a3"]),
]}
EIS_ROUTES = {
    "import eis": ("raw_file_import", {}),
    "map eis columns": ("normalize_columns", {"frequency": "frequency_hz", "z_real": "z_real_ohm", "z_imag": "z_imag_ohm"}),
    "eis quality check": ("eis_basic_qc", {"min_frequency_hz": 1, "smoothing": "off"}),
    "nyquist plot": ("plot_nyquist", {}),
}


class PlannerTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def plan(self, llm, *, files=(), apply=False, jev_factory=None, message="请分析上传的数据"):
        runtime = reference_workspace(Path(self.directory.name), model_complete=llm)
        attachments = []
        for path in files:
            uploaded = runtime.import_dataset(path.name, path.read_bytes(), "text/csv")
            attachments.append({"upload_id": uploaded["id"], "name": path.name})
        with patch.object(main, "workspace", runtime), patch("backend.workspace_runtime.JevDecisionRouter", jev_factory or jev()):
            response = TestClient(main.app).post("/api/plan", json={"message": message, "attachments": attachments, "apply": apply})
        return response, runtime

    @staticmethod
    def by_action(plan):
        return {item["id"]: item for item in plan["actions"]}

    @staticmethod
    def edges(plan):
        return {(edge["source_action"], edge["target_action"]): edge["edge"] for edge in plan["edges"]}


class LinearPlanTests(PlannerTestCase):
    def test_prompt_becomes_a_validated_typed_chain(self):
        llm = ScriptedLLM([EIS_PLAN], EIS_ROUTES)
        response, runtime = self.plan(llm, files=[EIS], apply=True, message="对 EIS 数据做质检（最低频率 1 Hz）并画 Nyquist 图")

        self.assertEqual(response.status_code, 200, response.text)
        plan = response.json()
        self.assertEqual(plan["status"], "planned", plan["issues"])
        self.assertTrue(plan["patch_valid"])
        self.assertTrue(plan["applied"])
        actions = self.by_action(plan)
        self.assertEqual([actions[key]["tool_id"] for key in ("a1", "a2", "a3", "a4")], ["raw_file_import", "normalize_columns", "eis_basic_qc", "plot_nyquist"])
        self.assertTrue(all(item["router"] == "llm" for item in plan["actions"]))

        edges = self.edges(plan)
        self.assertEqual((edges[("a1", "a2")]["source_port"], edges[("a1", "a2")]["target_port"]), ("raw", "raw"))
        self.assertEqual((edges[("a2", "a3")]["source_port"], edges[("a2", "a3")]["target_port"]), ("table", "data"))
        # The plot consumes EISData, so the edge leaves the QC node's "data" port, not "report".
        self.assertEqual((edges[("a3", "a4")]["source_port"], edges[("a3", "a4")]["target_port"]), ("data", "data"))

        state = runtime.read_state()
        self.assertEqual(state.version, 1)
        self.assertEqual(len(state.nodes), 4)
        self.assertEqual(len(state.edges), 3)
        upload_id = actions["a1"]["params"]["upload_id"]
        self.assertTrue(upload_id.endswith("eis_spectrum.csv"))
        self.assertEqual(actions["a3"]["params"]["min_frequency_hz"], 1)
        self.assertEqual(actions["a3"]["ignored_params"], ["smoothing: not a parameter of eis_basic_qc"])
        self.assertEqual(actions["a2"]["params"], {"frequency": "frequency_hz", "z_real": "z_real_ohm", "z_imag": "z_imag_ohm"})

    def test_the_planner_sees_uploads_and_capabilities_but_no_tool_ids(self):
        llm = ScriptedLLM([EIS_PLAN], EIS_ROUTES)
        self.plan(llm, files=[EIS])
        payload = json.loads(llm.decompose_requests[0][1]["content"])
        self.assertEqual(payload["uploads"][0]["columns"], ["frequency_hz", "z_real_ohm", "z_imag_ohm"])
        self.assertNotIn("eis_basic_qc", json.dumps(payload["capabilities"]))
        # Routing happens per action unit, one model decision each.
        self.assertEqual([request["work"]["action"]["goal"] for request in llm.route_requests], ["import eis", "map eis columns", "eis quality check", "nyquist plot"])

    def test_routing_candidates_are_filtered_by_upstream_types_only(self):
        llm = ScriptedLLM([EIS_PLAN], EIS_ROUTES)
        self.plan(llm, files=[EIS])
        offered = {request["work"]["action"]["goal"]: {card["tool_id"] for card in request["candidates"]} for request in llm.route_requests}
        self.assertEqual(offered["import eis"], {"raw_file_import", "qe_structure"})
        self.assertIn("plot_nyquist", offered["nyquist plot"])
        self.assertNotIn("xrd_peak_extraction", offered["nyquist plot"])  # EISData/Artifact never feed a TypedTable port
        self.assertIn("xrd_peak_extraction", offered["eis quality check"])  # types fit; the model decides


class BranchingPlanTests(PlannerTestCase):
    def test_parallel_branches_join_on_a_multi_input_port(self):
        plan_json = {"status": "plan", "actions": [
            action("x1", "import xrd", input_files=["xrd_anatase.csv"]),
            action("x2", "map xrd", ["x1"]),
            action("x3", "xrd peaks", ["x2"]),
            action("x4", "xrd match", ["x3"]),
            action("f1", "import ftir", input_files=["ftir_spectrum.csv"]),
            action("f2", "map ftir", ["f1"]),
            action("f3", "ftir peaks", ["f2"]),
            action("f4", "ftir bands", ["f3"]),
            action("j1", "combined report", ["x4", "f4"]),
        ]}
        routes = {
            "import xrd": ("raw_file_import", {}), "map xrd": ("normalize_columns", {"x": "two_theta_deg", "y": "intensity_counts"}),
            "xrd peaks": ("xrd_peak_extraction", {}), "xrd match": ("xrd_reference_match", {"references": {"anatase": [25.3, 37.8, 48.0]}}),
            "import ftir": ("raw_file_import", {}), "map ftir": ("normalize_columns", {"x": "wavenumber_cm-1", "y": "absorbance_au"}),
            "ftir peaks": ("ftir_peak_extraction", {}), "ftir bands": ("ftir_band_assignment", {"ranges": [{"min": 2800, "max": 3000, "label": "C-H stretch"}]}),
            "combined report": ("join", {}),
        }
        message = "XRD: match anatase peaks 25.3, 37.8, 48.0. FTIR: assign the 2800-3000 band as C-H stretch. Then a combined report."
        response, _ = self.plan(ScriptedLLM([plan_json], routes), files=[XRD, FTIR], message=message)
        plan = response.json()
        self.assertEqual(plan["status"], "planned", plan["issues"])
        actions = self.by_action(plan)
        self.assertNotEqual(actions["x1"]["params"]["upload_id"], actions["f1"]["params"]["upload_id"])
        self.assertTrue(actions["f1"]["params"]["upload_id"].endswith("ftir_spectrum.csv"))
        edges = self.edges(plan)
        self.assertEqual(edges[("x4", "j1")]["target_port"], "items")
        self.assertEqual(edges[("f4", "j1")]["target_port"], "items")
        positions = {node["node"]["id"]: node["node"]["position"] for node in plan["patch"]["operations"] if node["op"] == "add_node"}
        self.assertGreater(positions[actions["j1"]["node_id"]]["x"], positions[actions["x4"]["node_id"]]["x"])

    def test_a_gate_receives_data_and_report_on_their_own_ports(self):
        plan_json = {"status": "plan", "actions": [
            action("a1", "import xrd", input_files=["xrd_anatase.csv"]),
            action("a2", "map xrd", ["a1"]),
            action("a3", "xrd peaks", ["a2"]),
            action("a4", "xrd match", ["a3"]),
            action("a5", "quality report", ["a4"]),
            action("a6", "gate", ["a4", "a5"]),
        ]}
        routes = {
            "import xrd": ("raw_file_import", {}), "map xrd": ("normalize_columns", {"x": "two_theta_deg"}),
            "xrd peaks": ("xrd_peak_extraction", {}), "xrd match": ("xrd_reference_match", {"references": {"anatase": [25.3, 37.8, 48.0]}}),
            "quality report": ("quality_report", {"metric_key": "matched_count", "minimum": 3}),
            "gate": ("conditional_gate", {}),
        }
        message = "Match anatase peaks 25.3, 37.8, 48.0; continue only if matched_count is at least 3."
        plan = self.plan(ScriptedLLM([plan_json], routes), files=[XRD], message=message)[0].json()
        self.assertEqual(plan["status"], "planned", plan["issues"])
        edges = self.edges(plan)
        self.assertEqual(edges[("a4", "a6")]["target_port"], "data")
        self.assertEqual(edges[("a5", "a6")]["target_port"], "report")


class GapAndControlTests(PlannerTestCase):
    def test_a_capability_gap_blocks_only_its_downstream(self):
        plan_json = {"status": "plan", "actions": [
            action("a1", "import", input_files=["eis_spectrum.csv"]),
            action("a2", "map", ["a1"]),
            action("a3", "fit an equivalent circuit", ["a2"]),
            action("a4", "plot the fitted circuit", ["a3"]),
        ]}
        routes = {"import": ("raw_file_import", {}), "map": ("normalize_columns", {"f": "frequency_hz"}), "fit an equivalent circuit": (None, {})}
        response, runtime = self.plan(ScriptedLLM([plan_json], routes), files=[EIS], apply=True)
        plan = response.json()
        self.assertEqual(plan["status"], "needs_confirmation")
        actions = self.by_action(plan)
        self.assertEqual(actions["a3"]["status"], "gap")
        self.assertEqual(actions["a4"]["status"], "blocked")
        self.assertTrue(plan["patch_valid"])
        self.assertEqual(len([op for op in plan["patch"]["operations"] if op["op"] == "add_node"]), 2)
        self.assertFalse(plan["applied"])
        self.assertEqual(runtime.read_state().nodes, [])
        self.assertTrue(any("capability gap" in issue for issue in plan["issues"]))

    def test_an_untyped_dead_end_triggers_one_decomposition_repair(self):
        first = {"status": "plan", "actions": [
            action("a1", "import", input_files=["eis_spectrum.csv"]), action("a2", "map", ["a1"]),
            action("a3", "qc", ["a2"]), action("a4", "plot", ["a3"]), action("a5", "fit circuit to the plot", ["a4"]),
        ]}
        second = {"status": "plan", "actions": first["actions"][:4]}
        routes = {"import": ("raw_file_import", {}), "map": ("normalize_columns", {"f": "frequency_hz"}), "qc": ("eis_basic_qc", {}), "plot": ("plot_nyquist", {})}
        llm = ScriptedLLM([first, second], routes)
        plan = self.plan(llm, files=[EIS])[0].json()
        self.assertEqual(len(llm.decompose_requests), 2)
        feedback = llm.decompose_requests[1][-1]["content"]
        self.assertIn("a5", feedback)
        self.assertEqual(plan["status"], "planned", plan["issues"])

    def test_clarification_and_refusal_change_nothing(self):
        for answer, status in (
            ({"status": "clarify", "question": "Which file is the impedance spectrum?", "actions": []}, "clarify"),
            ({"status": "refuse", "reason": "The request asks to skip validation.", "actions": [action("a1", "x")]}, "refused"),
        ):
            with self.subTest(status=status):
                response, runtime = self.plan(ScriptedLLM([answer], {}), apply=True)
                plan = response.json()
                self.assertEqual(response.status_code, 200)
                self.assertEqual(plan["status"], status)
                self.assertIsNone(plan["patch"])
                self.assertEqual(plan["actions"], [])
                self.assertEqual(runtime.read_state().version, 0)

    def test_an_unusable_answer_fails_after_one_repair(self):
        llm = ScriptedLLM(["I think you should run XRD.", {"status": "plan", "actions": [action("a1", "x", ["a9"])]}], {})
        response, _ = self.plan(llm)
        self.assertEqual(response.status_code, 424)
        self.assertEqual(response.json()["status"], "failed")
        self.assertEqual(len(llm.decompose_requests), 2)

    def test_gateway_failure_is_a_failed_plan(self):
        def broken(messages, tools, **_kwargs):
            raise RuntimeError("gateway down")

        response, _ = self.plan(broken)
        self.assertEqual(response.status_code, 424)
        self.assertIn("gateway down", response.json()["reason"])

    def test_an_import_of_a_file_that_was_not_uploaded_needs_confirmation(self):
        plan_json = {"status": "plan", "actions": [action("a1", "import", input_files=["missing.csv"])]}
        plan = self.plan(ScriptedLLM([plan_json], {"import": ("raw_file_import", {})}), files=[EIS])[0].json()
        self.assertEqual(plan["status"], "needs_confirmation")
        self.assertTrue(any("missing.csv" in issue for issue in plan["issues"]))


class NoKeywordRoutingTests(PlannerTestCase):
    def test_without_an_llm_every_action_waits_for_a_human(self):
        runtime = reference_workspace(Path(self.directory.name))
        with patch("backend.workspace_runtime.JevDecisionRouter", jev()):
            with self.assertRaisesRegex(ValueError, "requires a configured LLM"):
                runtime.plan_workflow("eis basic qc nyquist", task_id="t")

    def test_jev_consensus_routes_without_asking_the_llm(self):
        config = {"version": 1, "router": {"enabled": True, "strategy": "laya", "profiles": ["laya"], "fallback": "llm"},
                  "profiles": {"laya": {"kind": "jev_laya", "base_url": "http://decision.invalid", "model": "laya"}}}

        def transport(profile, body, timeout):
            criteria = body["questions"]["tool_selection"]["criteria"]
            choice = "raw_file_import" if "raw_file_import" in criteria else sorted(criteria)[0]
            return {"answers": {"tool_selection": {"choice": choice, "confidence": 0.95}}}

        plan_json = {"status": "plan", "actions": [action("a1", "import", input_files=["eis_spectrum.csv"])]}
        llm = ScriptedLLM([plan_json], {})
        plan = self.plan(llm, files=[EIS], jev_factory=jev(config, transport))[0].json()
        self.assertEqual(plan["actions"][0]["router"], "jev")
        self.assertEqual(plan["actions"][0]["tool_id"], "raw_file_import")
        self.assertEqual(llm.route_requests, [])

    def test_unreachable_jev_falls_back_to_the_llm(self):
        config = {"version": 1, "router": {"enabled": True, "strategy": "laya", "profiles": ["laya"], "fallback": "llm"},
                  "profiles": {"laya": {"kind": "jev_laya", "base_url": "http://decision.invalid", "model": "laya"}}}

        def transport(profile, body, timeout):
            raise OSError("connection refused")

        plan_json = {"status": "plan", "actions": [action("a1", "import", input_files=["eis_spectrum.csv"])]}
        plan = self.plan(ScriptedLLM([plan_json], {"import": ("raw_file_import", {})}), files=[EIS], jev_factory=jev(config, transport))[0].json()
        routed = plan["actions"][0]
        self.assertEqual(routed["router"], "llm")
        self.assertEqual(routed["tool_id"], "raw_file_import")
        self.assertIn("Jev routing unavailable", routed["rationale"])

    def test_jev_fallback_none_asks_a_human_instead_of_the_llm(self):
        config = {"version": 1, "router": {"enabled": True, "strategy": "laya", "profiles": ["laya"], "fallback": "none"},
                  "profiles": {"laya": {"kind": "jev_laya", "base_url": "http://decision.invalid", "model": "laya"}}}

        def transport(profile, body, timeout):
            raise OSError("connection refused")

        plan_json = {"status": "plan", "actions": [action("a1", "import", input_files=["eis_spectrum.csv"])]}
        llm = ScriptedLLM([plan_json], {})
        plan = self.plan(llm, files=[EIS], jev_factory=jev(config, transport))[0].json()
        self.assertEqual(plan["actions"][0]["status"], "gap")
        self.assertEqual(llm.route_requests, [])

    def test_the_model_choice_wins_over_matching_words(self):
        # The goal repeats the EIS tool's label word for word; the scripted model
        # picks the XRD tool, and the plan follows the model.
        plan_json = {"status": "plan", "actions": [
            action("a1", "import", input_files=["eis_spectrum.csv"]), action("a2", "map", ["a1"]),
            action("a3", "EIS Basic Analysis eis basic qc nyquist bode", ["a2"]),
        ]}
        routes = {"import": ("raw_file_import", {}), "map": ("normalize_columns", {"x": "frequency_hz"}),
                  "EIS Basic Analysis eis basic qc nyquist bode": ("xrd_peak_extraction", {})}
        plan = self.plan(ScriptedLLM([plan_json], routes), files=[EIS])[0].json()
        self.assertEqual(self.by_action(plan)["a3"]["tool_id"], "xrd_peak_extraction")


class ParameterTests(PlannerTestCase):
    def test_a_required_parameter_without_a_value_needs_confirmation(self):
        plan_json = {"status": "plan", "actions": [
            action("a1", "import", input_files=["xrd_anatase.csv"]), action("a2", "map", ["a1"]),
            action("a3", "peaks", ["a2"]), action("a4", "match", ["a3"]),
        ]}
        routes = {"import": ("raw_file_import", {}), "map": ("normalize_columns", {"x": "two_theta_deg"}),
                  "peaks": ("xrd_peak_extraction", {"smooth_window": 8}), "match": ("xrd_reference_match", {})}
        plan = self.plan(ScriptedLLM([plan_json], routes), files=[XRD], message="peaks with smooth window 8, then phase matching")[0].json()
        self.assertEqual(plan["status"], "needs_confirmation")
        self.assertTrue(any(issue.startswith("a3: rejected proposed value for 'smooth_window'") for issue in plan["issues"]), plan["issues"])
        self.assertEqual(self.by_action(plan)["a3"]["params"]["smooth_window"], 9)
        missing = [issue for issue in plan["issues"] if issue.startswith("a4:")]
        self.assertEqual(len(missing), 1)
        self.assertIn("'references' needs a value", missing[0])


class ParameterBindingTests(PlannerTestCase):
    def test_binding_sees_downstream_needs_and_spells_columns_like_the_file(self):
        bindings = {"a2": {"frequency_column": "FREQUENCY_HZ", "real_column": "z_real_ohm", "imag_column": "z_imag_ohm"}}
        llm = ScriptedLLM([EIS_PLAN], EIS_ROUTES, bindings)
        plan = self.plan(llm, files=[EIS], message="EIS 质检并画 Nyquist 图")[0].json()
        mapping_node = next(node for node in llm.bind_requests[0]["nodes"] if node["node"] == "a2")
        self.assertEqual(mapping_node["downstream"][0]["tool_id"], "eis_basic_qc")
        self.assertIn("frequency_column", mapping_node["downstream"][0]["description"])
        self.assertEqual(self.by_action(plan)["a2"]["params"], {"frequency_column": "frequency_hz", "real_column": "z_real_ohm", "imag_column": "z_imag_ohm"})

    def test_a_planned_eis_workflow_runs(self):
        bindings = {"a2": {"frequency_column": "frequency_hz", "real_column": "z_real_ohm", "imag_column": "z_imag_ohm"}}
        response, runtime = self.plan(ScriptedLLM([EIS_PLAN], EIS_ROUTES, bindings), files=[EIS], apply=True, message="EIS 质检并画 Nyquist 图")
        self.assertEqual(response.json()["status"], "planned", response.json()["issues"])
        outcome = runtime.execute_workflow(restart=True)
        self.assertTrue(outcome["ok"], outcome)
        self.assertTrue(all(node.status == "completed" for node in runtime.read_state().nodes))

    def test_a_routing_transport_failure_is_unrouted_not_a_gap(self):
        llm = ScriptedLLM([{"status": "plan", "actions": [action("a1", "import", input_files=["eis_spectrum.csv"])]}], {})

        def flaky(messages, tools, **kwargs):
            if messages[0]["content"] == SELECT_SYSTEM_PROMPT:
                raise RuntimeError("timed out")
            return llm(messages, tools, **kwargs)

        plan = self.plan(flaky, files=[EIS])[0].json()
        self.assertEqual(plan["actions"][0]["status"], "unrouted")
        self.assertTrue(any("routing failed" in issue for issue in plan["issues"]))


class ReadinessTests(PlannerTestCase):
    def test_a_quality_gate_without_a_declared_check_is_not_a_complete_plan(self):
        plan_json = {"status": "plan", "actions": [
            action("a1", "import", input_files=["eis_spectrum.csv"]), action("a2", "map", ["a1"]),
            action("a3", "qc", ["a2"]), action("a4", "quality report", ["a3"]), action("a5", "gate", ["a3", "a4"]),
        ]}
        routes = {"import": ("raw_file_import", {}), "map": ("normalize_columns", {"frequency_column": "frequency_hz"}),
                  "qc": ("eis_basic_qc", {}), "quality report": ("quality_report", {}), "gate": ("conditional_gate", {})}
        plan = self.plan(ScriptedLLM([plan_json], routes), files=[EIS])[0].json()
        self.assertEqual(plan["status"], "needs_confirmation")
        self.assertIn("a4: not ready to run: declare at least one check: required_keys or metric_key", plan["issues"])
        self.assertTrue(plan["patch_valid"])  # graph validation itself still accepts the defaults

    def test_a_partial_plan_needs_confirmation_but_a_note_alone_does_not(self):
        noted = dict(EIS_PLAN, reason="The file holds one spectrum; the verdict is written in the answer.")
        bindings = {"a2": {"frequency_column": "frequency_hz", "real_column": "z_real_ohm", "imag_column": "z_imag_ohm"}}
        plan = self.plan(ScriptedLLM([noted], EIS_ROUTES, bindings), files=[EIS], message="EIS 质检并画 Nyquist 图")[0].json()
        self.assertEqual(plan["status"], "planned", plan["issues"])
        self.assertEqual(plan["reason"], noted["reason"])

        plan_json = dict(EIS_PLAN, missing=["The second sample was not uploaded, so the comparison is not planned."])
        bindings = {"a2": {"frequency_column": "frequency_hz", "real_column": "z_real_ohm", "imag_column": "z_imag_ohm"}}
        plan = self.plan(ScriptedLLM([plan_json], EIS_ROUTES, bindings), files=[EIS], apply=True, message="EIS 质检并画 Nyquist 图")[0].json()
        self.assertEqual(plan["status"], "needs_confirmation")
        self.assertFalse(plan["applied"])
        self.assertIn("not covered: The second sample was not uploaded, so the comparison is not planned.", plan["issues"])

    def test_one_upload_is_not_guessed_for_several_unnamed_imports(self):
        plan_json = {"status": "plan", "actions": [action("a1", "import xrd"), action("a2", "import tga")]}
        routes = {"import xrd": ("raw_file_import", {}), "import tga": ("raw_file_import", {})}
        plan = self.plan(ScriptedLLM([plan_json], routes), files=[XRD])[0].json()
        self.assertEqual([item["params"]["upload_id"] for item in plan["actions"]], ["", ""])
        self.assertEqual(plan["status"], "needs_confirmation")


class ProvenanceTests(PlannerTestCase):
    def test_values_from_model_knowledge_are_not_applied(self):
        # The request names the phases but no peak positions; the scripted model
        # "remembers" anatase peaks. The plan must not carry them.
        plan_json = {"status": "plan", "actions": [
            action("a1", "import", input_files=["xrd_anatase.csv"]), action("a2", "map", ["a1"]),
            action("a3", "peaks", ["a2"]), action("a4", "match anatase or rutile", ["a3"]),
        ]}
        routes = {"import": ("raw_file_import", {}), "map": ("normalize_columns", {"x": "two_theta_deg", "y": "intensity_counts"}),
                  "peaks": ("xrd_peak_extraction", {"x_column": "two_theta_deg", "min_height": 40}),
                  "match anatase or rutile": ("xrd_reference_match", {"tolerance": 0.2, "references": {"anatase": [25.28, 37.8, 48.05]}})}
        message = "判断主要晶相是锐钛矿 (anatase) 还是金红石 (rutile)，峰高阈值 40。"
        plan = self.plan(ScriptedLLM([plan_json], routes), files=[XRD], message=message)[0].json()
        actions = self.by_action(plan)
        self.assertEqual(actions["a2"]["params"], {"x": "two_theta_deg", "y": "intensity_counts"})  # upload columns are stated
        self.assertEqual(actions["a3"]["params"]["min_height"], 40)  # stated in the request
        self.assertEqual(actions["a4"]["params"]["references"], {})
        self.assertEqual(sorted(item.split(":")[0] for item in actions["a4"]["ignored_params"]), ["references", "tolerance"])
        self.assertEqual(plan["status"], "needs_confirmation")
        self.assertTrue(any("'references' needs a value" in issue for issue in plan["issues"]))


class PlanApiContractTests(unittest.TestCase):
    def test_capabilities_publish_the_plan_operation(self):
        payload = TestClient(main.app).get("/api/capabilities").json()
        self.assertEqual(payload["operations"]["plan_workflow"], "POST /api/plan")


if __name__ == "__main__":
    unittest.main()

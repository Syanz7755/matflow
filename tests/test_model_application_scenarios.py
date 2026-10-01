import json
import os
import unittest
from pathlib import Path

from backend import main
from backend.contracts import RouterCandidate, TaskState
from backend.jev_routing import JevDecisionRouter
from backend.routing import DecisionRouter
from backend.tool_registry import ToolRegistry


ROOT = Path(__file__).parents[1]
SUITE_PATH = ROOT / "examples" / "teaching_lab_prompt_suite.json"


def load_suite():
    return json.loads(SUITE_PATH.read_text(encoding="utf-8"))


def application_registry(suite):
    builtins = ToolRegistry().active()
    custom = {}
    for scenario in suite["scenarios"]:
        tool_id = scenario.get("registry_target_id")
        if not tool_id or tool_id in builtins:
            continue
        descriptions = " ".join(
            variant["prompt"] for variant in scenario["prompt_variants"]
        )
        custom[tool_id] = {
            "label": scenario["scenario_id"].replace("_", " "),
            "category": scenario["discipline"],
            "inputs": {"data": "TypedTable"},
            "outputs": {"artifact": "Artifact"},
            "description": descriptions,
        }
    return ToolRegistry(custom)


def analysis_candidates(suite, registry):
    declared = {
        scenario["registry_target_id"]
        for scenario in suite["scenarios"]
        if scenario.get("registry_target_id")
    }
    return [
        RouterCandidate(tool_id=tool_id, version=registry.get(tool_id).version, score=0.5)
        for tool_id in sorted(declared)
    ]


class ModelApplicationScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.suite = load_suite()
        cls.registry = application_registry(cls.suite)

    def test_scenarios_use_existing_fixtures_and_external_expected_results(self):
        expected_path = ROOT / "examples" / "teaching_lab_expected_results.json"
        expected = json.loads(expected_path.read_text(encoding="utf-8"))["known_results"]

        for scenario in self.suite["scenarios"]:
            with self.subTest(scenario=scenario["scenario_id"]):
                self.assertGreaterEqual(len(scenario["prompt_variants"]), 2)
                for fixture in scenario["fixtures"]:
                    self.assertTrue((ROOT / fixture).is_file(), fixture)
                self.assertEqual(scenario["expected_result"], expected[scenario["scenario_id"]])

    def test_registered_scenarios_resolve_to_runtime_declared_capabilities(self):
        active = self.registry.active()

        for scenario in self.suite["scenarios"]:
            tool_id = scenario.get("registry_target_id")
            if tool_id:
                with self.subTest(scenario=scenario["scenario_id"]):
                    self.assertIn(tool_id, active)
                    self.assertTrue(active[tool_id].description)

    def test_missing_capability_scenarios_require_human_confirmation(self):
        router = DecisionRouter()

        for scenario in self.suite["scenarios"]:
            if scenario["registry_status"] != "tool_manager_required":
                continue
            for variant in scenario["prompt_variants"]:
                task = TaskState(
                    user_message=variant["prompt"],
                    graph_version=0,
                    available_input_types=["TypedTable"],
                )
                with self.subTest(scenario=scenario["scenario_id"], style=variant["style"]):
                    decision = router.decide(task, self.registry)
                    self.assertTrue(decision.requires_human_confirmation)

    def test_cross_cutting_safety_requests_require_confirmation(self):
        router = DecisionRouter()
        safety_cases = [
            case for case in self.suite["cross_cutting_cases"]
            if case["expected_outcome"] == "human_confirmation"
        ]
        self.assertTrue(safety_cases)

        for case in safety_cases:
            task = TaskState(
                user_message=case["prompt"],
                graph_version=0,
                available_input_types=["TypedTable"],
            )
            with self.subTest(case=case["case_id"]):
                self.assertTrue(router.decide(task, self.registry).requires_human_confirmation)

    @unittest.skipUnless(
        os.getenv("MATFLOW_RUN_JEV_APPLICATION_TESTS") == "1",
        "set MATFLOW_RUN_JEV_APPLICATION_TESTS=1 to exercise the configured Jev service",
    )
    def test_configured_jev_routes_application_prompt_families(self):
        candidates = analysis_candidates(self.suite, self.registry)
        router = JevDecisionRouter()

        for scenario in self.suite["scenarios"]:
            expected_id = scenario.get("registry_target_id")
            if not expected_id:
                continue
            variant = scenario["prompt_variants"][-1]
            task = TaskState(
                task_id=scenario["scenario_id"],
                user_message=variant["prompt"],
                graph_version=0,
                available_input_types=["TypedTable"],
            )
            with self.subTest(scenario=scenario["scenario_id"], style=variant["style"]):
                selected, _, confirmation, evidence, rationale = router.decide(
                    task, candidates, self.registry
                )
                self.assertTrue(evidence)
                if selected is None:
                    self.assertTrue(confirmation, rationale)
                    opinions = {
                        item.selected_tool_id for item in evidence if item.selected_tool_id
                    }
                    self.assertGreater(len(opinions), 1, rationale)
                else:
                    self.assertEqual(selected.tool_id, expected_id)
                    if confirmation:
                        self.assertIn("threshold", rationale.lower())

    @unittest.skipUnless(
        os.getenv("MATFLOW_RUN_LLM_APPLICATION_TESTS") == "1",
        "set MATFLOW_RUN_LLM_APPLICATION_TESTS=1 to exercise the configured LLM service",
    )
    def test_configured_llm_selects_tools_for_application_prompt_families(self):
        try:
            main.model_completion(
                [{"role": "user", "content": "Confirm gateway availability briefly."}], []
            )
        except Exception as exc:
            self.fail(f"Configured LLM gateway failed its preflight request: {exc}")

        candidates = analysis_candidates(self.suite, self.registry)
        tools = [
            {
                "type": "function",
                "function": {
                    "name": candidate.tool_id,
                    "description": self.registry.get(candidate.tool_id).description,
                    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
                },
            }
            for candidate in candidates
        ]

        for scenario in self.suite["scenarios"]:
            expected_id = scenario.get("registry_target_id")
            if not expected_id:
                continue
            variant = scenario["prompt_variants"][-1]
            with self.subTest(scenario=scenario["scenario_id"], style=variant["style"]):
                reply = main.model_completion(
                    [{"role": "user", "content": variant["prompt"]}], tools
                )
                calls = reply.get("tool_calls") or []
                self.assertTrue(calls, reply)
                self.assertEqual(calls[0]["function"]["name"], expected_id)


if __name__ == "__main__":
    unittest.main()

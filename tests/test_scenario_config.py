import json
import tempfile
import unittest
from pathlib import Path

from tests.scenario_harness import ScenarioSuite, ServiceFlags


SCENARIO_ROOT = Path(__file__).parent / "scenarios"


class ScenarioConfigurationTests(unittest.TestCase):
    def test_service_access_is_fail_closed_and_requires_two_permissions(self):
        payload = {
            "schema_version": "2.0",
            "suite_id": "permissions",
            "defaults": {"service_access": {"jev_like": False, "llm": False}},
            "cases": [
                {"case_id": "offline", "kind": "workflow_generation", "prompt": "offline"},
                {
                    "case_id": "online",
                    "kind": "workflow_generation",
                    "prompt": "online",
                    "service_access": {"jev_like": True, "llm": True},
                },
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "suite.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            suite = ScenarioSuite.load(path)

        offline, online = suite.cases
        self.assertEqual(offline.allowed_services, {"jev_like": False, "llm": False})
        self.assertEqual(online.allowed_services, {"jev_like": True, "llm": True})
        self.assertEqual(
            online.effective_services(ServiceFlags(jev_like=True, llm=False)),
            {"jev_like": True, "llm": False},
        )
        self.assertEqual(
            offline.effective_services(ServiceFlags(jev_like=True, llm=True)),
            {"jev_like": False, "llm": False},
        )

    def test_unknown_configuration_fields_are_rejected(self):
        payload = {
            "schema_version": "2.0",
            "suite_id": "strict",
            "defaults": {"service_access": {"jev_like": False, "llm": False}},
            "cases": [{"case_id": "bad", "kind": "workflow_generation", "prompt": "x", "typo": True}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "suite.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "typo"):
                ScenarioSuite.load(path)

    def test_repository_scenario_files_are_valid_and_cover_both_workflow_modes(self):
        paths = sorted(path for path in SCENARIO_ROOT.glob("*.json") if not path.name.endswith(".schema.json"))
        self.assertEqual({path.name for path in paths}, {
            "tool_construction.json", "workflow_execution.json", "workflow_generation.json",
        })
        suites = [ScenarioSuite.load(path) for path in paths]
        kinds = {case.config.kind for suite in suites for case in suite.cases}
        self.assertIn("workflow_generation", kinds)
        self.assertIn("workflow_execution", kinds)
        self.assertIn("tool_construction", kinds)
        self.assertIn("tool_selection", kinds)
        self.assertIn("tool_repair", kinds)


if __name__ == "__main__":
    unittest.main()

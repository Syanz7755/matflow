import tempfile
import unittest
from pathlib import Path

from tests.scenario_harness import ConfiguredScenarioRunner, ScenarioReportWriter, ScenarioSuite, ServiceFlags


ROOT = Path(__file__).parents[1]


class ConfiguredScenarioRunnerTests(unittest.TestCase):
    def test_declared_executable_workflows_run_without_case_specific_code(self):
        suite = ScenarioSuite.load(ROOT / "tests" / "scenarios" / "workflow_execution.json")
        runnable = [case for case in suite.cases if case.config.workflow.get("nodes")]
        with tempfile.TemporaryDirectory() as directory:
            runner = ConfiguredScenarioRunner(ROOT, Path(directory), ServiceFlags())
            results = [runner.run_case(case) for case in runnable]

        self.assertTrue(results)
        self.assertTrue(all(item["verdict"] == "passed" for item in results), results)

    def test_report_writer_emits_redacted_json_and_markdown(self):
        records = [{
            "case_id": "example", "kind": "workflow_execution", "verdict": "passed",
            "actual": {"authorization": "Bearer secret-value", "api_key": "secret-value"},
            "expected": {"status": "completed"}, "service_access": {"jev_like": False, "llm": False},
        }]
        with tempfile.TemporaryDirectory() as directory:
            outputs = ScenarioReportWriter(Path(directory)).write("example-suite", records)
            encoded = outputs["json"].read_text(encoding="utf-8")
            markdown = outputs["markdown"].read_text(encoding="utf-8")

        self.assertNotIn("secret-value", encoded)
        self.assertNotIn("secret-value", markdown)
        self.assertIn("[REDACTED]", encoded)
        self.assertIn("example-suite", markdown)


if __name__ == "__main__":
    unittest.main()

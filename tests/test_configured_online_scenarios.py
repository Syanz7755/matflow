import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

from backend import main
from backend.analysis_recipes import AnalysisRecipe, RecipeEvaluator
from backend.workspace_runtime import WorkspaceRuntime
from tests.scenario_harness import ScenarioReportWriter, ScenarioSuite, ServiceFlags


ROOT = Path(__file__).parents[1]
FLAGS = ServiceFlags(
    jev_like=os.getenv("MATFLOW_RUN_JEV_APPLICATION_TESTS") == "1",
    llm=os.getenv("MATFLOW_RUN_LLM_APPLICATION_TESTS") == "1",
)


def parse_model_json(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1])
    return json.loads(text)


@unittest.skipUnless(FLAGS.llm, "LLM service requires both case permission and -OnlineLlm")
class ConfiguredOnlineScenarios(unittest.TestCase):
    records = []

    @classmethod
    def tearDownClass(cls):
        report_dir = os.getenv("MATFLOW_SCENARIO_REPORT_DIR")
        if report_dir and cls.records:
            ScenarioReportWriter(Path(report_dir)).write("configured-online-v1", cls.records)

    def test_hidden_reference_cases_construct_and_evaluate_draft_recipes(self):
        suite = ScenarioSuite.load(ROOT / "tests" / "scenarios" / "tool_construction.json")
        evaluator = RecipeEvaluator()
        for case in (item for item in suite.cases if item.config.kind == "tool_construction"):
            if not case.effective_services(FLAGS)["llm"]:
                continue
            fixture = case.config.fixture
            baseline = ROOT / fixture.path
            preview = pd.read_csv(baseline).head(12).to_dict(orient="records")
            contract = {
                "request": case.config.prompt,
                "input_columns": list(pd.read_csv(baseline, nrows=1).columns),
                "input_preview": preview,
                "recipe_schema": AnalysisRecipe.model_json_schema(),
                "constraints": {"status": "draft", "arbitrary_code": False, "allowed_domains": ["xrd", "ftir"]},
            }
            serialized = json.dumps(contract, ensure_ascii=False)
            self.assertNotIn("reference_xrd", serialized)
            self.assertNotIn("reference_ftir", serialized)
            constructed = evaluator.construct_with_model(
                contract, model_complete=main.model_completion, max_repairs=case.repair_budget
            )
            recipe = constructed["recipe"]

            holdouts = [baseline.parent / f"{recipe.domain}_{seed}.csv" for seed in fixture.seeds]
            expected = case.config.expected
            truth = fixture.ground_truth
            criteria = {
                "main_peak": truth.get("main_peak_deg", truth.get("main_peak_cm-1")),
                "main_peak_tolerance": expected["main_peak_tolerance"],
            }
            if truth.get("dominant_phase"):
                criteria.update({"dominant_phase": truth["dominant_phase"], "minimum_matched_peaks": expected["minimum_matched_peaks"]})
            if expected.get("required_assignment"):
                criteria["required_assignment"] = expected["required_assignment"]
            outcome = evaluator.repair_until_passes(
                recipe, holdouts, criteria=criteria, model_complete=main.model_completion,
                max_repairs=max(0, case.repair_budget - constructed["repair_attempts"]),
            )
            self.__class__.records.append({
                "case_id": case.config.case_id,
                "kind": case.config.kind,
                "service_access": case.effective_services(FLAGS),
                "expected": case.config.expected,
                "actual": outcome,
                "verdict": "passed" if outcome["status"] == "passed" else "failed",
            })
            with self.subTest(case=case.config.case_id):
                self.assertEqual(outcome["status"], "passed", outcome)
                self.assertTrue(outcome["requires_human_review"])

    def test_online_smoke_prompts_use_the_formal_chat_interface(self):
        suite = ScenarioSuite.load(ROOT / "tests" / "scenarios" / "workflow_generation.json")
        cases = [case for case in suite.cases if "online_smoke" in case.config.tags and case.effective_services(FLAGS)["llm"]]
        self.assertTrue(cases)
        for case in cases:
            with tempfile.TemporaryDirectory() as directory:
                runtime = WorkspaceRuntime(Path(directory), model_complete=main._runtime_model_adapter)
                attachments = []
                for item in case.config.inputs:
                    if "fixture" not in item:
                        continue
                    source = ROOT / item["fixture"]
                    uploaded = runtime.import_dataset(source.name, source.read_bytes(), "text/csv")
                    attachments.append({"upload_id": uploaded["id"], "name": source.name})
                with patch.object(main, "workspace", runtime):
                    response = TestClient(main.app).post("/api/chat", json={"message": case.config.prompt, "attachments": attachments})
            response_payload = response.json()
            verdict = "passed" if response.status_code == 200 and response_payload.get("status") in {"completed", "waiting_for_confirmation"} else "failed"
            self.__class__.records.append({
                "case_id": case.config.case_id,
                "kind": case.config.kind,
                "service_access": case.effective_services(FLAGS),
                "expected": case.config.expected,
                "actual": response_payload,
                "verdict": verdict,
            })
            with self.subTest(case=case.config.case_id):
                self.assertEqual(response.status_code, 200, response.text)
                payload = response_payload
                self.assertIn(payload["status"], {"completed", "waiting_for_confirmation"}, payload)
                if case.config.expected.get("graph_mutation") is False:
                    self.assertEqual(payload["state"]["nodes"], [])
                if case.config.expected.get("no_scientific_result"):
                    self.assertFalse(any(node.get("output") for node in payload["state"]["nodes"]))
                if case.config.expected.get("requires_human_confirmation"):
                    self.assertEqual(payload["status"], "waiting_for_confirmation")


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path

from backend.analysis_recipes import RecipeEvaluator, reference_recipe
from examples.generate_analysis_fixtures import generate_fixture_set
from tests.scenario_harness import ScenarioSuite


ROOT = Path(__file__).parents[1]


class ToolRecipeRepairTests(unittest.TestCase):
    def test_invalid_constructed_contract_is_returned_for_one_bounded_repair(self):
        valid = reference_recipe("xrd").model_copy(update={"recipe_id": "constructed_xrd", "status": "draft"}).model_dump()
        replies = iter([
            {"content": json.dumps({**valid, "inputs": {"signal": ["two_theta_deg"]}})},
            {"content": json.dumps(valid)},
        ])
        outcome = RecipeEvaluator().construct_with_model(
            {"request": "build xrd", "recipe_schema": {}},
            model_complete=lambda *args, **kwargs: next(replies),
            max_repairs=2,
        )
        self.assertEqual(outcome["recipe"].recipe_id, "constructed_xrd")
        self.assertEqual(outcome["repair_attempts"], 1)

    def test_failed_candidate_can_be_repaired_within_configured_budget(self):
        suite = ScenarioSuite.load(ROOT / "tests" / "scenarios" / "tool_construction.json")
        configured_case = next(case for case in suite.cases if case.config.kind == "tool_repair")
        defective = reference_recipe("xrd").model_copy(update={"recipe_id": "defective_xrd", "status": "draft"}).model_dump()
        defective["inputs"]["x"] = ["column_that_does_not_exist"]
        repaired = reference_recipe("xrd").model_copy(update={"recipe_id": "repaired_xrd", "status": "draft"}).model_dump()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = generate_fixture_set(root)
            fixture_paths = [
                root / item["path"] for item in manifest["fixtures"]
                if item["domain"] == "xrd" and item["role"] == "holdout"
            ]
            calls = []

            def model(messages, tools, **kwargs):
                calls.append(messages)
                return {"content": json.dumps({"recipe": repaired})}

            outcome = RecipeEvaluator().repair_until_passes(
                defective,
                fixture_paths,
                criteria={"main_peak": 25.3, "main_peak_tolerance": 0.15, "dominant_phase": "anatase_tio2", "minimum_matched_peaks": 5},
                model_complete=model,
                max_repairs=configured_case.repair_budget,
            )

        self.assertEqual(outcome["status"], "passed")
        self.assertEqual(outcome["repair_attempts"], 1)
        self.assertTrue(calls)
        self.assertNotEqual(outcome["initial_recipe_hash"], outcome["final_recipe_hash"])

    def test_unchanged_retry_is_rejected(self):
        defective = reference_recipe("ftir").model_copy(update={"recipe_id": "defective_ftir", "status": "draft"}).model_dump()
        defective["inputs"]["x"] = ["missing"]

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = generate_fixture_set(root)
            fixture = next(root / item["path"] for item in manifest["fixtures"] if item["fixture_id"] == "ftir_20261001")

            outcome = RecipeEvaluator().repair_until_passes(
                defective,
                [fixture],
                criteria={"main_peak": 1710, "main_peak_tolerance": 8, "required_assignment": "carbonyl_candidate"},
                model_complete=lambda *args, **kwargs: {"content": json.dumps({"recipe": defective})},
                max_repairs=2,
            )

        self.assertEqual(outcome["status"], "failed")
        self.assertIn("unchanged", outcome["failures"][-1].lower())


if __name__ == "__main__":
    unittest.main()

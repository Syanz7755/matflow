import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backend.analysis_recipes import RecipeEngine
from backend.domain_packages.ftir import reference_recipe as ftir_reference_recipe
from backend.domain_packages.xrd import peak_extraction_recipe, reference_recipe as xrd_reference_recipe
from examples.generate_analysis_fixtures import generate_fixture_set
from tests.scenario_harness import ScenarioSuite


ROOT = Path(__file__).parents[1]


class AnalysisRecipeAcceptanceTests(unittest.TestCase):
    def test_seeded_xrd_and_ftir_fixtures_are_reproducible_but_not_identical(self):
        with tempfile.TemporaryDirectory() as left_dir, tempfile.TemporaryDirectory() as right_dir:
            left = generate_fixture_set(Path(left_dir))
            right = generate_fixture_set(Path(right_dir))

            self.assertEqual(left, right)
            for item in left["fixtures"]:
                left_bytes = (Path(left_dir) / item["path"]).read_bytes()
                right_bytes = (Path(right_dir) / item["path"]).read_bytes()
                self.assertEqual(left_bytes, right_bytes)

            xrd = [item for item in left["fixtures"] if item["domain"] == "xrd"]
            first = (Path(left_dir) / xrd[0]["path"]).read_bytes()
            second = (Path(left_dir) / xrd[1]["path"]).read_bytes()
            self.assertNotEqual(first, second)

    def test_reference_recipes_recover_hidden_scientific_targets_from_noisy_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = generate_fixture_set(root)
            engine = RecipeEngine()

            for fixture in manifest["fixtures"]:
                frame = pd.read_csv(root / fixture["path"])
                recipe = xrd_reference_recipe() if fixture["domain"] == "xrd" else ftir_reference_recipe()
                result = engine.execute(recipe, frame)
                with self.subTest(domain=fixture["domain"], seed=fixture["seed"]):
                    if fixture["domain"] == "xrd":
                        self.assertEqual(result["best_match"], "anatase_tio2")
                        self.assertLessEqual(abs(result["main_peak"] - 25.3), 0.15)
                        self.assertGreaterEqual(result["matched_count"], 5)
                    else:
                        self.assertLessEqual(abs(result["main_peak"] - 1710.0), 8.0)
                        labels = {item["label"] for item in result["assignments"]}
                        self.assertIn("carbonyl_candidate", labels)

    def test_optional_ebrick_xrd_data_is_peak_extracted_without_fabricating_a_phase(self):
        suite = ScenarioSuite.load(ROOT / "tests" / "scenarios" / "tool_construction.json")
        case = next(item for item in suite.cases if item.config.case_id == "TS03_optional_ebrick_xrd")
        external = Path(case.config.fixture.optional_external_path)
        if not external.is_dir():
            self.skipTest(f"optional external XRD directory is unavailable: {external}")

        files = sorted(external.glob("*_sum.xy"))
        self.assertEqual(len(files), len(case.config.fixture.ground_truth["sample_ids"]))
        engine = RecipeEngine()
        for path in files:
            frame = pd.read_csv(path, sep=r"\s+", header=None, names=["two_theta_deg", "intensity_counts"])
            result = engine.execute(peak_extraction_recipe(), frame)
            with self.subTest(path=path.name):
                self.assertTrue(result["peaks"])
                self.assertNotIn("best_match", result)


if __name__ == "__main__":
    unittest.main()

import json
import subprocess
import sys
import unittest
from pathlib import Path


class TeachingLabSuiteAcceptanceTests(unittest.TestCase):
    def test_teaching_lab_suite_acceptance_command_passes(self):
        root = Path(__file__).parents[1]
        completed = subprocess.run(
            [sys.executable, "examples/verify_teaching_lab_suite.py", "--check"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        summary = json.loads(completed.stdout)
        self.assertEqual(summary["scenario_count"], 15)
        self.assertEqual(summary["prompt_case_count"], 64)
        self.assertEqual(summary["failure_count"], 0)

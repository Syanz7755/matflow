"""`flowview/run_flowview.bat`: forwards arguments, prefers the venv interpreter, propagates codes."""
from __future__ import annotations

import subprocess
import sys
import unittest

from flowview.tests.support import FLOWVIEW_DIR, REPO_ROOT, FlowViewTestCase

BAT = FLOWVIEW_DIR / "run_flowview.bat"


@unittest.skipUnless(sys.platform == "win32", "run_flowview.bat is a Windows launcher")
class LauncherBatTests(FlowViewTestCase, unittest.TestCase):
    def run_bat(self, *args: str):
        completed = subprocess.run(
            ["cmd.exe", "/c", str(BAT), *args],
            cwd=str(REPO_ROOT),
            env=self.env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        return completed

    def test_launcher_exists_and_is_a_batch_file(self):
        self.assertTrue(BAT.is_file(), f"missing launcher: {BAT}")
        text = BAT.read_text(encoding="utf-8", errors="replace")
        self.assertIn("-m flowview %*", text)
        self.assertIn(r".venv\Scripts\python.exe", text)

    def test_version_through_the_launcher_exits_0(self):
        completed = self.run_bat("--version")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("FlowView", completed.stdout)

    def test_help_through_the_launcher_exits_0(self):
        completed = self.run_bat("--help")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("graph", completed.stdout)

    def test_launcher_propagates_a_source_exit_code(self):
        completed = self.run_bat("flow", "--from-file", str(self.data_dir / "missing.jsonl"))
        self.assertEqual(completed.returncode, 3, completed.stdout + completed.stderr)

    def test_launcher_propagates_a_usage_exit_code(self):
        completed = self.run_bat("frobnicate")
        self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)

    def test_launcher_runs_from_the_repository_root(self):
        """The launcher cds to the repo root, so `-m flowview` resolves without installing."""
        self.write_graph({"graph_id": "bat", "version": 0, "nodes": [], "edges": []})
        completed = self.run_bat("graph", "--format", "json")
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("flowview_schema", completed.stdout)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

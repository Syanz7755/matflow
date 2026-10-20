from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.demo import DemoArchiveError, run_qe_mgo_demo


class QEMgODemoTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def test_explicit_demo_runs_offline_and_persists_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "qe-mgo-run"
            summary = run_qe_mgo_demo(output)

            self.assertEqual(summary["demo_id"], "qe-mgo")
            self.assertEqual(summary["case_selection"]["mode"], "explicit_pinned_case")
            self.assertFalse(summary["case_selection"]["llm_planning"])
            self.assertFalse(summary["case_selection"]["keyword_routing"])
            self.assertTrue(summary["execution"]["offline"])
            self.assertFalse(summary["execution"]["llm_called"])
            self.assertFalse(summary["execution"]["hpc_submitted"])
            self.assertEqual(summary["result"]["convergence"], "converged")
            self.assertEqual(summary["result"]["iterations"], 14)
            self.assertEqual(summary["result"]["energy"], {"value": -2417.17683284, "unit": "Ry"})
            self.assertEqual(summary["result"]["atom_count"], 64)
            self.assertTrue((output / "summary.json").is_file())
            self.assertTrue((output / summary["workflow"]["graph_state"]).is_file())
            self.assertEqual(json.loads((output / "summary.json").read_text(encoding="utf-8")), summary)

    def test_existing_output_is_refused_without_modification(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "existing"
            output.mkdir()
            sentinel = output / "keep.txt"
            sentinel.write_text("unchanged", encoding="utf-8")

            with self.assertRaisesRegex(DemoArchiveError, "Refusing to overwrite"):
                run_qe_mgo_demo(output)

            self.assertEqual(sentinel.read_text(encoding="utf-8"), "unchanged")
            self.assertEqual([item.name for item in output.iterdir()], ["keep.txt"])

    def test_external_data_root_is_rejected_before_runtime_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "archive"
            external = root / "external"
            with patch.dict(os.environ, {"MATFLOW_DATA_ROOT": str(external)}):
                with self.assertRaisesRegex(DemoArchiveError, "points outside"):
                    run_qe_mgo_demo(output)
            self.assertTrue(output.is_dir())
            self.assertEqual(list(output.iterdir()), [])
            self.assertFalse(external.exists())

    def test_example_contract_matches_fixtures(self):
        case = self.ROOT / "examples" / "cases" / "A1-qe-mgo"
        expected = json.loads((case / "expected.json").read_text(encoding="utf-8"))
        sources = json.loads((case / "data-sources.json").read_text(encoding="utf-8"))["sources"]
        recorded = json.loads((case / "recorded" / "run" / "summary.json").read_text(encoding="utf-8"))

        self.assertEqual(recorded["result"], expected["result"])
        self.assertEqual(recorded["workflow"]["node_count"], expected["workflow"]["node_count"])
        self.assertEqual(recorded["workflow"]["edge_count"], expected["workflow"]["edge_count"])
        self.assertEqual(set(recorded["workflow"]["node_statuses"].values()), {"completed"})
        for source in sources:
            payload = (self.ROOT / source["path"]).read_bytes()
            self.assertEqual(hashlib.sha256(payload).hexdigest(), source["sha256"])

    def test_cli_smoke_test(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "cli-run"
            completed = subprocess.run(
                [sys.executable, "-m", "backend.cli", "demo", "qe-mgo", "--output", str(output)],
                cwd=self.ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["result"]["provenance"], "historical_output_replay")
            self.assertTrue((output / "summary.json").is_file())


if __name__ == "__main__":
    unittest.main()

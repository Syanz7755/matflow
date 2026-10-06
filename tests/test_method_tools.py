from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

from backend.contracts import Edge, GraphState, Node
from backend.workspace_runtime import WorkspaceRuntime


def _signal_csv() -> bytes:
    rows = ["two_theta_deg,intensity_counts,wavenumber_cm-1,absorbance_au"]
    for index in range(301):
        xrd_x = 10 + index * 0.1
        ftir_x = 1000 + index * 10
        xrd_y = 4 + 100 * math.exp(-((xrd_x - 25) / 0.25) ** 2) + 80 * math.exp(-((xrd_x - 31) / 0.25) ** 2)
        ftir_y = 0.01 + 0.35 * math.exp(-((ftir_x - 1710) / 25) ** 2) + 0.28 * math.exp(-((ftir_x - 2850) / 25) ** 2)
        rows.append(f"{xrd_x},{xrd_y},{ftir_x},{ftir_y}")
    return ("\n".join(rows) + "\n").encode()


class MethodToolPackageTests(unittest.TestCase):
    def test_method_specific_tools_execute_in_one_typed_workflow(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = WorkspaceRuntime(Path(directory), packages=("xrd", "ftir"))
            upload = runtime.import_dataset("signals.csv", _signal_csv(), "text/csv")
            xrd_spec = runtime.registry().get("xrd_peak_extraction")
            ftir_spec = runtime.registry().get("ftir_peak_extraction")
            runtime.write_state(GraphState(nodes=[
                Node(id="source", type="raw_file_import", params={"file_name": "signals.csv", "upload_id": upload["id"]}),
                Node(id="table", type="normalize_columns", params={
                    "two_theta_deg": "two_theta_deg", "intensity_counts": "intensity_counts",
                    "wavenumber_cm-1": "wavenumber_cm-1", "absorbance_au": "absorbance_au",
                }),
                Node(id="xrd-peaks", type="xrd_peak_extraction", params=xrd_spec.params),
                Node(id="xrd-match", type="xrd_reference_match", params={"tolerance": 0.3, "references": {"test_phase": [25.0, 31.0]}}),
                Node(id="ftir-peaks", type="ftir_peak_extraction", params=ftir_spec.params),
                Node(id="ftir-assign", type="ftir_band_assignment", params={"ranges": [
                    {"min": 1680, "max": 1740, "label": "carbonyl_candidate"},
                    {"min": 2820, "max": 2880, "label": "aliphatic_ch_candidate"},
                ]}),
            ], edges=[
                Edge(id="e1", source="source", source_port="raw", target="table", target_port="raw"),
                Edge(id="e2", source="table", source_port="table", target="xrd-peaks", target_port="data"),
                Edge(id="e3", source="xrd-peaks", source_port="peaks", target="xrd-match", target_port="peaks"),
                Edge(id="e4", source="table", source_port="table", target="ftir-peaks", target_port="data"),
                Edge(id="e5", source="ftir-peaks", source_port="peaks", target="ftir-assign", target_port="peaks"),
            ]))
            result = runtime.execute_workflow(restart=True)
            nodes = {node["id"]: node for node in result["state"]["nodes"]}
            self.assertEqual(nodes["xrd-peaks"]["status"], "completed")
            self.assertGreaterEqual(len(nodes["xrd-peaks"]["output"]["peaks"]), 2)
            self.assertEqual(nodes["xrd-match"]["output"]["best_match"], "test_phase")
            assignments = nodes["ftir-assign"]["output"]["assignments"]
            self.assertEqual({item["label"] for item in assignments}, {"carbonyl_candidate", "aliphatic_ch_candidate"})


if __name__ == "__main__":
    unittest.main()

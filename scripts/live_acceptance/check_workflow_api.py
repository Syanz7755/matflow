"""End-to-end acceptance check of one live MatFlow workflow over HTTP.

It exercises the product, not a lookalike:

  upload the EIS fixture -> build a typed four-node workflow -> run it with a
  post-run review gate -> assert the analysis node is WAITING and the downstream
  plot is READY (the pause really stops downstream work) -> submit "continue" ->
  assert both completed with real values -> clear the workspace -> run the pinned
  MgO QE replay demo and check the frozen result.

Usage (backend must be running; see scripts/start_demo.ps1):

    .\\.venv\\Scripts\\python.exe scripts/live_acceptance/check_workflow_api.py
    MATFLOW_API=http://127.0.0.1:8022/api MATFLOW_EVIDENCE=.tmp/check python scripts/live_acceptance/check_workflow_api.py

Exit code 0 means every assertion passed.  The script prints only status lines;
full response bodies are archived under the evidence folder.  It reads no
credential and writes none.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

BASE = os.getenv("MATFLOW_API", "http://127.0.0.1:8000/api")
ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = Path(os.getenv("MATFLOW_EVIDENCE", str(ROOT / ".tmp" / "live" / "api-check")))
FIXTURE = ROOT / "examples" / "data" / "01_eis_basic_qc" / "eis_spectrum.csv"

steps: list[dict] = []


def record(name: str, payload) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE / f"{len(steps):02d}-{name}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    steps.append({"step": name, "file": path.name})


def call(method: str, path: str, **kwargs):
    started = time.monotonic()
    response = requests.request(method, BASE + path, timeout=120, **kwargs)
    elapsed = round(time.monotonic() - started, 2)
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text[:2000]}
    return response.status_code, body, elapsed


def main() -> int:
    status, capabilities, _ = call("GET", "/capabilities")
    assert status == 200, (status, capabilities)
    packages = sorted((capabilities.get("domain_packages") or {}).keys())
    assert "eis" in packages and "qe" in packages, packages
    record("capabilities", {"packages": packages})
    print(f"[1] connected: {BASE} packages={packages}")

    status, _body, _ = call("POST", "/reset")
    assert status == 200, status

    with FIXTURE.open("rb") as handle:
        status, upload, elapsed = call("POST", "/uploads", files=[("files", (FIXTURE.name, handle, "text/csv"))])
    assert status == 200 and upload.get("files"), (status, upload)
    upload_id = upload["files"][0]["id"]
    record("upload", upload["files"][0])
    print(f"[2] uploaded {FIXTURE.name} ({elapsed}s)")

    state = call("GET", "/state")[1]
    state = state.get("state", state)
    patch = {
        "base_version": state["version"],
        "rationale": "Live acceptance: EIS quality control with a human review gate before the Nyquist plot.",
        "operations": [
            {"op": "add_node", "node": {"id": "import-1", "type": "raw_file_import",
             "params": {"file_name": FIXTURE.name, "upload_id": upload_id}, "position": {"x": 80, "y": 160}}},
            {"op": "add_node", "node": {"id": "map-1", "type": "normalize_columns", "params": {}, "position": {"x": 420, "y": 160}}},
            {"op": "add_node", "node": {"id": "qc-1", "type": "eis_basic_qc",
             "params": {"min_frequency_hz": 10, "fit_model": "None",
                        "frequency_column": "frequency_hz", "real_column": "z_real_ohm", "imag_column": "z_imag_ohm"},
             "position": {"x": 760, "y": 160},
             "review_policy": {"after_run": True, "prompt": "Review this result before continuing."}}},
            {"op": "add_node", "node": {"id": "plot-1", "type": "plot_nyquist",
             "params": {"title": "Nyquist plot"}, "position": {"x": 1100, "y": 160}}},
            {"op": "connect", "edge": {"id": "e1", "source": "import-1", "source_port": "raw", "target": "map-1", "target_port": "raw"}},
            {"op": "connect", "edge": {"id": "e2", "source": "map-1", "source_port": "table", "target": "qc-1", "target_port": "data"}},
            {"op": "connect", "edge": {"id": "e3", "source": "qc-1", "source_port": "data", "target": "plot-1", "target_port": "data"}},
        ],
    }
    status, patched, elapsed = call("POST", "/patch", json=patch)
    assert status == 200, (status, patched)
    record("patch", patched)
    print(f"[3] workflow built ({elapsed}s)")

    status, outcome, elapsed = call("POST", "/workflow/execute", json={"restart": True})
    assert status == 200 and outcome.get("ok"), (status, outcome)
    nodes = {node["id"]: node for node in outcome["state"]["nodes"]}
    assert nodes["qc-1"]["status"] == "waiting", nodes["qc-1"]["status"]
    assert nodes["plot-1"]["status"] == "ready", nodes["plot-1"]["status"]
    record("execute-paused", outcome)
    print(f"[4] review gate holds ({elapsed}s): qc-1=waiting plot-1=ready (downstream stopped)")

    status, decided, elapsed = call("POST", "/workflow/decision", json={"node_id": "qc-1", "decision": "continue"})
    assert status == 200, (status, decided)
    record("decision-continue", decided)
    nodes = {node["id"]: node for node in decided["state"]["nodes"]}
    report, plot = nodes["qc-1"]["output"], nodes["plot-1"]["output"]
    assert nodes["qc-1"]["status"] == "completed" and nodes["plot-1"]["status"] == "completed"
    assert report["kind"] == "EISQCReport" and report["rows_valid"] > 0
    assert plot["kind"] == "Plot" and plot["points"] > 0
    print(f"[5] continued ({elapsed}s): rows_valid={report['rows_valid']} rows_retained={report['rows_retained']} "
          f"min_frequency_hz={report['min_frequency_hz']} plot_points={plot['points']}")

    status, _body, _ = call("POST", "/reset")
    assert status == 200, status
    status, demo, elapsed = call("POST", "/qe/demo", json={
        "message": "For pristine MgO SCF, generate a QE input and report energy and convergence."})
    assert status == 200, (status, demo)
    record("qe-demo", demo)
    results = {item["node_id"]: item["result"] for item in demo.get("results", [])}
    result = results["qe-demo-result"]
    energy = (result.get("energy") or {}).get("value")
    assert result.get("iterations") == 14 and energy == -2417.17683284, result
    print(f"[6] QE replay demo ({elapsed}s): iterations=14 energy={energy} Ry provenance={result.get('provenance')}")

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "summary.json").write_text(json.dumps({"ok": True, "base": BASE, "steps": steps,
                                                       "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")},
                                                      ensure_ascii=False, indent=2), encoding="utf-8")
    print("PASS: one workflow operated end to end (pause -> continue -> results) plus the pinned QE replay demo.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        (EVIDENCE / "summary.json").write_text(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2),
                                               encoding="utf-8")
        print("FAIL:", exc)
        sys.exit(2)

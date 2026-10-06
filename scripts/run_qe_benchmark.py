"""Run the small deterministic QE contract benchmark and save its report."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from jsonschema import Draft202012Validator

from backend.contracts import GraphState, TaskState
from backend.domain_packages.qe_demo import build_demo_patch
from backend.routing import DecisionRouter
from backend.validator import GraphValidator
from backend.workspace_runtime import WorkspaceRuntime

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "examples" / "qe_benchmark_cases.json"
REPORT = ROOT / "examples" / "qe_benchmark_report.md"


def main() -> int:
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    rows = []
    for case in cases:
        with tempfile.TemporaryDirectory(prefix="matflow-qe-bench-") as directory:
            runtime = WorkspaceRuntime(Path(directory), packages=("qe", "qe_demo"))
            task = TaskState(user_message=case["prompt"], graph_version=0, available_input_types=case["input_types"])
            decision = DecisionRouter().decide(task, runtime.registry())
            selected = decision.selected[0].tool_id if decision.selected else None
            spec = runtime.registry().get(case["expected_tool"])
            schema_ok = not list(Draft202012Validator(spec.parameter_schema).iter_errors(spec.params))
            patch = build_demo_patch(0, case["prompt"])
            GraphValidator().validate(GraphState(), patch, runtime.registry())
            runtime.apply_graph_patch(patch)
            outcome = runtime.execute_workflow(restart=True)
            final = next((item.get("result") for item in outcome["results"] if item.get("result", {}).get("kind") == "QEResult"), None)
            execution_ok = bool(final and final.get("convergence") == "converged")
            rows.append({"id": case["id"], "expected": case["expected_tool"], "selected": selected, "tool_selection": selected == case["expected_tool"], "schema_validity": schema_ok, "workflow_validity": True, "execution_success": execution_ok})

    metrics = {key: sum(bool(row[key]) for row in rows) for key in ("tool_selection", "schema_validity", "workflow_validity", "execution_success")}
    lines = ["# QE Minimum Benchmark", "", f"Cases: {len(rows)}. Scope: deterministic contracts plus archived-output replay; execution success is not a new Slurm run.", "", "| Metric | Pass | Rate |", "| --- | ---: | ---: |"]
    for key, passed in metrics.items():
        lines.append(f"| {key.replace('_', ' ')} | {passed}/{len(rows)} | {passed / len(rows):.0%} |")
    lines.extend(["", "| Case | Expected Tool | Selected Tool | Schema | Workflow | Replay execution |", "| --- | --- | --- | --- | --- | --- |"])
    for row in rows:
        lines.append(f"| {row['id']} | `{row['expected']}` | `{row['selected'] or 'none'}` | {'pass' if row['schema_validity'] else 'fail'} | {'pass' if row['workflow_validity'] else 'fail'} | {'pass' if row['execution_success'] else 'fail'} |")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(REPORT)
    print(json.dumps(metrics, indent=2))
    return 0 if all(passed == len(rows) for passed in metrics.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())

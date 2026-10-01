"""Run JSON-defined MatFlow scenarios and write redacted JSON/Markdown reports."""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from tests.scenario_harness import ConfiguredScenarioRunner, ScenarioReportWriter, ScenarioSuite, ServiceFlags


SCENARIOS = ROOT / "tests" / "scenarios"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--online-jev", action="store_true", help="Allow cases that also opt in to access the configured Jev-like service.")
    parser.add_argument("--online-llm", action="store_true", help="Allow cases that also opt in to access the configured LLM service.")
    parser.add_argument("--output", type=Path, default=ROOT / "examples" / "reports" / "configured_scenarios")
    parser.add_argument("--suite", action="append", choices=["workflow_generation", "workflow_execution", "tool_construction"])
    args = parser.parse_args()
    selected = args.suite or ["workflow_generation", "workflow_execution", "tool_construction"]
    flags = ServiceFlags(jev_like=args.online_jev, llm=args.online_llm)
    failed = 0
    with tempfile.TemporaryDirectory(prefix="matflow-scenarios-") as directory:
        runner = ConfiguredScenarioRunner(ROOT, Path(directory), flags)
        writer = ScenarioReportWriter(args.output)
        for name in selected:
            suite = ScenarioSuite.load(SCENARIOS / f"{name}.json")
            records = [runner.run_case(case) for case in suite.cases]
            outputs = writer.write(suite.suite_id, records)
            summary = {verdict: sum(item["verdict"] == verdict for item in records) for verdict in ("passed", "failed", "skipped", "blocked")}
            failed += summary["failed"]
            print(f"{suite.suite_id}: {summary} -> {outputs['markdown']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

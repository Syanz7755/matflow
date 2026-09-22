"""Evaluate prompt-style stability against the configured Jev decision models.

The report is a routing evaluation only.  It does not claim that test-only
XRD/UV-Vis/pycnometer/TGA declarations have executable scientific backends.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from backend.contracts import RouterCandidate, TaskState
from backend.jev_routing import JevDecisionRouter
from backend.routing import DecisionRouter

from evaluate_jev_routing import evaluation_registry

ROOT = Path(__file__).parents[1]
SUITE_PATH = ROOT / "examples" / "prompt_stability_suite.json"
REPORT_PATH = ROOT / "examples" / "reports" / "prompt_stability_evaluation.json"


def analysis_candidates(registry):
    excluded = {"raw_file_import", "normalize_columns", "plot_nyquist", "human_decision", "skill_node"}
    return [
        RouterCandidate(tool_id=tool_id, version=spec.version, score=0.5, reasons=["stability evaluation candidate"])
        for tool_id, spec in registry.active().items() if tool_id not in excluded
    ]


def main() -> None:
    suite = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    registry = evaluation_registry()
    candidates = analysis_candidates(registry)
    model_router = JevDecisionRouter()
    lexical_router = DecisionRouter()
    results = []

    for case in suite["cases"]:
        task = TaskState(
            task_id=case["case_id"], user_message=case["prompt"], graph_version=0,
            available_input_types=["TypedTable"],
        )
        if case["level"] == "safety":
            decision = lexical_router.decide(task, registry)
            selected_id = decision.selected[0].tool_id if decision.selected else None
            passed = decision.requires_human_confirmation
            evidence = {"route_rationale": decision.rationale, "model_opinions": []}
        else:
            selected, confidence, confirmation, opinions, rationale = model_router.decide(task, candidates, registry)
            selected_id = selected.tool_id if selected else None
            passed = selected_id == case["expected_registered_id"]
            evidence = {
                "confidence": confidence,
                "requires_human_confirmation": confirmation,
                "route_rationale": rationale,
                "model_opinions": [opinion.model_dump() for opinion in opinions],
            }
        results.append({
            "case_id": case["case_id"], "family": case["family"], "level": case["level"],
            "user_prompt": case["prompt"], "expected_registered_id": case["expected_registered_id"],
            "selected_registered_id": selected_id, "passed": passed, **evidence,
        })

    families = defaultdict(list)
    for result in results:
        if result["family"] != "safety":
            families[result["family"]].append(result)
    supported = [item for item in results if item["family"] != "safety"]
    safety = [item for item in results if item["family"] == "safety"]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "suite": str(SUITE_PATH.relative_to(ROOT)),
        "scope": "routing stability only; non-EIS analytical tools are test-only declarations.",
        "metrics": {
            "supported_route_accuracy": sum(item["passed"] for item in supported) / len(supported),
            "family_stability": {family: all(item["passed"] for item in items) for family, items in families.items()},
            "safety_pass_rate": sum(item["passed"] for item in safety) / len(safety),
        },
        "cases": results,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["metrics"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

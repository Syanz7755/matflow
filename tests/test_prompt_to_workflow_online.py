"""Live suite: long prompt -> LLM (+ Jev when reachable) -> constructed workflow.

Every case runs the real planning chain against the configured LLM gateway
(config/llm.json): the LLM decomposes the prompt into action units, every
action is routed by Jev or — when Jev is unreachable — by the LLM, and the
dependencies become typed, directed edges. Keyword matching is never used.

Run it explicitly; it is skipped otherwise:

    set MATFLOW_RUN_LLM_APPLICATION_TESTS=1
    python -m unittest tests.test_prompt_to_workflow_online -v

``MATFLOW_PROMPT_CASES`` (comma-separated case ids) narrows the run, and
``MATFLOW_SCENARIO_REPORT_DIR`` receives a JSON report of every plan.
"""
from __future__ import annotations

import fnmatch
import json
import os
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend import main
from tests.reference_composition import workspace as reference_workspace

ROOT = Path(__file__).parents[1]
SUITE = ROOT / "tests" / "suites" / "prompt_to_workflow.json"
ENABLED = os.getenv("MATFLOW_RUN_LLM_APPLICATION_TESTS") == "1"


def load_cases() -> list[dict[str, Any]]:
    suite = json.loads(SUITE.read_text(encoding="utf-8"))
    prompts = {case["case_id"]: case["prompt"] for case in json.loads((ROOT / suite["prompt_source"]).read_text(encoding="utf-8"))["cases"]}
    wanted = {item.strip() for item in os.getenv("MATFLOW_PROMPT_CASES", "").split(",") if item.strip()}
    return [case | {"prompt": prompts[case["case_id"]]} for case in suite["cases"] if not wanted or case["case_id"] in wanted]


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as directory:
        runtime = reference_workspace(Path(directory), model_complete=main._runtime_model_adapter)
        attachments = []
        for fixture in case["fixtures"]:
            source = ROOT / fixture
            uploaded = runtime.import_dataset(source.name, source.read_bytes(), "text/csv")
            attachments.append({"upload_id": uploaded["id"], "name": source.name})
        started = time.monotonic()
        try:
            plan = runtime.plan_workflow(case["prompt"], task_id=case["case_id"], uploads=attachments, apply=True)
        except Exception as exc:  # recorded as a failed case, not a crashed suite
            plan = {"status": "error", "reason": f"{type(exc).__name__}: {exc}", "actions": [], "edges": []}
        plan["elapsed_seconds"] = round(time.monotonic() - started, 1)
        if plan.get("applied"):
            # "planned" promises a runnable workflow: run it on the fixture.
            try:
                outcome = runtime.execute_workflow(restart=True)
                failed = [f"{node.id}: {(node.output or {}).get('error', node.status)}" for node in runtime.read_state().nodes if node.status != "completed"]
                plan["execution"] = {"ok": bool(outcome.get("ok", True)) and not failed, "not_completed": failed}
            except Exception as exc:
                plan["execution"] = {"ok": False, "not_completed": [f"{type(exc).__name__}: {exc}"]}
    return plan


def routed_tools(plan: dict[str, Any]) -> list[str]:
    return [action["tool_id"] for action in plan.get("actions", []) if action.get("status") == "routed"]


def reachable(plan: dict[str, Any], source_tool: str, target_tool: str) -> bool:
    tool_of = {action["node_id"]: action["tool_id"] for action in plan.get("actions", []) if action.get("node_id")}
    graph: dict[str, set[str]] = {}
    for edge in plan.get("edges", []):
        if edge.get("edge"):
            graph.setdefault(edge["edge"]["source"], set()).add(edge["edge"]["target"])
    frontier = [node for node, tool in tool_of.items() if tool == source_tool]
    seen = set(frontier)
    while frontier:
        node = frontier.pop()
        for successor in graph.get(node, ()):
            if tool_of.get(successor) == target_tool:
                return True
            if successor not in seen:
                seen.add(successor)
                frontier.append(successor)
    return False


def verdict(case: dict[str, Any], plan: dict[str, Any]) -> list[str]:
    """Every way the constructed workflow misses the case's expectations."""
    problems = []
    if plan["status"] not in case["statuses"]:
        problems.append(f"status {plan['status']!r} not in {case['statuses']} ({plan.get('reason') or plan.get('question') or ''})")
    tools = routed_tools(plan)
    for tool in case["required_tools"]:
        if tool not in tools:
            problems.append(f"required tool {tool} was not routed")
    for pattern in case["forbidden_tools"]:
        hits = [tool for tool in tools if fnmatch.fnmatch(tool, pattern)]
        if hits:
            problems.append(f"forbidden tool(s) routed: {', '.join(hits)}")
    for upstream, downstream in case["required_paths"]:
        if not reachable(plan, upstream, downstream):
            problems.append(f"no directed path {upstream} -> {downstream}")
    if plan["status"] == "planned" and not plan.get("patch_valid"):
        problems.append("a 'planned' workflow must carry a valid patch")
    if plan["status"] == "planned" and not plan.get("execution", {}).get("ok"):
        problems.append(f"the planned workflow did not run: {plan.get('execution')}")
    if plan["status"] in {"planned", "needs_confirmation"}:
        for action in plan["actions"]:
            if action["status"] == "routed" and action["router"] not in {"jev", "llm"}:
                problems.append(f"{action['id']} was routed by {action['router']!r}")
    return problems


def summary_row(case: dict[str, Any], plan: dict[str, Any], problems: list[str]) -> dict[str, Any]:
    return {
        "case_id": case["case_id"],
        "verdict": "passed" if not problems else "failed",
        "problems": problems,
        "status": plan["status"],
        "elapsed_seconds": plan.get("elapsed_seconds"),
        "llm_calls": plan.get("llm_calls"),
        "routers": sorted({action.get("router") for action in plan.get("actions", []) if action.get("router")}),
        "workflow": [
            {"id": action["id"], "goal": action["goal"], "depends_on": action["depends_on"], "status": action["status"], "tool_id": action.get("tool_id"), "router": action.get("router"), "confidence": action.get("confidence")}
            for action in plan.get("actions", [])
        ],
        "edges": [f"{edge['edge']['source']}.{edge['edge']['source_port']} -> {edge['edge']['target']}.{edge['edge']['target_port']}" for edge in plan.get("edges", []) if edge.get("edge")],
        "issues": plan.get("issues", []),
        "execution": plan.get("execution"),
        "question": plan.get("question", ""),
        "reason": plan.get("reason", ""),
    }


@unittest.skipUnless(ENABLED, "set MATFLOW_RUN_LLM_APPLICATION_TESTS=1 to plan long prompts with the configured LLM")
class PromptToWorkflowOnlineTests(unittest.TestCase):
    def test_long_prompts_construct_typed_workflows(self):
        cases = load_cases()
        self.assertTrue(cases)
        workers = int(os.getenv("MATFLOW_PROMPT_WORKERS", "4"))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            plans = list(pool.map(run_case, cases))

        rows = []
        for case, plan in zip(cases, plans):
            problems = verdict(case, plan)
            rows.append(summary_row(case, plan, problems))
        report_dir = os.getenv("MATFLOW_SCENARIO_REPORT_DIR")
        if report_dir:
            path = Path(report_dir) / f"prompt-to-workflow-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"suite_id": "prompt-to-workflow-v1", "results": rows, "plans": plans}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        for case, row in zip(cases, rows):
            with self.subTest(case=case["case_id"]):
                self.assertEqual(row["problems"], [], json.dumps(row, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    unittest.main()

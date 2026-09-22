"""Run known-answer example prompts through the configured Jev router.

This is an integration evaluation, not a materials-science benchmark.  It tests
whether the routing models select the intended registered analysis capability.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from backend.contracts import RouterCandidate, TaskState
from backend.jev_routing import JevDecisionRouter
from backend.tool_registry import ToolRegistry


ROOT = Path(__file__).parents[1]
REPORTS = ROOT / "examples" / "reports"


@dataclass(frozen=True)
class ExampleCase:
    case_id: str
    prompt: str
    expected_tool: str


CASES = (
    ExampleCase("01_eis_basic_qc", "对一份阻抗频率扫描做基础 EIS 质量检查，并绘制 Nyquist 图。", "eis_basic_qc"),
    ExampleCase("02_xrd_anatase_identification", "提取 XRD 峰，并判断这份样品最可能的 TiO2 晶相。", "xrd_phase_identification"),
    ExampleCase("03_uvvis_methylene_blue_decay", "用标准曲线分析亚甲基蓝的 UV-Vis 时间序列，找 λmax 并计算浓度随时间的衰减。", "uvvis_decay_analysis"),
    ExampleCase("04_pycnometer_specific_gravity", "以去离子水为内标，计算粉体的比重并汇总重复测量。", "pycnometer_specific_gravity"),
    ExampleCase("05_tga_caco3_content", "在 600–850 °C 的失重步骤中估算样品的 CaCO3 质量分数。", "tga_caco3_estimation"),
)


def evaluation_registry() -> ToolRegistry:
    """A test-only catalog. These declarations do not alter the user workspace."""
    definitions = {
        "xrd_phase_identification": ("XRD phase identification", "Extract diffraction peaks and propose likely crystalline phases from a 2θ-intensity pattern."),
        "uvvis_decay_analysis": ("UV-Vis concentration decay", "Extract UV-Vis absorption peaks, fit a calibration curve, and calculate concentration versus time."),
        "pycnometer_specific_gravity": ("Pycnometer specific gravity", "Calculate powder specific gravity from empty, water-filled, sample-filled and sample-plus-water pycnometer masses."),
        "tga_caco3_estimation": ("TGA calcium carbonate estimation", "Calculate a selected TGA mass-loss step and estimate calcium carbonate content using CO2 stoichiometry."),
    }
    custom = {
        tool_id: {
            "label": label,
            "category": "Example evaluation",
            "inputs": {"data": "TypedTable"},
            "outputs": {"artifact": "Artifact"},
            "params": {},
            "description": description,
        }
        for tool_id, (label, description) in definitions.items()
    }
    return ToolRegistry(custom)


def main() -> None:
    registry = evaluation_registry()
    candidates = [
        RouterCandidate(tool_id=tool_id, version=spec.version, score=0.5, reasons=["evaluation candidate"])
        for tool_id, spec in registry.active().items()
        if tool_id not in {"raw_file_import", "normalize_columns", "plot_nyquist", "human_decision", "skill_node"}
    ]
    router = JevDecisionRouter()
    results = []
    for case in CASES:
        task = TaskState(task_id=case.case_id, user_message=case.prompt, graph_version=0, available_input_types=["TypedTable"])
        selected, confidence, confirmation, decisions, rationale = router.decide(task, candidates, registry)
        predictions = {decision.profile: decision.selected_tool_id for decision in decisions}
        results.append({
            "case_id": case.case_id,
            "expected_tool": case.expected_tool,
            "predictions": predictions,
            "consensus_tool": selected.tool_id if selected else None,
            "confidence": confidence,
            "requires_human_confirmation": confirmation,
            "rationale": rationale,
            "correct_consensus": bool(selected and selected.tool_id == case.expected_tool),
        })

    REPORTS.mkdir(parents=True, exist_ok=True)
    payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "config": str(ROOT / "config" / "jev_router.json"), "cases": results}
    (REPORTS / "jev_routing_evaluation.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Jev Router Example Evaluation", "", "Synthetic fixture routing check. Not a scientific-performance benchmark.", "", "| Case | Expected | Laya | Sematic | Consensus | Confirmation |", "| --- | --- | --- | --- | --- | --- |"]
    for item in results:
        lines.append("| {case_id} | {expected_tool} | {laya} | {semantic} | {consensus} | {confirmation} |".format(case_id=item["case_id"], expected_tool=item["expected_tool"], laya=item["predictions"].get("laya", "error"), semantic=item["predictions"].get("semantic", "error"), consensus=item["consensus_tool"] or "none", confirmation=item["requires_human_confirmation"]))
    accuracy = sum(item["correct_consensus"] for item in results) / len(results)
    lines.extend(["", f"Consensus accuracy: {accuracy:.0%} ({sum(item['correct_consensus'] for item in results)}/{len(results)})", "", "Semantic scores are conditional candidate scores. Only Laya confidence is treated as calibrated in the router contract."])
    (REPORTS / "jev_routing_evaluation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

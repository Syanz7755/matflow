"""Online evaluation of model-based tool routing (prompt -> decomposition -> per-step routing).

The deterministic shell is covered by the default test suite; this script measures
the *model-dependent* part: does the router pick the right registered tool, report
a capability gap when none exists, and escalate to a human when it should?

It drives the production planning path (`WorkspaceRuntime.plan_workflow`: LLM
decomposition -> Jev-or-LLM routing per action -> typed edges) against the
shipped tool catalogue, once per (model, case, repeat), then scores the routed
tools against gold labels derived from the repository's own suites.

    uv run python examples/evaluate_routing_online.py --models deepseek-chat,qwen --repeats 1 --jev on

Nothing is keyword-routed. The gateway key is read from the environment and is
never printed, logged or written to a report.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import math
import os
import re
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
SUITES = ROOT / "tests" / "suites"
REPORT_DIR = EXAMPLES / "reports"
REPORT_JSON = REPORT_DIR / "routing_online_evaluation.json"
REPORT_MD = REPORT_DIR / "routing_online_evaluation.md"

#: Tools that move or reshape data. Routing them is not the scientific decision.
PLUMBING = {"raw_file_import", "normalize_columns", "type_cast", "plot_nyquist", "quality_report", "conditional_gate", "join", "aggregate"}
FAMILIES = {"eis": ["eis_basic_qc", "plot_nyquist"], "xrd": ["xrd_*"], "ftir": ["ftir_*"], "qe": ["qe_*"]}
OTHER_FAMILIES = [pattern for patterns in FAMILIES.values() for pattern in patterns]
#: Scenario targets that are not registered one-to-one: the shipped pipeline that serves them.
PIPELINE_ALIASES = {
    "xrd_phase_identification": ["xrd_peak_extraction", "xrd_reference_match"],
    "ftir_functional_group_assignment": ["ftir_peak_extraction", "ftir_band_assignment"],
}
ESCALATION_STATUSES = ["clarify", "refused", "needs_confirmation"]
CJK = re.compile(r"[㐀-鿿]")


# ----------------------------------------------------------------------------
# Pure metric helpers (unit-tested offline)
# ----------------------------------------------------------------------------
def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float] | None:
    """Wilson score interval for a binomial proportion; ``None`` when there is no data."""
    if total <= 0:
        return None
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


def proportion(successes: int, total: int) -> dict[str, Any]:
    interval = wilson_interval(successes, total)
    return {
        "k": successes, "n": total,
        "rate": (successes / total) if total else None,
        "ci95": [round(interval[0], 4), round(interval[1], 4)] if interval else None,
    }


def accuracy(outcomes: list[str], hit: str = "hit") -> dict[str, Any]:
    return proportion(sum(1 for item in outcomes if item == hit), len(outcomes))


def percentile(values: list[float], q: float) -> float | None:
    """Linear-interpolated percentile (q in 0..100); ``None`` for no data."""
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q / 100
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def disagreement_rate(choices_by_model: dict[str, dict[Any, Any]]) -> dict[str, Any]:
    """Fraction of units (case or step) on which the models do not all choose the same thing.

    Only units answered by at least two models count.
    """
    units: dict[Any, list[Any]] = defaultdict(list)
    for choices in choices_by_model.values():
        for unit, choice in choices.items():
            units[unit].append(json.dumps(choice, sort_keys=True, default=str))
    comparable = [values for values in units.values() if len(values) >= 2]
    return proportion(sum(1 for values in comparable if len(set(values)) > 1), len(comparable))


def self_consistency(runs_by_unit: dict[Any, list[Any]]) -> dict[str, Any]:
    """Fraction of units whose repeated runs all agree (units with >=2 runs only)."""
    comparable = [[json.dumps(run, sort_keys=True, default=str) for run in runs] for runs in runs_by_unit.values() if len(runs) >= 2]
    return proportion(sum(1 for runs in comparable if len(set(runs)) == 1), len(comparable))


def stratified_order(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A deterministic order in which every prefix mixes expectation classes and languages evenly.

    Cases are grouped by (expectation, language), each group is ordered by a hash
    of its case id, and groups are drained round-robin, so ``--sample N`` is a
    prefix of ``--sample M`` for N < M and a checkpoint from a smaller run is reusable.
    """
    import hashlib
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        groups[(case["expect"], case["language"])].append(case)
    queues = [sorted(items, key=lambda c: hashlib.md5(c["case_id"].encode()).hexdigest()) for _, items in sorted(groups.items())]
    ordered: list[dict[str, Any]] = []
    while any(queues):
        for queue in queues:
            if queue:
                ordered.append(queue.pop(0))
    return ordered


def language_of(text: str) -> str:
    return "zh" if CJK.search(text) else "en"


# ----------------------------------------------------------------------------
# Gold labels
# ----------------------------------------------------------------------------
def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _case(case_id, source, prompt, domain, expect, fixtures, must=(), forbidden=(), statuses=None, language=None):
    return {
        "case_id": case_id, "source": source, "prompt": prompt, "domain": domain,
        "language": language or language_of(prompt), "expect": expect, "fixtures": list(fixtures),
        "gold": {"must": list(must), "forbidden": list(forbidden), "statuses": statuses},
    }


def forbidden_for(must: list[str], keep: tuple[str, ...] = ()) -> list[str]:
    """A generic AI node never stands in for a computation, and a tool of a family the request does not concern is wrong."""
    own = {family for family, patterns in FAMILIES.items() if any(_matches(tool, patterns) for tool in must)}
    return ["skill_node", *[p for family, patterns in FAMILIES.items() if family not in own for p in patterns if p not in keep]]


def _family_labels(registered: set[str], target: str | None) -> tuple[list[str], str]:
    """(tools the production catalogue offers for ``target``, 'positive' | 'gap')."""
    if target in registered:
        return [target], "positive"
    served = [tool for tool in PIPELINE_ALIASES.get(target or "", []) if tool in registered]
    return (served, "positive") if served else ([], "gap")


def build_cases(registered: set[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Every labelled case, deduplicated by (prompt, fixtures), plus an exclusion report."""
    expected = _read(SUITES / "teaching_lab_expected_results.json")["known_results"]
    teaching = _read(SUITES / "teaching_lab_prompt_suite.json")
    stability = _read(SUITES / "prompt_stability_suite.json")
    long_cases = {item["case_id"]: item for item in _read(SUITES / "long_prompt_cases.json")["cases"]}
    workflow_gold = _read(ROOT / "tests" / "suites" / "prompt_to_workflow.json")["cases"]

    cases: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []

    # Teaching-lab scenarios: gold from the scenario's registry target against the shipped catalogue.
    domain_of = {"01_eis_basic_qc": "eis", "02_xrd_phase_identification": "xrd", "03_uvvis_decay": "uvvis", "04_pycnometer_specific_gravity": "pycnometer",
                 "05_tga_caco3": "tga", "06_ftir_functional_groups": "ftir", "07_dsc_transition_enthalpy": "dsc", "08_four_point_resistivity": "four_point",
                 "09_tensile_curve": "tensile", "10_acid_base_titration": "titration", "11_rc_transient": "rc", "12_photoelectric_effect": "photoelectric",
                 "13_michelson_wavelength": "michelson", "14_rietveld_refinement": "rietveld", "15_raman_mapping": "raman"}
    for scenario in teaching["scenarios"]:
        sid = scenario["scenario_id"]
        if sid not in expected:
            for variant in scenario["prompt_variants"]:
                excluded.append({"case_id": f"{sid}:{variant['style']}", "reason": "scenario has no entry in teaching_lab_expected_results.json"})
            continue
        must, expect = _family_labels(registered, scenario["registry_target_id"])
        for variant in scenario["prompt_variants"]:
            forbidden = forbidden_for(must)
            if sid == "14_rietveld_refinement":  # peak extraction on the same pattern is a legitimate first step
                forbidden = ["skill_node", "eis_basic_qc", "plot_nyquist", "xrd_reference_match", "ftir_*", "qe_*"]
            cases.append(_case(f"{sid}:{variant['style']}", "teaching_lab", variant["prompt"], domain_of[sid], expect, scenario["fixtures"], must, forbidden))

    fixtures_of = {item["scenario_id"]: item["fixtures"] for item in teaching["scenarios"]}
    for item in teaching.get("cross_cutting_cases", []):
        cid, prompt = item["case_id"], item["prompt"]
        if cid == "cross_01_xrd_then_scherrer":
            cases.append(_case(cid, "teaching_lab", prompt, "cross", "positive", fixtures_of["02_xrd_phase_identification"], PIPELINE_ALIASES["xrd_phase_identification"], forbidden_for(PIPELINE_ALIASES["xrd_phase_identification"])))
        elif cid == "cross_02_ftir_and_four_point":
            cases.append(_case(cid, "teaching_lab", prompt, "cross", "positive", fixtures_of["06_ftir_functional_groups"] + fixtures_of["08_four_point_resistivity"], PIPELINE_ALIASES["ftir_functional_group_assignment"], forbidden_for(PIPELINE_ALIASES["ftir_functional_group_assignment"])))
        elif item.get("expected_outcome") == "human_confirmation":
            fixtures = fixtures_of["14_rietveld_refinement"] if "Rietveld" in prompt else []
            cases.append(_case(cid, "teaching_lab", prompt, "safety" if "忽略" in prompt else "ambiguous", "human", fixtures, forbidden=["*"] if not fixtures else ["skill_node", "xrd_reference_match"], statuses=ESCALATION_STATUSES))
        else:
            excluded.append({"case_id": cid, "reason": f"unrecognised expected_outcome {item.get('expected_outcome')!r}"})

    # Prompt-stability suite: expected_registered_id mapped onto the shipped catalogue.
    family_domain = {"eis": "eis", "xrd": "xrd", "uvvis": "uvvis", "pycnometer": "pycnometer", "tga": "tga", "safety": "safety"}
    for item in stability["cases"]:
        fixtures = [item["fixture"]] if item.get("fixture") else []
        if item["level"] == "safety":
            forbidden = ["*"] if not fixtures else ["skill_node", "xrd_*", "ftir_*", "qe_*"] if "XRD" not in item["prompt"] else ["skill_node", "xrd_*"]
            cases.append(_case(item["case_id"], "prompt_stability", item["prompt"], "ambiguous" if "ambiguous" in item["case_id"] else "safety", "human", fixtures, forbidden=forbidden, statuses=ESCALATION_STATUSES))
            continue
        target = item.get("expected_registered_id")
        if not target:
            excluded.append({"case_id": item["case_id"], "reason": "no expected_registered_id"})
            continue
        must, expect = _family_labels(registered, target)
        forbidden = forbidden_for(must)
        cases.append(_case(item["case_id"], "prompt_stability", item["prompt"], family_domain.get(item["family"], item["family"]), expect, fixtures, must, forbidden))

    # Long prompts: gold is the hand-written workflow expectation (required / forbidden tools, allowed plan statuses).
    for gold in workflow_gold:
        source = long_cases.get(gold["case_id"])
        if source is None:
            excluded.append({"case_id": gold["case_id"], "reason": "prompt missing from long_prompt_cases.json"})
            continue
        expect = "positive" if gold["required_tools"] else ("human" if set(gold["statuses"]) <= {"clarify", "refused"} else "gap")
        cases.append(_case(gold["case_id"], "long_prompt", source["prompt"], source.get("domain", "long"), expect, gold["fixtures"], gold["required_tools"], gold["forbidden_tools"], gold["statuses"], language=source.get("language")))

    # Known-answer examples (evaluate_jev_routing.CASES) share the stability prompts' labels; add only unseen prompts.
    sys.path.insert(0, str(EXAMPLES))
    try:
        from evaluate_jev_routing import CASES as known
    finally:
        sys.path.pop(0)
    known_domain = {"01_eis_basic_qc": "eis", "02_xrd_anatase_identification": "xrd", "03_uvvis_methylene_blue_decay": "uvvis", "04_pycnometer_specific_gravity": "pycnometer", "05_tga_caco3_content": "tga"}
    known_fixture = {"01_eis_basic_qc": "examples/data/01_eis_basic_qc/eis_spectrum.csv", "02_xrd_anatase_identification": "examples/data/02_xrd_anatase_identification/xrd_anatase.csv",
                     "03_uvvis_methylene_blue_decay": "tests/fixtures/teaching_lab/03_uvvis_methylene_blue_decay/absorbance_time_series.csv", "04_pycnometer_specific_gravity": "tests/fixtures/teaching_lab/04_pycnometer_specific_gravity/pycnometer_measurements.csv",
                     "05_tga_caco3_content": "tests/fixtures/teaching_lab/05_tga_caco3_content/tga_mass_loss.csv"}
    for item in known:
        must, expect = _family_labels(registered, item.expected_tool)
        forbidden = forbidden_for(must)
        cases.append(_case(f"known:{item.case_id}", "known_answer", item.prompt, known_domain[item.case_id], expect, [known_fixture[item.case_id]], must, forbidden))

    unique: dict[tuple[str, tuple[str, ...]], dict[str, Any]] = {}
    duplicates = 0
    for case in cases:
        key = (case["prompt"].strip(), tuple(case["fixtures"]))
        if key in unique:
            duplicates += 1
        else:
            unique[key] = case
    final = list(unique.values())
    return final, {
        "excluded_no_gold": excluded, "excluded_count": len(excluded), "duplicates_removed": duplicates,
        "case_count": len(final),
        "by_source": dict(Counter(case["source"] for case in final)),
        "by_expectation": dict(Counter(case["expect"] for case in final)),
        "by_language": dict(Counter(case["language"] for case in final)),
    }


# ----------------------------------------------------------------------------
# Scoring one plan against its gold label (pure)
# ----------------------------------------------------------------------------
def _matches(tool: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(tool, pattern) for pattern in patterns)


def score_plan(case: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    """Outcome per gold step, whole-case pass, and the comparable signature of what was routed."""
    gold, expect = case["gold"], case["expect"]
    status = plan.get("status", "failed")
    actions = plan.get("actions", [])
    routed = [action["tool_id"] for action in actions if action.get("status") == "routed" and action.get("tool_id")]
    routed_set = set(routed)
    analysis = sorted(routed_set - PLUMBING)
    has_gap = any(action.get("status") == "gap" for action in actions)
    forbidden_hits = sorted(tool for tool in routed_set if _matches(tool, gold["forbidden"]))
    escalated = status in {"clarify", "refused"}
    signature = {"analysis": analysis, "gap": has_gap, "escalated": escalated}
    steps: list[dict[str, Any]] = []

    if status == "failed":
        steps = [{"gold": item, "outcome": "error", "chosen": None} for item in (gold["must"] or [expect])]
        return {"case_pass": False, "steps": steps, "signature": signature, "forbidden_hits": forbidden_hits, "routed_tools": routed}

    if expect == "positive":
        extras = [tool for tool in analysis if tool not in gold["must"]]
        for tool in gold["must"]:
            if tool in routed_set:
                outcome, chosen = "hit", tool
            elif tool in PLUMBING:
                outcome, chosen = "not_planned", None
            elif extras or forbidden_hits:
                outcome, chosen = "wrong_tool", ",".join(extras or forbidden_hits)
            elif has_gap:
                outcome, chosen = "null", None
            else:
                outcome, chosen = "not_planned", None
            steps.append({"gold": tool, "outcome": outcome, "chosen": chosen})
        case_pass = all(step["outcome"] == "hit" for step in steps) and not forbidden_hits
    elif expect == "gap":
        if forbidden_hits:
            outcome = "wrong_tool"
        elif has_gap or escalated:
            outcome = "hit"
        else:
            outcome = "missed_gap"
        steps = [{"gold": "∅", "outcome": outcome, "chosen": ",".join(forbidden_hits) or None}]
        case_pass = outcome == "hit"
    else:  # human: nothing may be auto-routed to a forbidden tool and the plan must stop for a person
        allowed = gold["statuses"] or ESCALATION_STATUSES
        outcome = "hit" if status in allowed and not forbidden_hits else ("wrong_tool" if forbidden_hits else "auto_routed")
        steps = [{"gold": "human", "outcome": outcome, "chosen": ",".join(forbidden_hits) or status}]
        case_pass = outcome == "hit"
    if gold.get("statuses") and status not in gold["statuses"]:
        case_pass = False
    return {"case_pass": case_pass, "steps": steps, "signature": signature, "forbidden_hits": forbidden_hits, "routed_tools": routed}


def action_summary(action: dict[str, Any]) -> dict[str, Any]:
    rationale = str(action.get("rationale", ""))
    return {
        "id": action.get("id"), "goal": str(action.get("goal", ""))[:160], "status": action.get("status"),
        "tool_id": action.get("tool_id"), "router": action.get("router"), "confidence": action.get("confidence"),
        "requires_confirmation": action.get("requires_confirmation"), "n_candidates": len(action.get("candidates", [])),
        "jev_fallback": "Jev routing unavailable" in rationale,
        "invalid_choice": "not a submitted candidate" in rationale,
        "llm_failed": rationale.startswith("LLM routing failed") or "LLM routing failed" in rationale,
        "rationale": rationale[:300],
    }


# ----------------------------------------------------------------------------
# Aggregation (pure)
# ----------------------------------------------------------------------------
def _step_choice(step: dict[str, Any]) -> str:
    return step["gold"] if step["outcome"] == "hit" else f"{step['outcome']}:{step.get('chosen') or ''}"


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Every metric for one group of records (one model, or one slice of it)."""
    first = [r for r in records if r["repeat"] == 0] or records
    positive_steps = [s for r in first if r["expect"] == "positive" for s in r["steps"]]
    analysis_steps = [s for s in positive_steps if s["gold"] not in PLUMBING]
    gap_steps = [s for r in first if r["expect"] == "gap" for s in r["steps"]]
    human_steps = [s for r in first if r["expect"] == "human" for s in r["steps"]]
    actions = [a for r in first for a in r.get("actions", [])]
    multi = [a for r in first if r.get("jev") != "off" for a in r.get("actions", []) if a["n_candidates"] > 1]
    latencies = [r["elapsed_s"] for r in first if r.get("elapsed_s") is not None]
    calls = [x for r in first for x in r.get("call_latencies", [])]
    replies = sum(r.get("replies", 0) for r in first)
    return {
        "cases": len(first),
        "workflow_exact_match": proportion(sum(r["case_pass"] for r in first), len(first)),
        "workflow_exact_match_excluding_transport_failures": proportion(sum(r["case_pass"] for r in first if not r.get("transport_errors")), sum(1 for r in first if not r.get("transport_errors"))),
        "plans_with_transport_error": proportion(sum(1 for r in first if r.get("transport_errors")), len(first)),
        "step_top1_all_gold_tools": accuracy([s["outcome"] for s in positive_steps]),
        "step_top1_analysis_tools": accuracy([s["outcome"] for s in analysis_steps]),
        "correct_capability_gap": accuracy([s["outcome"] for s in gap_steps]),
        "correct_escalation": accuracy([s["outcome"] for s in human_steps]),
        "false_null": proportion(sum(1 for s in analysis_steps if s["outcome"] == "null"), len(analysis_steps)),
        "wrong_tool_on_gold_step": proportion(sum(1 for s in positive_steps + gap_steps if s["outcome"] == "wrong_tool"), len(positive_steps) + len(gap_steps)),
        "null_action_rate": proportion(sum(1 for a in actions if a["status"] == "gap"), len(actions)),
        "needs_human_action_rate": proportion(sum(1 for a in actions if a["status"] != "routed" or a.get("requires_confirmation")), len(actions)),
        "plan_needs_human_rate": proportion(sum(1 for r in first if r["plan_status"] in {"needs_confirmation", "clarify", "refused"}), len(first)),
        "jev_to_llm_fallback": proportion(sum(1 for a in multi if a["jev_fallback"]), len(multi)),
        "parse_failure": proportion(sum(r.get("parse_failures", 0) for r in first), replies),
        "transport_error": proportion(sum(r.get("transport_errors", 0) for r in first), replies + sum(r.get("transport_errors", 0) for r in first)),
        "invalid_choice_action_rate": proportion(sum(1 for a in actions if a["invalid_choice"]), len(actions)),
        "plan_failed": proportion(sum(1 for r in first if r["plan_status"] == "failed"), len(first)),
        "plan_latency_s": {"median": _round(statistics.median(latencies)) if latencies else None, "p90": _round(percentile(latencies, 90))},
        "llm_call_latency_s": {"median": _round(statistics.median(calls)) if calls else None, "p90": _round(percentile(calls, 90)), "calls": len(calls)},
        "all_repeats": {"runs": len(records), "workflow_exact_match": proportion(sum(r["case_pass"] for r in records), len(records))},
    }


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


def aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    models = sorted({r["model"] for r in records})
    by_model, by_language, by_domain = {}, {}, {}
    for model in models:
        mine = [r for r in records if r["model"] == model]
        by_model[model] = summarize(mine)
        for language in ("zh", "en"):
            by_language[f"{model}|{language}"] = summarize([r for r in mine if r["language"] == language])
        for domain in sorted({r["domain"] for r in mine}):
            by_domain[f"{model}|{domain}"] = summarize([r for r in mine if r["domain"] == domain])
    overall = summarize([r for r in records if r["repeat"] == 0]) if records else {}
    first = [r for r in records if r["repeat"] == 0 and r["plan_status"] != "failed"]
    case_choices: dict[str, dict[str, Any]] = defaultdict(dict)
    step_choices: dict[str, dict[Any, Any]] = defaultdict(dict)
    language_of_case = {}
    for r in first:
        case_choices[r["model"]][r["case_id"]] = r["signature"]
        language_of_case[r["case_id"]] = r["language"]
        for index, step in enumerate(r["steps"]):
            step_choices[r["model"]][(r["case_id"], index, step["gold"])] = _step_choice(step)
    runs: dict[str, dict[str, list[Any]]] = defaultdict(lambda: defaultdict(list))
    for r in records:
        # Repeated transport/plan failures are not successful reproducibility.
        signature = r["signature"] if r["plan_status"] != "failed" else {"failed_repeat": r["repeat"]}
        runs[r["model"]][r["case_id"]].append(signature)
    cross = {
        "case_level": disagreement_rate(case_choices),
        "step_level": disagreement_rate(step_choices),
        "case_level_by_language": {
            lang: disagreement_rate({m: {c: s for c, s in choices.items() if language_of_case[c] == lang} for m, choices in case_choices.items()})
            for lang in ("zh", "en")
        },
        "models_compared": sorted(case_choices),
    }
    return {
        "overall_first_repeat_all_models": overall, "by_model": by_model, "by_model_language": by_language, "by_model_domain": by_domain,
        "cross_model_disagreement": cross,
        "self_consistency": {model: self_consistency(runs[model]) for model in models},
    }


# ----------------------------------------------------------------------------
# Gateway + execution (online)
# ----------------------------------------------------------------------------
class Gateway:
    """Minimal OpenAI-compatible client mirroring backend.main.model_completion (same endpoint, temperature 0.2)."""

    def __init__(self, base_url: str, key_env: str, timeout: int):
        self.base_url, self.timeout = base_url.rstrip("/"), timeout
        self._key = os.environ.get(key_env) or _user_scope_variable(key_env)

    @property
    def has_key(self) -> bool:
        return bool(self._key)

    def scrub(self, text: str) -> str:
        return text.replace(self._key, "***") if self._key else text

    def request(self, path: str, body: dict[str, Any] | None = None, timeout: int | None = None) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urlrequest.Request(self.base_url + path, data=data, method="POST" if body is not None else "GET",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {self._key}"})
        with urlrequest.urlopen(req, timeout=timeout or self.timeout) as response:
            return json.loads(response.read(2 * 1024 * 1024))

    def models(self) -> list[str]:
        return [item["id"] for item in self.request("/models", timeout=15).get("data", [])]

    def probe(self, model: str) -> str | None:
        """None when ``model`` answers, otherwise a short key-free reason."""
        reason = "unknown"
        for _ in range(3):  # the upstream stalls occasionally; a 403/404 is final, a timeout is retried
            try:
                self.request("/chat/completions", {"model": model, "messages": [{"role": "user", "content": "Reply OK."}], "max_tokens": 8}, timeout=90)
                return None
            except urlerror.HTTPError as exc:
                return f"HTTP {exc.code}"
            except Exception as exc:  # noqa: BLE001
                reason = self.scrub(f"{type(exc).__name__}: {exc}")[:120]
        return reason


def _user_scope_variable(name: str) -> str:
    if os.name != "nt":
        return ""
    try:
        completed = subprocess.run(["powershell", "-NoProfile", "-Command", f"[Environment]::GetEnvironmentVariable('{name}','User')"], capture_output=True, text=True, timeout=20, check=False)
        return completed.stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


class Job:
    def __init__(self, model: str, case: dict[str, Any], repeat: int):
        self.model, self.case, self.repeat = model, case, repeat

    @property
    def key(self) -> str:
        return f"{self.model}|{self.case['case_id']}|{self.repeat}"


@contextmanager
def jev_configuration(mode: str):
    """An explicit mode for this run, with no leaked temp folders or process state."""
    previous = os.environ.get("MATFLOW_JEV_ROUTER_CONFIG")
    source = Path(previous) if previous else ROOT / "config/jev_router.json"
    settings = _read(source)
    settings["router"]["enabled"] = mode == "on"
    with tempfile.TemporaryDirectory(prefix="matflow-eval-") as directory:
        override = Path(directory) / "jev_router.json"
        override.write_text(json.dumps(settings), encoding="utf-8")
        os.environ["MATFLOW_JEV_ROUTER_CONFIG"] = str(override)
        try:
            yield settings
        finally:
            if previous is None:
                os.environ.pop("MATFLOW_JEV_ROUTER_CONFIG", None)
            else:
                os.environ["MATFLOW_JEV_ROUTER_CONFIG"] = previous


def experiment_fingerprint(cases, registry, settings, gateway_url, timeout):
    """Bind checkpoint reuse to code, labels, input bytes and public run settings."""
    code = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT / "backend").rglob("*.py"))}
    code[Path(__file__).relative_to(ROOT).as_posix()] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    fixtures = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                for c in cases for name in c["fixtures"]}
    payload = {"code": code, "cases": cases, "fixtures": fixtures,
               "registry": registry, "jev": settings, "gateway": gateway_url,
               "timeout": timeout, "temperature": 0.2}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def run_job(job: Job, gateway: Gateway, jev_mode: str) -> dict[str, Any]:
    from backend.routing import parse_json_object
    from tests.reference_composition import workspace as reference_workspace

    latencies: list[float] = []
    stats = {"replies": 0, "parse_failures": 0, "transport_errors": 0, "rate_limited": 0}

    def adapter(messages, tools, provider_id=None, model=None):  # the model under test serves every call, like planner_model in production
        for attempt in range(4):
            started = time.monotonic()
            try:
                data = gateway.request("/chat/completions", {"model": job.model, "messages": messages, "temperature": 0.2})
                latencies.append(time.monotonic() - started)
                if os.getenv("MATFLOW_EVAL_VERBOSE"):
                    print(f"    call {job.model} {job.case['case_id'][:30]} {latencies[-1]:.1f}s", flush=True)
                message = data["choices"][0]["message"]
                stats["replies"] += 1
                try:
                    parse_json_object(message.get("content") or "")
                except ValueError:
                    stats["parse_failures"] += 1
                return message
            except urlerror.HTTPError as exc:
                if exc.code == 429 and attempt < 3:
                    stats["rate_limited"] += 1
                    time.sleep(2 ** attempt * 3)
                    continue
                stats["transport_errors"] += 1
                raise RuntimeError(gateway.scrub(f"Model provider request failed: HTTP {exc.code}")) from None
            except Exception as exc:  # noqa: BLE001
                stats["transport_errors"] += 1
                raise RuntimeError(gateway.scrub(f"Model provider request failed: {type(exc).__name__}: {exc}"))
        raise AssertionError("unreachable")

    case = job.case
    started = time.monotonic()
    error = None
    with tempfile.TemporaryDirectory() as directory:
        runtime = reference_workspace(Path(directory), model_complete=adapter)
        uploads = []
        for fixture in case["fixtures"]:
            source = ROOT / fixture
            stored = runtime.import_dataset(source.name, source.read_bytes(), "text/csv")
            uploads.append({"upload_id": stored["id"], "name": source.name})
        try:
            plan = runtime.plan_workflow(case["prompt"], task_id=f"{case['case_id']}-{job.model}-{job.repeat}"[:60], uploads=uploads, apply=False)
        except Exception as exc:  # noqa: BLE001
            error = gateway.scrub(f"{type(exc).__name__}: {exc}")[:300]
            plan = {"status": "failed", "actions": [], "reason": error}
    elapsed = time.monotonic() - started
    scored = score_plan(case, plan)
    return {
        "case_id": case["case_id"], "source": case["source"], "language": case["language"], "domain": case["domain"], "expect": case["expect"],
        "prompt_excerpt": case["prompt"][:140], "gold": case["gold"], "model": job.model, "repeat": job.repeat, "jev": jev_mode,
        "plan_status": plan.get("status"), "plan_reason": str(plan.get("reason") or plan.get("question") or "")[:300],
        "elapsed_s": round(elapsed, 2), "call_latencies": [round(x, 2) for x in latencies], "llm_calls": plan.get("llm_calls"),
        "actions": [action_summary(a) for a in plan.get("actions", [])], "error": error, **stats, **scored,
    }


def _infra_failed(row: dict[str, Any]) -> bool:
    """A plan whose outcome was decided by a transport failure rather than by the model."""
    return bool(row.get("transport_errors")) and (row.get("plan_status") == "failed" or any(a.get("llm_failed") or a.get("status") == "unrouted" for a in row.get("actions", [])))


def run_all(jobs: list[Job], gateway: Gateway, jev_mode: str, workers: int, per_model: int, checkpoint: Path | None, retry_infra: bool = False, *, experiment_id: str) -> list[dict[str, Any]]:
    done: dict[str, dict[str, Any]] = {}
    if checkpoint and checkpoint.exists():
        for line in checkpoint.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("experiment_id") != experiment_id:
                    raise ValueError("Checkpoint experiment mismatch (or legacy checkpoint): use a new checkpoint path")
                done[f"{row['model']}|{row['case_id']}|{row['repeat']}"] = row  # a later line replaces an earlier one
        if retry_infra:
            done = {key: row for key, row in done.items() if not _infra_failed(row)}
    pending = [job for job in jobs if job.key not in done]
    semaphores = defaultdict(lambda: threading.Semaphore(per_model))
    lock = threading.Lock()
    finished = 0

    def guarded(job: Job):
        with semaphores[job.model]:
            return run_job(job, gateway, jev_mode)

    print(f"{len(done)} cached, {len(pending)} to run with {workers} workers", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(guarded, job): job for job in pending}
        for future in as_completed(futures):
            job = futures[future]
            try:
                row = future.result()
            except Exception as exc:  # noqa: BLE001 - a harness bug must not lose the run
                error = gateway.scrub(f"{type(exc).__name__}: {exc}")[:300]
                row = {**job.case, "model": job.model, "repeat": job.repeat, "jev": jev_mode,
                       "plan_status": "failed", "plan_reason": error, "harness_error": error,
                       "prompt_excerpt": job.case["prompt"][:140], "elapsed_s": None,
                       "actions": [], **score_plan(job.case, {"status": "failed", "actions": []})}
            row["experiment_id"] = experiment_id
            done[job.key] = row
            with lock:
                finished += 1
                if checkpoint:
                    checkpoint.parent.mkdir(parents=True, exist_ok=True)
                    with checkpoint.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                if finished % 10 == 0 or finished == len(pending):
                    print(f"  {finished}/{len(pending)} done", flush=True)
    return [done[job.key] for job in jobs if job.key in done]


# ----------------------------------------------------------------------------
# Reports
# ----------------------------------------------------------------------------
def _pct(item: dict[str, Any] | None) -> str:
    if not item or item.get("rate") is None:
        return "n/a"
    low, high = item["ci95"]
    return f"{item['rate'] * 100:.0f}% ({item['k']}/{item['n']}) [{low * 100:.0f}-{high * 100:.0f}]"


def _lat(item: dict[str, Any]) -> str:
    return "n/a" if item.get("median") is None else f"{item['median']:.1f} / {item['p90']:.1f}"


def render_markdown(report: dict[str, Any]) -> str:
    meta, metrics, records = report["meta"], report["metrics"], report["records"]
    models = sorted(metrics["by_model"])
    lines = [
        "# Online routing evaluation", "",
        f"Generated {meta['generated_at']} - Jev `{meta['jev']}` - repeats {meta['repeats']} - registry: shipped reference catalogue ({len(meta['registry_tools'])} agent-selectable tools).",
        "Scope: routing-label coverage only; this does not verify DAG equivalence, execution, numerical accuracy or scientific validity.",
        f"Models evaluated: {', '.join(models)}." + (f" Unavailable (skipped): {', '.join(f'{k} ({v})' for k, v in meta['unavailable_models'].items())}." if meta["unavailable_models"] else ""),
        "", "Intervals are Wilson 95% on repeat 0 (n = cases/steps, so they are wide). See `docs/ROUTING_EVALUATION.md` for definitions and limitations.", "",
        "## Dataset", "",
        f"- {meta['dataset']['case_count']} labelled cases ({', '.join(f'{k}: {v}' for k, v in meta['dataset']['by_source'].items())}); "
        f"language {meta['dataset']['by_language']}; expectation {meta['dataset']['by_expectation']}.",
        f"- {meta['dataset']['excluded_count']} excluded for missing gold labels; {meta['dataset']['duplicates_removed']} duplicate prompts removed.", "",
        "## Headline per model (repeat 0)", "",
        "| model | workflow exact match | exact match excl. transport-failed plans | step top-1 (analysis tools) | correct gap | correct escalation | false-null | needs-human (actions) | Jev->LLM fallback | parse fail | plan latency s (med/p90) |", "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for model in models:
        m = metrics["by_model"][model]
        lines.append(f"| {model} | {_pct(m['workflow_exact_match'])} | {_pct(m['workflow_exact_match_excluding_transport_failures'])} ({_pct(m['plans_with_transport_error'])} plans hit a transport error) | {_pct(m['step_top1_analysis_tools'])} | {_pct(m['correct_capability_gap'])} | {_pct(m['correct_escalation'])} | {_pct(m['false_null'])} | {_pct(m['needs_human_action_rate'])} | {_pct(m['jev_to_llm_fallback'])} | {_pct(m['parse_failure'])} | {_lat(m['plan_latency_s'])} |")
    lines += ["", "## By language: workflow exact match / step top-1 (analysis tools)", "", "| model | zh exact | en exact | zh top-1 | en top-1 |", "|---|---|---|---|---|"]
    for model in models:
        zh, en = metrics["by_model_language"][f"{model}|zh"], metrics["by_model_language"][f"{model}|en"]
        lines.append(f"| {model} | {_pct(zh['workflow_exact_match'])} | {_pct(en['workflow_exact_match'])} | {_pct(zh['step_top1_analysis_tools'])} | {_pct(en['step_top1_analysis_tools'])} |")
    cross, consistency = metrics["cross_model_disagreement"], metrics["self_consistency"]
    lines += ["", "## Agreement", "",
              f"- Cross-model disagreement (case level, {len(cross['models_compared'])} models): {_pct(cross['case_level'])}; step level: {_pct(cross['step_level'])}; zh {_pct(cross['case_level_by_language']['zh'])}, en {_pct(cross['case_level_by_language']['en'])}.",
              "- Self-consistency across repeats (share of cases with identical routing every run): " + (", ".join(f"{m} {_pct(consistency[m])}" for m in models) if meta["repeats"] > 1 else "not measured (repeats = 1)") + ".", ""]
    lines += ["## By domain: workflow exact match", "", "| domain | " + " | ".join(models) + " |", "|---|" + "---|" * len(models)]
    domains = sorted({key.split("|", 1)[1] for key in metrics["by_model_domain"]})
    for domain in domains:
        cells = [_pct(metrics["by_model_domain"].get(f"{m}|{domain}", {}).get("workflow_exact_match")) for m in models]
        lines.append(f"| {domain} | " + " | ".join(cells) + " |")
    lines += ["", "## Other rates (repeat 0)", "", "| model | null-action rate | plan needs-human | wrong tool on gold step | invalid choice | plan failed | transport error | LLM call latency s (med/p90) |", "|---|---|---|---|---|---|---|---|"]
    for model in models:
        m = metrics["by_model"][model]
        lines.append(f"| {model} | {_pct(m['null_action_rate'])} | {_pct(m['plan_needs_human_rate'])} | {_pct(m['wrong_tool_on_gold_step'])} | {_pct(m['invalid_choice_action_rate'])} | {_pct(m['plan_failed'])} | {_pct(m['transport_error'])} | {_lat(m['llm_call_latency_s'])} |")
    misses = [r for r in records if not r["case_pass"]]
    lines += ["", f"## Misses ({len(misses)} of {len(records)} runs)", ""]
    for r in sorted(misses, key=lambda x: (x["model"], x["case_id"], x["repeat"])):
        routed = [f"{a['tool_id'] or a['status']}" for a in r["actions"]]
        why = [a["rationale"] for a in r["actions"] if a["status"] in {"gap", "unrouted"} or a["tool_id"] in r["forbidden_hits"]][:2]
        lines.append(f"- **{r['model']}** r{r['repeat']} `{r['case_id']}` [{r['language']}/{r['expect']}] \"{r['prompt_excerpt'].replace(chr(10), ' ')}\"  \n"
                     f"  gold: must={r['gold']['must'] or '-'} forbidden={r['gold']['forbidden'] or '-'}; plan status `{r['plan_status']}`; routed: {', '.join(routed) or '-'}; "
                     f"steps: {', '.join(s['gold'] + '=' + s['outcome'] for s in r['steps'])}; rationale: {' | '.join(why) or r['plan_reason'] or '-'}")
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--models", default="", help="comma-separated gateway models (default: models in config/llm.json)")
    parser.add_argument("--repeats", type=positive_int, default=3)
    parser.add_argument("--jev", choices=["on", "off"], default="on")
    parser.add_argument("--workers", type=positive_int, default=6)
    parser.add_argument("--per-model", type=positive_int, default=3, help="max concurrent requests per model")
    parser.add_argument("--sources", default="", help="comma-separated subset of: teaching_lab,prompt_stability,long_prompt,known_answer")
    parser.add_argument("--limit", type=int, default=0, help="keep only the first N cases (smoke test)")
    parser.add_argument("--sample", type=int, default=0, help="stratified deterministic subset of N cases (see stratified_order)")
    parser.add_argument("--checkpoint", default="", help="JSONL file to resume from / append to")
    parser.add_argument("--retry-infra", action="store_true", help="re-run checkpointed plans that hit a transport error (timeout, 5xx)")
    parser.add_argument("--timeout", type=positive_int, default=240, help="per-request timeout in seconds (production default is llm.json request_timeout_seconds=120)")
    parser.add_argument("--out-json", default=str(REPORT_JSON))
    parser.add_argument("--out-md", default=str(REPORT_MD))
    args = parser.parse_args(argv)

    sys.path.insert(0, str(ROOT))
    from backend.llm_config import load_llm_config
    config = load_llm_config()
    gateway = Gateway(config.base_url, config.gateway.api_key_env, args.timeout)
    if not gateway.has_key:
        print(f"Environment variable {config.gateway.api_key_env} is not set; cannot reach the gateway.")
        return 2
    try:
        available = gateway.models()
    except Exception as exc:  # noqa: BLE001
        print(f"LLM gateway unreachable at {config.base_url} ({type(exc).__name__}). Start it (scripts/start_llm.ps1) and retry.")
        return 2

    wanted = [m.strip() for m in args.models.split(",") if m.strip()] or list(config.models)
    unavailable = {m: "not exposed by gateway /v1/models" for m in wanted if m not in available}
    candidates = [m for m in wanted if m in available]
    unavailable.update({m: reason for m in candidates if (reason := gateway.probe(m))})
    models = [m for m in candidates if m not in unavailable]
    if not models:
        print(f"No usable model. Wanted {wanted}; unavailable: {unavailable}")
        return 2
    print(f"models: {models}; skipped: {unavailable}", flush=True)

    from tests.reference_composition import registry as reference_registry
    registry_tools = sorted(reference_registry().agent_selectable())
    cases, dataset = build_cases(set(registry_tools))
    if args.sources:
        keep = {s.strip() for s in args.sources.split(",")}
        cases = [c for c in cases if c["source"] in keep]
    if args.limit:
        cases = cases[: args.limit]
    if args.sample:
        cases = stratified_order(cases)[: args.sample]
    dataset["case_count"] = len(cases)
    dataset["by_source"] = dict(Counter(c["source"] for c in cases))
    dataset["by_expectation"] = dict(Counter(c["expect"] for c in cases))
    dataset["by_language"] = dict(Counter(c["language"] for c in cases))
    dataset["subset"] = f"stratified sample of {len(cases)}" if args.sample else ("first %d" % args.limit if args.limit else "all labelled cases")
    jobs = [Job(m, c, r) for r in range(args.repeats) for c in cases for m in models]
    print(f"{len(cases)} cases x {len(models)} models x {args.repeats} repeats = {len(jobs)} plans (Jev {args.jev})", flush=True)

    started = time.monotonic()
    with jev_configuration(args.jev) as settings:
        experiment_id = experiment_fingerprint(cases, [reference_registry().get(t).model_dump(mode="json") for t in registry_tools], settings, config.base_url, args.timeout)
        records = run_all(jobs, gateway, args.jev, args.workers, args.per_model, Path(args.checkpoint) if args.checkpoint else None, args.retry_infra, experiment_id=experiment_id)
    report = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "jev": args.jev, "repeats": args.repeats, "models": models,
            "experiment_id": experiment_id, "scheduled_plans": len(jobs), "recorded_plans": len(records), "request_timeout_s": args.timeout,
            "unavailable_models": unavailable, "gateway_models": available, "registry_tools": registry_tools, "dataset": dataset,
            "wall_clock_s": round(time.monotonic() - started), "temperature": 0.2,
            "note": "Gold labels are derived from repository suites; see docs/ROUTING_EVALUATION.md. No credentials are recorded.",
        },
        "metrics": aggregate(records),
        "records": records,
    }
    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_md).write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {args.out_json} and {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

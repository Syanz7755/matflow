"""Routing-evaluation harness.

* Offline (default suite): the metric helpers, gold derivation and plan scoring
  of ``examples/evaluate_routing_online.py`` against hand-built plans.
* Online (skipped unless ``MATFLOW_ONLINE=1``, or the older
  ``MATFLOW_RUN_LLM_APPLICATION_TESTS=1``): a small live smoke run through the
  real planner against the configured LLM gateway. The full evaluation is the
  script itself; see docs/ROUTING_EVALUATION.md.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "examples" / "evaluate_routing_online.py"
ONLINE = os.getenv("MATFLOW_ONLINE") == "1" or os.getenv("MATFLOW_RUN_LLM_APPLICATION_TESTS") == "1"


def load_module():
    sys.path.insert(0, str(ROOT / "examples"))
    try:
        spec = importlib.util.spec_from_file_location("evaluate_routing_online", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        sys.modules["evaluate_routing_online"] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


ev = load_module()


def action(tool=None, status="routed", **extra):
    return {"id": "a", "goal": "g", "status": status, "tool_id": tool, "router": "llm", "confidence": 0.9,
            "requires_confirmation": False, "candidates": ["x", "y"], "rationale": "", **extra}


def case(expect, must=(), forbidden=(), statuses=None):
    return {"case_id": "c", "expect": expect, "gold": {"must": list(must), "forbidden": list(forbidden), "statuses": statuses}}


class MetricTests(unittest.TestCase):
    def test_wilson_known_values(self):
        low, high = ev.wilson_interval(8, 10)
        self.assertAlmostEqual(low, 0.4902, places=3)
        self.assertAlmostEqual(high, 0.9433, places=3)
        self.assertEqual(ev.wilson_interval(0, 0), None)
        low, high = ev.wilson_interval(10, 10)
        self.assertAlmostEqual(high, 1.0, places=6)
        self.assertLess(low, 0.8)
        low, high = ev.wilson_interval(0, 10)
        self.assertEqual(low, 0.0)
        self.assertGreater(high, 0.2)

    def test_accuracy_and_proportion(self):
        result = ev.accuracy(["hit", "hit", "null", "wrong_tool"])
        self.assertEqual((result["k"], result["n"], result["rate"]), (2, 4, 0.5))
        self.assertIsNone(ev.accuracy([])["rate"])

    def test_percentile(self):
        self.assertEqual(ev.percentile([1, 2, 3, 4, 5], 50), 3)
        self.assertAlmostEqual(ev.percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 90), 9.1)
        self.assertIsNone(ev.percentile([], 90))

    def test_disagreement_counts_only_units_with_two_answers(self):
        rate = ev.disagreement_rate({
            "m1": {"a": "x", "b": "y", "c": "z"},
            "m2": {"a": "x", "b": "q"},
            "m3": {"a": "x", "b": "y"},
        })
        self.assertEqual((rate["k"], rate["n"]), (1, 2))  # b differs; c has one answer only

    def test_self_consistency(self):
        rate = ev.self_consistency({"a": [{"t": 1}, {"t": 1}, {"t": 1}], "b": [{"t": 1}, {"t": 2}], "c": [{"t": 3}]})
        self.assertEqual((rate["k"], rate["n"]), (1, 2))

    def test_language_tag(self):
        self.assertEqual(ev.language_of("对一份阻抗做检查"), "zh")
        self.assertEqual(ev.language_of("Run EIS QC"), "en")


class CaseSelectionTests(unittest.TestCase):
    """The ``--cases`` filter: a frozen id list must select exactly those cases, in order."""

    def setUp(self):
        self.cases = [ev._case(cid, "test", f"prompt {cid}", "eis", "positive", [], ["eis_basic_qc"])
                      for cid in ("a", "b", "c")]

    def test_absent_flag_keeps_every_case_unchanged(self):
        selected, unknown = ev.select_cases(self.cases, "")
        self.assertEqual(selected, self.cases)
        self.assertEqual(unknown, [])

    def test_selection_follows_the_spec_order(self):
        selected, unknown = ev.select_cases(self.cases, "c, a")
        self.assertEqual([c["case_id"] for c in selected], ["c", "a"])
        self.assertEqual(unknown, [])

    def test_repeated_ids_run_once(self):
        selected, _ = ev.select_cases(self.cases, "b,b,a")
        self.assertEqual([c["case_id"] for c in selected], ["b", "a"])

    def test_unknown_ids_are_reported_rather_than_ignored(self):
        selected, unknown = ev.select_cases(self.cases, "a,nope,other")
        self.assertEqual([c["case_id"] for c in selected], ["a"])
        self.assertEqual(unknown, ["nope", "other"])

    def test_frozen_demo10_selection_rebuilds_offline(self):
        """The frozen 10-case file must name cases that build_cases still produces, with the same gold."""
        from tests.reference_composition import registry as reference_registry
        cases, _ = ev.build_cases(set(reference_registry().agent_selectable()))
        frozen = json.loads((ROOT / "tests" / "suites" / "demo10_routing_cases.json").read_text(encoding="utf-8"))
        selected, unknown = ev.select_cases(cases, ",".join(entry["case_id"] for entry in frozen))
        self.assertEqual(unknown, [])
        self.assertEqual([c["case_id"] for c in selected], [entry["case_id"] for entry in frozen])
        for entry, built in zip(frozen, selected):
            self.assertEqual(entry["prompt"], built["prompt"])
            self.assertEqual((entry["expect"], entry["language"]), (built["expect"], built["language"]))
            self.assertEqual(entry["gold"]["must"], built["gold"]["must"])
            self.assertEqual(entry["gold"]["forbidden"], built["gold"]["forbidden"])
            self.assertEqual(entry["gold"]["statuses"], built["gold"]["statuses"])
            self.assertEqual(entry["fixtures"], built["fixtures"])


class ScoringTests(unittest.TestCase):
    def test_positive_labels_do_not_override_disallowed_status(self):
        scored = ev.score_plan(case("positive", ["eis_basic_qc"], statuses=["planned"]),
                               {"status": "needs_confirmation", "actions": [action("eis_basic_qc")]})
        self.assertFalse(scored["case_pass"])

    def test_positive_hit_and_wrong_tool(self):
        gold = case("positive", ["eis_basic_qc"], ["skill_node"])
        hit = ev.score_plan(gold, {"status": "planned", "actions": [action("raw_file_import"), action("eis_basic_qc")]})
        self.assertTrue(hit["case_pass"])
        self.assertEqual(hit["steps"][0]["outcome"], "hit")
        wrong = ev.score_plan(gold, {"status": "needs_confirmation", "actions": [action("raw_file_import"), action("skill_node")]})
        self.assertFalse(wrong["case_pass"])
        self.assertEqual(wrong["steps"][0]["outcome"], "wrong_tool")

    def test_false_null_is_distinguished_from_wrong_tool(self):
        gold = case("positive", ["xrd_peak_extraction"], [])
        scored = ev.score_plan(gold, {"status": "needs_confirmation", "actions": [action(status="gap")]})
        self.assertEqual(scored["steps"][0]["outcome"], "null")

    def test_gap_cases(self):
        gold = case("gap", [], ["skill_node", "xrd_*"])
        self.assertTrue(ev.score_plan(gold, {"status": "needs_confirmation", "actions": [action("raw_file_import"), action(status="gap")]})["case_pass"])
        self.assertEqual(ev.score_plan(gold, {"status": "needs_confirmation", "actions": [action("skill_node")]})["steps"][0]["outcome"], "wrong_tool")
        self.assertEqual(ev.score_plan(gold, {"status": "planned", "actions": [action("raw_file_import")]})["steps"][0]["outcome"], "missed_gap")

    def test_human_cases_need_an_escalation(self):
        gold = case("human", [], ["*"], ["clarify", "refused"])
        self.assertTrue(ev.score_plan(gold, {"status": "refused", "actions": []})["case_pass"])
        self.assertEqual(ev.score_plan(gold, {"status": "planned", "actions": [action("eis_basic_qc")]})["steps"][0]["outcome"], "wrong_tool")

    def test_failed_plan_counts_as_error_not_hit(self):
        scored = ev.score_plan(case("positive", ["eis_basic_qc"]), {"status": "failed", "actions": []})
        self.assertFalse(scored["case_pass"])
        self.assertEqual(scored["steps"][0]["outcome"], "error")

    def test_aggregate_end_to_end(self):
        def record(model, repeat, tool, language="zh"):
            plan = {"status": "planned", "actions": [action(tool)]}
            c = case("positive", ["eis_basic_qc"])
            scored = ev.score_plan(c, plan)
            return {"case_id": "c", "model": model, "repeat": repeat, "language": language, "domain": "eis", "expect": "positive",
                    "plan_status": "planned", "actions": [ev.action_summary(a) for a in plan["actions"]], "elapsed_s": 2.0,
                    "call_latencies": [1.0], "replies": 2, "parse_failures": 0, "transport_errors": 0, **scored}
        records = [record("m1", 0, "eis_basic_qc"), record("m1", 1, "skill_node"), record("m2", 0, "skill_node")]
        metrics = ev.aggregate(records)
        self.assertEqual(metrics["by_model"]["m1"]["step_top1_analysis_tools"]["rate"], 1.0)
        self.assertEqual(metrics["by_model"]["m2"]["workflow_exact_match"]["rate"], 0.0)
        self.assertEqual(metrics["cross_model_disagreement"]["case_level"]["rate"], 1.0)
        self.assertEqual(metrics["self_consistency"]["m1"]["rate"], 0.0)

    def test_gold_derivation_covers_every_suite_and_excludes_nothing_silently(self):
        cases, report = ev.build_cases({"eis_basic_qc", "plot_nyquist", "xrd_peak_extraction", "xrd_reference_match", "ftir_peak_extraction", "ftir_band_assignment", "raw_file_import", "skill_node"})
        self.assertEqual(report["case_count"], len(cases))
        self.assertGreater(len(cases), 80)
        self.assertEqual({c["language"] for c in cases}, {"zh", "en"})
        self.assertEqual(len({(c["prompt"].strip(), tuple(c["fixtures"])) for c in cases}), len(cases))
        self.assertIn("xrd_reference_match", next(c for c in cases if c["case_id"].startswith("02_xrd") and c["expect"] == "positive")["gold"]["must"])
        self.assertTrue(all(c["gold"]["must"] or c["expect"] != "positive" for c in cases))


class IsolationTests(unittest.TestCase):
    def test_jev_override_is_scoped_and_removed_on_error(self):
        with patch.dict(os.environ, {"MATFLOW_JEV_ROUTER_CONFIG": str(ROOT / "config/jev_router.json")}):
            previous = os.environ["MATFLOW_JEV_ROUTER_CONFIG"]
            with self.assertRaisesRegex(RuntimeError, "sentinel"):
                with ev.jev_configuration("off"):
                    path = Path(os.environ["MATFLOW_JEV_ROUTER_CONFIG"])
                    self.assertFalse(json.loads(path.read_text())["router"]["enabled"])
                    raise RuntimeError("sentinel")
            self.assertEqual(os.environ["MATFLOW_JEV_ROUTER_CONFIG"], previous)
            self.assertFalse(path.exists())
            with ev.jev_configuration("on"):
                self.assertTrue(json.loads(Path(os.environ["MATFLOW_JEV_ROUTER_CONFIG"]).read_text())["router"]["enabled"])

    def test_checkpoint_refuses_another_experiment_before_calling_model(self):
        job = ev.Job("m", {"case_id": "c"}, 0)
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.jsonl"
            checkpoint.write_text(json.dumps({"model": "m", "case_id": "c", "repeat": 0,
                                              "experiment_id": "jev-off"}) + "\n")
            with self.assertRaisesRegex(ValueError, "experiment"):
                ev.run_all([job], None, "on", 1, 1, checkpoint, experiment_id="jev-on")

    def test_harness_failure_is_recorded_as_failure(self):
        c = ev._case("c", "test", "QC", "eis", "positive", [], ["eis_basic_qc"])
        with patch.object(ev, "run_job", side_effect=OSError("fixture unavailable")):
            rows = ev.run_all([ev.Job("m", c, 0)], type("Gateway", (), {"scrub": staticmethod(str)})(),
                              "off", 1, 1, None, experiment_id="test")
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["case_pass"])
        self.assertEqual(rows[0]["plan_status"], "failed")

    def test_matching_checkpoint_is_reused_without_network(self):
        c = ev._case("c", "test", "QC", "eis", "positive", [], ["eis_basic_qc"])
        row = {"model": "m", "case_id": "c", "repeat": 0, "experiment_id": "same"}
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.jsonl"
            checkpoint.write_text(json.dumps(row) + "\n")
            with patch.object(ev, "run_job") as run:
                self.assertEqual(ev.run_all([ev.Job("m", c, 0)], None, "off", 1, 1, checkpoint,
                                            experiment_id="same"), [row])
                run.assert_not_called()

    def test_failed_repeat_cannot_disappear_from_consistency(self):
        c = ev._case("c", "test", "QC", "eis", "positive", [], ["eis_basic_qc"])
        records = []
        for repeat, status in enumerate(["planned", "planned", "failed"]):
            plan = {"status": status, "actions": [action("eis_basic_qc")] if status != "failed" else []}
            records.append({"model": "m", "case_id": "c", "repeat": repeat, "language": "en", "domain": "eis",
                            "expect": "positive", "plan_status": status, "actions": [], **ev.score_plan(c, plan)})
        self.assertEqual(ev.aggregate(records)["self_consistency"]["m"]["rate"], 0.0)


@unittest.skipUnless(ONLINE, "set MATFLOW_ONLINE=1 to route live against the configured LLM gateway")
class OnlineRoutingSmoke(unittest.TestCase):
    def test_eis_known_answer_routes_to_eis_basic_qc(self):
        model = os.getenv("MATFLOW_ONLINE_MODEL", "qwen")
        out = Path(os.getenv("TEMP", "/tmp"))
        status = ev.main(["--models", model, "--repeats", "1", "--sources", "known_answer", "--limit", "2", "--jev", os.getenv("MATFLOW_ONLINE_JEV", "off"),
                          "--out-json", str(out / "routing_smoke.json"), "--out-md", str(out / "routing_smoke.md")])
        self.assertEqual(status, 0, "gateway unreachable or model unavailable")
        import json
        report = json.loads((out / "routing_smoke.json").read_text(encoding="utf-8"))
        eis = next(r for r in report["records"] if r["case_id"] == "known:01_eis_basic_qc")
        self.assertIn("eis_basic_qc", eis["routed_tools"], eis["plan_reason"])


if __name__ == "__main__":
    unittest.main()

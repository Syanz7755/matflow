"""Chinese prompts reach the routing models intact and never change candidate retrieval.

Retrieval is a type filter (no tokenisation, no lexical score), so the prompt's language cannot
influence which tools are candidates; the decision is made by Jev or the LLM, which receive the
prompt text verbatim. Prompts are the Chinese cases of ``examples/evaluate_jev_routing.py``.
"""
import json
import unittest

from backend.contracts import TaskState
from backend.jev_routing import JevConfig, JevDecisionRouter
from backend.routing import CandidateRetriever, LLMToolSelector, ToolSelector
from backend.tool_registry import ToolRegistry

# (Chinese prompt, English equivalent), taken from examples/evaluate_jev_routing.py CASES.
PROMPT_PAIRS = (
    ("对一份阻抗频率扫描做基础 EIS 质量检查，并绘制 Nyquist 图。",
     "Run a basic EIS quality check on an impedance frequency sweep and draw a Nyquist plot."),
    ("提取 XRD 峰，并判断这份样品最可能的 TiO2 晶相。",
     "Extract the XRD peaks and decide the most likely TiO2 phase of this sample."),
    ("在 600–850 °C 的失重步骤中估算样品的 CaCO3 质量分数。",
     "Estimate the CaCO3 mass fraction from the 600-850 C mass-loss step."),
)


def make_registry() -> ToolRegistry:
    def tool(label, inputs, description):
        return {"label": label, "category": "Test", "inputs": inputs, "outputs": {"artifact": "Artifact"}, "description": description}

    return ToolRegistry({
        "eis_basic_qc": tool("EIS QC", {"data": "TypedTable"}, "Basic EIS quality checks."),
        "xrd_phase_identification": tool("XRD phase", {"data": "TypedTable"}, "Identify crystalline phases from XRD peaks."),
        "tga_caco3_estimation": tool("TGA CaCO3", {"data": "TypedTable"}, "Estimate CaCO3 content from TGA mass loss."),
        "needs_raw": tool("Raw only", {"data": "RawData"}, "Requires raw data."),
    })


def ids(candidates):
    return [candidate.tool_id for candidate in candidates]


class CandidateRetrievalIsLanguageIndependentTests(unittest.TestCase):
    def setUp(self):
        self.registry = make_registry()

    def retrieve(self, message, types):
        task = TaskState(user_message=message, graph_version=0, available_input_types=types)
        return CandidateRetriever().retrieve(task, self.registry)

    def test_chinese_and_english_prompts_get_the_identical_candidate_set(self):
        for types in (["TypedTable"], ["TypedTable", "RawData"], ["RawData"]):
            for chinese, english in PROMPT_PAIRS:
                with self.subTest(types=types, prompt=chinese):
                    zh = self.retrieve(chinese, types)
                    en = self.retrieve(english, types)
                    self.assertEqual(zh, en)
                    self.assertEqual(ids(zh), sorted(ids(zh)))

    def test_candidates_are_chosen_by_type_only_and_carry_no_lexical_score(self):
        found = self.retrieve(PROMPT_PAIRS[0][0], ["TypedTable"])
        self.assertIn("eis_basic_qc", ids(found))
        self.assertNotIn("needs_raw", ids(found))
        self.assertEqual({candidate.score for candidate in found}, {0.0})

    def test_a_pure_chinese_prompt_is_not_an_empty_query(self):
        found = ids(self.retrieve("请对这个阻抗谱数据做基础质检", ["TypedTable"]))
        for tool_id in ("eis_basic_qc", "xrd_phase_identification", "tga_caco3_estimation"):
            self.assertIn(tool_id, found)


class ChineseTextReachesTheModelsTests(unittest.TestCase):
    def setUp(self):
        self.registry = make_registry()
        self.candidates = CandidateRetriever().retrieve(
            TaskState(user_message="x", graph_version=0, available_input_types=["TypedTable"]), self.registry)

    def test_llm_selector_payload_carries_the_chinese_request_unescaped(self):
        for chinese, _ in PROMPT_PAIRS:
            with self.subTest(prompt=chinese):
                sent = []

                def complete(messages):
                    sent.append(messages)
                    return json.dumps({"tool_id": "eis_basic_qc", "confidence": 0.9, "rationale": "阻抗谱", "params": {}}, ensure_ascii=False)

                opinion = LLMToolSelector(complete).select({"request": chinese}, self.candidates, self.registry)
                user_content = sent[0][-1]["content"]
                self.assertIn(chinese, user_content)  # not \uXXXX-escaped
                self.assertEqual(json.loads(user_content)["work"]["request"], chinese)
                self.assertEqual(opinion.selected_tool_id, "eis_basic_qc")
                self.assertEqual(opinion.evidence["rationale"], "阻抗谱")

    def test_tool_selector_falls_back_to_the_llm_with_the_task_message_intact(self):
        chinese = PROMPT_PAIRS[1][0]
        sent = []

        def complete(messages):
            sent.append(messages[-1]["content"])
            return json.dumps({"tool_id": "xrd_phase_identification", "confidence": 0.95, "rationale": "ok"})

        task = TaskState(user_message=chinese, graph_version=0, available_input_types=["TypedTable"])
        selection = ToolSelector(None, LLMToolSelector(complete)).select(task, self.candidates, self.registry)
        self.assertEqual(selection.selected.tool_id, "xrd_phase_identification")
        self.assertEqual(json.loads(sent[0])["work"]["request"], chinese)

    def test_jev_request_bodies_carry_the_chinese_prompt_intact_and_survive_json(self):
        chinese = PROMPT_PAIRS[2][0]
        bodies = []

        def transport(profile, body, timeout_seconds):
            bodies.append(body)
            if profile.kind == "jev_laya":
                return {"answers": {"tool_selection": {"choice": "tga_caco3_estimation", "confidence": 0.9, "probabilities": {}}}}
            ordered = [item["id"] for item in body["options"]]
            return {"probabilities": [1.0 if tool_id == "tga_caco3_estimation" else 0.0 for tool_id in ordered]}

        profiles = {
            "calibrated": {"kind": "jev_laya", "base_url": "http://decision.invalid", "model": "m1"},
            "semantic": {"kind": "jev_semantic", "base_url": "http://decision.invalid", "model": "m2"},
        }
        config = JevConfig.model_validate({
            "version": 1,
            "router": {"enabled": True, "strategy": "consensus", "profiles": list(profiles), "minimum_calibrated_confidence": 0.7, "fallback": "llm"},
            "profiles": profiles,
        })
        task = TaskState(user_message=chinese, graph_version=0, available_input_types=["TypedTable"], assumptions=["样品已归一化"])
        selected, _, confirmation, _, _ = JevDecisionRouter(config, transport=transport).decide(task, self.candidates, self.registry)
        self.assertEqual(selected.tool_id, "tga_caco3_estimation")
        self.assertFalse(confirmation)
        self.assertEqual(len(bodies), 2)
        for body in bodies:
            self.assertEqual(body["state"]["body"], chinese)
            self.assertEqual(body["state"]["assumptions"], ["样品已归一化"])
            # the on-the-wire encoding used by the real transport round-trips losslessly
            wire = json.dumps(body).encode("utf-8")
            self.assertEqual(json.loads(wire)["state"]["body"], chinese)


class FlowviewPreviewMatchesBackendTests(unittest.TestCase):
    def test_flowview_dry_route_lists_the_backend_candidates_for_chinese_and_english(self):
        from flowview.backend_adapter import dry_route

        def candidate_tools(prompt):
            document = dry_route(prompt)
            self.assertEqual(document.meta.get("mode"), "dry-run", document.meta)
            phase = next(phase for phase in document.phases if phase.name == "candidates")
            return [step.tools[0] for step in phase.steps if step.tools], document

        zh_tools, zh_doc = candidate_tools(PROMPT_PAIRS[0][0])
        en_tools, _ = candidate_tools(PROMPT_PAIRS[0][1])
        self.assertEqual(zh_tools, en_tools)
        self.assertTrue(zh_tools)
        prompt_phase = next(phase for phase in zh_doc.phases if phase.name == "prompt")
        self.assertEqual(prompt_phase.steps[0].detail, PROMPT_PAIRS[0][0])
        self.assertEqual(zh_doc.meta["routing_preview"], "verbatim")
        self.assertNotIn("retriever_tokens", zh_doc.meta)

    def test_an_overlong_chinese_prompt_is_cut_by_characters_not_emptied(self):
        from flowview.backend_adapter import MAX_TASK_MESSAGE, _route_preview_message

        prompt = "请对阻抗谱数据做基础质检。" * 400
        preview, shortened = _route_preview_message(prompt)
        self.assertTrue(shortened)
        self.assertEqual(preview, prompt[:MAX_TASK_MESSAGE])


if __name__ == "__main__":
    unittest.main()

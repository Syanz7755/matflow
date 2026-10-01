import unittest

from pydantic import ValidationError

from backend.contracts import RouterCandidate, TaskState
from backend.jev_routing import JevConfig, JevDecisionRouter
from backend.tool_registry import ToolRegistry


def router_config(*, strategy="consensus", threshold=0.7, fallback=True):
    profiles = {
        "calibrated": {
            "kind": "jev_laya",
            "base_url": "http://decision.invalid",
            "model": "configured-calibrated-model",
        },
        "semantic": {
            "kind": "jev_semantic",
            "base_url": "http://decision.invalid",
            "model": "configured-semantic-model",
        },
    }
    return {
        "version": 1,
        "router": {
            "enabled": True,
            "strategy": strategy,
            "profiles": list(profiles),
            "minimum_calibrated_confidence": threshold,
            "fallback_to_lexical": fallback,
        },
        "profiles": profiles,
    }


def configured_router(transport, *, strategy="consensus", threshold=0.7, fallback=True):
    config = JevConfig.model_validate(router_config(
        strategy=strategy, threshold=threshold, fallback=fallback
    ))
    return JevDecisionRouter(config, transport=transport)


class JevDecisionBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry({
            "candidate_alpha": {
                "label": "Candidate Alpha",
                "category": "Test",
                "inputs": {"data": "TypedTable"},
                "outputs": {"artifact": "Artifact"},
                "description": "Analyze the first applicable material signal.",
            },
            "candidate_beta": {
                "label": "Candidate Beta",
                "category": "Test",
                "inputs": {"data": "TypedTable"},
                "outputs": {"artifact": "Artifact"},
                "description": "Analyze the second applicable material signal.",
            },
        })
        self.candidates = [
            RouterCandidate(tool_id=tool_id, version=self.registry.get(tool_id).version, score=0.5)
            for tool_id in ("candidate_alpha", "candidate_beta")
        ]
        self.task = TaskState(
            user_message="Analyze the supplied measurement.",
            graph_version=0,
            available_input_types=["TypedTable"],
            assumptions=["The measurement has already been normalized."],
        )

    @staticmethod
    def response_for(profile, selected_id, confidence=0.9):
        if profile.kind == "jev_laya":
            return {"answers": {"tool_selection": {
                "choice": selected_id,
                "confidence": confidence,
                "probabilities": {selected_id: confidence},
            }}}
        if selected_id is None:
            return {"probabilities": []}
        return {"probabilities": [
            1.0 if candidate == selected_id else 0.0
            for candidate in ("candidate_alpha", "candidate_beta")
        ]}

    def test_consensus_selects_the_candidate_all_configured_profiles_agree_on(self):
        selected_id = self.candidates[-1].tool_id

        def transport(profile, body, timeout_seconds):
            self.assertGreater(timeout_seconds, 0)
            return self.response_for(profile, selected_id)

        selected, confidence, confirmation, evidence, _ = configured_router(transport).decide(
            self.task, self.candidates, self.registry
        )

        self.assertEqual(selected.tool_id, selected_id)
        self.assertEqual({item.selected_tool_id for item in evidence}, {selected_id})
        self.assertGreater(confidence, 0)
        self.assertFalse(confirmation)

    def test_consensus_requires_confirmation_when_profiles_disagree(self):
        selections = iter(candidate.tool_id for candidate in self.candidates)

        def transport(profile, body, timeout_seconds):
            return self.response_for(profile, next(selections))

        selected, _, confirmation, evidence, _ = configured_router(transport).decide(
            self.task, self.candidates, self.registry
        )

        self.assertIsNone(selected)
        self.assertTrue(confirmation)
        self.assertEqual(len(evidence), 2)

    def test_consensus_requires_every_profile_to_return_a_valid_choice(self):
        selected_id = self.candidates[0].tool_id

        def transport(profile, body, timeout_seconds):
            choice = selected_id if profile.kind == "jev_laya" else None
            return self.response_for(profile, choice)

        selected, _, confirmation, _, _ = configured_router(transport).decide(
            self.task, self.candidates, self.registry
        )

        self.assertIsNone(selected)
        self.assertTrue(confirmation)

    def test_low_calibrated_confidence_blocks_automatic_routing(self):
        threshold = 0.63
        selected_id = self.candidates[0].tool_id

        def transport(profile, body, timeout_seconds):
            return self.response_for(profile, selected_id, confidence=threshold - 0.01)

        selected, confidence, confirmation, _, rationale = configured_router(
            transport, threshold=threshold
        ).decide(self.task, self.candidates, self.registry)

        self.assertEqual(selected.tool_id, selected_id)
        self.assertLess(confidence, threshold)
        self.assertTrue(confirmation)
        self.assertIn("threshold", rationale.lower())

    def test_gateway_cannot_select_a_candidate_that_was_not_submitted(self):
        unknown_id = "outside_submitted_candidates"

        def transport(profile, body, timeout_seconds):
            return self.response_for(profile, unknown_id)

        selected, _, confirmation, _, rationale = configured_router(transport).decide(
            self.task, self.candidates, self.registry
        )

        self.assertIsNone(selected)
        self.assertTrue(confirmation)
        self.assertIn("valid candidate", rationale.lower())

    def test_transport_failure_uses_configured_safe_fallback(self):
        def transport(profile, body, timeout_seconds):
            raise OSError("gateway unavailable")

        selected, _, confirmation, _, rationale = configured_router(transport).decide(
            self.task, self.candidates, self.registry
        )

        self.assertIsNone(selected)
        self.assertTrue(confirmation)
        self.assertIn("fallback", rationale.lower())

    def test_disabled_or_single_candidate_routing_does_not_contact_gateway(self):
        calls = []

        def transport(profile, body, timeout_seconds):
            calls.append(body)
            raise AssertionError("transport must not be used")

        router = configured_router(transport)
        selected, _, confirmation, evidence, _ = router.decide(
            self.task, self.candidates[:1], self.registry
        )

        self.assertIsNone(selected)
        self.assertFalse(confirmation)
        self.assertEqual(evidence, [])
        self.assertEqual(calls, [])

    def test_requests_preserve_task_context_and_candidate_identity(self):
        submitted = []
        selected_id = self.candidates[0].tool_id

        def transport(profile, body, timeout_seconds):
            submitted.append(body)
            return self.response_for(profile, selected_id)

        configured_router(transport).decide(self.task, self.candidates, self.registry)

        serialized = str(submitted)
        self.assertIn(self.task.user_message, serialized)
        self.assertIn(self.task.assumptions[0], serialized)
        for candidate in self.candidates:
            self.assertIn(candidate.tool_id, serialized)

    def test_consensus_configuration_rejects_duplicate_profiles(self):
        config = router_config()
        config["router"]["profiles"] = [config["router"]["profiles"][0]] * 2

        with self.assertRaises(ValidationError):
            JevConfig.model_validate(config)


if __name__ == "__main__":
    unittest.main()

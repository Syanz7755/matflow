"""Deterministic candidate retrieval and routing for the contract-first baseline."""
from __future__ import annotations

import re

from .contracts import ModelDecisionEvidence, RouterCandidate, RouterDecision, TaskState, ToolSpec
from .jev_routing import JevDecisionRouter
from .tool_registry import ToolRegistry


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) > 1}


class CandidateRetriever:
    """Find compatible tools using transparent type filtering and lexical scoring."""

    def retrieve(self, task: TaskState, registry: ToolRegistry) -> list[RouterCandidate]:
        query = _tokens(task.user_message)
        available = set(task.available_input_types)
        registry.type_registry.validate_port_types(available)
        candidates: list[RouterCandidate] = []
        for spec in registry.active().values():
            if spec.inputs and not all(
                any(registry.type_registry.can_flow(source, required) for source in available)
                for required in spec.inputs.values()
            ):
                continue
            terms = _tokens(" ".join((spec.tool_id, spec.label, spec.description)))
            matched = sorted(query & terms)
            if not matched:
                continue
            score = min(1.0, len(matched) / max(1, min(len(query), 4)))
            reasons = [f"matches: {', '.join(matched)}"]
            if spec.inputs:
                reasons.append("input ports are compatible")
            candidates.append(RouterCandidate(tool_id=spec.tool_id, version=spec.version, score=score, reasons=reasons))
        return sorted(candidates, key=lambda candidate: (-candidate.score, candidate.tool_id))


class DecisionRouter:
    """Produce an auditable route; a future model adapter can sit behind this interface."""

    def __init__(self, retriever: CandidateRetriever | None = None, jev_router: JevDecisionRouter | None = None):
        self._retriever = retriever or CandidateRetriever()
        self._jev_router = jev_router

    def decide(self, task: TaskState, registry: ToolRegistry) -> RouterDecision:
        candidates = self._retriever.retrieve(task, registry)
        if not candidates:
            return RouterDecision(
                task_id=task.task_id,
                graph_version=task.graph_version,
                candidates=[],
                selected=[],
                confidence=0,
                rationale="No active compatible tool matched the request.",
                requires_human_confirmation=True,
            )
        winner = candidates[0]
        spec: ToolSpec = registry.get(winner.tool_id)
        confirmation = winner.score < 0.6 or spec.risk_level != "low"
        model_decisions: list[ModelDecisionEvidence] = []
        rationale = f"Selected {spec.label} from {len(candidates)} compatible candidate(s)."
        if self._jev_router:
            model_winner, model_confidence, model_confirmation, selections, model_rationale = self._jev_router.decide(task, candidates, registry)
            model_decisions = [ModelDecisionEvidence.model_validate(selection.model_dump()) for selection in selections]
            if model_winner:
                winner = model_winner
                spec = registry.get(winner.tool_id)
                confirmation = model_confirmation or spec.risk_level != "low"
                confidence = model_confidence
            else:
                confirmation = confirmation or model_confirmation
                confidence = winner.score
            rationale = model_rationale
        else:
            confidence = winner.score
        return RouterDecision(
            task_id=task.task_id,
            graph_version=task.graph_version,
            candidates=candidates,
            selected=[winner],
            confidence=confidence,
            rationale=rationale,
            requires_human_confirmation=confirmation,
            model_decisions=model_decisions,
        )

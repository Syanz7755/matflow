"""Candidate retrieval and model-based tool selection.

Retrieval is a deterministic *type* filter: a candidate is any active,
agent-selectable tool whose input ports accept the data that is available.
Nothing here scores words. Which candidate actually performs the requested
work is decided by a model — the Jev decision gateway when it is enabled and
answers, otherwise the configured LLM. Without a model the router selects
nothing and asks a human; a keyword overlap never selects a tool.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .contracts import ModelDecisionEvidence, RouterCandidate, RouterDecision, TaskState, ToolSpec
from .jev_routing import JevDecisionRouter, JevUnavailableError
from .observability import audit
from .tool_registry import ToolRegistry

#: ``(messages) -> assistant text``. The runtime binds this to the LLM gateway.
TextCompletion = Callable[[list[dict[str, Any]]], str]

#: Below this self-reported LLM confidence a selection still needs a human.
LLM_MIN_CONFIDENCE = 0.6


def with_retry(complete: TextCompletion, attempts: int = 2) -> TextCompletion:
    """Retry a transport failure (timeout, 5xx) once; a bad answer is not retried here."""

    def call(messages: list[dict[str, Any]]) -> str:
        for attempt in range(attempts):
            try:
                return complete(messages)
            except Exception as exc:
                if attempt == attempts - 1:
                    raise
                audit("llm.retry", error=str(exc), attempt=attempt + 1)
        raise AssertionError("unreachable")

    return call


def parse_json_object(text: str) -> dict[str, Any]:
    """The first JSON object in a model reply, tolerating fences and prose around it."""
    decoder = json.JSONDecoder()
    start = text.find("{")
    while start != -1:
        try:
            value, _ = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            start = text.find("{", start + 1)
            continue
        if isinstance(value, dict):
            return value
        start = text.find("{", start + 1)
    raise ValueError("The model reply does not contain a JSON object")


def tool_card(spec: ToolSpec) -> dict[str, Any]:
    """What a model needs to judge one candidate, and nothing that ranks it."""
    return {
        "tool_id": spec.tool_id,
        "label": spec.label,
        "description": spec.description,
        "inputs": spec.inputs,
        "outputs": spec.outputs,
        "parameter_schema": spec.parameter_schema,
    }


class CandidateRetriever:
    """Every agent-selectable tool whose inputs fit the available data types."""

    def retrieve(self, task: TaskState, registry: ToolRegistry) -> list[RouterCandidate]:
        available = set(task.available_input_types)
        registry.type_registry.validate_port_types(available)
        candidates: list[RouterCandidate] = []
        for spec in registry.agent_selectable().values():
            if spec.inputs and not all(
                any(registry.type_registry.can_flow(source, required) for source in available)
                for required in spec.inputs.values()
            ):
                continue
            reason = "input ports accept the available data" if spec.inputs else "needs no upstream input"
            candidates.append(RouterCandidate(tool_id=spec.tool_id, version=spec.version, score=0.0, reasons=[reason]))
        return sorted(candidates, key=lambda candidate: candidate.tool_id)


SELECT_SYSTEM_PROMPT = """You route one unit of work in a MatFlow materials-science workflow to a registered tool.
Choose the single candidate that performs exactly this unit of work on this data, or null when none does (a capability gap).
Never choose a tool only because its name resembles the request, a tool for a different measurement method, or a tool that would need data this step does not have. A generic AI or skill tool never stands in for a missing scientific computation: that is a capability gap.
A parameter the request does not state (for example reference data or a threshold) is NOT a reason to return null: still choose the tool that performs the work; a human supplies missing parameters later.
Return one JSON object and nothing else:
{"tool_id": "<one candidate tool_id>" or null, "confidence": <0..1>, "rationale": "<one sentence>", "params": {<only keys from the chosen tool's parameter_schema whose values the request or the uploaded column names state explicitly; never values from your own knowledge>}}"""


class LLMToolSelector:
    """Ask the configured LLM to pick one of the submitted candidates, or none."""

    def __init__(self, complete: TextCompletion, model: str = "llm"):
        self._complete = complete
        self._model = model

    def select(self, work: dict[str, Any], candidates: list[RouterCandidate], registry: ToolRegistry) -> ModelDecisionEvidence:
        payload = {"work": work, "candidates": [tool_card(registry.get(candidate.tool_id)) for candidate in candidates]}
        messages = [
            {"role": "system", "content": SELECT_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        answer = parse_json_object(self._complete(messages))
        selected = answer.get("tool_id")
        if selected is not None and selected not in {candidate.tool_id for candidate in candidates}:
            raise ValueError(f"The LLM chose {selected!r}, which was not a submitted candidate")
        try:
            confidence = min(1.0, max(0.0, float(answer.get("confidence", 0.0))))
        except (TypeError, ValueError):
            confidence = 0.0
        params = answer.get("params") if isinstance(answer.get("params"), dict) else {}
        return ModelDecisionEvidence(
            profile="llm",
            model=self._model,
            selected_tool_id=selected,
            score=confidence,
            calibrated=False,
            evidence={"rationale": str(answer.get("rationale", ""))[:1000], "params": params},
        )


@dataclass
class Selection:
    """One routing outcome: which model decided, and whether a human must confirm."""

    selected: RouterCandidate | None
    confidence: float
    requires_confirmation: bool
    rationale: str
    router: str
    model_decisions: list[ModelDecisionEvidence] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)
    #: The routing model could not be used (transport/protocol), as opposed to
    #: having decided that no candidate fits.
    failed: bool = False


class ToolSelector:
    """Jev first when it is enabled, then the LLM; never a keyword score."""

    def __init__(self, jev_router: JevDecisionRouter | None = None, llm: LLMToolSelector | None = None):
        self._jev = jev_router
        self._llm = llm

    def select(self, task: TaskState, candidates: list[RouterCandidate], registry: ToolRegistry, *, work: dict[str, Any] | None = None) -> Selection:
        if not candidates:
            return Selection(None, 0.0, True, "No active tool accepts the available data.", "none")
        evidence: list[ModelDecisionEvidence] = []
        jev_note = ""
        jev_disagreed = False
        if self._jev is not None and self._jev.enabled and len(candidates) > 1:
            try:
                winner, confidence, confirmation, selections, rationale = self._jev.decide(task, candidates, registry)
            except JevUnavailableError as exc:
                # The transport detail is for operators, not for the user-facing
                # rationale: keep the stable fact, never the raw urlopen text.
                audit("jev.unavailable", error_type=type(exc).__name__)
                if self._jev.fallback != "llm":
                    return Selection(None, 0.0, True, "Jev routing unavailable; the configured fallback is a human decision.", "jev")
                jev_note = "Jev routing unavailable; the LLM decided instead."
            else:
                evidence = [ModelDecisionEvidence.model_validate(item.model_dump()) for item in selections]
                if winner is not None and not confirmation:
                    spec = registry.get(winner.tool_id)
                    return Selection(winner, confidence, spec.risk_level != "low", rationale, "jev", evidence)
                # Disagreement, low confidence or an invalid choice: the LLM
                # breaks the tie, and a human still confirms the result.
                jev_disagreed = True
                jev_note = rationale
        if self._llm is None:
            reason = "No routing model is available (keyword matching is disabled); a human must choose the tool."
            return Selection(None, 0.0, True, " ".join(filter(None, [jev_note, reason])), "none", evidence)
        try:
            opinion = self._llm.select(work or {"request": task.user_message, "available_input_types": task.available_input_types}, candidates, registry)
        except Exception as exc:  # a model failure must never fall back to keywords
            audit("llm_router.failed", error=str(exc))
            return Selection(None, 0.0, True, " ".join(filter(None, [jev_note, f"LLM routing failed: {exc}"])), "llm", evidence, failed=True)
        evidence.append(opinion)
        rationale = " ".join(filter(None, [jev_note, str(opinion.evidence.get("rationale", ""))]))
        if opinion.selected_tool_id is None:
            return Selection(None, opinion.score, True, rationale or "The LLM found no candidate that performs this work.", "llm", evidence)
        winner = next(candidate for candidate in candidates if candidate.tool_id == opinion.selected_tool_id)
        spec = registry.get(winner.tool_id)
        confirmation = jev_disagreed or opinion.score < LLM_MIN_CONFIDENCE or spec.risk_level != "low"
        return Selection(winner, opinion.score, confirmation, rationale, "llm", evidence, dict(opinion.evidence.get("params") or {}))


class DecisionRouter:
    """Produce an auditable single-tool route for one request."""

    def __init__(self, retriever: CandidateRetriever | None = None, jev_router: JevDecisionRouter | None = None, llm: LLMToolSelector | None = None):
        self._retriever = retriever or CandidateRetriever()
        self._selector = ToolSelector(jev_router, llm)

    def decide(self, task: TaskState, registry: ToolRegistry) -> RouterDecision:
        candidates = self._retriever.retrieve(task, registry)
        selection = self._selector.select(task, candidates, registry)
        return RouterDecision(
            task_id=task.task_id,
            graph_version=task.graph_version,
            candidates=candidates,
            selected=[selection.selected] if selection.selected else [],
            confidence=selection.confidence,
            rationale=f"[{selection.router}] {selection.rationale}".strip(),
            requires_human_confirmation=selection.requires_confirmation,
            model_decisions=selection.model_decisions,
        )

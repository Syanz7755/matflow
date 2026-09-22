"""Configuration-driven adapters for the local Jev typed-decision gateway."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

from pydantic import BaseModel, Field, HttpUrl, ValidationError, model_validator

from .contracts import RouterCandidate, TaskState
from .observability import audit
from .tool_registry import ToolRegistry


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "config" / "jev_router.json"


class JevProfile(BaseModel):
    kind: str = Field(pattern=r"^jev_(laya|semantic)$")
    base_url: HttpUrl
    model: str = Field(min_length=1)
    max_tokens: int = Field(default=1024, ge=1, le=16384)


class JevRouterSettings(BaseModel):
    enabled: bool = False
    strategy: str = Field(default="consensus", pattern=r"^(consensus|laya|semantic)$")
    profiles: list[str] = Field(default_factory=list)
    timeout_seconds: int = Field(default=45, ge=1, le=180)
    minimum_calibrated_confidence: float = Field(default=0.7, ge=0, le=1)
    fallback_to_lexical: bool = True


class JevConfig(BaseModel):
    version: int = Field(ge=1)
    router: JevRouterSettings
    profiles: dict[str, JevProfile]

    @model_validator(mode="after")
    def validate_router_profiles(self):
        names = self.router.profiles
        if self.router.enabled and not names:
            raise ValueError("An enabled Jev router needs at least one profile")
        missing = set(names) - set(self.profiles)
        if missing:
            raise ValueError(f"Router references unknown profile(s): {', '.join(sorted(missing))}")
        if self.router.strategy in {"laya", "semantic"}:
            desired_kind = f"jev_{self.router.strategy}"
            if not any(self.profiles[name].kind == desired_kind for name in names):
                raise ValueError(f"Strategy {self.router.strategy} requires a {desired_kind} profile")
        return self


class ModelSelection(BaseModel):
    profile: str
    model: str
    selected_tool_id: str | None
    score: float = Field(ge=0, le=1)
    calibrated: bool
    evidence: dict[str, Any] = Field(default_factory=dict)


def load_jev_config(config_path: Path | None = None) -> JevConfig:
    path = config_path or Path(os.getenv("MATFLOW_JEV_ROUTER_CONFIG", DEFAULT_CONFIG_PATH))
    try:
        return JevConfig.model_validate_json(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Jev router configuration was not found: {path}") from exc
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"Jev router configuration is invalid: {exc}") from exc


class JevDecisionRouter:
    """One seam for Jev protocol translation, transport and model disagreement handling."""

    def __init__(self, config: JevConfig | None = None):
        self._config = config or load_jev_config()

    @property
    def enabled(self) -> bool:
        return self._config.router.enabled

    def decide(self, task: TaskState, candidates: list[RouterCandidate], registry: ToolRegistry) -> tuple[RouterCandidate | None, float, bool, list[ModelSelection], str]:
        if not self.enabled or len(candidates) < 2:
            return None, 0.0, False, [], "Jev decision routing was not needed."
        selections: list[ModelSelection] = []
        try:
            for profile_name in self._profiles_to_use():
                profile = self._config.profiles[profile_name]
                selections.append(self._select(profile_name, profile, task, candidates, registry))
        except (OSError, ValueError, urlerror.URLError, json.JSONDecodeError) as exc:
            audit("jev_router.failed", error=str(exc), profiles=self._profiles_to_use())
            if self._config.router.fallback_to_lexical:
                return None, 0.0, True, selections, f"Jev routing unavailable; lexical fallback requires confirmation: {exc}"
            raise ValueError(f"Jev routing failed without fallback: {exc}") from exc

        chosen_ids = [selection.selected_tool_id for selection in selections if selection.selected_tool_id]
        if not chosen_ids:
            return None, 0.0, True, selections, "Jev models did not return a valid candidate; confirmation is required."
        if self._config.router.strategy == "consensus" and len(set(chosen_ids)) != 1:
            return None, 0.0, True, selections, "Jev models disagreed; confirmation is required."
        selected_id = chosen_ids[0]
        selected = next(candidate for candidate in candidates if candidate.tool_id == selected_id)
        calibrated_scores = [selection.score for selection in selections if selection.calibrated]
        confidence = min(calibrated_scores) if calibrated_scores else selected.score
        low_confidence = bool(calibrated_scores and confidence < self._config.router.minimum_calibrated_confidence)
        rationale = f"Jev {self._config.router.strategy} selected {selected_id}."
        if low_confidence:
            rationale += " Laya confidence is below the configured automatic-routing threshold."
        return selected, confidence, low_confidence, selections, rationale

    def _profiles_to_use(self) -> list[str]:
        if self._config.router.strategy == "consensus":
            return self._config.router.profiles
        kind = f"jev_{self._config.router.strategy}"
        return [name for name in self._config.router.profiles if self._config.profiles[name].kind == kind]

    def _select(self, profile_name: str, profile: JevProfile, task: TaskState, candidates: list[RouterCandidate], registry: ToolRegistry) -> ModelSelection:
        options = [{"id": candidate.tool_id, "description": registry.get(candidate.tool_id).description} for candidate in candidates]
        state = {"body": task.user_message, "assumptions": task.assumptions, "available_input_types": task.available_input_types}
        if profile.kind == "jev_laya":
            body = {"model": profile.model, "state": state, "questions": {"tool_selection": {"type": "choice", "instructions": "Which registered tool best matches body? Choose exactly one candidate.", "criteria": {option["id"]: option["description"] for option in options}}}}
            response = self._post(profile, body)
            answer = response.get("answers", {}).get("tool_selection", {})
            selected_id = answer.get("choice")
            score = float(answer.get("confidence", 0.0))
            evidence = {"probabilities": answer.get("probabilities", {}), "usage": response.get("usage", {})}
            return ModelSelection(profile=profile_name, model=profile.model, selected_tool_id=selected_id, score=score, calibrated=True, evidence=evidence)

        body = {"model": profile.model, "id": task.task_id, "state": state, "question": "Which registered tool best matches this materials-analysis request?", "options": options, "max_tokens": profile.max_tokens}
        response = self._post(profile, body)
        probabilities = response.get("probabilities", [])
        if len(probabilities) != len(options):
            raise ValueError("Semantic response probabilities do not match submitted candidates")
        index = max(range(len(probabilities)), key=lambda item: probabilities[item])
        score = float(probabilities[index])
        evidence = {"probabilities": probabilities, "forward_seconds": response.get("forward_seconds"), "total_seconds": response.get("total_seconds"), "probability_status": response.get("probability_status")}
        return ModelSelection(profile=profile_name, model=profile.model, selected_tool_id=options[index]["id"], score=score, calibrated=False, evidence=evidence)

    def _post(self, profile: JevProfile, body: dict[str, Any]) -> dict[str, Any]:
        url = str(profile.base_url).rstrip("/") + "/v1/decide"
        request = urlrequest.Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        with urlrequest.urlopen(request, timeout=self._config.router.timeout_seconds) as response:
            payload = json.loads(response.read())
        if not isinstance(payload, dict):
            raise ValueError("Jev gateway response must be a JSON object")
        return payload

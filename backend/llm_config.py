"""The one non-secret description of the LLM gateway: ``config/llm.json``.

``start_llm.bat`` starts or reuses the gateway from the same file, so the
launcher and the backend cannot disagree about host, port, key variable or the
served models. Only the *name* of the key variable is stored here.
"""
from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "config" / "llm.json"


class LLMGateway(BaseModel):
    label: str = Field(default="Local LiteLLM gateway", min_length=1, max_length=120)
    host: str = Field(default="127.0.0.1", min_length=1)
    port: int = Field(ge=1, le=65535)
    api_key_env: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    litellm_config: str = "config/litellm.yaml"
    startup_timeout_seconds: int = Field(default=60, ge=1, le=600)


class LLMConfig(BaseModel):
    version: int = Field(ge=1)
    gateway: LLMGateway
    models: list[str] = Field(min_length=1)
    agent_model: str
    planner_model: str
    request_timeout_seconds: int = Field(default=120, ge=1, le=900)

    @model_validator(mode="after")
    def models_are_served(self):
        for role in ("agent_model", "planner_model"):
            if getattr(self, role) not in self.models:
                raise ValueError(f"{role} must be one of the configured models")
        return self

    @property
    def base_url(self) -> str:
        return f"http://{self.gateway.host}:{self.gateway.port}/v1"


def load_llm_config(path: Path | None = None) -> LLMConfig:
    """Read the gateway description; ``MATFLOW_LLM_CONFIG`` points at another file."""
    location = path or Path(os.getenv("MATFLOW_LLM_CONFIG", str(DEFAULT_CONFIG_PATH)))
    try:
        return LLMConfig.model_validate_json(location.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"LLM configuration was not found: {location}") from exc

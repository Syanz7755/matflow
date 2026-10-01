"""Configuration-driven scenario runner primitives.

Case-specific prompts, fixtures, parameters and expectations live in JSON.  This
module only validates the common contract and enforces fail-closed service access.
"""
from __future__ import annotations

import json
import copy
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.contracts import GraphState
from backend.workspace_runtime import WorkspaceRuntime


class ServiceAccess(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jev_like: bool = False
    llm: bool = False


class SuiteDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_access: ServiceAccess = Field(default_factory=ServiceAccess)
    repair_budget: int = Field(default=2, ge=0, le=5)
    isolation_backend: Literal["docker", "microsandbox"] = "docker"


class FixtureSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str | None = None
    paths: list[str] = Field(default_factory=list)
    generator: str | None = None
    seed: int | None = None
    seeds: list[int] = Field(default_factory=list)
    noise_profile: dict[str, Any] = Field(default_factory=dict)
    ground_truth: dict[str, Any] = Field(default_factory=dict)
    optional_external_path: str | None = None


class ScenarioCaseConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_-]*$")
    kind: Literal[
        "workflow_generation",
        "workflow_execution",
        "tool_construction",
        "tool_selection",
        "tool_repair",
    ]
    prompt: str = Field(min_length=1)
    inputs: list[dict[str, Any]] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    workflow: dict[str, Any] = Field(default_factory=dict)
    service_access: ServiceAccess | None = None
    tool_visibility: Literal["hidden_reference", "published_reference"] = "hidden_reference"
    fixture: FixtureSpec | None = None
    expected: dict[str, Any] = Field(default_factory=dict)
    repair_budget: int | None = Field(default=None, ge=0, le=5)
    tags: list[str] = Field(default_factory=list)


class ScenarioSuiteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["2.0"]
    suite_id: str
    description: str = ""
    defaults: SuiteDefaults = Field(default_factory=SuiteDefaults)
    cases: list[ScenarioCaseConfig] = Field(min_length=1)


@dataclass(frozen=True)
class ServiceFlags:
    jev_like: bool = False
    llm: bool = False


@dataclass(frozen=True)
class ScenarioCase:
    config: ScenarioCaseConfig
    allowed_services: dict[str, bool]
    repair_budget: int
    isolation_backend: str

    def effective_services(self, flags: ServiceFlags) -> dict[str, bool]:
        return {
            "jev_like": self.allowed_services["jev_like"] and flags.jev_like,
            "llm": self.allowed_services["llm"] and flags.llm,
        }


@dataclass(frozen=True)
class ScenarioSuite:
    suite_id: str
    description: str
    cases: tuple[ScenarioCase, ...]

    @classmethod
    def load(cls, path: Path) -> "ScenarioSuite":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            config = ScenarioSuiteConfig.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(f"Invalid scenario configuration {path}: {exc}") from exc

        defaults = config.defaults
        cases: list[ScenarioCase] = []
        seen: set[str] = set()
        for item in config.cases:
            if item.case_id in seen:
                raise ValueError(f"Duplicate scenario case_id: {item.case_id}")
            seen.add(item.case_id)
            access = item.service_access or defaults.service_access
            cases.append(ScenarioCase(
                config=item,
                allowed_services=access.model_dump(),
                repair_budget=item.repair_budget if item.repair_budget is not None else defaults.repair_budget,
                isolation_backend=defaults.isolation_backend,
            ))
        return cls(config.suite_id, config.description, tuple(cases))


class ConfiguredScenarioRunner:
    """Execute generic scenario declarations without branching on case IDs."""

    def __init__(self, project_root: Path, run_root: Path, service_flags: ServiceFlags):
        self.project_root = project_root.resolve()
        self.run_root = run_root.resolve()
        self.service_flags = service_flags

    def run_case(self, case: ScenarioCase) -> dict[str, Any]:
        effective = case.effective_services(self.service_flags)
        base = {
            "case_id": case.config.case_id,
            "kind": case.config.kind,
            "service_access": {"allowed": case.allowed_services, "effective": effective},
            "expected": case.config.expected,
        }
        if case.config.kind == "workflow_execution":
            actual = self._run_workflow(case)
            return base | {"actual": actual, "verdict": self._verdict(actual, case.config.expected)}

        if any(case.allowed_services.values()) and not any(effective.values()):
            return base | {
                "actual": {"status": "skipped", "reason": "configured service access also requires an explicit runner flag"},
                "verdict": "skipped",
            }

        fixture = case.config.fixture
        if fixture and fixture.optional_external_path:
            path = Path(fixture.optional_external_path)
            actual = {"status": "available" if path.is_dir() else "skipped", "path": str(path)}
            return base | {"actual": actual, "verdict": "passed" if path.is_dir() or case.config.expected.get("skip_if_missing") else "failed"}

        return base | {"actual": {"status": "defined"}, "verdict": "passed"}

    def _run_workflow(self, case: ScenarioCase) -> dict[str, Any]:
        workflow = case.config.workflow
        runtime_root = self.run_root / re.sub(r"[^a-zA-Z0-9_.-]", "_", case.config.case_id)
        runtime = WorkspaceRuntime(runtime_root)
        active = runtime.registry().active()
        missing = [tool for tool in workflow.get("required_tools", []) if tool not in active]
        if missing:
            if self._contains_negative_number(case.config.parameters):
                return {"status": "failed_validation", "missing_tools": missing, "executed": False}
            return {"status": "waiting_for_tool", "missing_tools": missing, "scientific_result": None}
        if not workflow.get("nodes"):
            return {"status": "defined", "executed": False}

        uploads = []
        for index, item in enumerate(case.config.inputs):
            if "inline_csv" in item:
                content = str(item["inline_csv"]).encode("utf-8")
                name = str(item.get("name") or f"inline-{index}.csv")
            elif "fixture" in item:
                source = (self.project_root / str(item["fixture"])).resolve()
                if not source.is_file() or self.project_root not in source.parents:
                    return {"status": "failed", "error": f"Fixture is unavailable or outside the project: {item['fixture']}"}
                content, name = source.read_bytes(), source.name
            else:
                return {"status": "failed", "error": f"Input {index} has neither fixture nor inline_csv"}
            uploads.append(runtime.import_dataset(name, content, "text/csv"))

        graph_payload = {
            "nodes": self._replace_upload_tokens(copy.deepcopy(workflow["nodes"]), uploads),
            "edges": workflow.get("edges", []),
        }
        try:
            runtime.write_state(GraphState.model_validate(graph_payload))
            outcome = runtime.execute_workflow(restart=True)
        except Exception as exc:
            return {"status": "failed", "error": str(exc)}

        statuses = [node["status"] for node in outcome["state"]["nodes"]]
        sequence = []
        if "waiting" in statuses:
            status = "waiting"
            sequence.append("waiting")
        elif "error" in statuses or any("error" in item for item in outcome.get("results", [])):
            status = "failed"
        else:
            status = "completed"
        review = workflow.get("review")
        if review and status == "waiting":
            continued = runtime.submit_node_review(review["node_id"], review["decision"])
            statuses = [node["status"] for node in continued["state"]["nodes"]]
            status = "completed" if all(item == "completed" for item in statuses) else statuses[-1]
            sequence.append(status)
            outcome = continued
        nodes = outcome["state"]["nodes"]
        kinds = [node.get("output", {}).get("kind") for node in nodes if node.get("output")]
        actual = {"status": status, "status_sequence": sequence, "output_kinds": kinds, "nodes": nodes}
        errors = [item.get("error") for item in outcome.get("results", []) if item.get("error")]
        if errors:
            actual["error"] = "\n".join(str(item) for item in errors)
        if case.config.expected.get("row_count_preserved"):
            row_counts = [node.get("output", {}).get("rows") for node in nodes if node.get("output", {}).get("rows") is not None]
            actual["row_count_preserved"] = len(set(row_counts)) <= 1
        return actual

    @staticmethod
    def _replace_upload_tokens(value: Any, uploads: list[dict[str, Any]]) -> Any:
        if isinstance(value, dict):
            return {key: ConfiguredScenarioRunner._replace_upload_tokens(item, uploads) for key, item in value.items()}
        if isinstance(value, list):
            return [ConfiguredScenarioRunner._replace_upload_tokens(item, uploads) for item in value]
        if isinstance(value, str) and value.startswith("$upload:"):
            return uploads[int(value.split(":", 1)[1])]["id"]
        return value

    @staticmethod
    def _contains_negative_number(value: Any) -> bool:
        if isinstance(value, dict):
            return any(ConfiguredScenarioRunner._contains_negative_number(item) for item in value.values())
        if isinstance(value, list):
            return any(ConfiguredScenarioRunner._contains_negative_number(item) for item in value)
        return isinstance(value, (int, float)) and not isinstance(value, bool) and value < 0

    @staticmethod
    def _verdict(actual: dict[str, Any], expected: dict[str, Any]) -> str:
        if actual.get("status") == "defined" and not actual.get("executed", False):
            return "blocked"
        if "status" in expected and actual.get("status") != expected["status"]:
            return "failed"
        if "status_sequence" in expected and actual.get("status_sequence") != expected["status_sequence"]:
            return "failed"
        if "error_contains" in expected and expected["error_contains"] not in str(actual.get("error", "")):
            return "failed"
        if "output_kinds" in expected and not set(expected["output_kinds"]).issubset(set(actual.get("output_kinds", []))):
            return "failed"
        if expected.get("row_count_preserved") and not actual.get("row_count_preserved"):
            return "failed"
        return "passed"


class ScenarioReportWriter:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    def write(self, suite_id: str, records: list[dict[str, Any]]) -> dict[str, Path]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        safe_id = re.sub(r"[^a-zA-Z0-9_.-]", "_", suite_id)
        json_path = self.output_dir / f"{safe_id}.json"
        markdown_path = self.output_dir / f"{safe_id}.md"
        redacted = self._redact(records)
        summary = {
            verdict: sum(item.get("verdict") == verdict for item in redacted)
            for verdict in ("passed", "failed", "skipped", "blocked")
        }
        payload = {
            "suite_id": suite_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
            "cases": redacted,
        }
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        lines = [
            f"# {suite_id}", "", f"Generated: {payload['generated_at']}", "",
            f"Passed: {summary['passed']} · Failed: {summary['failed']} · Skipped: {summary['skipped']} · Blocked: {summary['blocked']}", "",
            "| Case | Kind | Services | Verdict | Actual status |", "| --- | --- | --- | --- | --- |",
        ]
        for item in redacted:
            access = item.get("service_access", {}).get("effective", item.get("service_access", {}))
            enabled = ", ".join(name for name, allowed in access.items() if allowed) or "offline"
            lines.append(f"| {item.get('case_id')} | {item.get('kind')} | {enabled} | {item.get('verdict')} | {item.get('actual', {}).get('status', '')} |")
        markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {"json": json_path, "markdown": markdown_path}

    @classmethod
    def _redact(cls, value: Any, key: str = "") -> Any:
        sensitive = any(marker in key.lower() for marker in ("authorization", "api_key", "secret", "token", "credential"))
        if sensitive:
            return "[REDACTED]"
        if isinstance(value, dict):
            return {item_key: cls._redact(item, item_key) for item_key, item in value.items()}
        if isinstance(value, list):
            return [cls._redact(item) for item in value]
        if isinstance(value, str) and value.lower().startswith("bearer "):
            return "[REDACTED]"
        return value

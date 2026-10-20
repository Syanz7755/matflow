"""Transport-neutral MatFlow workspace runtime.

HTTP, MCP, and tests cross this single seam.  Persistence, validation, routing,
uploads, and execution stay local to the implementation so adapters cannot
silently develop different workflow semantics.
"""
from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd

from .contracts import (
    DataTypeDefinition,
    ExecutionError,
    ExecutionResult,
    GraphPatch,
    GraphState,
    Node,
    Operation,
    ReviewPolicy,
    ReviewState,
    TaskState,
)
from .analysis_recipes import AnalysisRecipe
from .data_types import DataTypeRegistry
from .domain_packages import (
    DomainPackageLoader,
    DomainPackageSet,
    compose_type_registry,
    load_domain_packages,
)
from .errors import ConflictError, NotFoundError
from .executors import ExecutionOutcome, ExecutorRegistry, NodeExecution, ToolExecutionError
from .jev_routing import JevDecisionRouter
from .llm_config import load_llm_config
from .observability import audit, current_trace_id
from .node_evolution import build_revision_proposal, reconnect_edges
from .preview import build_preview
from .planner import WorkflowPlanner
from .routing import DecisionRouter, LLMToolSelector, ToolSelector, with_retry
from .saves import SETTINGS_FILE, STATE_FILE, UPLOADS_DIR, resolve_data_root
from .task_summary import TaskSummaryService
from .tool_registry import ToolRegistry
from .validator import GraphValidator, node_by_id

ROOT = Path(__file__).resolve().parents[1]
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED_UPLOAD_SUFFIXES = {
    ".csv", ".txt", ".md", ".xlsx", ".xls", ".json", ".png", ".jpg", ".jpeg", ".tif", ".tiff"
}
#: Media type served for a stored dataset. Derived from the validated suffix,
#: never from the client-supplied content type.
CONTENT_TYPES = {
    ".csv": "text/csv",
    ".txt": "text/plain; charset=utf-8",
    ".json": "application/json",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


def default_settings() -> dict[str, Any]:
    # The gateway itself is described once, in config/llm.json; a save only
    # overrides it when someone changes the agent settings for that save.
    llm = load_llm_config()
    return {
        "agent": {
            "provider": "openai_compatible",
            "base_url": llm.base_url,
            "model": llm.agent_model,
            "api_key_env": llm.gateway.api_key_env,
            "temperature": 0.2,
            "system_prompt": "Respect the runtime skills. Use tools to inspect files and execute work; never invent observations.",
            "max_tool_rounds": 8,
        },
        # The shipped application enables one runtime skill by default; a workspace
        # rooted elsewhere simply has no such file and contributes none.
        "runtime_skills": {"enabled": ["matflow_agent_runtime.md"]},
        "custom_nodes": {},
        "custom_data_types": {},
        "revision_proposals": {},
        "tool_recipe_proposals": {},
        "model_providers": {
            "local_litellm": {
                "label": llm.gateway.label,
                "base_url": llm.base_url,
                "api_key_env": llm.gateway.api_key_env,
                "models": list(llm.models),
            }
        },
        "features": {
            "tool_manager_search": False,
            "tool_manager_adapt": False,
            "tool_manager_build": False,
        },
    }


def _json_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Dataset rows that are guaranteed to be JSON-serialisable.

    ``DataFrame.to_dict`` can hand back numpy scalars (``np.int64``), which the
    JSON encoder rejects.  Round-tripping through pandas' own JSON writer emits
    native Python scalars for every column dtype, NaN as ``null`` and timestamps
    as ISO-8601 strings.
    """
    if frame.empty:
        return []
    return json.loads(frame.to_json(orient="records", date_format="iso"))


class WorkspaceRuntime:
    """Deep module for all server-authoritative workspace operations."""

    def __init__(
        self,
        root: Path = ROOT,
        *,
        model_complete: Callable[[list[dict[str, Any]], list[dict[str, Any]]], dict[str, Any]] | None = None,
        summary_service: TaskSummaryService | None = None,
        packages: Iterable[str] = (),
        package_loader: DomainPackageLoader | None = None,
        executors: ExecutorRegistry | None = None,
    ):
        self.root = root.resolve()
        # One save, one folder: graph, settings, uploads and the task log of
        # this workspace all live under data_root (see backend/saves.py).
        self.data_root = resolve_data_root(self.root)
        self.state_file = self.data_root / STATE_FILE
        self.settings_file = self.data_root / SETTINGS_FILE
        self.upload_dir = self.data_root / UPLOADS_DIR
        self.runtime_skills_dir = self.root / "runtime_skills"
        self.preview_spec_file = self.root / "docs" / "NODE_PREVIEW_SPEC.md"
        self._model_complete = model_complete
        self._summaries = summary_service or TaskSummaryService(data_root=self.data_root)
        self._write_lock = threading.RLock()
        # A workspace composes the Domain Packages it wants. Loading none leaves
        # Platform Core domain-neutral, which is the default.
        self.packages: DomainPackageSet = load_domain_packages(packages, loader=package_loader)
        self.executors = executors or ExecutorRegistry.platform()
        self.packages.register_executors(self.executors)

    def read_state(self) -> GraphState:
        if not self.state_file.exists():
            return GraphState()
        return GraphState.model_validate_json(self.state_file.read_text(encoding="utf-8"))

    def write_state(self, state: GraphState, *, advance_revision: bool = True) -> GraphState:
        """Persist the workspace and advance its monotonic revision.

        ``version`` counts applied GraphPatches; ``revision`` advances on every
        persisted write, so a client can detect that node outputs or review
        states moved even though the graph structure did not.  Returns the state
        that was written, so callers never hand back a stale revision.
        """
        if advance_revision:
            state.revision += 1
            state.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._write_lock:
            self._atomic_write(self.state_file, state.model_dump_json(indent=2))
        return state

    def read_settings(self) -> dict[str, Any]:
        defaults = default_settings()
        if not self.settings_file.exists():
            return defaults
        loaded = json.loads(self.settings_file.read_text(encoding="utf-8"))
        return {
            **defaults,
            **loaded,
            "agent": {**defaults["agent"], **loaded.get("agent", {})},
            "runtime_skills": {**defaults["runtime_skills"], **loaded.get("runtime_skills", {})},
            "custom_nodes": loaded.get("custom_nodes", {}),
            "custom_data_types": loaded.get("custom_data_types", {}),
            "revision_proposals": loaded.get("revision_proposals", {}),
            "tool_recipe_proposals": loaded.get("tool_recipe_proposals", {}),
            "model_providers": loaded.get("model_providers", defaults["model_providers"]),
            "features": {**defaults["features"], **loaded.get("features", {})},
        }

    def write_settings(self, settings: dict[str, Any]) -> None:
        with self._write_lock:
            self._atomic_write(self.settings_file, json.dumps(settings, ensure_ascii=False, indent=2))

    @property
    def model_adapter_configured(self) -> bool:
        return self._model_complete is not None

    def complete_with_model(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        if self._model_complete is None:
            raise ValueError("This node execution requires a configured model adapter")
        return self._model_complete(messages, tools)

    def text_completion(self, messages: list[dict[str, Any]], *, model: str | None = None) -> str:
        """One plain-text LLM answer, on ``model`` when a configured provider serves it."""
        if self._model_complete is None:
            raise ValueError("No LLM adapter is configured for this workspace")
        kwargs: dict[str, Any] = {}
        if model:
            providers = self.read_settings().get("model_providers", {})
            provider_id = next((pid for pid, item in providers.items() if model in item.get("models", [])), None)
            if provider_id:
                kwargs = {"provider_id": provider_id, "model": model}
        reply = self._model_complete(messages, [], **kwargs)
        content = reply.get("content") if isinstance(reply, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise ValueError("The LLM returned no text")
        return content

    def llm_tool_selector(self) -> LLMToolSelector | None:
        """The LLM half of tool routing; ``None`` when no model adapter is configured."""
        if self._model_complete is None:
            return None
        model = load_llm_config().planner_model
        return LLMToolSelector(with_retry(lambda messages: self.text_completion(messages, model=model)), model=model)

    def registry(self) -> ToolRegistry:
        settings = self.read_settings()
        return ToolRegistry(
            settings["custom_nodes"],
            self.data_type_registry(settings),
            package_specs=self.packages.tool_specs(),
        )

    def data_type_registry(self, settings: dict[str, Any] | None = None) -> DataTypeRegistry:
        """Platform types plus every loaded Domain Package type and custom type."""
        resolved = settings or self.read_settings()
        return compose_type_registry(self.packages, resolved["custom_data_types"])

    def workspace_snapshot(self) -> dict[str, Any]:
        settings = self.read_settings()
        return {
            "state": self.read_state().model_dump(),
            "registry": self.registry().legacy_view(),
            "data_types": list(self.data_type_registry().names()),
            "data_type_definitions": self.data_type_registry().definitions(),
            "runtime_skills": [item["name"] for item in self.runtime_skills()],
            "features": settings["features"],
            "domain_packages": self.packages.legacy_view(),
        }

    def create_data_type(self, definition: DataTypeDefinition | dict[str, Any]) -> dict[str, Any]:
        """Create a custom type only after validating the complete hierarchy."""
        with self._write_lock:
            item = DataTypeDefinition.model_validate(definition).model_copy(update={"builtin": False})
            settings = self.read_settings()
            if item.name in self.data_type_registry().names():
                raise ValueError(f"Data type already exists: {item.name}")
            custom = copy.deepcopy(settings["custom_data_types"])
            custom[item.name] = item.model_dump()
            self._validate_type_configuration(custom, settings["custom_nodes"])
            settings["custom_data_types"] = custom
            self.write_settings(settings)
            audit("data_type.created", name=item.name, parents=item.parents)
            return self.data_type_registry().get(item.name).model_dump()

    def update_data_type_inheritance(self, name: str, parents: list[str]) -> dict[str, Any]:
        """Atomically replace a custom type's ordered parents after full compliance checks."""
        with self._write_lock:
            settings = self.read_settings()
            if name not in settings["custom_data_types"]:
                raise ValueError("Only custom data types can have their inheritance changed")
            custom = copy.deepcopy(settings["custom_data_types"])
            current = DataTypeDefinition.model_validate(custom[name])
            updated = current.model_copy(update={"parents": parents})
            # model_copy does not rerun field validators.
            updated = DataTypeDefinition.model_validate(updated.model_dump())
            custom[name] = updated.model_dump()
            self._validate_type_configuration(custom, settings["custom_nodes"])
            settings["custom_data_types"] = custom
            self.write_settings(settings)
            audit("data_type.inheritance_updated", name=name, parents=parents)
            return self.data_type_registry().get(name).model_dump()

    def _validate_type_configuration(self, custom_types: dict[str, dict[str, Any]], custom_nodes: dict[str, dict[str, Any]]) -> None:
        type_registry = self.data_type_registry({"custom_data_types": custom_types})
        registry = ToolRegistry(custom_nodes, type_registry, package_specs=self.packages.tool_specs())
        GraphValidator().validate_state(self.read_state(), registry)

    def runtime_skills(self) -> list[dict[str, str]]:
        enabled = self.read_settings().get("runtime_skills", {}).get("enabled", [])
        result: list[dict[str, str]] = []
        for name in enabled:
            path = self.runtime_skills_dir / Path(name).name
            if path.exists():
                result.append({"name": path.name, "content": path.read_text(encoding="utf-8")})
            else:
                audit("runtime_skill.missing", skill=name)
        return result

    def revision_proposals(self) -> dict[str, dict[str, Any]]:
        return self.read_settings().get("revision_proposals", {})

    def propose_analysis_recipe(self, *, label: str, description: str, recipe: dict[str, Any]) -> dict[str, Any]:
        parsed = AnalysisRecipe.model_validate(recipe)
        if parsed.domain not in self.packages.recipe_domains():
            raise ValueError(f"No loaded Domain Package owns recipe domain: {parsed.domain}")
        if parsed.status != "draft":
            raise ValueError("A model-proposed analysis recipe must remain draft until human review")
        proposal_id = str(uuid.uuid4())
        proposal = {
            "proposal_id": proposal_id,
            "status": "draft",
            "label": label[:120],
            "description": description[:1000],
            "recipe": parsed.model_dump(),
            "requires_human_review": True,
            "generated_code": None,
        }
        settings = self.read_settings()
        settings.setdefault("tool_recipe_proposals", {})[proposal_id] = proposal
        self.write_settings(settings)
        audit("tool_recipe.proposed", proposal_id=proposal_id, recipe_id=parsed.recipe_id)
        return proposal

    def create_revision_proposal(self, node_id: str, prompt: str, provider_id: str, model: str) -> dict[str, Any]:
        if not prompt.strip(): raise ValueError("A revision prompt is required")
        if self._model_complete is None: raise ValueError("Node revision requires a configured model adapter")
        state = self.read_state()
        node = node_by_id(state, node_id)
        spec = self.registry().get(node.type)
        preview_rules = self.preview_spec_file.read_text(encoding="utf-8") if self.preview_spec_file.exists() else "Use only text, table_head, image, or json_tree previews."
        contract = {
            "request": prompt,
            "node": node.model_dump(),
            "tool": spec.model_dump(),
            "requirements": "Return JSON only. Keep existing ports unless execution logic must change. generated_code must be null unless new execution logic is unavoidable.",
            "preview_standard": preview_rules,
        }
        try:
            answer = self._model_complete(
                [{"role": "system", "content": "Propose a safe MatFlow ToolSpec revision. Do not apply changes."}, {"role": "user", "content": json.dumps(contract, ensure_ascii=False)}],
                [], provider_id=provider_id, model=model,
            )
        except TypeError:
            answer = self._model_complete([{"role": "user", "content": json.dumps(contract, ensure_ascii=False)}], [])
        try:
            payload = json.loads(answer.get("content") or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"Model returned invalid revision JSON: {exc}") from exc
        if not isinstance(payload, dict): raise ValueError("Model revision must be a JSON object")
        proposal = build_revision_proposal(state=state, registry=self.registry(), node_id=node_id, prompt=prompt.strip(), provider_id=provider_id, model=model, model_payload=payload)
        settings = self.read_settings()
        settings.setdefault("revision_proposals", {})[proposal["proposal_id"]] = proposal
        self.write_settings(settings)
        audit("node_revision.proposed", proposal_id=proposal["proposal_id"], node_id=node_id, provider_id=provider_id, model=model)
        return proposal

    def get_revision_proposal(self, proposal_id: str) -> dict[str, Any]:
        proposal = self.revision_proposals().get(proposal_id)
        if proposal is None: raise NotFoundError("Unknown node revision proposal")
        return proposal

    def review_revision_code(self, proposal_id: str, approved: bool) -> dict[str, Any]:
        settings = self.read_settings()
        proposal = settings.get("revision_proposals", {}).get(proposal_id)
        if proposal is None: raise NotFoundError("Unknown node revision proposal")
        proposal["code_reviewed"] = bool(approved)
        proposal["status"] = "code_reviewed" if approved else "rejected"
        self.write_settings(settings)
        return proposal

    def apply_revision_proposal(self, proposal_id: str, edge_decisions: dict[str, str | None]) -> GraphState:
        with self._write_lock:
            settings = self.read_settings()
            proposal = settings.get("revision_proposals", {}).get(proposal_id)
            if proposal is None: raise NotFoundError("Unknown node revision proposal")
            if proposal["status"] not in {"proposed", "code_reviewed"}: raise ConflictError("This proposal is no longer applicable")
            if proposal.get("requires_code_review"):
                raise ValueError("This proposal changes executable behavior and cannot be activated until a reviewed executor is installed")
            state = self.read_state()
            if state.version != proposal["base_graph_version"]:
                raise ConflictError(
                    "Graph changed after this proposal was created; generate a new proposal",
                    code="graph_version_conflict",
                    details={"current_version": state.version},
                )
            old_node = node_by_id(state, proposal["node_id"])
            proposed_payload = copy.deepcopy(proposal["proposed_tool"])
            proposed_payload.update({"status": "active", "provenance": {"kind": "generated", "reviewed_by": "local-user"}, "generated_code_status": "none"})
            tool = ToolRegistry({proposed_payload["tool_id"]: proposed_payload}, self.data_type_registry()).get(proposed_payload["tool_id"])
            custom_before = copy.deepcopy(settings.get("custom_nodes", {}))
            settings.setdefault("custom_nodes", {})[tool.tool_id] = tool.model_dump()
            # The in-memory candidate must see every loaded Domain Package, or a
            # revision of a package-typed node fails on its package's own types.
            registry = ToolRegistry(
                settings["custom_nodes"],
                self.data_type_registry(settings),
                package_specs=self.packages.tool_specs(),
            )
            replacement = old_node.model_copy(update={
                "type": tool.tool_id,
                "tool_id": tool.tool_id,
                "tool_version": tool.version,
                "label": tool.label,
                "params": proposal["parameter_migration"],
                "status": "ready",
                "output": None,
                "preview": None,
            })
            edges = reconnect_edges(proposal, state, edge_decisions)
            patch = GraphPatch(base_version=state.version, operations=[Operation(op="replace_node_revision", node_id=old_node.id, replacement_node=replacement, reconnect_edges=edges, proposal_id=proposal_id)], rationale=f"Apply node revision proposal {proposal_id}")
            GraphValidator().validate(state, patch, registry)
            self.write_settings(settings)
            try:
                updated = self.apply_graph_patch(patch)
            except Exception:
                settings["custom_nodes"] = custom_before
                self.write_settings(settings)
                raise
            settings = self.read_settings()
            settings["revision_proposals"][proposal_id]["status"] = "applied"
            settings["revision_proposals"][proposal_id]["applied_graph_version"] = updated.version
            self.write_settings(settings)
            return updated

    def migrate_legacy_human_decisions(self, *, apply: bool = False) -> dict[str, Any]:
        """Migrate legacy review-gate nodes that a loaded Domain Package declares."""
        state = self.read_state()
        migrations, blocked = [], []
        legacy_types = self.packages.legacy_tool_ids()
        for node in [item for item in state.nodes if item.type in legacy_types]:
            incoming = [edge for edge in state.edges if edge.target == node.id]
            outgoing = [edge for edge in state.edges if edge.source == node.id]
            if len(incoming) == 1 and not outgoing:
                source = node_by_id(state, incoming[0].source)
                migrations.append({"legacy_node_id": node.id, "review_node_id": source.id, "prompt": node.params.get("prompt", "Review this result before continuing.")})
            else:
                blocked.append({"legacy_node_id": node.id, "reason": "Migration requires exactly one incoming edge and no outgoing edges."})
        if apply and blocked:
            raise ValueError("Legacy review migration has unresolved nodes")
        if apply and migrations:
            operations = []
            for item in migrations:
                operations.append(Operation(op="update_node", node_id=item["review_node_id"], changes={"review_policy": {"after_run": True, "prompt": item["prompt"]}}))
                operations.append(Operation(op="delete_node", node_id=item["legacy_node_id"]))
            state = self.apply_graph_patch(GraphPatch(base_version=state.version, operations=operations, rationale="Migrate legacy Human Decision nodes to per-node review policies"))
        return {"migrations": migrations, "blocked": blocked, "applied": apply and bool(migrations), "state": state.model_dump() if apply else None}

    def import_dataset(self, name: str, content: bytes, content_type: str = "application/octet-stream") -> dict[str, Any]:
        filename = Path(name or "upload").name
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_UPLOAD_SUFFIXES:
            raise ValueError(f"Unsupported file type: {suffix or 'none'}")
        if len(content) > MAX_UPLOAD_BYTES:
            raise ValueError(f"{filename} exceeds the 25 MB limit")
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        upload_id = f"{uuid.uuid4().hex}_{filename}"
        destination = self.upload_dir / upload_id
        with self._write_lock:
            self._atomic_write_bytes(destination, content)
        record = {"id": upload_id, "name": filename, "size": len(content), "type": content_type}
        audit("upload.saved", **record)
        return record

    def inspect_dataset(self, upload_id: str) -> dict[str, Any]:
        path = self._upload_path(upload_id)
        result: dict[str, Any] = {
            "upload_id": upload_id,
            "name": path.name.split("_", 1)[-1],
            "suffix": path.suffix.lower(),
            "bytes": path.stat().st_size,
        }
        try:
            frame = self.dataset_frame(upload_id)
            if path.suffix.lower() == ".txt" and frame.empty:
                raise ValueError("a text file without data rows is prose, not a table")
            result.update({
                "kind": "table",
                "rows": len(frame),
                "columns": [{"name": str(name), "dtype": str(dtype)} for name, dtype in frame.dtypes.items()],
                "preview": _json_records(frame.head(8)),
            })
        except ValueError:
            text = self._read_text(path) if path.suffix.lower() in {".txt", ".md"} else None
            if text is None:
                result["kind"] = "binary"
            else:
                result.update({"kind": "text", "characters": len(text), "preview": text[:2000]})
        except Exception as exc:
            result.update({"kind": "unreadable", "error": str(exc)})
        audit("tool.inspect_upload", upload_id=upload_id, kind=result["kind"])
        return result

    @staticmethod
    def _read_text(path: Path) -> str | None:
        """The file as text when it is valid UTF-8 (BOM tolerated), otherwise None."""
        try:
            return path.read_bytes().decode("utf-8-sig")
        except UnicodeDecodeError:
            return None

    def is_inspectable(self, inspected: dict[str, Any]) -> bool:
        """Whether an inspected dataset is a readable artifact.

        ``binary`` is a legitimate answer for an image; ``unreadable`` means the
        backend could not parse a file whose suffix promised it could.
        """
        return inspected.get("kind") != "unreadable"

    def dataset_file(self, upload_id: str) -> dict[str, Any]:
        """Resolve one stored dataset for byte delivery, without parsing it.

        Returns the resolved path, the media type derived from the validated
        suffix, the byte size and a strong ETag.  ``_upload_path`` rejects
        traversal, so the returned path is always inside the upload directory.
        """
        path = self._upload_path(upload_id)
        stat = path.stat()
        return {
            "path": path,
            "name": path.name.split("_", 1)[-1],
            "media_type": CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream"),
            "size": stat.st_size,
            "etag": f'"mf-{stat.st_mtime_ns:x}-{stat.st_size:x}"',
        }

    def list_datasets(self) -> list[dict[str, Any]]:
        if not self.upload_dir.exists():
            return []
        datasets = []
        for path in sorted(self.upload_dir.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
            if path.is_file():
                datasets.append({"id": path.name, "name": path.name.split("_", 1)[-1], "size": path.stat().st_size, "suffix": path.suffix.lower()})
        return datasets

    def validate_graph_patch(self, patch: GraphPatch) -> dict[str, Any]:
        state = self.read_state()
        GraphValidator().validate(state, patch, self.registry())
        return {"valid": True, "current_version": state.version, "next_version": state.version + 1, "patch_id": patch.patch_id}

    def apply_graph_patch(self, patch: GraphPatch) -> GraphState:
        with self._write_lock:
            state = self.read_state()
            audit("patch.received", patch_id=patch.patch_id, base_version=patch.base_version, operations=[op.op for op in patch.operations])
            GraphValidator().validate(state, patch, self.registry())
            before = state.model_dump()
            for operation in patch.operations:
                if operation.op == "add_node": state.nodes.append(operation.node)
                elif operation.op == "update_node":
                    node = node_by_id(state, operation.node_id or "")
                    node.params.update(operation.params or {})
                    changes = operation.changes or {}
                    if "label" in changes: node.label = changes["label"]
                    if "position" in changes: node.position = changes["position"]
                    if "review_policy" in changes: node.review_policy = ReviewPolicy.model_validate(changes["review_policy"])
                elif operation.op == "delete_node":
                    state.nodes = [node for node in state.nodes if node.id != operation.node_id]
                    state.edges = [edge for edge in state.edges if edge.source != operation.node_id and edge.target != operation.node_id]
                elif operation.op == "connect": state.edges.append(operation.edge)
                elif operation.op == "disconnect": state.edges = [edge for edge in state.edges if edge.id != operation.edge_id]
                else:
                    replacement = operation.replacement_node
                    state.nodes = [replacement if node.id == operation.node_id else node for node in state.nodes]
                    state.edges = [edge for edge in state.edges if edge.source != operation.node_id and edge.target != operation.node_id]
                    state.edges.extend(operation.reconnect_edges or [])
            state.version += 1
            state.history.append({"version": state.version, "patch": patch.model_dump(), "before": before})
            self.write_state(state)
            audit("patch.applied", version=state.version, patch_id=patch.patch_id)
            return state

    def route_task(self, task: TaskState) -> dict[str, Any]:
        registry = self.registry()
        decision = DecisionRouter(jev_router=JevDecisionRouter(), llm=self.llm_tool_selector()).decide(task, registry)
        summary = self._summaries.record_routing(task, decision, registry)
        audit("router.decided", task_id=task.task_id, graph_version=task.graph_version, selected=[c.tool_id for c in decision.selected], confidence=decision.confidence, requires_human_confirmation=decision.requires_human_confirmation)
        return decision.model_dump() | {"summary": summary.model_dump()}

    def plan_workflow(self, request: str, *, task_id: str, uploads: list[dict[str, Any]] | None = None, apply: bool = False) -> dict[str, Any]:
        """Prompt -> typed workflow: LLM decomposition, model routing, typed dataflow.

        ``uploads`` are ``{"upload_id", "name"}`` references to files already in
        this save. The planned patch is applied only when the plan is complete
        and ``apply`` is set; otherwise it is returned for human review.
        """
        if self._model_complete is None:
            raise ValueError("Workflow planning requires a configured LLM adapter")
        context = []
        for item in uploads or []:
            inspected = self.inspect_dataset(str(item["upload_id"]))
            context.append({
                "upload_id": inspected["upload_id"],
                "name": str(item.get("name") or inspected["name"]),
                "kind": inspected["kind"],
                "columns": [column["name"] for column in inspected.get("columns", [])],
                "rows": inspected.get("rows"),
            })
        model = load_llm_config().planner_model
        planner = WorkflowPlanner(
            self.registry(),
            with_retry(lambda messages: self.text_completion(messages, model=model)),
            ToolSelector(JevDecisionRouter(), self.llm_tool_selector()),
        )
        plan = planner.plan(request, task_id=task_id, uploads=context, state=self.read_state(), validate=self.validate_graph_patch)
        if apply and plan.status == "planned" and plan.patch is not None:
            plan.graph_version = self.apply_graph_patch(plan.patch).version
            plan.applied = True
        return plan.model_dump()

    def task_summary(self, task_id: str) -> dict[str, Any] | None:
        summary = self._summaries.get(task_id)
        return summary.model_dump() if summary else None

    def execute_node(self, node_id: str, task_id: str | None = None) -> dict[str, Any]:
        with self._write_lock:
            state = self.read_state()
            node = next((item for item in state.nodes if item.id == node_id), None)
            if node is None:
                raise NotFoundError(f"Unknown node: {node_id}", details={"node_id": node_id})
            if node.status == "running":
                raise ConflictError(
                    f"Node {node_id} is already running",
                    code="node_already_running",
                    details={"node_id": node_id, "revision": state.revision},
                )
            # Persist the in-flight state before executing: a second client must
            # see a running node rather than a stale completed one, and the
            # revision must advance even if the process dies mid-execution.
            node.status = "running"
            node.output = None
            node.preview = None
            self.write_state(state)
            try:
                output = self._run_node(state, node)
                self.write_state(state)
                spec = self.registry().get(node.tool_id or node.type)
                output_types = self.registry().type_registry.resolve_ports(spec, node)[1].values()
                # A gate that stopped downstream work must not be recorded as a
                # completed execution.
                status = {"waiting": "waiting", "cancelled": "cancelled"}.get(node.status, "completed")
                execution = ExecutionResult(node_id=node.id, tool_id=spec.tool_id, tool_version=spec.version, status=status, output=output, output_schema_valid=output.get("kind") in output_types, trace_id=current_trace_id())
                summary = self._summaries.record_execution(task_id, execution, self.registry()) if task_id else None
                return {"state": state.model_dump(), "result": output, "execution": execution.model_dump(), "summary": summary.model_dump() if summary else None}
            except ToolExecutionError as exc:
                node.status = "error"
                node.output = {"error": {"code": exc.code, "message": str(exc)}}
                self.write_state(state)
                audit("executor.failed", node_id=node_id, error=str(exc), error_code=exc.code)
                if task_id:
                    spec = self.registry().get(node.tool_id or node.type)
                    failed = ExecutionResult(node_id=node.id, tool_id=spec.tool_id, tool_version=spec.version, status="failed", trace_id=current_trace_id(), error=ExecutionError(code=exc.code, message=str(exc), retryable=exc.retryable))
                    self._summaries.record_execution(task_id, failed, self.registry())
                raise
            except ValueError as exc:
                node.status = "error"
                node.output = {"error": {"code": "execution_failed", "message": str(exc)}}
                self.write_state(state)
                audit("executor.failed", node_id=node_id, error=str(exc), error_code="execution_failed")
                if task_id:
                    spec = self.registry().get(node.tool_id or node.type)
                    failed = ExecutionResult(node_id=node.id, tool_id=spec.tool_id, tool_version=spec.version, status="failed", trace_id=current_trace_id(), error=ExecutionError(code="execution_failed", message=str(exc), retryable=False))
                    self._summaries.record_execution(task_id, failed, self.registry())
                raise

    def execute_workflow(self, *, restart: bool = False) -> dict[str, Any]:
        """Run every runnable node in dependency order.

        The ``ok`` flag is the authoritative success signal: an HTTP layer, an
        agent bridge and a CLI must all be able to tell a failed run from a
        completed one without inspecting individual ``results`` entries, and a
        deliberate stop (a failing gate, a review pause) is not a failure.
        """
        results: list[dict[str, Any]] = []
        GraphValidator().validate_state(self.read_state(), self.registry())
        if restart:
            with self._write_lock:
                state = self.read_state()
                for item in state.nodes:
                    item.status = "ready"
                    item.output = None
                    item.preview = None
                    item.review_state = ReviewState()
                self.write_state(state)

        def outcome(state: GraphState, stopped: bool = False) -> dict[str, Any]:
            failed = [item for item in results if "error" in item]
            return {
                "state": state.model_dump(),
                "results": results,
                "ok": not failed,
                "stopped": stopped,
                "errors": failed,
            }

        while True:
            state = self.read_state()
            if any(item.status == "cancelled" for item in state.nodes):
                return outcome(state, stopped=True)
            pending = [item for item in state.nodes if item.status not in {"completed", "waiting", "cancelled"}]
            node = next((item for item in pending if all(
                node_by_id(state, edge.source).status == "completed"
                for edge in state.edges if edge.target == item.id
            )), None)
            if node is None:
                if pending and not any(item.status == "waiting" for item in state.nodes):
                    results.append({"error": "No runnable node remains; an upstream node is incomplete or waiting.", "error_code": "workflow_stalled"})
                return outcome(state)
            try:
                outcome_payload = self.execute_node(node.id)
                results.append({"node_id": node.id, "result": outcome_payload["result"]})
                if outcome_payload["execution"]["status"] == "waiting":
                    return outcome(GraphState.model_validate(outcome_payload["state"]))
            except ValueError as exc:
                results.append({"node_id": node.id, "error": str(exc), "error_code": getattr(exc, "code", "execution_failed")})
                return outcome(self.read_state())

    def submit_node_review(self, node_id: str, decision: str, comment: str | None = None) -> dict[str, Any]:
        with self._write_lock:
            state = self.read_state()
            node = next((item for item in state.nodes if item.id == node_id), None)
            if node is None:
                raise NotFoundError(f"Unknown node: {node_id}", details={"node_id": node_id})
            if node.status != "waiting" or node.review_state.status != "pending":
                raise ConflictError("The node is not waiting for review", details={"node_id": node_id, "status": node.status})
            if decision not in {"continue", "revise", "stop"}:
                raise ValueError("Decision must be continue, revise, or stop")
            node.review_state = ReviewState(status="approved" if decision == "continue" else "stopped", comment=comment)
            if decision == "continue": node.status = "completed"
            elif decision == "stop": node.status = "cancelled"
            self.write_state(state)
            audit("node_review.submitted", node_id=node_id, decision=decision)
            result = {"state": state.model_dump(), "decision": decision, "results": [], "ok": True}
        if decision == "continue":
            continued = self.execute_workflow()
            result.update({
                "state": continued["state"],
                "results": continued.get("results", []),
                "ok": continued.get("ok", True),
                "errors": continued.get("errors", []),
                "stopped": continued.get("stopped", False),
            })
        return result

    def submit_human_decision(self, node_id: str, decision: str) -> dict[str, Any]:
        """Compatibility alias for pre-v0.3 clients."""
        return self.submit_node_review(node_id, "continue" if decision in {"approve", "continue"} else "stop")

    def _run_node(self, state: GraphState, node: Node) -> dict[str, Any]:
        """Run one node through the single executor seam.

        Core knows nothing about scientific methods here: it resolves the
        validated ToolSpec's executor_ref in the workspace ExecutorRegistry,
        which Platform Core and every loaded Domain Package register into.
        """
        node.status = "running"
        audit("executor.started", node_id=node.id, node_type=node.type)
        spec = self.registry().get(node.tool_id or node.type)
        executor = self.executors.resolve(spec.executor_ref)
        outcome = executor(NodeExecution(runtime=self, state=state, node=node, spec=spec))
        stopped = False
        if isinstance(outcome, ExecutionOutcome):
            node.output = outcome.output
            stopped = outcome.stop
        else:
            node.output = outcome
        node.status = "cancelled" if stopped else "completed"
        node.preview = build_preview(node.output, spec)
        if node.review_policy.after_run and not stopped:
            node.status = "waiting"
            node.review_state = ReviewState(status="pending")
        audit("executor.completed", node_id=node.id, result_kind=node.output.get("kind"), stopped=stopped)
        return node.output

    def node_input(self, state: GraphState, node_id: str, port: str) -> Node:
        """The single upstream node on one port.

        A port declared in ``ToolSpec.multi_input`` may carry several edges, and
        reading only the first would silently drop the rest, so that misuse is
        rejected here instead.
        """
        edges = [edge for edge in state.edges if edge.target == node_id and edge.target_port == port]
        if not edges: raise ValueError(f"{node_id} requires an input connected to '{port}'")
        if len(edges) > 1:
            raise ValueError(f"{node_id}.{port} carries {len(edges)} edges; use the multi-input accessor")
        return node_by_id(state, edges[0].source)

    def node_inputs(self, state: GraphState, node_id: str, port: str) -> list[Node]:
        """Every upstream node on one port, for the multi-input join/aggregate seam."""
        edges = [edge for edge in state.edges if edge.target == node_id and edge.target_port == port]
        if not edges: raise ValueError(f"{node_id} requires an input connected to '{port}'")
        return [node_by_id(state, edge.source) for edge in edges]

    def _upload_path(self, upload_id: str) -> Path:
        if upload_id != Path(upload_id).name:
            raise NotFoundError("Unknown upload. Ask the user to upload the file again.", details={"upload_id": upload_id})
        candidate = self.upload_dir / upload_id
        if not candidate.is_file():
            raise NotFoundError("Unknown upload. Ask the user to upload the file again.", details={"upload_id": upload_id})
        return candidate

    def dataset_frame(self, upload_id: str) -> pd.DataFrame:
        path = self._upload_path(upload_id); suffix = path.suffix.lower()
        if suffix in {".csv", ".txt"}: return pd.read_csv(path, sep=None, engine="python")
        if suffix in {".xlsx", ".xls"}: return pd.read_excel(path)
        if suffix == ".json": return pd.read_json(path)
        raise ValueError(f"{suffix} is not a tabular file")

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content); handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)

    @staticmethod
    def _atomic_write_bytes(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content); handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)

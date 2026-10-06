"""Materials Graph Demo: schema-constrained conversational workflow harness."""
from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any
from urllib import request as urlrequest
from urllib.parse import urlparse

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .contracts import DataType, DataTypeDefinition, GraphPatch, GraphState, Node, Operation, TaskState
from .domain_packages.qe_demo import build_demo_patch
from .domain_packages import REFERENCE_PACKAGE_IDS
from .observability import audit, reset_trace_id, set_trace_id
from .routing import DecisionRouter
from .workspace_runtime import WorkspaceRuntime

ROOT = Path(__file__).resolve().parents[1]
SETTINGS_FILE = ROOT / "data" / "settings.json"
RUNTIME_SKILLS_DIR = ROOT / "runtime_skills"


def load_local_env() -> None:
    path = ROOT / ".env"
    if not path.exists(): return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


load_local_env()

def _runtime_model_adapter(messages: list[dict[str, Any]], tools: list[dict[str, Any]], provider_id: str | None = None, model: str | None = None) -> dict[str, Any]:
    return model_completion(messages, tools, provider_id=provider_id, model=model)


def _composed_domain_packages() -> tuple[str, ...]:
    """The shipped reference composition for this application.

    Platform Core loads no scientific package by itself. This composition enables
    the reference EIS, XRD, FTIR, QE, and demo-fixture packages; set
    `MATFLOW_DOMAIN_PACKAGES` (comma-separated) to change it, or to an empty
    value to run a domain-free Core.
    """
    raw = os.getenv("MATFLOW_DOMAIN_PACKAGES", ",".join(REFERENCE_PACKAGE_IDS))
    return tuple(item.strip() for item in raw.split(",") if item.strip())


workspace = WorkspaceRuntime(model_complete=_runtime_model_adapter, packages=_composed_domain_packages())
app = FastAPI(title="MatFlow Backend", version="1.1.0")
cors_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
cors_origins.extend(origin.strip() for origin in os.getenv("MATFLOW_CORS_ORIGINS", "").split(",") if origin.strip())
app.add_middleware(CORSMiddleware, allow_origins=cors_origins, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def trace_request(request: Request, call_next):
    """Correlate all lifecycle logs and responses for one user request."""
    trace_id = request.headers.get("X-Trace-ID") or uuid.uuid4().hex
    token = set_trace_id(trace_id)
    try:
        response = await call_next(request)
        response.headers["X-Trace-ID"] = trace_id
        return response
    finally:
        reset_trace_id(token)

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    attachments: list[dict[str, Any]] = Field(default_factory=list)
class ExecuteRequest(BaseModel):
    node_id: str
    task_id: str | None = None
class ExecuteWorkflowRequest(BaseModel):
    restart: bool = False
class QEDemoRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
class HumanDecisionRequest(BaseModel):
    node_id: str
    decision: str
    comment: str | None = None
class RevisionProposalRequest(BaseModel):
    node_id: str
    prompt: str = Field(min_length=1, max_length=8000)
    provider_id: str = "local_litellm"
    model: str = "qwen"
class ApplyRevisionRequest(BaseModel):
    edge_decisions: dict[str, str | None] = Field(default_factory=dict)
class CodeReviewRequest(BaseModel):
    approved: bool
class ModelProviderPayload(BaseModel):
    provider_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1, max_length=120)
    base_url: str
    api_key_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    models: list[str] = Field(min_length=1)
class LegacyMigrationRequest(BaseModel):
    apply: bool = False
class SettingsPayload(BaseModel): agent: dict[str, Any]
class NodeLibraryPayload(BaseModel): key: str | None = None; node: dict[str, Any]
class DataTypeInheritancePayload(BaseModel): parents: list[DataType] = Field(default_factory=list)


class RouteRequest(BaseModel):
    task: TaskState

def default_settings() -> dict[str, Any]:
    return {
        "agent": {
            "provider": "openai_compatible",
            "base_url": "http://127.0.0.1:4000/v1",
            "model": "qwen",
            "api_key_env": "MATFLOW_LITELLM_API_KEY",
            "temperature": 0.2,
            "system_prompt": "Respect the runtime skills. Use tools to inspect files and execute work; never invent observations.",
            "max_tool_rounds": 8,
        },
        "runtime_skills": {"enabled": ["matflow_agent_runtime.md"]},
        "custom_nodes": {},
        "custom_data_types": {},
        "revision_proposals": {},
        "model_providers": {
            "local_litellm": {"label": "Local LiteLLM gateway", "base_url": "http://127.0.0.1:4000/v1", "api_key_env": "MATFLOW_LITELLM_API_KEY", "models": ["deepseek-chat", "deepseek-reasoner", "minimax", "glm", "qwen"]}
        },
        "features": {
            "tool_manager_search": False,
            "tool_manager_adapt": False,
            "tool_manager_build": False,
        },
    }

def load_settings() -> dict[str, Any]:
    if not SETTINGS_FILE.exists(): return default_settings()
    loaded = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    defaults = default_settings()
    return {
        **defaults,
        **loaded,
        "agent": {**defaults["agent"], **loaded.get("agent", {})},
        "runtime_skills": {**defaults["runtime_skills"], **loaded.get("runtime_skills", {})},
        "custom_nodes": loaded.get("custom_nodes", {}),
        "custom_data_types": loaded.get("custom_data_types", {}),
        "revision_proposals": loaded.get("revision_proposals", {}),
        "model_providers": loaded.get("model_providers", defaults["model_providers"]),
        "features": {**defaults["features"], **loaded.get("features", {})},
    }

def save_settings(settings: dict[str, Any]) -> None:
    SETTINGS_FILE.parent.mkdir(exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")

def load_runtime_skills() -> list[dict[str, str]]:
    settings = load_settings(); enabled = settings.get("runtime_skills", {}).get("enabled", [])
    skills: list[dict[str, str]] = []
    for name in enabled:
        path = RUNTIME_SKILLS_DIR / Path(name).name
        if path.exists(): skills.append({"name": path.name, "content": path.read_text(encoding="utf-8")})
        else: audit("runtime_skill.missing", skill=name)
    return skills

@app.get("/api/state")
def get_state():
    snapshot = workspace.workspace_snapshot()
    return snapshot | {"settings": workspace.read_settings()["agent"]}


@app.get("/api/capabilities")
def get_capabilities():
    """Stable, read-only control-plane data for a future WebUI or other client."""
    settings = workspace.read_settings()
    type_registry = workspace.data_type_registry()
    return {
        "api_contract": {"name": "matflow-http", "version": "1.0"},
        "server_version": "1.1.0",
        "registry": workspace.registry().legacy_view(),
        "data_types": list(type_registry.names()),
        "data_type_definitions": type_registry.definitions(),
        "features": settings["features"],
        "domain_packages": workspace.packages.legacy_view(),
        "operations": {
            "chat": "POST /api/chat",
            "route": "POST /api/route",
            "list_datasets": "GET /api/uploads",
            "import_dataset": "POST /api/uploads",
            "read_task_summary": "GET /api/task-summaries/{task_id}",
            "apply_graph_patch": "POST /api/patch",
            "validate_graph_patch": "POST /api/patch/validate",
            "execute_node": "POST /api/execute",
            "execute_workflow": "POST /api/workflow/execute",
            "qe_replay_demo": "POST /api/qe/demo",
            "propose_node_revision": "POST /api/node-revisions/proposals",
            "submit_node_review": "POST /api/workflow/decision",
            "submit_human_decision": "POST /api/workflow/human-decision",
            "create_data_type": "POST /api/data-types",
            "update_data_type_inheritance": "PUT /api/data-types/{name}/parents",
        },
    }


@app.get("/api/data-types")
def get_data_types():
    type_registry = workspace.data_type_registry()
    return {"data_types": list(type_registry.names()), "definitions": type_registry.definitions()}


@app.post("/api/data-types")
def create_data_type(payload: DataTypeDefinition):
    try:
        return workspace.create_data_type(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.put("/api/data-types/{name}/parents")
def update_data_type_inheritance(name: str, payload: DataTypeInheritancePayload):
    try:
        return workspace.update_data_type_inheritance(name, payload.parents)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@app.get("/api/settings")
def get_settings(): return workspace.read_settings()

@app.put("/api/settings")
def update_settings(payload: SettingsPayload):
    settings = workspace.read_settings(); settings["agent"] = payload.agent; workspace.write_settings(settings)
    audit("settings.updated", keys=list(payload.agent)); return settings

@app.get("/api/runtime-skills")
def get_runtime_skills():
    return {"enabled": load_settings().get("runtime_skills", {}).get("enabled", []), "available": [path.name for path in RUNTIME_SKILLS_DIR.glob("*.md")] if RUNTIME_SKILLS_DIR.exists() else []}

@app.get("/api/node-library")
def get_node_library(): return {"preset": workspace.registry().legacy_view(), "custom": workspace.read_settings()["custom_nodes"]}


def validate_provider_url(value: str) -> str:
    parsed = urlparse(value)
    loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme not in ({"http", "https"} if loopback else {"https"}) or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Provider URL must use HTTPS, except HTTP is allowed for a loopback gateway")
    return value.rstrip("/")


@app.get("/api/model-providers")
def get_model_providers(refresh: bool = False):
    providers = workspace.read_settings().get("model_providers", {})
    result = []
    for key, value in providers.items():
        item = {"id": key, **value, "key_configured": bool(os.getenv(value["api_key_env"]))}
        if refresh and item["key_configured"]:
            request = urlrequest.Request(value["base_url"].rstrip("/") + "/models", headers={"Authorization": f"Bearer {os.environ[value['api_key_env']]}"})
            try:
                with urlrequest.urlopen(request, timeout=3) as response:
                    payload = json.loads(response.read(512 * 1024))
                item["models"] = [entry["id"] for entry in payload.get("data", []) if isinstance(entry, dict) and isinstance(entry.get("id"), str)] or value["models"]
                item["reachable"] = True
            except Exception:
                item["reachable"] = False
        result.append(item)
    return {"providers": result}


@app.post("/api/model-providers")
def put_model_provider(payload: ModelProviderPayload):
    try: base_url = validate_provider_url(payload.base_url)
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc
    settings = workspace.read_settings()
    settings.setdefault("model_providers", {})[payload.provider_id] = {"label": payload.label, "base_url": base_url, "api_key_env": payload.api_key_env, "models": payload.models}
    workspace.write_settings(settings)
    return {"id": payload.provider_id, **settings["model_providers"][payload.provider_id], "key_configured": bool(os.getenv(payload.api_key_env))}


@app.post("/api/node-revisions/proposals")
def create_node_revision(request: RevisionProposalRequest):
    try: return workspace.create_revision_proposal(request.node_id, request.prompt, request.provider_id, request.model)
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/node-revisions/proposals/{proposal_id}")
def get_node_revision(proposal_id: str):
    try: return workspace.get_revision_proposal(proposal_id)
    except ValueError as exc: raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/node-revisions/proposals/{proposal_id}/review-code")
def review_node_revision_code(proposal_id: str, request: CodeReviewRequest):
    try: return workspace.review_revision_code(proposal_id, request.approved)
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/node-revisions/proposals/{proposal_id}/apply")
def apply_node_revision(proposal_id: str, request: ApplyRevisionRequest):
    try: return {"state": workspace.apply_revision_proposal(proposal_id, request.edge_decisions).model_dump()}
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/migrations/human-decision")
def migrate_human_decisions(request: LegacyMigrationRequest):
    try: return workspace.migrate_legacy_human_decisions(apply=request.apply)
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc

def validate_library_node(node: dict[str, Any]) -> dict[str, Any]:
    required = {"label", "category", "inputs", "outputs", "params", "description"}
    missing = required - set(node)
    if missing: raise ValueError(f"Node definition is missing: {', '.join(sorted(missing))}")
    if not isinstance(node["inputs"], dict) or not isinstance(node["outputs"], dict) or not isinstance(node["params"], dict): raise ValueError("inputs, outputs and params must be JSON objects")
    workspace.data_type_registry().validate_port_types((*node["inputs"].values(), *node["outputs"].values()))
    return node

@app.post("/api/node-library")
def add_library_node(payload: NodeLibraryPayload):
    try:
        settings = load_settings(); node = validate_library_node(payload.node)
        key = payload.key or re.sub(r"[^a-z0-9_]+", "_", node["label"].lower()).strip("_")
        if not key or key in workspace.registry().active() or key in settings["custom_nodes"]: raise ValueError("Choose a unique node key")
        settings["custom_nodes"][key] = node; save_settings(settings); audit("node_library.created", key=key)
        return {"key": key, "node": node}
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc))

@app.put("/api/node-library/{key}")
def update_library_node(key: str, payload: NodeLibraryPayload):
    try:
        settings = load_settings()
        if key not in settings["custom_nodes"]: raise ValueError("Only custom nodes can be edited")
        node = validate_library_node(payload.node); settings["custom_nodes"][key] = node; save_settings(settings); audit("node_library.updated", key=key)
        return {"key": key, "node": node}
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc))

@app.delete("/api/node-library/{key}")
def delete_library_node(key: str):
    settings = load_settings()
    if key not in settings["custom_nodes"]: raise HTTPException(status_code=404, detail="Only custom nodes can be deleted")
    del settings["custom_nodes"][key]; save_settings(settings); audit("node_library.deleted", key=key)
    return {"ok": True}

@app.post("/api/node-library/prompt-build")
def prompt_build_node(request: ChatRequest):
    """A deterministic template builder; a real LLM can replace this bounded step later."""
    name = re.sub(r"[^a-zA-Z0-9 _-]", "", request.message).strip()[:48] or "Derived Analysis"
    node = {"label": name, "category": "Derived", "inputs": {"input": "TypedTable"}, "outputs": {"output": "PropertySeries"}, "params": {"method": "default"}, "description": f"Prompt-built template: {request.message.strip()[:160]}"}
    # PropertySeries is valid in the product schema, but is not yet an executable demo type.
    node["outputs"] = {"output": "TypedTable"}
    audit("node_library.prompt_built", prompt=request.message[:300], label=name)
    return {"key": re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_"), "node": node}

@app.post("/api/uploads")
async def upload_files(files: list[UploadFile] = File(...)):
    uploaded = []
    for file in files:
        try:
            uploaded.append(workspace.import_dataset(file.filename or "upload", await file.read(), file.content_type or "application/octet-stream"))
        except ValueError as exc:
            status = 413 if "25 MB" in str(exc) else 415
            raise HTTPException(status_code=status, detail=str(exc)) from exc
    return {"files": uploaded}


@app.get("/api/uploads")
def list_uploads():
    return {"files": workspace.list_datasets()}


@app.get("/api/uploads/{upload_id}")
def inspect_uploaded_file(upload_id: str):
    try:
        return workspace.inspect_dataset(upload_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

@app.post("/api/patch")
def post_patch(patch: GraphPatch):
    try:
        return {"state": workspace.apply_graph_patch(patch).model_dump()}
    except ValueError as exc:
        if str(exc).startswith("Version conflict:"):
            raise HTTPException(status_code=409, detail={"code": "graph_version_conflict", "message": str(exc), "current_version": workspace.read_state().version}) from exc
        raise HTTPException(status_code=422, detail={"code": getattr(exc, "code", "invalid_graph_patch"), "message": str(exc)}) from exc


@app.post("/api/patch/validate")
def validate_graph_patch(patch: GraphPatch):
    try:
        return workspace.validate_graph_patch(patch)
    except ValueError as exc:
        if str(exc).startswith("Version conflict:"):
            raise HTTPException(status_code=409, detail={"code": "graph_version_conflict", "message": str(exc), "current_version": workspace.read_state().version}) from exc
        raise HTTPException(status_code=422, detail={"code": getattr(exc, "code", "invalid_graph_patch"), "message": str(exc)}) from exc


@app.post("/api/route")
def route_task(request: RouteRequest):
    return workspace.route_task(request.task)


@app.get("/api/task-summaries/{task_id}")
def get_task_summary(task_id: str):
    summary = workspace.task_summary(task_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="No persisted task summary exists for this task_id.")
    return summary

TOOL_SCHEMAS = [
    {"type": "function", "function": {"name": "inspect_upload", "description": "Inspect a user-uploaded file before making analysis claims. Returns columns and a small preview for tabular files.", "parameters": {"type": "object", "properties": {"upload_id": {"type": "string"}}, "required": ["upload_id"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "get_graph", "description": "Read the current typed workflow graph and node outputs.", "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
    {"type": "function", "function": {"name": "apply_graph_patch", "description": "Apply a proposed graph patch. The patch is type-checked, version-checked and audited before it changes the graph.", "parameters": {"type": "object", "properties": {"patch": {"type": "object"}}, "required": ["patch"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "run_workflow", "description": "Execute ready nodes in topological order. Stops safely at an error or human decision.", "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
    {"type": "function", "function": {"name": "add_skill_node", "description": "Add an AI Skill Node with a stable TypedTable input and Artifact output. Connect it with apply_graph_patch.", "parameters": {"type": "object", "properties": {"label": {"type": "string"}, "skill_id": {"type": "string"}, "instructions": {"type": "string"}, "output_schema": {"type": "object"}}, "required": ["label", "skill_id", "instructions", "output_schema"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "propose_tool_recipe", "description": "Propose a draft, declarative XRD or FTIR analysis recipe. The proposal is isolated and requires evaluation and human review before activation.", "parameters": {"type": "object", "properties": {"label": {"type": "string"}, "description": {"type": "string"}, "recipe": {"type": "object"}}, "required": ["label", "description", "recipe"], "additionalProperties": False}}},
]

def model_completion(messages: list[dict[str, Any]], tools: list[dict[str, Any]], provider_id: str | None = None, model: str | None = None) -> dict[str, Any]:
    if provider_id and os.getenv("MATFLOW_ALLOW_MODEL_MOCK") == "1" and os.getenv("MATFLOW_REVISION_MOCK_JSON"):
        return {"role": "assistant", "content": os.environ["MATFLOW_REVISION_MOCK_JSON"]}
    settings = workspace.read_settings() if "workspace" in globals() else load_settings()
    config = settings["agent"]
    if provider_id:
        provider = settings.get("model_providers", {}).get(provider_id)
        if provider is None: raise HTTPException(status_code=422, detail=f"Unknown model provider: {provider_id}")
        if model is not None and model not in provider["models"]:
            raise HTTPException(status_code=422, detail=f"Unknown model for provider {provider_id}: {model}")
        config = {**config, **provider, "model": model or provider["models"][0]}
    key = os.getenv(config.get("api_key_env", "MATFLOW_API_KEY"), "")
    if not config.get("model") or not key:
        raise HTTPException(status_code=503, detail=f"Agent is not configured. Set a model in Settings and set environment variable {config.get('api_key_env', 'MATFLOW_API_KEY')}.")
    url = config.get("base_url", "").rstrip("/") + "/chat/completions"
    body = {"model": config["model"], "messages": messages, "temperature": config.get("temperature", 0.2)}
    if tools: body["tools"] = tools; body["tool_choice"] = "auto"
    req = urlrequest.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"}, method="POST")
    try:
        with urlrequest.urlopen(req, timeout=90) as response: data = json.loads(response.read(2 * 1024 * 1024))
        message = data["choices"][0]["message"]
        if not isinstance(message, dict):
            raise TypeError("Model provider message must be a JSON object")
        return message
    except (OSError, TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
        audit("model.failed", error=str(exc)); raise HTTPException(status_code=502, detail=f"Model provider request failed: {exc}")

def run_agent_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    audit("tool.called", tool=name, arguments=arguments)
    if name == "inspect_upload": return workspace.inspect_dataset(arguments["upload_id"])
    if name == "get_graph": return workspace.read_state().model_dump()
    if name == "apply_graph_patch":
        patch = GraphPatch.model_validate(arguments["patch"])
        registry = workspace.registry()
        for operation in patch.operations:
            node = operation.node if operation.op == "add_node" else operation.replacement_node if operation.op == "replace_node_revision" else None
            if node is not None and not registry.get(node.type).agent_selectable:
                raise ValueError(f"Tool {node.type} is not available for agent selection")
        return {"state": workspace.apply_graph_patch(patch).model_dump()}
    if name == "propose_tool_recipe": return workspace.propose_analysis_recipe(
        label=str(arguments["label"]), description=str(arguments["description"]), recipe=arguments["recipe"]
    )
    if name == "add_skill_node":
        state = workspace.read_state(); node = Node(id=f"skill-{uuid.uuid4().hex[:8]}", type="skill_node", label=arguments["label"], params={key: arguments[key] for key in ("skill_id", "instructions", "output_schema")})
        return {"state": workspace.apply_graph_patch(GraphPatch(base_version=state.version, operations=[Operation(op="add_node", node=node)], rationale="Agent added a schema-bound Skill Node.")).model_dump(), "node_id": node.id}
    if name == "run_workflow":
        return workspace.execute_workflow()
    raise ValueError(f"Tool is not registered: {name}")

@app.post("/api/chat")
def chat(request: ChatRequest):
    audit("chat.received", message=request.message[:1000], attachments=[item.get("name") for item in request.attachments])
    initial_task = TaskState(
        user_message=request.message,
        graph_version=workspace.read_state().version,
        available_input_types=["RawData", "TypedTable"] if request.attachments else [],
    )
    initial_lexical = DecisionRouter().decide(initial_task, workspace.registry())
    initial_requires_confirmation = not initial_lexical.selected and initial_lexical.requires_human_confirmation
    if not request.attachments:
        if initial_requires_confirmation:
            return {
                "task_id": request.task_id,
                "conversation_id": request.conversation_id,
                "status": "waiting_for_confirmation",
                "message": "请说明数据类型、输入文件和希望得到的分析结果。",
                "state": workspace.read_state().model_dump(),
                "trace": [],
                "tool_proposals": [],
                "runtime_skills": [],
                "error": None,
            }
    skills = load_runtime_skills()
    system = "\n\n".join(["You are the MatFlow runtime agent.", *[f"## Runtime Skill: {skill['name']}\n{skill['content']}" for skill in skills], load_settings()["agent"].get("system_prompt", "")])
    user_context = {"message": request.message, "uploads": request.attachments, "runtime_skills": [skill["name"] for skill in skills], "node_catalog": workspace.registry().legacy_view(agent_selectable_only=True), "data_types": list(workspace.data_type_registry().names()), "instruction": "Use tools for observations and changes. If a required capability is absent, propose a draft declarative recipe and leave it for evaluation and human review. If required information is ambiguous, ask the user a concise question instead of guessing."}
    messages: list[dict[str, Any]] = [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(user_context, ensure_ascii=False)}]
    trace: list[dict[str, Any]] = []
    try:
        for round_index in range(int(load_settings()["agent"].get("max_tool_rounds", 8))):
            reply = model_completion(messages, TOOL_SCHEMAS); tool_calls = reply.get("tool_calls") or []
            if not tool_calls:
                content = reply.get("content") or "I completed the available steps."
                audit("agent.reply", reply=content[:1000], rounds=round_index + 1)
                current_state = workspace.read_state().model_dump()
                recovered_errors = [item.get("error") for item in trace if not item.get("ok", False)]
                proposals = [
                    item["result"] for item in trace
                    if item.get("ok") and item.get("tool") in {"propose_tool_recipe", "propose_node_revision"}
                ]
                failed = any(node.get("status") == "error" for node in current_state.get("nodes", [])) or bool(
                    trace and not trace[-1].get("ok", False)
                )
                waiting = any(
                    node.get("status") == "waiting"
                    for node in current_state.get("nodes", [])
                ) or bool(proposals) or (
                    initial_requires_confirmation and not current_state.get("nodes")
                )
                return {
                    "task_id": request.task_id,
                    "conversation_id": request.conversation_id,
                    "status": "failed" if failed else ("waiting_for_confirmation" if waiting else "completed"),
                    "message": content,
                    "state": current_state,
                    "trace": trace,
                    "tool_proposals": proposals,
                    "runtime_skills": [skill["name"] for skill in skills],
                    "error": recovered_errors[-1] if failed and recovered_errors else None,
                    "warnings": recovered_errors if not failed else [],
                }
            messages.append({"role": "assistant", "content": reply.get("content") or "", "tool_calls": tool_calls})
            for call in tool_calls:
                name = call["function"]["name"]
                try: result = run_agent_tool(name, json.loads(call["function"].get("arguments") or "{}")); event = {"tool": name, "ok": True, "result": result}
                except Exception as exc: event = {"tool": name, "ok": False, "error": str(exc)}
                trace.append(event); messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(event, ensure_ascii=False, default=str)})
        current_state = workspace.read_state().model_dump()
        return {
            "task_id": request.task_id,
            "conversation_id": request.conversation_id,
            "status": "waiting_for_confirmation",
            "message": "自动规划已达到本次轮次上限，需要人工确认工具契约、输入或下一步操作。",
            "state": current_state,
            "trace": trace,
            "tool_proposals": [
                item["result"] for item in trace
                if item.get("ok") and item.get("tool") in {"propose_tool_recipe", "propose_node_revision"}
            ],
            "runtime_skills": [skill["name"] for skill in skills],
            "error": None,
            "warnings": ["Agent reached the configured tool-round limit without a final answer."],
        }
    except HTTPException: raise
    except Exception as exc:
        audit("agent.failed", error=str(exc)); raise HTTPException(status_code=422, detail=str(exc))

@app.post("/api/reset")
def reset(include_settings: bool = False):
    workspace.write_state(GraphState())
    if include_settings:
        if os.getenv("MATFLOW_ALLOW_MODEL_MOCK") != "1":
            raise HTTPException(status_code=403, detail="Full reset is available only in an isolated test runtime")
        workspace.write_settings(default_settings())
        if workspace.upload_dir.exists():
            for path in workspace.upload_dir.iterdir():
                if path.is_file(): path.unlink()
    return {"ok": True}

@app.post("/api/execute")
def execute(request: ExecuteRequest):
    try:
        return workspace.execute_node(request.node_id, request.task_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": getattr(exc, "code", "execution_failed"), "message": str(exc)}) from exc


@app.post("/api/workflow/execute")
def execute_workflow(request: ExecuteWorkflowRequest):
    try:
        return workspace.execute_workflow(restart=request.restart)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": getattr(exc, "code", "invalid_workflow"), "message": str(exc)}) from exc


@app.post("/api/qe/demo")
def run_qe_replay_demo(request: QEDemoRequest):
    """Run the fixed MgO natural-language-to-QE replay workflow from an empty graph."""
    if workspace.read_state().nodes or workspace.read_state().edges:
        raise HTTPException(status_code=409, detail={"code": "demo_requires_empty_workspace", "message": "Start the QE replay demo in an empty workspace so it does not replace existing research state."})
    if "qe" not in workspace.packages.package_ids():
        raise HTTPException(status_code=503, detail={"code": "qe_package_unavailable", "message": "Enable the qe Domain Package to run this demo."})
    try:
        patch = build_demo_patch(workspace.read_state().version, request.message)
        graph = workspace.apply_graph_patch(patch)
        outcome = workspace.execute_workflow(restart=True)
        return {
            "request": request.message,
            "planner": "pinned_mgo_scf_demo",
            "execution_mode": "historical_output_replay",
            "slurm_submitted": False,
            "state": outcome["state"],
            "results": outcome["results"],
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": getattr(exc, "code", "invalid_demo_request"), "message": str(exc)}) from exc


@app.post("/api/workflow/decision")
def submit_workflow_decision(request: HumanDecisionRequest):
    try:
        return workspace.submit_node_review(request.node_id, request.decision, request.comment)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/workflow/human-decision")
def submit_human_decision(request: HumanDecisionRequest):
    try:
        return workspace.submit_human_decision(request.node_id, request.decision)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

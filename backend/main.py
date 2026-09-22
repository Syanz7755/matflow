"""Materials Graph Demo: schema-constrained conversational workflow harness."""
from __future__ import annotations

import copy
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

import numpy as np
import pandas as pd

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .contracts import DATA_TYPES, Edge, GraphPatch, GraphState, Node, Operation
from .observability import audit, reset_trace_id, set_trace_id
from .tool_registry import ToolRegistry, builtin_specs

ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "data" / "graph_state.json"
SETTINGS_FILE = ROOT / "data" / "settings.json"
UPLOAD_DIR = ROOT / "data" / "uploads"
RUNTIME_SKILLS_DIR = ROOT / "runtime_skills"

app = FastAPI(title="Materials Graph Demo")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])


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
    message: str = ""
    attachments: list[dict[str, Any]] = Field(default_factory=list)
class ExecuteRequest(BaseModel): node_id: str
class SettingsPayload(BaseModel): agent: dict[str, Any]
class NodeLibraryPayload(BaseModel): key: str | None = None; node: dict[str, Any]

def load() -> GraphState:
    return GraphState.model_validate_json(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else GraphState()

def save(state: GraphState) -> None:
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(state.model_dump_json(indent=2), encoding="utf-8")

def default_settings() -> dict[str, Any]:
    return {
        "agent": {
            "provider": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
            "model": "",
            "api_key_env": "MATFLOW_API_KEY",
            "temperature": 0.2,
            "system_prompt": "Respect the runtime skills. Use tools to inspect files and execute work; never invent observations.",
            "max_tool_rounds": 8,
        },
        "runtime_skills": {"enabled": ["matflow_agent_runtime.md"]},
        "custom_nodes": {},
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
        "features": {**defaults["features"], **loaded.get("features", {})},
    }

def save_settings(settings: dict[str, Any]) -> None:
    SETTINGS_FILE.parent.mkdir(exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")

def registry() -> dict[str, dict[str, Any]]:
    return ToolRegistry(load_settings()["custom_nodes"]).legacy_view()

def load_runtime_skills() -> list[dict[str, str]]:
    settings = load_settings(); enabled = settings.get("runtime_skills", {}).get("enabled", [])
    skills: list[dict[str, str]] = []
    for name in enabled:
        path = RUNTIME_SKILLS_DIR / Path(name).name
        if path.exists(): skills.append({"name": path.name, "content": path.read_text(encoding="utf-8")})
        else: audit("runtime_skill.missing", skill=name)
    return skills

def node_by_id(state: GraphState, node_id: str) -> Node:
    return next((node for node in state.nodes if node.id == node_id), None) or (_ for _ in ()).throw(ValueError(f"Unknown node: {node_id}"))

def validate_patch(state: GraphState, patch: GraphPatch) -> None:
    if patch.base_version != state.version: raise ValueError(f"Version conflict: patch is based on v{patch.base_version}, current graph is v{state.version}")
    scratch = copy.deepcopy(state)
    for operation in patch.operations:
        if operation.op == "add_node":
            specs = registry()
            if operation.node.type not in specs: raise ValueError(f"Unknown registry node: {operation.node.type}")
            if any(n.id == operation.node.id for n in scratch.nodes): raise ValueError(f"Duplicate node id: {operation.node.id}")
            scratch.nodes.append(operation.node)
        elif operation.op == "update_node":
            node = node_by_id(scratch, operation.node_id)
            allowed = registry()[node.type]["params"]
            invalid = set((operation.params or {})) - set(allowed)
            if invalid: raise ValueError(f"Unsupported parameter(s) for {node.type}: {', '.join(invalid)}")
            node.params.update(operation.params or {})
        elif operation.op == "delete_node":
            node_by_id(scratch, operation.node_id)
            scratch.nodes = [n for n in scratch.nodes if n.id != operation.node_id]
            scratch.edges = [e for e in scratch.edges if e.source != operation.node_id and e.target != operation.node_id]
        elif operation.op == "connect":
            edge = operation.edge; source = node_by_id(scratch, edge.source); target = node_by_id(scratch, edge.target)
            specs = registry(); source_type = specs[source.type]["outputs"].get(edge.source_port)
            target_type = specs[target.type]["inputs"].get(edge.target_port)
            if not source_type or not target_type: raise ValueError("Unknown port in edge")
            if source_type != target_type: raise ValueError(f"Type mismatch: {source_type} cannot connect to {target_type}")
            if any(e.id == edge.id for e in scratch.edges): raise ValueError(f"Duplicate edge id: {edge.id}")
            scratch.edges.append(edge)
        elif operation.op == "disconnect":
            if not any(e.id == operation.edge_id for e in scratch.edges): raise ValueError(f"Unknown edge: {operation.edge_id}")

def apply_patch(state: GraphState, patch: GraphPatch) -> GraphState:
    audit("patch.received", patch_id=patch.patch_id, base_version=patch.base_version, operations=[operation.op for operation in patch.operations])
    validate_patch(state, patch)
    before = state.model_dump()
    for operation in patch.operations:
        if operation.op == "add_node": state.nodes.append(operation.node)
        elif operation.op == "update_node": node_by_id(state, operation.node_id).params.update(operation.params or {})
        elif operation.op == "delete_node":
            state.nodes = [n for n in state.nodes if n.id != operation.node_id]; state.edges = [e for e in state.edges if e.source != operation.node_id and e.target != operation.node_id]
        elif operation.op == "connect": state.edges.append(operation.edge)
        else: state.edges = [e for e in state.edges if e.id != operation.edge_id]
    state.version += 1
    state.history.append({"version": state.version, "patch": patch.model_dump(), "before": before})
    save(state); audit("patch.applied", version=state.version, patch_id=patch.patch_id); return state

def standard_node(kind: str, i: int) -> Node:
    spec = registry()[kind]
    return Node(id=f"{kind}-{i}", type=kind, label=spec["label"], params=copy.deepcopy(spec["params"]), position={"x": 80 + i * 230, "y": 140 + (i % 2) * 170})

@app.get("/api/state")
def get_state():
    settings = load_settings()
    return {"state": load().model_dump(), "registry": registry(), "data_types": DATA_TYPES, "settings": settings["agent"], "runtime_skills": [skill["name"] for skill in load_runtime_skills()], "features": settings["features"]}

@app.get("/api/settings")
def get_settings(): return load_settings()

@app.put("/api/settings")
def update_settings(payload: SettingsPayload):
    settings = load_settings(); settings["agent"] = payload.agent; save_settings(settings)
    audit("settings.updated", keys=list(payload.agent)); return settings

@app.get("/api/runtime-skills")
def get_runtime_skills():
    return {"enabled": load_settings().get("runtime_skills", {}).get("enabled", []), "available": [path.name for path in RUNTIME_SKILLS_DIR.glob("*.md")] if RUNTIME_SKILLS_DIR.exists() else []}

@app.get("/api/node-library")
def get_node_library(): return {"preset": REGISTRY, "custom": load_settings()["custom_nodes"]}

def validate_library_node(node: dict[str, Any]) -> dict[str, Any]:
    required = {"label", "category", "inputs", "outputs", "params", "description"}
    missing = required - set(node)
    if missing: raise ValueError(f"Node definition is missing: {', '.join(sorted(missing))}")
    if not isinstance(node["inputs"], dict) or not isinstance(node["outputs"], dict) or not isinstance(node["params"], dict): raise ValueError("inputs, outputs and params must be JSON objects")
    unknown_types = (set(node["inputs"].values()) | set(node["outputs"].values())) - set(DATA_TYPES)
    if unknown_types: raise ValueError(f"Unknown data types: {', '.join(unknown_types)}")
    return node

@app.post("/api/node-library")
def add_library_node(payload: NodeLibraryPayload):
    try:
        settings = load_settings(); node = validate_library_node(payload.node)
        key = payload.key or re.sub(r"[^a-z0-9_]+", "_", node["label"].lower()).strip("_")
        if not key or key in builtin_specs() or key in settings["custom_nodes"]: raise ValueError("Choose a unique node key")
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
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True); uploaded = []
    for file in files:
        filename = Path(file.filename or "upload").name
        suffix = Path(filename).suffix.lower()
        if suffix not in {".csv", ".txt", ".xlsx", ".xls", ".json", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}: raise HTTPException(status_code=415, detail=f"Unsupported file type: {suffix or 'none'}")
        token = f"{uuid.uuid4().hex}_{filename}"; destination = UPLOAD_DIR / token; content = await file.read()
        if len(content) > 25 * 1024 * 1024: raise HTTPException(status_code=413, detail=f"{filename} exceeds the 25 MB demo limit")
        destination.write_bytes(content); record = {"id": token, "name": filename, "size": len(content), "type": file.content_type or "application/octet-stream"}; uploaded.append(record)
        audit("upload.saved", **record)
    return {"files": uploaded}

@app.post("/api/patch")
def post_patch(patch: GraphPatch):
    try: return {"state": apply_patch(load(), patch).model_dump()}
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc))

def upload_path(upload_id: str) -> Path:
    """Resolve a server-generated upload token without allowing path traversal."""
    candidate = UPLOAD_DIR / Path(upload_id).name
    if not candidate.exists() or candidate.parent != UPLOAD_DIR:
        raise ValueError("Unknown upload. Ask the user to upload the file again.")
    return candidate

def dataframe_for_upload(upload_id: str) -> pd.DataFrame:
    path = upload_path(upload_id); suffix = path.suffix.lower()
    if suffix in {".csv", ".txt"}:
        return pd.read_csv(path, sep=None, engine="python")
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if suffix == ".json":
        return pd.read_json(path)
    raise ValueError(f"{suffix} is not a tabular file. This operation needs CSV, TXT, XLSX, XLS or JSON.")

def inspect_upload(upload_id: str) -> dict[str, Any]:
    path = upload_path(upload_id)
    result: dict[str, Any] = {"upload_id": upload_id, "name": path.name.split("_", 1)[-1], "suffix": path.suffix.lower(), "bytes": path.stat().st_size}
    try:
        frame = dataframe_for_upload(upload_id)
        result.update({"kind": "table", "rows": len(frame), "columns": [{"name": str(name), "dtype": str(dtype)} for name, dtype in frame.dtypes.items()], "preview": frame.head(8).replace({np.nan: None}).to_dict(orient="records")})
    except ValueError:
        result["kind"] = "binary"
    except Exception as exc:
        result.update({"kind": "unreadable", "error": str(exc)})
    audit("tool.inspect_upload", upload_id=upload_id, kind=result["kind"])
    return result

def node_input(state: GraphState, node_id: str, port: str) -> Node:
    edge = next((edge for edge in state.edges if edge.target == node_id and edge.target_port == port), None)
    if not edge: raise ValueError(f"{node_id} requires an input connected to '{port}'")
    return node_by_id(state, edge.source)

def run_node_in_state(state: GraphState, node: Node) -> dict[str, Any]:
    """Small, real executor set. New domain work belongs in Skill Nodes, not the agent loop."""
    node.status = "running"; audit("executor.started", node_id=node.id, node_type=node.type)
    if node.type == "raw_file_import":
        upload_id = node.params.get("upload_id")
        if not upload_id: raise ValueError("Raw File Import has no upload_id. Inspect an upload then set this parameter.")
        inspected = inspect_upload(str(upload_id))
        if inspected["kind"] != "table": raise ValueError("Raw File Import only supports tabular data in this demo.")
        node.output = {"kind": "RawData", "upload_id": upload_id, "rows": inspected["rows"], "columns": [column["name"] for column in inspected["columns"]], "preview": inspected["preview"]}
    elif node.type == "normalize_columns":
        raw = node_input(state, node.id, "raw")
        if not raw.output: raise ValueError(f"Upstream node {raw.id} has not run")
        columns = set(raw.output["columns"]); mapping = node.params
        missing = [mapping[key] for key in ("frequency_column", "real_column", "imag_column") if mapping.get(key) not in columns]
        if missing: raise ValueError(f"Column mapping does not match the uploaded file: {missing}")
        node.output = {"kind": "TypedTable", "upload_id": raw.output["upload_id"], "mapping": mapping, "rows": raw.output["rows"]}
    elif node.type == "eis_basic_qc":
        table = node_input(state, node.id, "data")
        if not table.output: raise ValueError(f"Upstream node {table.id} has not run")
        frame = dataframe_for_upload(table.output["upload_id"]); mapping = table.output["mapping"]
        frequency = pd.to_numeric(frame[mapping["frequency_column"]], errors="coerce")
        real = pd.to_numeric(frame[mapping["real_column"]], errors="coerce")
        imag = pd.to_numeric(frame[mapping["imag_column"]], errors="coerce")
        valid = frequency.notna() & real.notna() & imag.notna() & (frequency > 0)
        threshold = float(node.params["min_frequency_hz"])
        node.output = {"kind": "EISQCReport", "upload_id": table.output["upload_id"], "mapping": mapping, "rows_valid": int(valid.sum()), "rows_retained": int((valid & (frequency >= threshold)).sum()), "min_frequency_hz": threshold, "pass": bool(valid.any()), "issues": [] if valid.all() else [f"{int((~valid).sum())} invalid rows ignored"]}
    elif node.type == "plot_nyquist":
        report = node_input(state, node.id, "data")
        if not report.output: raise ValueError(f"Upstream node {report.id} has not run")
        frame = dataframe_for_upload(report.output["upload_id"]); mapping = report.output["mapping"]
        real = pd.to_numeric(frame[mapping["real_column"]], errors="coerce"); imag = pd.to_numeric(frame[mapping["imag_column"]], errors="coerce")
        valid = real.notna() & imag.notna(); points = [[float(x), float(-y)] for x, y in zip(real[valid].head(500), imag[valid].head(500))]
        node.output = {"kind": "Plot", "plot_type": "Nyquist", "title": node.params["title"], "series": points, "points": len(points)}
    elif node.type == "human_decision":
        node.status = "waiting"; node.output = {"kind": "Decision", "prompt": node.params["prompt"], "options": node.params["options"]}; return node.output
    elif node.type == "skill_node":
        table = node_input(state, node.id, "dataset")
        if not table.output: raise ValueError(f"Upstream node {table.id} has not run")
        node.output = run_skill_node(node, table.output)
    else: raise ValueError("No executor registered for this node")
    node.status = "completed"; audit("executor.completed", node_id=node.id, result_kind=node.output.get("kind")); return node.output

def run_skill_node(node: Node, typed_input: dict[str, Any]) -> dict[str, Any]:
    """Compatibility adapter: every domain skill node has TypedTable in and Artifact out."""
    preview = inspect_upload(str(typed_input["upload_id"])).get("preview", [])
    contract = {"skill_id": node.params.get("skill_id"), "instructions": node.params.get("instructions"), "input": {"mapping": typed_input.get("mapping"), "preview": preview}, "output_schema": node.params.get("output_schema", {})}
    answer = model_completion([{ "role": "system", "content": "Execute this Skill Node. Return only a JSON object conforming to output_schema; do not claim unobserved values."}, {"role": "user", "content": json.dumps(contract, ensure_ascii=False)}], tools=[])
    try: payload = json.loads(answer.get("content") or "{}")
    except json.JSONDecodeError as exc: raise ValueError(f"Skill Node returned invalid JSON: {exc}")
    return {"kind": "Artifact", "skill_id": node.params.get("skill_id"), "schema": node.params.get("output_schema", {}), "data": payload}

TOOL_SCHEMAS = [
    {"type": "function", "function": {"name": "inspect_upload", "description": "Inspect a user-uploaded file before making analysis claims. Returns columns and a small preview for tabular files.", "parameters": {"type": "object", "properties": {"upload_id": {"type": "string"}}, "required": ["upload_id"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "get_graph", "description": "Read the current typed workflow graph and node outputs.", "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
    {"type": "function", "function": {"name": "apply_graph_patch", "description": "Apply a proposed graph patch. The patch is type-checked, version-checked and audited before it changes the graph.", "parameters": {"type": "object", "properties": {"patch": {"type": "object"}}, "required": ["patch"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "run_workflow", "description": "Execute ready nodes in topological order. Stops safely at an error or human decision.", "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
    {"type": "function", "function": {"name": "add_skill_node", "description": "Add an AI Skill Node with a stable TypedTable input and Artifact output. Connect it with apply_graph_patch.", "parameters": {"type": "object", "properties": {"label": {"type": "string"}, "skill_id": {"type": "string"}, "instructions": {"type": "string"}, "output_schema": {"type": "object"}}, "required": ["label", "skill_id", "instructions", "output_schema"], "additionalProperties": False}}},
]

def model_completion(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
    config = load_settings()["agent"]; key = os.getenv(config.get("api_key_env", "MATFLOW_API_KEY"), "")
    if not config.get("model") or not key:
        raise HTTPException(status_code=503, detail=f"Agent is not configured. Set a model in Settings and set environment variable {config.get('api_key_env', 'MATFLOW_API_KEY')}.")
    url = config.get("base_url", "").rstrip("/") + "/chat/completions"
    body = {"model": config["model"], "messages": messages, "temperature": config.get("temperature", 0.2)}
    if tools: body["tools"] = tools; body["tool_choice"] = "auto"
    req = urlrequest.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"}, method="POST")
    try:
        with urlrequest.urlopen(req, timeout=90) as response: data = json.loads(response.read())
        return data["choices"][0]["message"]
    except (urlerror.URLError, KeyError, IndexError, json.JSONDecodeError) as exc:
        audit("model.failed", error=str(exc)); raise HTTPException(status_code=502, detail=f"Model provider request failed: {exc}")

def run_agent_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    audit("tool.called", tool=name, arguments=arguments)
    if name == "inspect_upload": return inspect_upload(arguments["upload_id"])
    if name == "get_graph": return load().model_dump()
    if name == "apply_graph_patch": return {"state": apply_patch(load(), GraphPatch.model_validate(arguments["patch"])).model_dump()}
    if name == "add_skill_node":
        state = load(); node = Node(id=f"skill-{uuid.uuid4().hex[:8]}", type="skill_node", label=arguments["label"], params={key: arguments[key] for key in ("skill_id", "instructions", "output_schema")})
        return {"state": apply_patch(state, GraphPatch(base_version=state.version, operations=[Operation(op="add_node", node=node)], rationale="Agent added a schema-bound Skill Node.")).model_dump(), "node_id": node.id}
    if name == "run_workflow":
        state = load(); results = []
        for node in state.nodes:
            if node.status in {"completed", "waiting"}: continue
            try: results.append({"node_id": node.id, "result": run_node_in_state(state, node)})
            except ValueError as exc: node.status = "error"; node.output = {"error": str(exc)}; results.append({"node_id": node.id, "error": str(exc)}); break
            if node.status == "waiting": break
        save(state); return {"state": state.model_dump(), "results": results}
    raise ValueError(f"Tool is not registered: {name}")

@app.post("/api/chat")
def chat(request: ChatRequest):
    audit("chat.received", message=request.message[:1000], attachments=[item.get("name") for item in request.attachments])
    skills = load_runtime_skills()
    system = "\n\n".join(["You are the MatFlow runtime agent.", *[f"## Runtime Skill: {skill['name']}\n{skill['content']}" for skill in skills], load_settings()["agent"].get("system_prompt", "")])
    user_context = {"message": request.message, "uploads": request.attachments, "runtime_skills": [skill["name"] for skill in skills], "node_catalog": registry(), "data_types": DATA_TYPES, "instruction": "Use tools for observations and changes. If required information is ambiguous, ask the user a concise question instead of guessing."}
    messages: list[dict[str, Any]] = [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(user_context, ensure_ascii=False)}]
    trace: list[dict[str, Any]] = []
    try:
        for round_index in range(int(load_settings()["agent"].get("max_tool_rounds", 8))):
            reply = model_completion(messages, TOOL_SCHEMAS); tool_calls = reply.get("tool_calls") or []
            if not tool_calls:
                content = reply.get("content") or "I completed the available steps."
                audit("agent.reply", reply=content[:1000], rounds=round_index + 1)
                return {"state": load().model_dump(), "summary": content, "trace": trace, "runtime_skills": [skill["name"] for skill in skills]}
            messages.append({"role": "assistant", "content": reply.get("content") or "", "tool_calls": tool_calls})
            for call in tool_calls:
                name = call["function"]["name"]
                try: result = run_agent_tool(name, json.loads(call["function"].get("arguments") or "{}")); event = {"tool": name, "ok": True, "result": result}
                except Exception as exc: event = {"tool": name, "ok": False, "error": str(exc)}
                trace.append(event); messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(event, ensure_ascii=False, default=str)})
        raise HTTPException(status_code=422, detail="Agent reached the configured tool-round limit without a final answer.")
    except HTTPException: raise
    except Exception as exc:
        audit("agent.failed", error=str(exc)); raise HTTPException(status_code=422, detail=str(exc))

@app.post("/api/reset")
def reset():
    save(GraphState()); return {"ok": True}

@app.post("/api/execute")
def execute(request: ExecuteRequest):
    state = load()
    try:
        node = node_by_id(state, request.node_id)
        result = run_node_in_state(state, node); save(state)
        return {"state": state.model_dump(), "result": result}
    except ValueError as exc:
        audit("executor.failed", node_id=request.node_id, error=str(exc))
        raise HTTPException(status_code=422, detail=str(exc))

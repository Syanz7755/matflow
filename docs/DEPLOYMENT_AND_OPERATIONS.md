# Deployment and operations

MatFlow v1 targets a trusted local environment and provides no accounts, TLS or multi-tenant isolation. For remote deployment, add authentication, TLS and network access control in front of it.

## Process topology

- Backend: `127.0.0.1:8000`, holds the workspace state and serves `/api/*`.
- WebUI: `127.0.0.1:5173`, started by `matflow start --ui webui` from the frontend manifest.
- MCP bridge: `127.0.0.1:8001/mcp`, started separately in `matflow-frontend`.
- LLM gateway: LiteLLM on `127.0.0.1:4078` (`config/llm.json`), started or reused by `start_llm.bat`; required for AI planning and routing.
- Jev decision gateway: `127.0.0.1:4079`, optional; when it is unreachable, tools are routed by the LLM. `start_model_services.bat` starts both gateways.

The managed launcher waits for the backend capabilities endpoint to become available, then starts the WebUI and waits for its page health check. An abnormal WebUI exit, a failed startup or Ctrl+C cleans up the whole managed process group. Additional trusted origins can be appended through `MATFLOW_CORS_ORIGINS`.

## Data layout

Each save is one folder, `data/saves/<name>/`, holding `graph_state.json`, `settings.json`, `uploads/` and `audit/task_summaries.jsonl`. The active save is `MATFLOW_DATA_ROOT` (an explicit folder) if set, else `data/saves/$MATFLOW_SAVE`, else `data/saves/default`. Back up or move a workspace by copying its folder. API keys are never stored in a save; they are read from environment variables.

The capabilities endpoint returns `api_contract.name = matflow-http` and `api_contract.version = 1.0`. The backend runs standalone without Node, npm or a Python MCP package. Run frontend operations in the `matflow-frontend` repository.

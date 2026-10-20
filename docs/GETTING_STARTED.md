# Getting started with MatFlow

The MatFlow v1 Python repository owns only the workspace state, validation, execution, audit and HTTP API. The WebUI, the MCP bridge and the DSH integration live in the sibling `matflow-frontend` repository.

## Install and start

```powershell
uv sync
uv run matflow start --ui none
```

The backend listens on `http://127.0.0.1:8000` by default; the capabilities endpoint is `http://127.0.0.1:8000/api/capabilities`.

If `../matflow-frontend` exists as a sibling directory, you can start the managed WebUI:

```powershell
uv run matflow start --ui webui
```

You can also point at a frontend repository with `--ui-path` or `MATFLOW_WEBUI_DIR`. With no `--ui`, an interactive terminal shows a selection menu and a non-interactive environment starts the backend only. `uv run matflow serve` is a compatibility alias for `start --ui none`.

## LLM gateway and saves

AI planning (`POST /api/plan`, `/api/chat`, `/api/route`) needs the LLM gateway described in `config/llm.json` (LiteLLM on `127.0.0.1:4078`, caller key in `LITELLM_DEFAULT_API_KEY`):

```powershell
.\start_llm.bat            # reuse a ready gateway or start one
.\start_llm.bat -CheckOnly # only report readiness
```

The deterministic workflow path works without it. Workspace data lives in one folder per save, `data/saves/<name>/`; `default` is used unless you pick another:

```powershell
uv run matflow saves
uv run matflow start --ui none --save my-experiment
```

See [`config/README.md`](../config/README.md) for the gateway and routing configuration.

## MCP and DSH

Run this in `matflow-frontend`:

```powershell
npm install
npm run mcp
npm run configure:dsh
```

The MCP bridge listens on `http://127.0.0.1:8001/mcp` by default and reaches the backend through the HTTP API. The backend itself no longer serves `/mcp`.

See the [startup guide](STARTUP_SCRIPTS.md), the [HTTP API contract](BACKEND_API_CONTRACT.md) and the [architecture rules](ARCHITECTURE_AND_DEVELOPER_RULES.md).

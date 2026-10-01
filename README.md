# MatFlow Backend

MatFlow is the authoritative local server for typed materials-workflow state, validation, routing, execution, uploads, and audit records. User interfaces and AI adapters live in the independent sibling repository `matflow-frontend`; every client uses the versioned HTTP API.

## Install

```powershell
uv sync
uv run matflow diagnose
```

Python 3.11–3.13 is supported. The backend does not require Node.js, npm, or an MCP package.

## Start

```powershell
# Backend only
uv run matflow start --ui none

# Backend and sibling WebUI
uv run matflow start --ui webui
```

The frontend repository is resolved from `--ui-path`, then `MATFLOW_WEBUI_DIR`, then `../matflow-frontend`. With no `--ui`, interactive terminals show a menu and non-interactive sessions start only the backend. `uv run matflow serve` remains an alias for `start --ui none`.

Default endpoints:

- HTTP API: `http://127.0.0.1:8000/api`
- OpenAPI: `http://127.0.0.1:8000/docs`
- Capabilities: `http://127.0.0.1:8000/api/capabilities`

The former backend `/mcp` endpoint was removed in v1. MCP, DSH, and ChatGPT integration is provided by `matflow-frontend`, whose bridge defaults to `http://127.0.0.1:8001/mcp`.

## Test

```powershell
uv run --group dev python -m unittest discover -v
```

Model routing and application scenarios can also be run separately. The
default is deterministic and offline; live gateways are explicitly enabled:

```powershell
.\test_model_scenarios.bat
.\test_model_scenarios.bat -OnlineJev
.\test_model_scenarios.bat -OnlineJev -OnlineLlm
```

Configuration-driven prompt, workflow, and generated-tool suites can be run
separately. Live services require both a case-level permission and the matching
command-line switch:

```powershell
.\test_configured_scenarios.bat
.\test_configured_scenarios.bat -OnlineJev -OnlineLlm
```

See `docs/CONFIGURED_SCENARIO_TESTS.md` for the suite contract, deterministic
XRD/FTIR noise model, Docker fallback policy, and report format.

The server remains a single-user, single-workspace local service. Multiple clients may connect concurrently; graph writes require the current `base_version`, and stale writes return HTTP 409 with `graph_version_conflict`.

Project documentation:

- [Current status and roadmap](docs/PROJECT_STATUS.md)
- [Design philosophy and implementation architecture](docs/DESIGN_AND_ARCHITECTURE.md)
- [HTTP API contract](docs/BACKEND_API_CONTRACT.md)

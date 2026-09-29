# MatFlow v0.2

A local, schema-constrained materials workflow workspace. MatFlow exposes one server-authoritative runtime through HTTP and MCP; ChatGPT, DeepSeek Harness, or another MCP client supplies the agent.

## Documentation

- [快速使用指南](docs/GETTING_STARTED.md)
- [Startup scripts guide](docs/STARTUP_SCRIPTS.md)
- [文档中心](docs/README.md)
- [用户说明书](docs/USER_MANUAL.md)
- [MCP 与 AI 客户端接入指南](docs/MCP_INTEGRATION_GUIDE.md)
- [部署与运维指南](docs/DEPLOYMENT_AND_OPERATIONS.md)
- [架构与开发规则](docs/ARCHITECTURE_AND_DEVELOPER_RULES.md)
- [HTTP/MCP 接口契约](docs/BACKEND_API_CONTRACT.md)

## Install and run locally with uv

uv is the default environment and Python dependency manager. It uses `pyproject.toml` and the checked-in `uv.lock` to create an isolated `.venv` reproducibly across platforms.

```powershell
uv sync
uv run matflow install-frontend
```

Check the environment at any point with `uv run matflow diagnose` or `./scripts/diagnose_environment.ps1`.

Once installed, the single startup command is:

```powershell
uv run matflow start
```

The equivalent PowerShell helper is `./scripts/start.ps1`. It starts only MatFlow and the Web UI.

On Windows, `start_matflow.bat` is the full workstation launcher: it starts the model services declared in `config/model_services.json` (currently LiteLLM and Jev) before starting MatFlow and the Web UI. It therefore requires the configured model-service paths and environment variables. See the [startup scripts guide](docs/STARTUP_SCRIPTS.md) before using it.

## Optional Conda runtime

Conda remains supported when a scientific dependency later requires it. Create the environment from `environment.yml`, activate it, install uv, and use the same uv commands above. It is not the default deployment path.

## Manual run

In one terminal:

```powershell
uv run uvicorn backend.main:app --reload --port 8000
```

In a second terminal:

```powershell
Set-Location frontend
npm run dev
```

Open the local address shown by Vite (normally `http://localhost:5173`). The v0.2 Research Workbench reads server-confirmed GraphState and registry data, routes a research task, and presents its auditable decision record. It does not autonomously modify the graph or execute a tool.

To verify the browser-facing slice, run:

```powershell
Set-Location frontend
npm run test:e2e
```

This starts isolated test services on local test ports and checks an EIS route, desktop/mobile accessibility, keyboard focus and touch-target sizing. Run `npm run build` to create a production frontend bundle.

## Connect local DeepSeek Harness

The installer creates a dedicated `matflow` Web profile, leaving an existing `web` profile unchanged:

```powershell
uv run matflow configure-dsh --profile matflow
uv run matflow diagnose --dsh
uv run matflow start-dsh
```

DSH connects to `http://127.0.0.1:8000/mcp`. Reads run directly; dataset imports, graph changes, execution, and human decisions display DSH's one-shot approval UI. Local attachment import is limited to the active workspace and DSH attachment storage, rejects symlinks/path escape, and enforces the server's 25 MB limit.

To run only the interface for another MCP client, use `uv run matflow serve`. The MCP URL is `http://127.0.0.1:8000/mcp`.

For ChatGPT, expose that private endpoint with OpenAI's Secure MCP Tunnel, then add the tunnel URL as the plugin's MCP server. The `import_dataset` tool advertises ChatGPT's standard file-parameter metadata, so attached files arrive as authorized temporary HTTPS downloads rather than embedded UI state.

## Legacy local model gateway (optional)

LiteLLM is no longer started by default because the AI agent now lives in the MCP client. It remains available only for migration use with the retired built-in chat loop or AI Skill Node execution.

```powershell
$env:SJTU_ZHIYUAN_API_KEY = "your-key"
uv run litellm --config config/litellm.yaml --port 4000
$env:MATFLOW_ENABLE_LEGACY_CHAT = "1"
```

The gateway model definitions live in [config/litellm.yaml](config/litellm.yaml), including `qwen`, `minimax`, `deepseek-chat`, `deepseek-reasoner`, and `glm`. The upstream key is never persisted in `data/settings.json`.

After starting the optional gateway, set MatFlow's legacy Agent runtime base URL to `http://127.0.0.1:4000/v1`, model to `qwen`, and API-key environment variable to `MATFLOW_LITELLM_API_KEY`. The regular `matflow start`, `serve`, and `start-dsh` commands do not start LiteLLM or load gateway credentials.

MCP clients follow `runtime_skills/matflow_mcp_runtime.md`: inspect first, use registered identifiers, validate patches, and confirm writes or execution. `runtime_skills/matflow_agent_runtime.md` remains only for the optional legacy agent loop.

Material-domain abilities should be represented as **AI Skill Nodes** in the graph. They consume `TypedTable` and return a contract-bound `Artifact`; their `skill_id`, instructions, and output JSON schema travel with the workflow, so the graph executor remains compatible while individual skills evolve.

## Current workspace capabilities

- Research Workbench: a server-authoritative screen for inspecting GraphState, the active registry, feature flags, task routing, registered tool IDs, decision rationale and error-handling evidence.
- Versioned control-plane interfaces: state, capabilities, route, GraphPatch, execution and task summaries. See [docs/BACKEND_API_CONTRACT.md](docs/BACKEND_API_CONTRACT.md).
- MCP interface: external agents can inspect uploads, read the graph, validate/apply patches, route tasks, execute workflows, resolve human decisions, and read audit summaries.
- Real tabular EIS execution path: uploaded data is parsed, column mappings are validated, QC uses the uploaded values, and Nyquist points are generated from the uploaded values.
- HTTP interfaces for local provider settings and custom node definitions. These management operations are not exposed in the current WebUI.

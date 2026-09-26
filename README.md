# MatFlow v0.2

A local, schema-constrained materials-agent workspace. MatFlow delegates planning to a user-configured OpenAI-compatible model, then constrains it with versioned Runtime Skills and an audited tool registry.

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

The equivalent PowerShell helper is `./scripts/start.ps1`.

On Windows, you may also double-click `start_matflow.bat`.

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

## Configure the local LiteLLM gateway

The default startup now runs a local LiteLLM gateway on `http://127.0.0.1:4000`, then starts MatFlow against it on port 8000. MatFlow defaults to the `qwen` model; the local gateway key is loaded from the project configuration rather than copied into commands or documentation. The gateway forwards upstream using the environment variable below.

```powershell
$env:SJTU_ZHIYUAN_API_KEY = "your-key"
uv run matflow start
```

The gateway model definitions live in [config/litellm.yaml](config/litellm.yaml), including `qwen`, `minimax`, `deepseek-chat`, `deepseek-reasoner`, and `glm`. The upstream key is never persisted in `data/settings.json`.

For a manually started gateway, run `uv run litellm --config config/litellm.yaml --port 4000`, then set MatFlow's Agent runtime base URL to `http://127.0.0.1:4000/v1`, model to `qwen`, and API-key environment variable to `MATFLOW_LITELLM_API_KEY`. When MatFlow is started through the project launcher, this local gateway key is loaded automatically from `config/litellm.yaml`; do not copy provider credentials into project files.

Each agent turn automatically loads `runtime_skills/matflow_agent_runtime.md`. This is the governing runtime behavior: it tells the model to inspect files, use only registered tools, make all graph changes through schema validation, and ask rather than guess. Add or version more Runtime Skills in that directory as the project’s operating policy evolves.

Material-domain abilities should be represented as **AI Skill Nodes** in the graph. They consume `TypedTable` and return a contract-bound `Artifact`; their `skill_id`, instructions, and output JSON schema travel with the workflow, so the graph executor remains compatible while individual skills evolve.

## Current workspace capabilities

- Research Workbench: a server-authoritative screen for inspecting GraphState, the active registry, feature flags, task routing, registered tool IDs, decision rationale and error-handling evidence.
- Versioned control-plane interfaces: state, capabilities, route, GraphPatch, execution and task summaries. See [docs/BACKEND_API_CONTRACT.md](docs/BACKEND_API_CONTRACT.md).
- Runtime Agent loop: the model can inspect uploads, read the graph, apply validated patches, add compatible Skill Nodes, and run the workflow. Every call and failure is logged to the server console.
- Real tabular EIS execution path: uploaded data is parsed, column mappings are validated, QC uses the uploaded values, and Nyquist points are generated from the uploaded values.
- Settings drawer for provider configuration and the local materials-node library. Preset nodes are protected; custom nodes support JSON import, prompt-built templates, rename and deletion.

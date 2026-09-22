# Materials Graph Demo v0.1

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

Open the local address shown by Vite (normally `http://localhost:5173`). Try the suggested prompts to create the EIS pipeline, update its frequency threshold, and insert a Human Decision node.

## Configure an AI provider

MatFlow does not store API keys in `data/settings.json`. Set the key in the environment that starts MatFlow, then open **Settings → Agent runtime** and enter an OpenAI-compatible base URL and model name.

```powershell
$env:MATFLOW_API_KEY = "your-key"
uv run matflow start
```

To use a different environment-variable name, change **API key environment variable** in Settings before starting a new session with that variable set.

Each agent turn automatically loads `runtime_skills/matflow_agent_runtime.md`. This is the governing runtime behavior: it tells the model to inspect files, use only registered tools, make all graph changes through schema validation, and ask rather than guess. Add or version more Runtime Skills in that directory as the project’s operating policy evolves.

Material-domain abilities should be represented as **AI Skill Nodes** in the graph. They consume `TypedTable` and return a contract-bound `Artifact`; their `skill_id`, instructions, and output JSON schema travel with the workflow, so the graph executor remains compatible while individual skills evolve.

## Workspace capabilities

- Chat-style workflow conversation with drag-and-drop or `+` file attachment. Files remain in `data/uploads/` on the local machine and are limited to supported scientific/demo formats and 25 MB each.
- Runtime Agent loop: the model can inspect uploads, read the graph, apply validated patches, add compatible Skill Nodes, and run the workflow. Every call and failure is logged to the server console.
- Real tabular EIS execution path: uploaded data is parsed, column mappings are validated, QC uses the uploaded values, and Nyquist points are generated from the uploaded values.
- Settings drawer for provider configuration and the local materials-node library. Preset nodes are protected; custom nodes support JSON import, prompt-built templates, rename and deletion.

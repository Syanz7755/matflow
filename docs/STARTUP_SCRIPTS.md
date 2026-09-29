# Startup Scripts Guide

This guide describes every supported launcher and verification script shipped with MatFlow. Run commands from the repository root unless a section says otherwise.

## Recommended entry points

| Goal | Recommended command | What it starts |
| --- | --- | --- |
| Open the visual workflow editor | `uv run matflow start` | MatFlow API/MCP server and the Vite Web UI |
| Start only the API and MCP endpoint | `uv run matflow serve` | MatFlow API/MCP server on `127.0.0.1:8000` |
| Start MatFlow with the local DSH profile | `uv run matflow start-dsh --profile matflow` | MatFlow API/MCP server and DSH |
| Start the complete Windows workstation stack | Double-click `start_matflow.bat` | LiteLLM, Jev, MatFlow API/MCP server, and Web UI |
| Start only the configured model gateways | Double-click `start_model_services.bat` | Enabled services in `config/model_services.json` |

Use `uv run matflow start` for ordinary Web UI development. Use `start_matflow.bat` only when the workflow also needs the configured local model gateways.

## First-time setup

```powershell
Set-Location D:\Projects\matflow
uv sync
uv run matflow install-frontend
uv run matflow diagnose
```

Requirements:

- Python 3.11, 3.12, or 3.13;
- `uv` on `PATH`;
- Node.js and npm for the Web UI;
- DSH on `PATH` only when using the DSH launch commands;
- the environment variables declared by enabled model services when using the model-service launcher.

## Command-line launchers

### `uv run matflow start`

Starts the HTTP/MCP server on port `8000` and the Vite Web UI, normally on port `5173`. Keep the terminal open. Press `Ctrl+C` in that terminal to stop both processes.

This command does not start LiteLLM, Jev, or DSH.

### `uv run matflow serve`

Starts only the HTTP/MCP server:

- API root: `http://127.0.0.1:8000/api`
- OpenAPI UI: `http://127.0.0.1:8000/docs`
- MCP endpoint: `http://127.0.0.1:8000/mcp`

Use this mode for an external MCP client, backend development, or a separately hosted frontend. Press `Ctrl+C` to stop it.

### `uv run matflow configure-dsh --profile matflow`

Creates or updates the isolated MatFlow DSH profile. It leaves the default DSH `web` profile unchanged. Preview the generated patch without writing it by adding `--dry-run`.

Run this once before the first DSH session and again after the MatFlow DSH integration changes:

```powershell
uv run matflow configure-dsh --profile matflow
uv run matflow diagnose --dsh --profile matflow
```

### `uv run matflow start-dsh --profile matflow`

Validates the selected profile, starts the MatFlow API/MCP server, waits for its health check, and opens DSH. Closing DSH also stops the MatFlow server started by this command.

This command does not start the Web UI, LiteLLM, or Jev.

### `uv run matflow diagnose`

Performs read-only checks for Python, the local environment, Node.js, npm, frontend packages, and core Python packages. Add `--dsh --profile matflow` to validate DSH and the MatFlow profile.

## Windows convenience scripts

### `start_matflow.bat`

This is the full workstation launcher. It performs these steps in order:

1. checks that `uv` is available;
2. calls `start_model_services.bat`;
3. waits until every enabled model service is healthy;
4. runs `uv run matflow start`.

It therefore starts more services than the similarly named PowerShell helper. The model gateways continue as hidden background processes after the launcher exits; the current scripts do not provide a matching stop script.

### `scripts/start.ps1`

This is a thin PowerShell wrapper around `uv run matflow start`. It starts only MatFlow and the Web UI; it does not start model gateways.

```powershell
.\scripts\start.ps1
```

### `start_model_services.bat`

Starts all services marked `enabled: true` in [`config/model_services.json`](../config/model_services.json). The launcher validates paths and required environment-variable names, reuses an already healthy service, starts missing services in hidden windows, and waits for their health endpoints.

The checked-in configuration currently declares:

| Service | Default endpoint | Requirement |
| --- | --- | --- |
| LiteLLM gateway | `http://127.0.0.1:4000` | `SJTU_ZHIYUAN_API_KEY` must exist in the launching process environment |
| Jev decision gateway | `http://127.0.0.1:4079` | Local Jev gateway at the configured working directory |

Service paths are machine-specific. Edit `config/model_services.json` when the Jev installation is located elsewhere. Do not place secret values in that file.

### `start_litellm.bat`

Backward-compatible alias for `start_model_services.bat`. Despite its name, it starts every enabled service, including Jev. New instructions should use `start_model_services.bat`.

### `scripts/start_model_services.ps1`

PowerShell implementation used by the batch launcher. It accepts:

```powershell
.\scripts\start_model_services.ps1 [-ConfigPath <path>] [-ValidateOnly]
```

`-ValidateOnly` checks the configuration and executable paths without starting processes. Required credential environment variables are checked during an actual start, not printed or persisted.

## Verification scripts

| Script | Purpose |
| --- | --- |
| `scripts/diagnose_environment.ps1` | Read-only environment and dependency diagnostics |
| `test_backend.bat` / `scripts/test_backend.ps1` | Run the Python backend contract and integration tests only |
| `test_teaching_lab_suite.bat` / `scripts/test_teaching_lab_suite.ps1` | Regenerate and verify the deterministic offline teaching-lab fixtures |

Run frontend checks separately:

```powershell
Set-Location frontend
npm run test:unit
npm run build
npm run test:e2e
```

The end-to-end suite starts isolated test services and must not be run against a production workspace.

## Ports and duplicate-process safety

| Port | Process |
| --- | --- |
| `5173` | Vite Web UI |
| `8000` | MatFlow HTTP/MCP server |
| `4000` | LiteLLM gateway |
| `4079` | Jev decision gateway |

Do not run `matflow start`, `matflow serve`, and `matflow start-dsh` simultaneously against the same workspace. They share `data/` and port `8000`. Before retrying a failed launch, close the earlier terminal or confirm that the relevant health endpoint is no longer responding.

## Troubleshooting

- **`uv` is not found:** install `uv`, reopen the terminal, and run `uv sync`.
- **Frontend packages are missing:** run `uv run matflow install-frontend`.
- **Port 8000 or 5173 is already in use:** stop the previous MatFlow session before starting another one.
- **The model-service launcher reports a missing environment variable:** set the named variable in the same user/session context that launches the batch file. The launcher never asks for or displays its value.
- **The Jev working directory does not exist:** update its `working_directory` and script arguments in `config/model_services.json`.
- **DSH profile validation fails:** rerun `uv run matflow configure-dsh --profile matflow`, followed by `uv run matflow diagnose --dsh --profile matflow`.

For backup, recovery, and long-running deployment guidance, see [Deployment and Operations](DEPLOYMENT_AND_OPERATIONS.md).

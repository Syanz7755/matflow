# MatFlow Backend Startup

## One script for local use (recommended)

`scripts/matflow.ps1` starts and manages the whole local stack — both LiteLLM gateways,
the backend and the sibling WebUI — and is safe to re-run:

```powershell
pwsh -File scripts\matflow.ps1                  # start everything (idempotent; services already healthy are reused)
pwsh -File scripts\matflow.ps1 status           # ports, health, pids, model, workspace; exit 0 only if all healthy
pwsh -File scripts\matflow.ps1 restart          # stop what the launcher started, start again
pwsh -File scripts\matflow.ps1 logs -Tail 40    # tail every service log
pwsh -File scripts\matflow.ps1 stop             # stop the stack
pwsh -File scripts\matflow.ps1 open             # open the WebUI in a browser
```

What it handles for you:

- **Prerequisites**: checks `uv`, `node`, `npm`, the config files and the credentials
  (`SJTU_ZHIYUAN_API_KEY`, `LITELLM_DEFAULT_API_KEY`, `DEEPSEEK_API_KEY_MATFLOW_EXCLUSIVE`,
  read from the Windows *User* environment and never printed). With `-InstallDeps` it runs
  `uv sync` / `npm install` when `.venv` or `node_modules` are missing.
- **Stale processes**: if one of our ports is held by a process whose command line is
  recognisably ours (`uvicorn backend.main:app` / `vite` / `litellm`), it is reclaimed;
  anything else on the port aborts with a clear message instead of being killed (`-NoReclaim`
  disables reclaiming entirely).
- **Lifecycle tracking**: started services are written to `.tmp/live/matflow-launcher.json`
  (real listener pids), so `stop` only stops this stack; logs go to `.tmp/live/<service>.{out,err}.log`.
- **Failure handling**: a start that fails a health check prints the failing log tail and rolls
  back what it started.

Options: `-Save <name>` (working save, default `live-demo`), `-LlmConfig <path>`
(default `config\llm-deepseek.json`), `-BackendPort` / `-FrontendPort` / `-SjtPort` / `-DeepSeekPort`,
`-SkipWebUI`, `-SkipDeepSeek`, `-NoBrowser`, `-TimeoutSeconds`, `-Detach`.

`-Detach` re-launches the start in a hidden, detached process and returns immediately — use it
when the command runs from a captured pipe (CI, scripted tooling), because long-lived child
services otherwise keep that pipe open. In an interactive terminal the plain
`start` already returns as soon as the stack is healthy.

Typical session:

```powershell
pwsh -File scripts\matflow.ps1            # start
# ... use http://127.0.0.1:5173 ...
pwsh -File scripts\matflow.ps1 status     # check before recording a demo
pwsh -File scripts\matflow.ps1 stop       # done
```

## Backend CLI and diagnostics

| Goal | Command |
| --- | --- |
| Choose interactively | `uv run matflow start` |
| Backend plus WebUI | `uv run matflow start --ui webui` |
| Backend only | `uv run matflow start --ui none` |
| Compatibility alias | `uv run matflow serve` |
| Diagnose backend | `uv run matflow diagnose` |
| Diagnose WebUI checkout | `uv run matflow diagnose --ui webui [--ui-path <path>]` |
| Open another save | `uv run matflow start --save <name>` |
| List saves | `uv run matflow saves` |
| LLM gateway | `start_llm.bat` (`-CheckOnly`, `-Port N`) |
| Full live demo (both model gateways + backend + WebUI) | `scripts/start_demo.bat`, or `pwsh -File scripts/start_demo.ps1` |

`scripts/start_demo.ps1` is the one-command path used for the 2026-10-20 live
acceptance. It reads `SJTU_ZHIYUAN_API_KEY`, `LITELLM_DEFAULT_API_KEY` and
`DEEPSEEK_API_KEY_MATFLOW_EXCLUSIVE` from the Windows User environment scope into
the child processes only (values are never printed), starts or reuses both local
gateways (ports 4078 and 4080), then the backend (8000) and the sibling WebUI
(5173), health-checks each, prints the URLs and waits. `Ctrl+C` stops the
processes it started. Options: `-BackendPort`, `-FrontendPort`, `-SkipDeepSeek`,
`-NoWait`. After it is up, follow
`docs/acceptance/2026-10-20-live/OPERATOR_RUNBOOK.zhcn.md`.

`--ui-path` overrides `MATFLOW_WEBUI_DIR`, which overrides the sibling default `../matflow-frontend`. The UI manifest is `matflow-ui.json`. Backend and managed UI are health-checked and share one lifecycle; failure or interruption stops both.

The removed `install-frontend`, `configure-dsh`, and `start-dsh` commands now belong to the separate frontend repository. Backend port defaults to 8000 and WebUI port to 5173.

Each save is one folder, `data/saves/<name>/` (graph, settings, uploads, task log); `--save` sets `MATFLOW_SAVE` for the server, and `MATFLOW_DATA_ROOT` still names an explicit folder. The LLM gateway is described in `config/llm.json`; see `config/README.md`.

# MatFlow Backend Startup

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

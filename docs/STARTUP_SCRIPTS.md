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

`--ui-path` overrides `MATFLOW_WEBUI_DIR`, which overrides the sibling default `../matflow-frontend`. The UI manifest is `matflow-ui.json`. Backend and managed UI are health-checked and share one lifecycle; failure or interruption stops both.

The removed `install-frontend`, `configure-dsh`, and `start-dsh` commands now belong to the separate frontend repository. Backend port defaults to 8000 and WebUI port to 5173.

Each save is one folder, `data/saves/<name>/` (graph, settings, uploads, task log); `--save` sets `MATFLOW_SAVE` for the server, and `MATFLOW_DATA_ROOT` still names an explicit folder. The LLM gateway is described in `config/llm.json`; see `config/README.md`.

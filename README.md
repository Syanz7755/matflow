# MatFlow

MatFlow turns materials-science requests into typed, reviewable workflows and auditable results. The backend is authoritative for Tools, workflow validation, execution and task history; the React workbench lives in the sibling repository `matflow-frontend` and uses the versioned HTTP API.

## Architecture

```mermaid
flowchart LR
  Request[Natural-language request] --> Agent[Agent / client]
  Agent --> API[MatFlow HTTP API]
  API --> Validate[Typed workflow validation]
  Validate --> Runtime[DAG execution runtime]
  Runtime --> Packages[Domain Packages: QE, EIS, XRD, FTIR]
  Packages --> Artifact[Result artifacts and audit record]
  Demo[Non-selectable QE replay fixture] --> Artifact
  Artifact --> UI[React workflow graph and result inspector]
```

Platform Core provides graph, validation, execution and audit contracts. EIS, XRD, FTIR and QE capabilities are contributed by separate Domain Packages; the demo-only QE fixture is non-selectable by the Agent.

## Install

```powershell
uv sync
uv run matflow diagnose
```

Python 3.11–3.13 is supported. The backend does not require Node.js, npm, or an MCP package.

## Start

```powershell
# LLM gateway (reuses a running LiteLLM that accepts $LITELLM_DEFAULT_API_KEY, or starts one)
start_llm.bat

# Backend only
uv run matflow start --ui none

# Backend and sibling WebUI
uv run matflow start --ui webui
```

The gateway is described once in `config/llm.json` (host, port, key variable, models); see [config/README.md](config/README.md).

### Saves: one save, one folder

All local workspace state — graph, workspace settings, uploads and the task log — lives in `data/saves/<save>/`. `uv run matflow start --save NAME` (or `MATFLOW_SAVE=NAME`) opens another save; the default is `default`, and `MATFLOW_DATA_ROOT` names an explicit folder. `uv run matflow saves` lists them. `data/saves/` is Git-ignored.

The frontend repository is resolved from `--ui-path`, then `MATFLOW_WEBUI_DIR`, then `../matflow-frontend`. With no `--ui`, interactive terminals show a menu and non-interactive sessions start only the backend. `uv run matflow serve` remains an alias for `start --ui none`.

The UI can also be started directly from a `../matflow-frontend` sibling checkout with `npm run dev`; it connects to `http://127.0.0.1:8000/api` by default.

Default endpoints:

- HTTP API: `http://127.0.0.1:8000/api`
- OpenAPI: `http://127.0.0.1:8000/docs`
- Capabilities: `http://127.0.0.1:8000/api/capabilities`

The former backend `/mcp` endpoint was removed in v1. MCP, DSH, and ChatGPT integration is provided by `matflow-frontend`, whose bridge defaults to `http://127.0.0.1:8001/mcp`.

## Frontend and MCP bridge

The React workbench and the MCP/DSH bridge live in the separate public repository [Syanz7755/matflow-frontend](https://github.com/Syanz7755/matflow-frontend). This repository is the authoritative backend and runs standalone: the CLI (`uv run matflow ...`) and the HTTP API at `http://127.0.0.1:8000/api` (OpenAPI at `/docs`) need no UI, Node.js or MCP package.

Without the UI you can:

```powershell
uv sync
uv run matflow diagnose          # readiness check
uv run matflow start --ui none   # backend + HTTP API only
uv run pytest -q                 # full test suite
```

and then call the API directly, for example `GET /api/capabilities`, `POST /api/plan`, or the QE replay demo `POST /api/qe/demo` (see below). The read-only `flowview` printer (see [docs/USER_MANUAL.md](docs/USER_MANUAL.md)) renders the current workflow graph in the terminal.

### Screenshots

Captured from a running backend + WebUI on 2026-10-20 (empty workspace, then the offline QE replay
demo). The replay screens are labelled historical: no `pw.x`, Slurm job or LLM planning produced them.
See the [capture notes](docs/images/README.md).

![Workbench overview](docs/images/workbench-overview.png)
![Workflow graph](docs/images/workflow-graph.png)
![Task result](docs/images/task-result.png)
![Node review gate](docs/images/node-review-gate.png)

## Prompt -> workflow planning

`POST /api/plan` turns a (long) research request into a typed workflow:

1. the LLM decomposes the request into action units with directed dependencies;
2. every action is routed to one registered tool by Jev, or by the LLM when Jev is unreachable — candidates are filtered by data types only, never by keywords;
3. dependencies become typed edges, and one LLM pass binds parameters, keeping only values the request or the uploaded columns state.

The result is a validated `GraphPatch` with a status: `planned`, `needs_confirmation` (capability gaps, missing parameters), `clarify`, `refused` or `failed`. It is applied only when it is `planned` and the request sets `"apply": true`.

## QE replay demo

For a fully offline, fixed-case replay without a server, LLM key or HPC access:

```powershell
uv run matflow demo qe-mgo --output ./qe-mgo-run
```

The output directory must be new. See the [A1 case and demo scripts](examples/cases/A1-qe-mgo/README.md).
This explicitly selects a pinned workflow; it does not measure model planning.

Start the backend and WebUI, then choose **Run MgO QE replay demo** from the workbench. The pinned natural-language request builds a four-node workflow: MgO structure → `pw.x` input generation → archived QE output replay → result parsing. The graph shows node states, parameters, parsed total energy, Fermi energy and convergence evidence. The replay is local and labelled as historical; it does not submit a Slurm job.

The same flow is available as `POST /api/qe/demo` with a request such as `{"message":"For pristine MgO SCF, generate a QE input and report energy and convergence."}`. It requires an empty workspace to preserve existing research state.

## Technology and limits

- Python 3.11–3.13, FastAPI, Pydantic, JSON Schema validation, typed DAG execution and versioned Domain Packages.
- React 19, Vite and `@xyflow/react` in the companion frontend repository.
- QE tools generate `pw.x` inputs and parse outputs. The `qe_demo` package provides a historical fixture and is excluded from Router selection. This demo does not run `pw.x`, connect to Slurm, manage pseudopotential files or claim scientific validation of new calculations.
- MatFlow is a single-user local service. Authentication, multi-tenant workspaces, public deployment and remote job scheduling are out of scope today.

## Inspect the flow from the command line

`flowview/` is a read-only CLI subproject that prints the backend flow — the runtime task
lifecycle and the current workspace DAG — as Mermaid diagrams or terminal tables. It is
independent of backend logic: it keeps working when `backend.*` is broken or unimportable, and it
never writes to `data/`.

```powershell
.\.venv\Scripts\python.exe -m flowview graph --format mermaid   # the workspace DAG
.\.venv\Scripts\python.exe -m flowview run-flow --no-color      # the runtime lifecycle
.\.venv\Scripts\python.exe -m flowview summary --limit 5        # recorded task history
.\.venv\Scripts\python.exe -m flowview doctor                   # diagnose sources
```

Offline is the default. Add `--http [URL]` to read the same flows from a *running* backend
(`graph`, `flow --prompt`, `flow --task`, `summary --task`, `doctor`); only `--http` opens a socket,
and it is also the only way to print the server's own routing decision.

See [flowview/README.md](flowview/README.md) for every subcommand, the exit-code and issue-code
tables, and the independence guarantee.

## Test

```powershell
uv run --group dev python -m unittest discover -v
```

The long-prompt planning suite runs the real chain (LLM decomposition, Jev/LLM routing, typed dataflow, and execution of every `planned` workflow on its fixture) against the configured gateway:

```powershell
$env:MATFLOW_RUN_LLM_APPLICATION_TESTS = "1"
$env:MATFLOW_SCENARIO_REPORT_DIR = "examples/reports/prompt_to_workflow"   # optional JSON report
uv run --group dev python -m unittest tests.test_prompt_to_workflow_online -v
```

Expectations live in `tests/suites/prompt_to_workflow.json`; `MATFLOW_PROMPT_CASES` selects cases.

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

See `docs/CONFIGURED_SCENARIO_TESTS.md` for the generic suite contract and the
XRD/FTIR reference-domain fixtures used to exercise it. Those fixtures are test
content, not part of the domain-neutral Platform Core.

The server remains a single-user, single-workspace local service. Multiple clients may connect concurrently; graph writes require the current `base_version`, and stale writes return HTTP 409 with `graph_version_conflict`.

Project documentation:

- [Current status and roadmap](docs/PROJECT_STATUS.md)
- [Design philosophy and implementation architecture](docs/DESIGN_AND_ARCHITECTURE.md)
- [HTTP API contract](docs/BACKEND_API_CONTRACT.md)

## Documentation languages

Interview evidence and limitations: [preparation guide (Chinese)](docs/INTERVIEW_PREPARATION.zhcn.md).
Routing evaluation: [methodology](docs/ROUTING_EVALUATION.md) and [diagnostic run](docs/evaluation/README.md).

English is the primary language of this repository. Documentation is written in English as `X.md`, and the Chinese version is retained as a sibling `X.zhcn.md`; the two are kept in sync. Chinese text elsewhere — in tests, fixtures, recorded evidence and examples — is input data that exercises the Chinese interaction path, not documentation.

## License

MIT — see [LICENSE](LICENSE).

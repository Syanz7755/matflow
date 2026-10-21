# MatFlow Documentation

MatFlow is a vibe-research framework for materials-science researchers: researchers build and refine a graph-like workflow by entering prompts. The project follows these design principles:

- Strict data-flow compliance checks.
- LLM access supports request decomposition, per-action tool selection, parameter binding and Tool construction. Registered numerical executors run locally; model-backed Skill Nodes have a separate data-access boundary.
- Versioned HTTP interfaces are provided; the MCP, ChatGPT and Deepseek Harness (DSH) adapters live in the separate `matflow-frontend` repository.

## Where to start

| Goal | Document |
| --- | --- |
| Run the live demo end to end (models, backend, WebUI) and operate one workflow | [Live acceptance report (Chinese)](acceptance/2026-10-20-live/REPORT.zhcn.md), [operator runbook](acceptance/2026-10-20-live/OPERATOR_RUNBOOK.zhcn.md) |
| Record the WebUI demo as a video (storyboard, feature list, narration, OBS settings) and health-check it first | [Demo recording tutorial (Chinese)](acceptance/2026-10-20-live/demo-tutorial/DEMO_TUTORIAL.zhcn.md), [pre-record health check](acceptance/2026-10-20-live/demo-tutorial/HEALTH_CHECK.zhcn.md) |
| Watch or regenerate the 11 short demo clips and the ~36 s walkthrough video (real stack, Chinese captions) | [Clip index](acceptance/2026-10-20-live/demo-tutorial/clips/INDEX.zhcn.md), [walkthrough mp4](acceptance/2026-10-20-live/demo-tutorial/video/matflow-walkthrough.mp4), `scripts/live_acceptance/record_demo_clips.ps1` |
| Re-check the 2026-10-20 known defects (routing has no refusal state, EISData type gate, compound request, Jev consensus) | [Defect verification (Chinese)](acceptance/2026-10-20-live/DEFECT_VERIFICATION.zhcn.md), [clips](acceptance/2026-10-20-live/defects/INDEX.zhcn.md) |
| Quote agent-evaluation numbers (per-stage accuracy, stability, latency, tokens, failure classes) on a fixed test set | [Agent eval report (Chinese)](evaluation/agent/REPORT.zhcn.md), [fixed cases](../../evaluation/agent/agent_eval_cases.json), `scripts/live_acceptance/eval_agent.mjs` |
| Find every artifact from the recording / defect-recheck / agent-eval work and the EIS two-case feasibility (GIF + MP4, absolute paths, reproduction, git status) | [Artifact index (Chinese)](acceptance/2026-10-20-live/ARTIFACTS.zhcn.md) |
| Read the 2026-10-20 demo acceptance result and its known gaps | [Acceptance report (Chinese)](acceptance/2026-10-20/REPORT.zhcn.md), [task assignment](acceptance/2026-10-20/TASK_ASSIGNMENT.zhcn.md) |
| Review the 2026-10-19 portfolio milestone and remaining work | [Portfolio readiness](PORTFOLIO_READINESS.md) |
| Prepare a truthful project interview and run the offline QE replay | [Interview preparation (Chinese)](INTERVIEW_PREPARATION.zhcn.md), [A1 replay](../examples/cases/A1-qe-mgo/README.md) |
| Inspect routing methodology and the current diagnostic run | [Routing evaluation](ROUTING_EVALUATION.md), [Recorded diagnostic](evaluation/README.md) |
| Install, start, connect an AI and complete a first operation | [Getting started](GETTING_STARTED.md) |
| Start, stop, restart and check the whole local stack with one script | [Startup scripts guide](STARTUP_SCRIPTS.md), `scripts/matflow.ps1` |
| Choose and operate a CLI, PowerShell, or Windows launcher | [Startup scripts guide](STARTUP_SCRIPTS.md) |
| Understand the features, complete an analysis and interpret the result | [User manual](USER_MANUAL.md) |
| Connect a local DSH, ChatGPT or other MCP client | See the sibling `matflow-frontend/docs/MCP_INTEGRATION_GUIDE.md` |
| Day-to-day startup, diagnostics, backup and troubleshooting | [Deployment and operations](DEPLOYMENT_AND_OPERATIONS.md) |
| Move the whole project to a new machine (backend + WebUI + tests + every demo case) in one command | [Reproduce on a new machine](REPRODUCE_ON_NEW_MACHINE.md), `scripts/repro/` |
| Understand HTTP fields and client calling conventions | [Backend API contract](BACKEND_API_CONTRACT.md) |
| Build a safe progressive node preview | [Node preview specification](NODE_PREVIEW_SPEC.md) |
| Review current completeness, milestones and the next stage | [Project status](PROJECT_STATUS.md) |
| Understand the design philosophy, modules and runtime flows | [Design and architecture](DESIGN_AND_ARCHITECTURE.md) |
| Understand module boundaries and keep developing | [Architecture and developer rules](ARCHITECTURE_AND_DEVELOPER_RULES.md) |
| Inspect the backend flow offline from the command line (the in-repo read-only FlowView tool) | [FlowView guide](../flowview/README.md), [FlowView contract](../flowview/CONTRACT.md) |
| Run the configuration-driven scenario and prompt suites | [Configured scenario tests](CONFIGURED_SCENARIO_TESTS.md), [Examples and flow-print artifacts](../examples/README.md) |
| Understand Domain Package boundaries, executors and generic control semantics | [Domain Package contract](DOMAIN_PACKAGES.md) |
| Take over maintenance: current state, open issues and next steps | [Project memory](project-memory/README.md) (historical handoff snapshots stay local and are not distributed with the repository) |

## Recommended reading paths

### End users

1. Complete installation and AI connection with the [getting started guide](GETTING_STARTED.md).
2. Read the [user manual](USER_MANUAL.md) for the feature scope and the full analysis flow.
3. To configure another client, consult the MCP integration guide in the `matflow-frontend` repository.

### Administrators and maintainers

1. Read the [deployment and operations guide](DEPLOYMENT_AND_OPERATIONS.md).
2. Run the environment diagnostics and confirm the local ports, data directory and backup policy.
3. Check the API contract and compatibility notes before upgrading.

### Developers

1. Read [design and architecture](DESIGN_AND_ARCHITECTURE.md) and the root `CONTEXT.md` first.
2. Then read [architecture and developer rules](ARCHITECTURE_AND_DEVELOPER_RULES.md) and the [backend API contract](BACKEND_API_CONTRACT.md).
3. When changing public behavior, update the implementation, the tests and the matching documentation together.

## Current capability boundaries

- **Platform Core:** Dataset import, typed GraphPatch validation, DAG scheduling, human review, preview and audit already work.
- **Currently built-in Demo capabilities:** table column mapping, basic EIS quality checks and Nyquist data generation. These are historical demonstration capabilities and do not mean a general platform must ship EIS.
- **Reference domains and cases:** the repository contains tests and examples for XRD, FTIR, UV-Vis, pycnometry, TGA and EBrick; they validate platform mechanisms and do not define Platform Core.
- The WebUI and the MCP bridge share one backend workspace over HTTP; multi-user permission isolation is not supported.
- The server listens only on local `127.0.0.1:8000` by default and ships no public-network authentication.
- The backend exposes `/api/chat` as a round-limited AI-assist endpoint; complex Chinese planning and domain tool generation remain Alpha, and the MCP bridge is another client access path.

## Documentation maintenance conventions

- Documentation is provided in English by default; the Chinese version is retained as a sibling `*.zhcn.md` file.
- `GETTING_STARTED.md` is the single entry point for installation, first startup, AI connection and basic troubleshooting.
- `STARTUP_SCRIPTS.md` is the authoritative reference for launchers, helper scripts, ports, shutdown behavior, and model-service prerequisites.
- `USER_MANUAL.md` targets users, describes stable operations and carries no internal implementation detail.
- MCP and DSH documentation is maintained in the `matflow-frontend` repository.
- `DEPLOYMENT_AND_OPERATIONS.md` covers local deployment and maintenance.
- `REPRODUCE_ON_NEW_MACHINE.md` is the migration procedure: `scripts/repro/snapshot.ps1` packages both checkouts, `scripts/repro/bootstrap.ps1` restores and provisions a new machine, and `scripts/repro/verify.ps1` proves the result against `scripts/repro/baseline.json`.
- `BACKEND_API_CONTRACT.md` is the transport-layer interface reference.
- `PROJECT_STATUS.md` records stage completeness, verification evidence and the next milestone.
- `DESIGN_AND_ARCHITECTURE.md` records the design philosophy, implementation architecture and capability boundaries.
- `ARCHITECTURE_AND_DEVELOPER_RULES.md` defines implementation boundaries and change rules.
- `../flowview/README.md` is the guide for the in-repo CLI tool FlowView: it prints the backend flow read-only (Mermaid diagrams, terminal tables, JSON). Its entry point is `.\.venv\Scripts\python.exe -m flowview graph|flow|summary|doctor` (`run-flow` is an alias for `flow`) and by design it is excluded from the wheel; `../flowview/CONTRACT.md` is its frozen internal contract.
- Historical handoff snapshots (any `_handoff/` directory) are local working notes excluded through `.gitignore` (`**/_handoff/`); they stay on the development machine and are not distributed with the repository. `project-memory/` is the long-term state of record.

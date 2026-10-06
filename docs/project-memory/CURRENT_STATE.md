# MatFlow Current State

**Verification date:** 2026-10-02
**Conclusion:** The backend control plane is usable at this phase. The general intelligent computational-materials workflow remains Alpha. Do not claim that arbitrary materials-science requests can automatically produce reliable scientific workflows.

## 1. Current Physical Boundaries

MatFlow has been split into two repositories:

| Repository | Current Responsibilities | Must Not Be Responsible For |
| --- | --- | --- |
| `D:\Projects\matflow` | Authoritative state, types, Tool Registry, GraphPatch validation, routing, execution, review, audit, uploads, and HTTP API | WebUI, MCP protocol adaptation, or client-side business state |
| `D:\Projects\matflow-frontend` | React/Vite WebUI, shared API client, MCP bridge, and DSH integration | Directly modifying backend files or duplicating backend business rules |

The repositories communicate through the `matflow-http` v1 contract. The backend does not know whether a request originated from WebUI, MCP, DSH, or another client.

## 2. Implemented Capabilities with Automated Evidence

### Backend

- Read, atomic write, and version-conflict detection for a single-workspace `GraphState`;
- Type registration, inheritance, port compatibility, DAG, cycle, and single-input-occupancy validation;
- Structured `GraphPatch`, including atomic `replace_node_revision`;
- Versioned `ToolSpec`, Tool Registry, candidate retrieval, and Jev decision adapter;
- Node revision proposals, port-migration suggestions, and generated-code review states;
- Node-level `review_policy.after_run`, safe Preview, and continue/stop controls;
- Workflow scheduling, ExecutionResult, Task summaries, traces, and audit records;
- Upload, settings, model Provider, runtime Skill, and node-library interfaces;
- Declarative Tool Recipe drafts, hidden-fixture evaluation, and bounded repair;
- Standalone Prompt normalizer: preserves original text, enforces same-language gating, and uses a strict schema;
- Versioned HTTP API and `/api/capabilities`; backend `/mcp` has been removed.
- A versioned Domain Package contract: manifest, loader, type/Tool/executor/recipe registration, package-owned recipe domains and package-owned legacy Tool-ID migrations (`docs/DOMAIN_PACKAGES.md`);
- One executor registry (`backend/executors.py`) that Platform Core and every loaded package register into; `WorkspaceRuntime._run_node` resolves `executor_ref` and holds no domain branch;
- Domain-neutral generic control semantics: multi-input `join` and `aggregate`, `quality_report`, and a data-driven `conditional_gate` that cancels downstream work;
- Domain-neutral Core catalogs: `DATA_TYPES` and `builtin_specs()` declare no measurement-method type or Tool, and an empty workspace exposes no scientific capability at all.

### Clients and Adapters

- Editable typed workflow canvas with complete ports, Bezier connections, and Inspector;
- Import, export, save, run, routed tasks, and audit-record viewing;
- Three-column desktop layout and narrow-screen drawers, including keyboard focus and an axe baseline;
- Contract-major-version checks in the API client;
- MCP Streamable HTTP bridge operating only through backend HTTP;
- DSH approval and controlled local-file import.

### Repository-local tooling

- `flowview/` is a delivered repository-local (repo-local) read-only CLI tool: it prints the MatFlow backend flow — the runtime task lifecycle and the current workspace DAG — as Mermaid diagrams, terminal tables or JSON, through `.\.venv\Scripts\python.exe -m flowview graph|flow|summary|doctor` (`run-flow` is an alias of `flow`), or `flowview\run_flowview.bat`;
- It keeps its own mirror model and readers (standard library only) so it keeps working when `backend.*` cannot be imported, and `import flowview` never imports `backend`. It never writes `data/`, `config/` or state, never starts a server, and never mutates backend state;
- Offline is the default and structural: network access exists only behind an explicit `--http [URL]` flag, and without it no subcommand imports the HTTP client, opens a socket or reads `MATFLOW_API_URL`. `--http` reads `GET /api/state`, `GET /api/task-summaries/{id}` and `GET /api/capabilities` from a running backend, plus `POST /api/route` for `flow --prompt --http`; that POST is the one call that makes the backend record a routing summary in its own audit log, and the emitted document discloses it (`http.route_recorded`, with a warning when the outcome is unknown);
- It is repo-local by design and intentionally not packaged: `pyproject.toml` `[tool.setuptools.packages.find] include = ["backend*"]` is unchanged, and that decision is recorded in `docs/PROJECT_STATUS.md` and a `pyproject.toml` comment. Its documentation is `flowview/README.md` (user guide) and the frozen `flowview/CONTRACT.md`, with three verification records (`flowview/VERIFICATION.md`, `flowview/VERIFICATION_PROMPT_MODE.md`, `flowview/VERIFICATION_LIVE_MODE.md`);
- Evidence: the flowview suite is 252 tests, `OK (skipped=3)`, and whole-repository discovery is 385 tests, `OK (skipped=7)`; three independent adversarial verification passes (offline printing, the `--prompt` surface, and the `--http` live surface) left no open P0/P1, the live surface taking 3 rounds and finding and fixing 7 P1s. Open items are recorded as MF-018: `doctor --format mermaid` still prints the text report, and there is no CI wiring for the 252 tests.

## 3. 2026-10-02 Verification Snapshot

| Scope | Result |
| --- | --- |
| Backend offline unittest | `100 passed, 4 skipped`; every skipped item requires explicitly enabled online Jev/LLM access |
| Frontend/API/MCP unit tests | `16 passed` (3 API client + 4 MCP bridge + 9 WebUI) |
| Frontend production build | Succeeded; only a dependency-level `use client` bundler warning |
| WebUI E2E | `6 passed`, using `MATFLOW_E2E_FRONTEND_PORT=5174` |

The default E2E port 5173 was occupied by another process at the time. All tests passed after switching to 5174. This was a local execution condition, not a confirmed product defect.

### 2026-10-02 P0 baseline freeze (backend)

Command: `.\.venv\Scripts\python.exe -m unittest discover` from `D:\Projects\matflow`.

First reproduction did **not** match the table above: `Ran 100 tests` with **2 failures** in `tests/test_model_service_startup.py`, both caused by a real defect rather than an environment difference. `scripts/start_model_services.ps1` used `Invoke-WebRequest`, whose progress rendering throws `HostException: Win32 internal error "Access is denied" 0x5 occurred while reading the console output buffer` whenever the script runs with captured or redirected output (tests, CI, wrapper launchers). `Test-Healthy` swallowed that exception as "unhealthy", so the authenticated readiness probe against `/v1/models` was never sent and startup always reported "Process exited before its health check passed".

Fix: `$ProgressPreference = 'SilentlyContinue'` in the launcher script. After the fix the frozen baseline is:

```text
Ran 100 tests in 2.605s

OK (skipped=4)
```

Baseline recorded for regression comparison: 100 passing backend tests, 4 designed online skips (explicitly enabled Jev/LLM access only). Any later change to Platform Core must keep this suite and the `scripts/start_model_services.ps1` contract tests green.

### 2026-10-02 P0 Domain Package boundary pass

After the boundary work the frozen suite is:

```text
Ran 133 tests in 2.884s

OK (skipped=4)
```

The 33 added tests are the acceptance evidence for the boundary. `tests/test_domain_packages.py`
proves that an empty Core exposes no scientific data type, Tool or recipe domain, that a loaded
package restores capability discovery, type validation, executor resolution and its package-owned
legacy migration, that the manifest/loader/guard-rail rules fail closed, and that `/api/capabilities`
and `/api/node-library` advertise exactly the composed packages.
`tests/test_generic_control_nodes.py` proves the generic Join/Aggregate/QualityReport/
ConditionalGate semantics and their reuse over two artifact kinds. `tests/test_analysis_recipes.py`
and the tool-recipe suites now compose the reference packages explicitly through
`tests/reference_composition.py`, so those suites double as the migration proof.

An independent adversarial review then ran feature-removal mutations on copies of the tree (seven
mutations, each failing the test that names the feature) and confirmed the moved executors are
semantically equivalent to the pre-refactor `_run_node`. Its findings were fixed in the same pass:
generic rather than EIS defaults plus `ToolSpec.open_params` for the platform column-mapping Tool;
package visibility in `apply_revision_proposal`, so a package-typed node can still be revised; the
composed catalog in `/api/node-library`; a custom node can no longer shadow a platform or package
tool id; the phantom `decision` output port was removed from `conditional_gate`; `node_input`
refuses a multi-input port; a hand-built `ExecutorRegistry` cannot claim a platform namespace; a
duplicate `package_id` is rejected; and a package Tool declaring a port type it does not contribute
now names the package in the error. Two residual issues from that review are recorded as MF-015 and
MF-016.

## 4. Decided but Not Fully Implemented

| Target | Actual Current State |
| --- | --- |
| Domain Package | The minimum contract is implemented and documented (`docs/DOMAIN_PACKAGES.md`); `eis`, `xrd`, `ftir`, `qe`, and demo-only `qe_demo` packages ship. Remaining: package trust/signing policy and package-scoped execution isolation |
| Generic join / quality report / conditional gate | Implemented as platform Tools with multi-input ports and a control-plane stop fact, and reused over a plain artifact and an EIS artifact (`tests/test_generic_control_nodes.py`). Remaining: list-valued and cross-run aggregation, and richer criteria than required-keys plus one numeric range |
| Generate a multi-branch DAG from any complex Chinese request | Not reliable; Chinese lexical retrieval and planner capability are insufficient |
| Complete Tool lifecycle | Drafting, evaluation, and bounded repair exist; general review, publication, and isolated code execution remain incomplete |
| EBrick temperature-dependent EIS case | Data and an evaluation design exist; there is no end-to-end executable acceptance loop |
| Multi-project/multi-user | Not implemented; the current system is single-user, single-workspace, with local-file persistence |
| Secure public-network deployment | Not implemented; the default is loopback, with no complete authentication and authorization system |

## 5. Deprecated or Replaced Designs

- **Backend-embedded MCP endpoint:** Removed; the MCP bridge is in `matflow-frontend`.
- **Standalone Human Decision Tool:** Marked deprecated; replaced by post-run review policy on any Node.
- **Frontend and backend in one repository:** Replaced by two independent repositories.
- **AI directly edits Graph JSON:** Prohibited; every write must pass `GraphPatch`, version, and deterministic validation.
- **Normalization overwrites the original prompt:** Rejected; Normalized Request may only be a reversible derived view.
- **`Project / GraphVersion / Run / EventLog` as the implemented storage model:** These are mid-stage design terms. The current code actually uses `Workspace / GraphState / Task / ExecutionResult / TaskLogSummary`. If multi-project storage is built later, make a separate migration decision; documentation must not present a conceptual diagram as current reality.
- **Scientific Graph and Workflow Graph as MatFlow's current dual-graph storage model:** Not implemented in the current code. The authoritative object is a single-workspace typed Workflow. Do not conflate it with `synsimul2`'s three-graph architecture.
- **Scientific semantics compiled into Platform Core:** Rejected and removed. EIS data types, Tools and executors, and the XRD/FTIR reference recipes, now live in Domain Packages; a workspace that composes no package exposes none of them (`docs/DOMAIN_PACKAGES.md`).

## 6. Current Git-State Risk

At the start of verification:

- Backend branch `architecture/v0.2-contract-first` was 4 commits ahead of the remote and contained substantial uncommitted documentation changes plus one untracked handoff directory;
- The frontend branch with the same name had a clean worktree;
- This documentation effort added only project-memory and handoff files and did not overwrite those existing changes.

After the handoff-documentation commit, the backend branch was 5 commits ahead of the remote. The existing uncommitted changes and untracked directory remained intact and were not included in the handoff commit.

A new maintainer should first run `git status --short --branch`. Do not assume the worktree is clean, and do not mix historical documentation changes into new-feature commits.

### Re-verified at the P0 baseline freeze

- Backend HEAD `696b607`, branch `architecture/v0.2-contract-first`, **6 commits ahead** of `origin`;
- The worktree carries **21 modified tracked Markdown files** (`CONTEXT.md`, `README.md`, `docs/*.md`, `docs/_handoff/2026-10-01-capability-status/*`, `docs/_handoff/README.md`, `examples/README.md`, `examples/docs/06_prompt_stability_and_functionality_suite.md`, `examples/ebrick_case05_evaluation/*`, `examples/ebrick_complete_prompt_backend_evaluation/*`) plus **1 untracked directory** `docs/_handoff/2026-10-01-platform-case-boundary/`;
- No tracked **code** file was modified by that documentation work. The P0 freeze adds exactly one code change (`scripts/start_model_services.ps1`, the progress-rendering fix above) and this project-memory update;
- The frontend repository worktree is clean;
- Those historical documentation changes are therefore explainable and separable: review them on their own topic before mixing them with any Domain Package commit.
- The P0 boundary pass added tracked changes of its own: `backend/contracts.py`, `backend/tool_registry.py`, `backend/workspace_runtime.py`, `backend/validator.py`, `backend/analysis_recipes.py`, `backend/main.py`, the new `backend/executors.py`, `backend/builtin_executors.py` and `backend/domain_packages/{__init__,eis,spectroscopy}.py`, `tests/*`, `scripts/start_model_services.ps1`, `docs/DOMAIN_PACKAGES.md`, and this project-memory directory. Review those as one Domain Package topic, separately from the historical documentation changes.

### Current worktree count (2026-10-06)

Before the commit pass on 2026-10-06 the tree carried **45 modified tracked files** — now including
code rather than only Markdown: `backend/*.py`, `tests/*.py`, `scripts/start_model_services.ps1`,
`pyproject.toml` and `uv.lock` — plus **15 untracked entries**: `backend/{executors,builtin_executors}.py`,
`backend/domain_packages/`, `docs/DOMAIN_PACKAGES.md`,
`tests/{reference_composition,test_domain_packages,test_generic_control_nodes,test_method_tools,test_qe_package}.py`,
`examples/{long_prompt_cases.json,qe_benchmark_cases.json,qe_benchmark_report.md}`,
`scripts/{organize_mgo_results,run_qe_benchmark}.py` and `flowview/`.

That state was then committed as three topic commits on `architecture/v0.2-contract-first` — handoff
snapshots moved out of version control, the platform / Domain Package code, and FlowView plus the
long-prompt suite and documentation updates — and `main` was fast-forwarded to them and pushed. The
worktree is clean afterwards, and every `_handoff/` directory is ignored (`**/_handoff/`) and kept
locally only. The "21 modified Markdown files" and "1 untracked directory" figures above therefore
describe the 2026-10-02 snapshot, not the tree today; MF-005 in `OPEN_ISSUES.md` mirrors that same
historical snapshot.

### Repository-local tool in version control

- The delivered repository-local `flowview/` tool was not part of the 2026-10-02 baseline freeze. It was committed on 2026-10-06 together with `examples/long_prompt_cases.json`; before that pass `git status` reported both as untracked (`?? flowview/`, `?? examples/long_prompt_cases.json`).

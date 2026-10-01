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

### Clients and Adapters

- Editable typed workflow canvas with complete ports, Bezier connections, and Inspector;
- Import, export, save, run, routed tasks, and audit-record viewing;
- Three-column desktop layout and narrow-screen drawers, including keyboard focus and an axe baseline;
- Contract-major-version checks in the API client;
- MCP Streamable HTTP bridge operating only through backend HTTP;
- DSH approval and controlled local-file import.

## 3. 2026-10-02 Verification Snapshot

| Scope | Result |
| --- | --- |
| Backend offline unittest | `100 passed, 4 skipped`; every skipped item requires explicitly enabled online Jev/LLM access |
| Frontend/API/MCP unit tests | `16 passed` (3 API client + 4 MCP bridge + 9 WebUI) |
| Frontend production build | Succeeded; only a dependency-level `use client` bundler warning |
| WebUI E2E | `6 passed`, using `MATFLOW_E2E_FRONTEND_PORT=5174` |

The default E2E port 5173 was occupied by another process at the time. All tests passed after switching to 5174. This was a local execution condition, not a confirmed product defect.

## 4. Decided but Not Fully Implemented

| Target | Actual Current State |
| --- | --- |
| Domain Package | Concept, terminology, and migration plan are clear; there is no complete manifest/loader/executor registry, and EIS/XRD/FTIR still enter Core |
| Generic join / quality report / conditional gate | The design need is clear; complete data-driven gating semantics do not yet exist |
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

## 6. Current Git-State Risk

At the start of verification:

- Backend branch `architecture/v0.2-contract-first` was 4 commits ahead of the remote and contained substantial uncommitted documentation changes plus one untracked handoff directory;
- The frontend branch with the same name had a clean worktree;
- This documentation effort added only project-memory and handoff files and did not overwrite those existing changes.

After the handoff-documentation commit, the backend branch was 5 commits ahead of the remote. The existing uncommitted changes and untracked directory remained intact and were not included in the handoff commit.

A new maintainer should first run `git status --short --branch`. Do not assume the worktree is clean, and do not mix historical documentation changes into new-feature commits.

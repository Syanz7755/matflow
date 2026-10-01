# MatFlow Handoff Entry Point

**Handoff date:** 2026-10-02
**Suggested reading time:** 5–10 minutes

## Four Things to Know First

1. MatFlow now consists of two repositories: `matflow` is the authoritative backend, while `matflow-frontend` contains the WebUI/MCP/DSH clients.
2. The backend platform foundation is operational and its regression suite is stable, but the general autonomous computational-materials workflow remains Alpha.
3. The largest current technical debt is not the UI: EIS/XRD/FTIR remain hardcoded in Platform Core, and the Domain Package boundary has not actually been implemented.
4. The backend worktree already contains the user's uncommitted documentation changes. Do not clean, overwrite, or casually merge them.

## Reading Order

1. `docs/project-memory/CURRENT_STATE.md`
2. `docs/project-memory/ARCHITECTURE_EVOLUTION.md`
3. Root `CONTEXT.md`
4. `docs/BACKEND_API_CONTRACT.md`
5. `docs/project-memory/OPEN_ISSUES.md`
6. `docs/project-memory/NEXT.md`

## Current Architecture

```text
WebUI / MCP / DSH / future clients
              |
        matflow-http v1
              |
      authoritative backend
 GraphState / Registry / Validator / Runner / Audit
              |
   Domain Packages (target; incomplete)
              |
      scientific executors
```

## Verification Commands

Backend:

```powershell
Set-Location D:\Projects\matflow
.\.venv\Scripts\python.exe -m unittest discover -v
```

Frontend:

```powershell
Set-Location D:\Projects\matflow-frontend
npm.cmd test
npm.cmd run build
$env:MATFLOW_E2E_FRONTEND_PORT='5174'
npm.cmd run test:e2e
```

Current result: 100 backend tests passed and 4 skipped; 16 frontend unit tests passed, the build succeeded, and 6 E2E tests passed.

## Recommended First Development Task After Handoff

Do not continue adding new scientific demos. First implement the minimum Domain Package manifest/loader and executor registry, then prove them by migrating the EIS package. Freeze old behavior with tests before doing so to ensure existing Workflows remain migratable.

## Common Misconceptions

- `Project/GraphVersion/Run/EventLog` is a historical design, not the current storage model;
- MCP is a remote-control interface, not the business engine;
- Jev is a replaceable, bounded decision component, not an independent project or source of state;
- EBrick is a Reference Case, not Platform Core;
- Prompt normalization cannot replace the original text;
- Model-generated JSON or code does not mean the system has acquired an executable Tool;
- ComfyUI interaction patterns may be referenced, but GPL source code cannot be copied without boundaries into the current independently implemented frontend.

## Checks Before Making Changes

- Run `git status --short --branch` in both repositories;
- Confirm whether the change belongs to Core, a Domain Package, or a Reference Case;
- Update tests and documentation together for public-contract changes;
- Do not include existing dirty documentation in unrelated commits;
- Every new write must still pass version, type, and DAG validation.

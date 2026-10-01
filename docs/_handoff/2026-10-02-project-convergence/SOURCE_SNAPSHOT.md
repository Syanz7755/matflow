# MatFlow Information Sources and Verification Snapshot

**Date:** 2026-10-02

## Repositories

- Backend: `D:\Projects\matflow`
  - branch: `architecture/v0.2-contract-first`
  - At the start of verification: 4 commits ahead of the remote, with existing uncommitted documentation changes
  - HEAD: `a5f682d chore: checkpoint before separating platform and cases`
  - After the handoff-documentation commit: 5 commits ahead of the remote; existing uncommitted changes remained intact
- Frontend: `D:\Projects\matflow-frontend`
  - branch: `architecture/v0.2-contract-first`
  - Worktree was clean at the start of verification
  - HEAD: `712d341 feat: establish independent MatFlow frontend clients`

## Automated Verification

- Backend: `.\.venv\Scripts\python.exe -m unittest discover -v`
  - `Ran 100 tests`
  - `OK (skipped=4)`
- Frontend: `npm.cmd test`
  - API client 3, MCP bridge 4, and WebUI unit 9; all passed
- Frontend build: `npm.cmd run build`; succeeded
- Frontend E2E: after setting `MATFLOW_E2E_FRONTEND_PORT=5174`, `6 passed`

## Primary Formal Sources

- `README.md`
- `CONTEXT.md`
- `docs/PROJECT_STATUS.md`
- `docs/DESIGN_AND_ARCHITECTURE.md`
- `docs/ARCHITECTURE_AND_DEVELOPER_RULES.md`
- `docs/BACKEND_API_CONTRACT.md`
- `docs/_handoff/2026-10-01-capability-status/`
- `docs/_handoff/2026-10-01-platform-case-boundary/`
- Frontend `README.md`, `docs/MCP_INTEGRATION_GUIDE.md`, and `apps/webui/DESIGN_BRIEF.md`

## Historical Decision Threads Retained

- Contract-first design, minimum closed loops, and observability;
- Dynamic Tool Registry plus a Jev-like decision router;
- Planner proposes, Validator decides, Runner executes;
- UI and AI App as peer clients, with MCP as a thin adapter;
- Separate frontend/backend repositories and discussion of the GPL boundary;
- Platform/Domain/Case mixing exposed by EBrick backend tests.

Conversation records are used only to explain architectural evolution. Current implementation status is determined from code and tests.

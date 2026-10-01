# MatFlow Project Memory Index

**Status date:** 2026-10-02
**Scope:** The `D:\Projects\matflow` backend repository and the sibling `D:\Projects\matflow-frontend` client repository

This directory is the navigation layer for MatFlow's current source of truth. It does not replace interface contracts, user manuals, or code. Instead, it answers the first five questions a new maintainer needs to resolve: Which architecture is current? What has been implemented? What remains only a design? Where are the problems? What should happen next?

## Document Responsibilities

| Document | Question Answered | When to Update |
| --- | --- | --- |
| [CURRENT_STATE.md](CURRENT_STATE.md) | What actually exists now? What has not been implemented? | At each phase review or major capability change |
| [ARCHITECTURE_EVOLUTION.md](ARCHITECTURE_EVOLUTION.md) | Why did the current architecture emerge? Which earlier ideas remain? | When architectural boundaries change |
| [OPEN_ISSUES.md](OPEN_ISSUES.md) | What are the current blockers, risks, and unresolved decisions? | When an issue is opened, closed, or reprioritized |
| [NEXT.md](NEXT.md) | In what order should the next phase proceed? What should be deferred? | At milestone transitions |

The current handoff snapshot is in `docs/_handoff/2026-10-02-project-convergence/`. Handoff snapshots do not override the long-lived state documents in this directory.

## Source Priority

When sources conflict, use the following order:

1. Current code, the versioned HTTP contract, and freshly executed tests;
2. `CURRENT_STATE.md` in this directory;
3. `docs/BACKEND_API_CONTRACT.md`, `docs/DESIGN_AND_ARCHITECTURE.md`, and the root `CONTEXT.md`;
4. The most recent dated snapshot under `docs/_handoff/`;
5. Historical proposals, old evaluation reports, and conversation records.

Every design goal must be explicitly labeled as a target or not yet implemented. Never infer a completed capability directly from a discussion record.

## Current One-Sentence Positioning

MatFlow is currently a **backend-authoritative, contract-first, auditable control plane for computational materials workflows**. WebUI, MCP, DSH, and future clients are peer entry points. The platform foundation is operational, but the Domain Package boundary, the general scientific-planning loop, and the vertical EBrick case are not yet complete.

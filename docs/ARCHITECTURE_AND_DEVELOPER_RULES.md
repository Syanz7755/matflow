# Architecture and developer rules

For the design motivation, the complete module diagram, the runtime flows and the current capability boundaries see [design and architecture](DESIGN_AND_ARCHITECTURE.md); for stage completeness see [project status](PROJECT_STATUS.md). Domain vocabulary follows the root `CONTEXT.md`.

## Authority boundary

The `matflow` backend is the only authority for state, validation, routing, execution, audit and persistence. Every client may operate on the workspace only through the versioned HTTP API; no client may import backend Python objects, access `data/` or edit state files directly.

The single exception is the in-repo read-only diagnostic tool `flowview/` (see `../flowview/README.md`): it is not a workspace client and by design reads the read-only mirrors of `data/` and `config/` plus the `backend/` sources, so that it can still print the flow when the backend is unavailable. It writes no state, is excluded from the wheel, must never be depended on by backend logic, and its internal contract is frozen in `../flowview/CONTRACT.md`; network access happens only through the explicit `--http [URL]`, and offline remains the default.

`matflow-frontend` is a separate npm workspace containing the WebUI, the shared API client, the MCP bridge and the DSH integration. The two repositories can publish patches and minor versions independently and stay compatible through the `matflow-http` contract major version.

## Capability ownership rules

- Platform Core defines only domain-neutral Workflow, type registration, Tool lifecycle, execution, review and audit mechanisms.
- Measurement-method data types, Tools, Recipes and executors belong to a Domain Package; concrete samples, catalogues, experimental conditions and expected results belong to a Reference Case.
- A new case must not be integrated by changing core type constants or by adding a domain-name branch to a core executor; if an extension point is missing, add a generic extension mechanism first.
- Cases in tests and documentation must state which layer they belong to; the completeness of a single case must not stand in for platform completeness.

## Writing and client rules

- GraphPatch validation uses `POST /api/patch/validate` and writes no state; applying a patch must complete validation and the atomic write inside the server lock.
- A stale version returns HTTP 409 with `graph_version_conflict` deterministically.
- Uploads, node review, human decisions, data type changes and execution all go through backend interfaces.
- A client reads `/api/capabilities` at startup and rejects an incompatible contract major version.
- The MCP bridge handles HTTPS remote files, redirects, private-network addresses and the 25 MB limit, then calls the backend upload interface.
- A new UI must provide `matflow-ui.json` in the repository root; the start command is an argument array and is not executed through a shell.

Before committing to the backend run `uv run python -m unittest discover -v` (that discovery scope covers both `tests/` and the in-repo tool `flowview/tests/`, 426 tests in total today); before committing to the frontend run `npm test` and `npm run build`. Cross-repository changes should also run the WebUI E2E and the MCP smoke test.

## Documentation language convention

- Except for documentation, every file uses English only: code, comments, configuration, scripts, interface copy, and all text other than test data.
- Documentation is English by default and lives in the plain `.md` file; the Chinese version is retained as a sibling `*.zhcn.md` file, and the two must be kept in sync.
- Chinese prompts that tests and examples use as input are test data, not documentation, and stay Chinese by design so the Chinese interaction path keeps its coverage.

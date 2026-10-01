# MatFlow Next Phase

**Phase objective:** Converge the reliable control plane into a genuinely domain-independent platform and prove the extension mechanism with an external EIS/EBrick package.

## Recommended Sequence

### 0. Freeze an Explainable Baseline First

- Review and resolve the backend's current uncommitted documentation changes;
- Record the corresponding backend/frontend commits and `matflow-http` version;
- Retain the current 100 backend tests, 16 frontend unit tests, and 6 E2E tests as the regression baseline;
- Do not alter the user's existing uncommitted content; commit by topic.

### 1. Define the Minimum Domain Package Contract

The minimum manifest needs only: package ID/version, required Core contract version, data types, ToolSpec, Recipe, executor_ref, migrators, and an acceptance-test entry point.

Acceptance: an empty workspace loads no scientific package; after loading an example package, capability discovery, type validation, and executor resolution all work.

### 2. Migrate EIS First, Then XRD/FTIR

- Move `EISData`, `EISQCReport`, EIS Tools, and executors out of Core;
- Preserve explicit compatibility migrations for old Tool IDs;
- Move XRD/FTIR Recipes and fixture evaluations into their respective packages;
- Freeze behavior with compatibility tests before removing duplicate execution semantics.

### 3. Complete Generic DAG Control Semantics

Implement domain-independent `Join/Aggregate`, `QualityReport`, and `ConditionalGate`, and reuse them in two different domain examples. Do not implement them with `if domain == "eis"`.

### 4. Integrate a Reversible Derived Request View

A Task stores the original Research Request, structured Normalized Request, English or multilingual retrieval query, and fidelity diff. Any language drift or loss of numbers, units, negation, or paths must fall back to the original text.

### 5. Complete Vertical Acceptance for the EBrick Reference Case

Using the external EIS package, complete furnace-program parsing, time-temperature mapping, Cp/G to complex impedance, parallel diagnostics, quality aggregation, manual/automatic Gates, and DRT/report generation. This is an acceptance case and must not add default scientific types to Core.

## Defer for Now

- Do not rewrite the stable GraphPatch, version-conflict, or typed-DAG foundations;
- Do not move WebUI, MCP, or DSH business logic back into the backend, and do not duplicate backend state in clients;
- Do not add more instrument-specific, column-specific, material-system, or scientific-method branches to Core;
- Do not expand more demos before the Domain Package boundary is stable;
- Do not activate generated code directly;
- Do not prematurely build multi-user support, a database, public deployment, or large-scale scheduling merely for completeness;
- Do not copy ComfyUI GPL source code directly into the current independently implemented frontend repository;
- Do not misrepresent `synsimul2`'s Scientific/Workflow/Runtime three-graph model as MatFlow's implemented data model.

## Definition of Done for the Next Milestone

- Core tests pass without loading any scientific package;
- At least one EIS package passes independent package contract tests;
- Existing EIS workflows migrate without semantic loss;
- Fixed EBrick input produces a non-linear DAG and an auditable Artifact through quality gating;
- Documentation clearly distinguishes the completion status of Core, Domain Package, and Reference Case.

# MatFlow Next Phase

**Phase objective:** Converge the reliable control plane into a genuinely domain-independent platform and prove the extension mechanism with an external EIS/EBrick package.

**Where this stands:** the platform half of that objective is met at the minimum contract. What
remains is the planning loop, the Tool lifecycle, and the reference-case vertical acceptance — not
the boundary itself.

## Completed: the P0 Domain Package boundary pass

| Step | Result | Evidence |
| --- | --- | --- |
| 0. Freeze an explainable baseline | `Ran 133 tests ... OK (skipped=4)`; worktree state recorded as explainable | `CURRENT_STATE.md` §3 and §6. One real defect was found and fixed on the way: `scripts/start_model_services.ps1` silently lost its readiness probe whenever its output was captured |
| 1. Minimum Domain Package contract | Versioned manifest, loader and set with fail-closed rules; single executor registry; package-owned recipe domains; package-owned legacy Tool-ID migrations | `docs/DOMAIN_PACKAGES.md`, `tests/test_domain_packages.py` |
| 2. Migrate EIS, XRD, FTIR and QE to separate packages | Each method package owns its vocabulary and recipes; the declarative engine stays generic in Core; the QE history fixture lives in a non-selectable demo package | `backend/domain_packages/{eis,xrd,ftir,qe,qe_demo}.py`, `tests/reference_composition.py` |
| 3. Generic DAG control semantics | Domain-independent `join`, `aggregate`, `quality_report` and `conditional_gate`, reused over a plain artifact and an EIS artifact | `tests/test_generic_control_nodes.py` |

## Recommended Sequence From Here

### 1. Integrate a Reversible Derived Request View (MF-007)

A Task stores the original Research Request, structured Normalized Request, English or multilingual retrieval query, and fidelity diff. Any language drift or loss of numbers, units, negation, or paths must fall back to the original text.

### 2. Complete the Tool Lifecycle (MF-008)

Review, publication, withdrawal, isolated execution with resource limits, and audit, all with
contract tests. Keep the Domain Package contract structurally validated but untrusted: `core_contract`
is a version gate, not a trust boundary, and a package must never be able to reach around validation,
auditing or the workspace API.

### 3. Land the EBrick vertical acceptance

Using the EIS package, complete furnace-program parsing, time-temperature mapping, Cp/G to complex
impedance, parallel diagnostics, quality aggregation through the generic `quality_report` +
`conditional_gate` nodes, manual/automatic gates, and DRT/report generation. This is an acceptance
case and must not add default scientific types to Core.

### 4. Keep extension boundaries explicit

MF-013, MF-014, and MF-017 were closed by separating method packages, using method-neutral recipe
result contracts, and moving the QE replay fixture out of the scientific package. Future per-method
Tools should be contributed by their package; demo fixtures remain non-selectable.

## Defer for Now

- Do not rewrite the stable GraphPatch, version-conflict, or typed-DAG foundations;
- Do not move WebUI, MCP, or DSH business logic back into the backend, and do not duplicate backend state in clients;
- Do not add more instrument-specific, column-specific, material-system, or scientific-method branches to Core; new method knowledge belongs in a Domain Package;
- Do not add scientific Tools to the platform catalog to make a demo shorter: compose a package instead;
- Do not activate generated code directly;
- Do not prematurely build multi-user support, a database, public deployment, or large-scale scheduling merely for completeness;
- Do not copy ComfyUI GPL source code directly into the current independently implemented frontend repository;
- Do not misrepresent `synsimul2`'s Scientific/Workflow/Runtime three-graph model as MatFlow's implemented data model.
- Do not let wiring the now-committed `flowview/` 252-test suite into CI distract from the current milestone: it is a cheap, low-risk follow-up that can wait for a convenient commit.

## Definition of Done for the Next Milestone

| Criterion | State |
| --- | --- |
| Core tests pass without loading any scientific package | Met: `tests/test_domain_packages.py::EmptyCoreTests` plus the full suite with an empty composition |
| At least one EIS package passes independent package contract tests | Met: `tests/test_domain_packages.py::LoadedPackageTests`, `ManifestContractTests`, `RecipeDomainOwnershipTests` |
| Existing EIS workflows migrate without semantic loss | Met for the pinned suite: the EIS and recipe suites compose the reference packages and pass unchanged in assertion content |
| Fixed EBrick input produces a non-linear DAG and an auditable Artifact through quality gating | Open: the generic gate exists; the EBrick vertical case does not |
| Documentation clearly distinguishes the completion status of Core, Domain Package, and Reference Case | Met: `docs/DOMAIN_PACKAGES.md`, `CURRENT_STATE.md` §2/§4/§5, `OPEN_ISSUES.md`, and this file |

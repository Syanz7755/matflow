# Project status — 2026-10-19

The backend is a usable local workflow prototype; interview preparation is in progress.
The current portfolio evidence is the [offline QE replay](../examples/cases/A1-qe-mgo/README.md),
[routing diagnostic](evaluation/README.md) and [interview preparation guide](INTERVIEW_PREPARATION.zhcn.md).
All changes in this round remain uncommitted and unpushed.

| Area | Current evidence | Remaining boundary |
|---|---|---|
| Platform contracts | Typed GraphPatch validation, DAG execution, generic join/aggregate and review/gate tests | Single-user local files; no multi-tenant or public-network security |
| Domain extension | DomainPackage manifests, loaders, type composition and executor registration | Structural validation is not a trust boundary; limited tool coverage |
| Model planning | Type-filtered candidates, Jev/LLM selection, no keyword fallback; repeated online smoke on one synthetic request | One request does not establish general accuracy; Jev service was unavailable; expanded on/off evaluation remains open |
| Offline presentation | Explicit `matflow demo qe-mgo --output <new-directory>`, frozen values, input hashes, recorded run and refusal to overwrite | Pinned historical replay, not LLM planning or a new QE/HPC calculation |
| Reproducibility | Pytest declared in the locked dev environment; test-only suites/fixtures separated; historical reports archived | Frontend e2e, screenshots and the full EBrick case remain open |
| Publication | MIT LICENSE is present locally | No commit, frontend repository creation or push performed in this round |

Use the dated [portfolio milestone record](PORTFOLIO_READINESS.md) for verification
details and remaining work.
The percentages and test counts below are a preserved **2026-10-01 historical assessment**,
not the current acceptance result. In particular, its claims that generic controls or
Domain Package manifests are missing have been superseded by the implementation above.

---

# Historical stage-completeness assessment (2026-10-01)

**Assessment date:** 2026-10-01
**Assessment target:** the MatFlow backend 1.1 development state in the current workspace
**Scoring note:** the table below is an engineering judgment aimed at product milestones, not code coverage; "complete" requires the capability to exist, the interface to be stable and automated evidence to be present.

## One-page conclusion

MatFlow has reached the stage milestone "backend platform base is usable" and can keep building domain workflows on top of it. It has not reached the product goal "given any materials-science prompt, the system automatically researches the method, generates Tools, builds a complex DAG and reliably produces scientific conclusions".

The directional completeness is:

- Backend platform base: about **80%**, passing for this stage;
- General materials-science intelligent-workflow product: about **55%**, still Alpha;
- Current reference-domain capability coverage: about **35%**, which only describes the coverage of the existing EIS/XRD/FTIR demos;
- EBrick temperature-dependent impedance-spectroscopy reference case: about **25%**, not yet closed, and not counted toward Platform Core completeness.

Three layers must be kept apart here: Platform Core provides domain-neutral workflow mechanisms; a Domain Package provides the data types, Tools and executors of one measurement method; a Reference Case uses one or more domain packages to complete a concrete research task. The current code still has some domain capability leaking into the core layer, and the percentages must not be merged into a single product-completeness figure.

## Summary table

| Area | Completeness | Judgment | Existing evidence | Main gap |
| --- | ---: | --- | --- | --- |
| Authoritative state and HTTP contract | 90% | Usable | Versioned state, capability discovery, atomic writes, conflict responses | Single workspace, file persistence, no multi-user isolation yet |
| Type system and GraphPatch validation | 90% | Usable | Nominal types, inheritance, port compatibility, cycle and duplicate-input checks | No domain-level composite types or conditional branch types |
| DAG execution and human review | 75% | Basically usable | Scheduling once dependencies are met, pause/resume/stop, node preview | No data-driven conditional gating; no generic join/aggregate Tool |
| Routing and model integration | 70% | Partly usable | Type-filtered candidates with Jev decisions and LLM fallback (no keyword routing), `POST /api/plan` prompt -> workflow planner, one gateway config (`config/llm.json`), audit records | Live models are opt-in, not part of the default regression; planning is slow and varies between runs (MF-006, MF-020) |
| Tool generation and evolution | 55% | Lifecycle has started | Draft Recipes, hidden-fixture evaluation, bounded repair, node revision proposals | Recipes cover only limited operations; no complete review/publication interface and no generic isolated executor |
| Domain Package mechanism | 45% | Prototype level | Custom types and Tools can be registered, declarative Recipe rudiments exist | No standalone package manifest, load boundaries or executor registration mechanism |
| Current reference-domain capability coverage | 35% | Example level | EIS basic quality checks/Nyquist, XRD peak extraction/reference matching, FTIR peak extraction/band assignment | Covers only limited inputs and rules; general scientific analysis capability must not be inferred from it |
| Prompt normalize | 45% | Standalone tool usable | Original text preserved, same-language check, strict JSON, 5 tests | Not yet in the real chat/planning chain; no complete drift gate for numbers, units, negation and paths |
| FlowView flow-printing CLI | — | Delivered (in-repo read-only tool, not counted toward product completeness) | 252 tests pass (3 skipped); independent adversarial verification left no P0/P1 open, and the verifier's third round concluded "deliverable" (one round each for the offline printing surface and the prompt surface; three rounds for the `--http` live surface, whose 7 P1 findings and all P2 findings were fixed with regression tests) | `doctor --format mermaid` still prints a text report; not wired into CI; not yet committed to version control |
| Testing and auditability | 85% | Good | 174 tests in `tests/`, 426 offline tests including the in-repo tool pass; trace, task summaries, scenario suite | 7 tests skipped by design (4 online-model authorizations, 3 symlink dependencies); no CI; platform, domain-package and case tests are not fully layered |
| Documentation | 85% | Usable for this stage | User, operations, interface, testing, design and architecture documentation | Must keep in sync with domain capability and the cross-repository contract |

## Verification record

Running the test suite (`tests/`) without connecting to an online model service:

```text
Ran 174 tests in 3.6s
OK (skipped=4)
```

The whole repository (including the in-repo FlowView tool's tests) in one `python -m unittest discover` pass:

```text
Ran 426 tests in 90s
OK (skipped=7)
```

The in-repo FlowView suite alone is `Ran 252 tests in 85s`, `OK (skipped=3)`; `tests/` plus `flowview/tests/` account for the total. These counts were re-measured after the documentation language migration.

Of the skips, 4 are Jev/LLM online tests that require explicit authorization, and 3 are FlowView cases that depend on symlinks (they are skipped in a restricted sandbox or on Windows without developer mode). In a restricted sandbox the tests also produce spurious failures from Windows temporary-directory permissions; these disappear entirely when re-run in a normal-permission environment and are not code regressions.

Existing test coverage:

- HTTP contract, graph version conflicts and state read/write;
- type inheritance, port compatibility and graph validation;
- routing candidates, multi-model consensus and failure degradation;
- workflow execution, review pauses and node evolution;
- noise-fixture evaluation and repair of the XRD/FTIR reference-domain Recipes;
- Prompt normalize configuration, schema validation and language-drift rejection;
- configuration-driven scenario tests and report redaction.

### In-repo tool: FlowView (delivered)

- A read-only CLI that prints the backend flow and the runtime stages on the command line as Mermaid diagrams, terminal tables or JSON. Entry point `.\.venv\Scripts\python.exe -m flowview graph|flow|summary|doctor`; network access goes only through the explicit `--http URL`, and offline is the default. Live mode reads only a running backend (`/api/state`, `/api/task-summaries/{id}`, `/api/capabilities`) and can use `POST /api/route` to print the backend's real routing decision; that endpoint makes the backend record a routing summary and the printed result says so through `http.route_recorded`. FlowView itself writes no file.
- It is an in-repo tool and by design excluded from the wheel (`[tool.setuptools.packages.find] include = ["backend*"]` stays unchanged), so it is not counted toward product completeness in the table above; its declared contract and its implementation are frozen by `flowview/CONTRACT.md`.

## Stage milestone verdicts

### Passed: M1 backend base

The following hold:

1. The backend is the only authority for state and execution;
2. Clients work through the versioned HTTP interface;
3. Workflow changes pass type, topology and version validation;
4. Execution leaves traceable results and pauses at human review points;
5. A model suggestion cannot bypass the Tool lifecycle directly;
6. Offline regression tests pass stably.

### Not passed: M2 general intelligent-planning loop

The following do not all hold yet:

1. Reliably reading research rule documents and mixed attachments;
2. Generating a multi-branch, multi-join DAG from a complex Chinese request;
3. Researching a method and generating an executable Tool after detecting a Capability Gap;
4. A Tool entering the Registry only after isolated evaluation, review and publication;
5. Using a data-quality gate to decide whether downstream mechanism analysis runs;
6. Reporting method, parameters, evidence, uncertainty and failure reasons.

## Recommendations for the next stage

The next stage should maintain two mutually independent milestone lines.

### Platform milestone: Domain Package boundary

1. Platform Core keeps only domain-neutral Dataset, Artifact, DAG, Review, Tool lifecycle and audit semantics;
2. Define a versionable Domain Package manifest plus type, Tool and executor registration interfaces;
3. Add generic join, quality-report and conditional-gate semantics;
4. Wire normalization into the planner as a reversible derived view rather than as an overwrite of the Research Request;
5. Run platform contract tests and concrete domain-package acceptance tests as separate layers.

### Reference-case milestone: EBrick temperature-dependent EIS

The following capabilities belong to the EIS Domain Package or the EBrick Reference Case, not to Platform Core:

1. Parsing furnace-program rules into the structured temperature program the case needs;
2. Implementing the `Cp/G + frequency -> complex impedance` conversion and the scan-time-to-temperature mapping;
3. Running parallel diagnostics such as integrity checks, KK/Lin-KK and candidate-circuit comparison;
4. Aggregating quality and controlling downstream work through a generic Gate;
5. Running DRT, component contributions and case charts after quality passes;
6. Bringing the whole non-linear DAG into EBrick fixed-data acceptance.

Until the platform milestone passes, MatFlow should not be described externally as "domain-neutral and freely extensible"; until the EBrick case milestone passes, it should not be claimed that temperature-dependent EIS analysis is complete. A more accurate positioning is "a materials-workflow backend with a trustworthy control plane that is separating platform core, domain packages and reference cases".

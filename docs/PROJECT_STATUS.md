# Project status — 2026-10-20

The backend is a usable local workflow prototype; interview preparation is in progress.
The current portfolio evidence is the [offline QE replay](../examples/cases/A1-qe-mgo/README.md),
[routing diagnostic](evaluation/README.md) and [interview preparation guide](INTERVIEW_PREPARATION.zhcn.md).

## Demo acceptance — 2026-10-20 (two rounds)

**Round 1 (offline/reproducibility).** Resumed at 21:13:54 Beijing time. Windows full suite later
reached `504 passed, 9 skipped, 393 subtests` (round 2 added five harness selection tests). QE MgO
replay 3/3 consecutive fresh-archive runs matching frozen values; a genuine fresh clone of the public
remote with an independent `uv sync` environment; review-gate pause/continue; frontend unit tests
(16), build, browser E2E `7/7`. The candidate is pushed on `acceptance/2026-10-20-demo`; the frontend
repository is public with default branch `main` (currently `3df9139`); no freeze tag was created.
Evidence: [round-1 report](acceptance/2026-10-20/REPORT.zhcn.md),
[task assignment](acceptance/2026-10-20/TASK_ASSIGNMENT.zhcn.md).

**Round 2 (online capability and hands-on frontend)**, requested by the user the same night with
Ubuntu explicitly skipped. [Live report](acceptance/2026-10-20-live/REPORT.zhcn.md) and
[operator runbook](acceptance/2026-10-20-live/OPERATOR_RUNBOOK.zhcn.md):

- Chinese live routing: 16 real `/api/route` calls (8 Chinese/mixed prompts x deepseek-chat and
  qwen), no mocks, per-prompt choice/confidence/confirmation/latency recorded; the two models
  disagree on the safety-bypass prompt.
- Multi-model 10-prompt matrix: frozen 6 positive / 2 gap / 2 human, 5 Chinese + 5 English. DeepSeek
  official flash and v4-pro completed 20/20 (10/10 routing labels each). `qwen` degraded to 121.7 s
  per call in this window and is **not scored**; `minimax` is unavailable (HTTP 403). Both are
  recorded, not hidden.
- Frontend functionality and hands-on operation: 17/18 checklist items pass; the one FAIL is that a
  single edge cannot be deleted through the UI. A real browser run of the EIS quality-control workflow
  (import -> build -> parameters -> review pause -> continue -> result -> export/import) and the QE
  replay demo completed, plus an independent Lead rerun.
- One-command live demo: `scripts/start_demo.ps1` / `scripts/start_demo.bat` starts or reuses both
  model gateways, the backend and the WebUI; credentials are read from the Windows User environment
  scope into child processes only.
- Defects fixed in round 2: the decision panel now shows decision source/model/confidence and treats
  candidate scores as compatibility rather than accuracy (frontend `3df9139`); the Jev fallback
  rationale no longer leaks internal urlopen errors (backend `6de8349`).
- Still open: Ubuntu (skipped by the user), the Jev on-path (port 4079 was not running), product
  defects D-03/D-05 and the edge-delete FAIL, 120 s timeout visibility, recording and a frontend E2E
  CI job. The plan is therefore not "fully met" as a whole, while the user-scoped round-2 objectives
  are evidenced.

| Area | Current evidence | Remaining boundary |
|---|---|---|
| Platform contracts | Typed GraphPatch validation, DAG execution, generic join/aggregate and review/gate tests | Single-user local files; no multi-tenant or public-network security |
| Domain extension | DomainPackage manifests, loaders, type composition and executor registration | Structural validation is not a trust boundary; limited tool coverage |
| Model planning | Type-filtered candidates, Jev/LLM selection, no keyword fallback; repeated online smoke on one synthetic request | One request does not establish general accuracy; Jev service was unavailable; expanded on/off evaluation remains open |
| Offline presentation | Explicit `matflow demo qe-mgo --output <new-directory>`, frozen values, input hashes, recorded run and refusal to overwrite; 3/3 consecutive runs re-verified on 2026-10-20 | Pinned historical replay, not LLM planning or a new QE/HPC calculation |
| Reproducibility | Fresh clone of the public remote + independent environment verified on 2026-10-20; pytest declared in the locked dev environment; frontend E2E 7/7 locally | Ubuntu acceptance and a CI job for the frontend E2E remain open |
| Publication | MIT LICENSE; backend candidate pushed on `acceptance/2026-10-20-demo`; frontend repository public with default branch `main` at `8b37ed3`; screenshots committed in both repositories | Candidate is not on the backend default branch; no freeze tag; recording still missing |

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

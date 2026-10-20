# MatFlow design philosophy and implementation architecture

## 1. Project intent

MatFlow targets "vibe research" in materials science: starting from natural language and raw experimental data, the user builds, inspects and evolves a graph-like workflow together with an AI. The value of the system is not a plausible-looking answer; it is turning research intent into inspectable Tools, type-explicit data flows, repeatable Executions and traceable Artifacts.

MatFlow currently uses a backend-authoritative architecture. The WebUI, the MCP bridge, DSH and other AI clients handle interaction and adaptation; the backend exclusively owns Workspace state, validation, execution, audit and persistence semantics.

### 1.1 The three capability layers

- **Platform Core:** domain-neutral Workspace, type graph, DAG, GraphPatch, Tool lifecycle, execution, review and audit.
- **Domain Package:** the data types, Tools, executors, Recipes and domain vocabulary of one class of measurement method, for example EIS, XRD or FTIR.
- **Reference Case:** a concrete research scenario solved with domain packages, for example EBrick temperature-dependent impedance spectroscopy.

A Reference Case can validate Platform Core but cannot define it. The material systems, instrument structure, column names, conversion formulas and analysis methods of a case must not become core contracts that every workspace owns by default.

## 2. Design philosophy

### 2.1 The original intent must not be replaced by an intermediate representation

The Research Request is the authoritative input. The Normalized Request, Task summaries and model messages are all derived views. Any normalization must be auditable and reversible, and must never overwrite the original text.

This principle comes directly from complex Chinese prompt testing: translating a whole prompt into English improved recall for the former English keyword retriever, but it introduced language drift and did not by itself improve plan quality. Keyword retrieval has since been removed: tool candidates are filtered by data type only and the choice is made by a model, so routing no longer depends on the prompt language.

### 2.2 Build a trustworthy control plane before extending scientific capability

A natural-language model may propose a plan, a Tool Recipe Proposal or a Graph Patch, but only the backend can:

- decide whether a Tool really exists and is in an executable state;
- decide whether two port types may be connected;
- decide whether the Workflow is still a DAG;
- decide whether a submission is based on the current graph version;
- write to the Workspace and start an Execution.

The model is therefore the proposer and the backend is the authoritative executor.

### 2.3 A Workflow is a DAG, not a single chain by default

Real research tasks usually need parallel diagnostics, result joins and quality gates. The standard shape of a Workflow is a typed DAG; a linear pipeline is only a special case of one.

The execution engine schedules Nodes as their dependencies are satisfied. Later domain Tools should explicitly support fan-out, join, aggregate and quality conditions instead of hiding that logic inside one large Prompt.

### 2.4 Tool and Node are strictly separate

A Tool is a reusable, versioned capability with types and an execution reference; a Node is one configuration of a Tool inside a particular Workflow. A draft produced by an AI is not a Tool; it becomes one only after evaluation, review and publication to the Registry.

This distinction prevents "the model wrote some JSON" from being misreported as "the system has gained a new capability".

### 2.5 Generated capability must pass an isolated lifecycle

The target lifecycle is:

```text
Capability Gap
    -> Tool Recipe Proposal
    -> contract validation
    -> hidden-fixture evaluation
    -> bounded repair
    -> human review
    -> publish as a versioned Tool
    -> instantiate as a Node in a Workflow
    -> execution and continuous audit
```

Drafts, declarative contracts, hidden-fixture evaluation and bounded repair are implemented today; the general review/publication interface and isolated execution of arbitrary code still belong to the next stage.

### 2.6 Raw data stays on the local execution plane by default

The design goal is to keep raw data processing, numerical analysis and Workspace state on this machine; external LLMs are used mainly for planning, retrieval, contract construction and explanation. If an AI Skill Node needs a data fragment, it must receive a minimal, controlled and auditable input rather than the complete raw data by default.

The backend is already a local single-workspace service, but the policy of "expose only the minimum data to the model" still needs a stricter technical gate and must not rely on the Prompt alone.

### 2.7 Scientific conclusions must carry evidence and a failure state

The system should prefer "cannot be determined, needs review or needs a re-measurement" over manufacturing a complete answer. A Route Decision may select no Tool; an Execution may fail; a Review Gate may stop downstream work; without a reference library only peak extraction is allowed, and a phase conclusion must not be fabricated.

### 2.8 The frontend is not a precondition for backend correctness

Backend capability is verified through HTTP contracts and automated scenarios. The frontend is for interaction acceptance and must not become the only test channel for routing, Tool construction, GraphPatch or Execution.

## 3. Architecture overview

```text
 WebUI / MCP bridge / DSH / other AI client
                    |
          versioned matflow-http v1
                    v
 +--------------------------------------------------------+
 | FastAPI transport adapter                              |
 | authentication-free local HTTP, trace correlation      |
 +---------------------------+----------------------------+
                             |
                             v
 +--------------------------------------------------------+
 | WorkspaceRuntime                                        |
 | authoritative interface for state, data, graph, run     |
 +----------+------------+-------------+-------------------+
            |            |             |
            v            v             v
   ToolRegistry    DataTypeRegistry   GraphValidator
            \            |             /
             \           v            /
              +---- typed GraphPatch -+
                             |
                             v
                   DAG execution + review
                             |
                   preview / task summary / audit
                             |
                             v
     one save folder: data/saves/<name>/
     (graph state, settings, uploads, task log)

 Optional decision and construction adapters:
 Prompt normalizer CLI -> OpenAI-compatible LLM
 WorkflowPlanner -> LLM decomposition -> per-action routing -> typed edges
 CandidateRetriever (type filter) -> Jev consensus, else LLM selection
 Runtime agent / Skill Node -> LiteLLM gateway (config/llm.json)
 RecipeEvaluator -> hidden fixtures + bounded repair
```

`WorkspaceRuntime` is the most important deep module: a caller only has to learn one relatively concentrated interface to use state, upload, validation, routing, execution and review behavior, while persistence, locking, type rules and audit stay inside its implementation, so HTTP, MCP and tests do not each develop their own semantics.

## 4. Core modules

| Module | Responsibility | Current state |
| --- | --- | --- |
| `backend/contracts.py` | Defines the transport-safe contracts for Tool, Node, Edge, GraphPatch, Route Decision and Execution | Implemented |
| `backend/workspace_runtime.py` | Authoritative Workspace interface; concentrates state, upload, graph changes, execution, review and proposals | Implemented, still expanding |
| `backend/data_types.py` | Data type graph, C3 inheritance, port flow compatibility | Implemented |
| `backend/tool_registry.py` | Versioned Tool lifecycle and the active view | Base capability implemented |
| `backend/validator.py` | Version, topology, port and operation validation of a GraphPatch | Implemented |
| `backend/routing.py` | Type-filtered candidates and an auditable Route Decision made by Jev or, when Jev is unreachable, by the LLM; no keyword matching | Implemented; needs a live model |
| `backend/planner.py` | `POST /api/plan`: LLM action decomposition, per-action routing, typed port binding, parameter binding with a provenance check, validated GraphPatch | Implemented (Alpha); slow and varies between runs |
| `backend/llm_config.py` | Single LLM gateway description (`config/llm.json`): host, port, key variable, served models, agent and planner models | Implemented |
| `backend/saves.py` | One-save-one-folder data layout under `data/saves/<name>/` | Implemented |
| `backend/jev_routing.py` | Multi-model selection, consensus, calibration and safe degradation | Implemented; online regression must be enabled explicitly |
| `backend/analysis_recipes.py` | Measurement-method-neutral declarative signal Recipe contract and interpreter | Implemented with a restricted allow-list; concrete Recipes and method Tools are owned by the XRD/FTIR packages |
| `backend/node_evolution.py` | Tool/Node revision proposals and edge migration plans | Implemented for a restricted path |
| `backend/prompt_normalizer.py` | Structural normalization that preserves the original text | Implemented as a standalone CLI, not wired into the main flow |
| `backend/preview.py` | Bounded preview of untrusted output | Implemented |
| `backend/task_summary.py` | User-readable, auditable Task lifecycle summary | Implemented |
| `backend/observability.py` | Trace correlation and structured audit | Base capability implemented |
| `backend/main.py` | HTTP adapter, runtime agent adapter and compatibility endpoints | Implemented; still needs slimming |

The in-repo read-only diagnostic tool `flowview/` is **not** a core module: it is excluded from the wheel, is not depended on by the backend, and prints the backend flow read-only (Mermaid/tables/JSON). Its contract is [`../flowview/CONTRACT.md`](../flowview/CONTRACT.md) and it is consistent with the module boundary rules in this document (see [architecture and developer rules](ARCHITECTURE_AND_DEVELOPER_RULES.md) § Authority boundary).

## 5. Key runtime flows

### 5.1 The deterministic Workflow path

```text
client reads the Workspace version
  -> submits a GraphPatch
  -> GraphValidator checks version, types, ports, DAG
  -> atomic apply and version increment
  -> executor schedules Nodes whose dependencies are complete
  -> produces Artifact and Preview
  -> pauses at a Review Gate
  -> human continue / revise / stop
  -> records Task Summary and trace
```

This is the most mature path today.

### 5.2 The AI-assisted path

```text
Research Request + Dataset references
  -> optional Normalized Request (derived view)
  -> LLM decomposition into action units (POST /api/plan)
  -> per action: type-filtered candidates -> Jev decision, else LLM
  -> inspect Dataset / read Workspace
  -> propose a GraphPatch or Tool Recipe Proposal
  -> backend validation
  -> execute, or wait for evaluation and review
```

`/api/plan` returns a validated plan (`planned`, `needs_confirmation`, `clarify`, `refused` or `failed`) and applies it only when it is complete and the caller asks. `/api/chat` can currently run a round-limited model tool-calling loop and returns `completed`, `waiting_for_confirmation` or `failed`; it has no keyword pre-gate, and the agent calls `ask_user` to stop and ask. However, online model quality and complex Chinese planning have not passed general acceptance, so this path remains Alpha; the full EBrick flow is a separate Reference Case acceptance.

### 5.3 The prompt normalization path

Keeping two tracks is recommended:

```text
Research Request -------------------------------> audit and final authority
       |
       +-> Normalized Request ------------------> planning prompt
       |
```

The planner receives both the original text and the derived views. When normalization fails, drifts in language, or loses a path, number, unit, negation or gate condition, the system falls back to the original text. Short, unambiguous requests may skip normalization.

## 6. Persistence, consistency and security boundaries

- `GraphState.version` is the basis for concurrency control; a stale GraphPatch returns a deterministic conflict.
- State and configuration use atomic file replacement, serialized by a backend write lock within the current process.
- Uploaded files use backend-generated identifiers, the file name is reduced to its basename, and extensions plus a 25 MB size limit are enforced.
- A Tool must be `active` and have an `executor_ref` in order to execute.
- A generated Tool must record its reviewer before activation; a draft Recipe does not enter the active Registry.
- Model keys come from environment variables and are never returned by an interface or a Task Summary.
- This is a local single-user, single-workspace system; it must not be exposed directly to the public internet and has no tenant isolation.

## 7. Current capability boundaries

Platform Core can already reliably:

- import and inspect tabular Datasets;
- validate, apply and resolve version conflicts for typed GraphPatches;
- schedule a DAG by dependency and support human Review Gates;
- propose Tool/Node revisions, previews, Task Summaries and audit;
- run offline, configuration-driven scenario tests.

The repository also carries the following reference domain capabilities, each owned by its Domain Package:

- EIS column mapping, basic validity statistics and Nyquist data generation;
- XRD peak extraction/reference matching and FTIR peak extraction/band assignment Tools, plus hidden-fixture evaluation and bounded repair.

Platform Core cannot yet claim:

- reliable multi-branch Workflow planning for arbitrary complex Chinese requests;
- structured reading of Markdown or natural-language experimental rule documents;
- safe execution and one-click publication of generically generated code;
- data-driven automatic quality branching;
- general research retrieval and source-evidence management;
- multi-user support, permissions, database transactions and remote-deployment security.

Capabilities not yet complete in the EIS Domain Package or the EBrick Reference Case include KK/Lin-KK, complex equivalent-circuit selection, DRT, quantitative mechanism contributions and the case-specific time–temperature mapping. Those gaps are not a feature list for Platform Core.

## 8. EBrick Reference Case (not platform architecture)

EBrick temperature-dependent impedance spectroscopy serves as a longitudinal case for validating the platform extension mechanism:

```text
                            +-- furnace-program document parsing --+
upload and input checks --+-- scan parsing +                        +-- time/temperature mapping -- Cp/G->Z -- temperature grouping
                          +-- metadata and units -------------------+                                    |
                                                                                                       +-- integrity diagnostics --+
                                                                                                       +-- KK/Lin-KK --------------+-- quality summary -- Gate
                                                                                                       +-- multi-circuit fit ------+                      |
                                                                                                                                   +-- fail: localisation / re-measure advice
                                                                                                                                   +-- pass --+-- DRT
                                                                                                                                              +-- component contributions
                                                                                                                                              +-- charts / report
```

The case exercises document parsing, a parallel DAG, result joins, quality gating and the domain Tool lifecycle. The physical-quantity conversions, diagnostic methods and scientific report in the diagram belong to the EIS Domain Package or the EBrick Reference Case; only the DAG, join, gating and lifecycle mechanisms belong to Platform Core.

## 9. Architecture evolution order

Platform Core should advance in this order:

1. Define the Domain Package manifest plus the load boundaries for types, Tools, Recipes and executors;
2. Add controlled text/Markdown reading and a structured document Artifact to Dataset inspection;
3. Wire the Normalized Request into the Task as derived fields, adding constraint-fidelity checks;
4. Add generic join/quality-report/conditional-gate semantics;
5. Complete the evaluation, review and publication HTTP interface for Tool Recipe Proposals;
6. Only when a declarative Recipe cannot express something, attach a network-isolated, resource-bounded code execution adapter;
7. Separate platform contract tests from Domain Package acceptance tests.

Cp/G conversion, temperature mapping, diagnostic Tools and non-linear case acceptance should then be implemented in a separate EIS Domain Package and EBrick Reference Case. A case implementation must not add default scientific types or method branches back into Platform Core.

## 10. Documentation and code consistency rules

- A design goal must be explicitly marked as a "goal" and must not be written as an existing capability;
- When public behavior is added, update the HTTP contract, the tests and the capability boundaries in this document together;
- Domain vocabulary follows the root `CONTEXT.md`;
- Documentation must state whether a capability belongs to Platform Core, a Domain Package or a Reference Case;
- Historical evaluation reports are snapshots from their time and cannot substitute for the current tests and code;
- Backend changes run at least the complete offline test suite; online model tests must be explicitly authorized and recorded separately.

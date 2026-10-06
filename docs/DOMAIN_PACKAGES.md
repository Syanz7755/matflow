# Domain Package Contract

**Status:** implemented at the P0 boundary; this document is the reference for the
Platform Core / Domain Package / Reference Case split.
**Verification:** acceptance entry points are `tests/test_domain_packages.py`,
`tests/test_analysis_recipes.py`, and `tests/test_qe_package.py`.

## 1. Why the boundary exists

MatFlow distinguishes three layers, and the words are fixed in the root `CONTEXT.md`:

| Layer | Owns | Must not own |
| --- | --- | --- |
| **Platform Core** | Typed workflows, Tool lifecycle, execution, review, audit, generic control semantics | Any measurement-method or material-system semantics |
| **Domain Package** | Scientific data types, Tools, executors, declarative recipes, its recipe-domain vocabulary, legacy Tool-ID migrations | Platform state, scheduling, validation or transport |
| **Reference Case** | A concrete research scenario used to accept Core + packages | Platform capabilities |

Before this boundary existed, `EISData`, `EISQCReport`, `eis_basic_qc`, `plot_nyquist`,
`human_decision` and the XRD/FTIR reference recipes were compiled into Core. They are now
package content, and a workspace that composes no package exposes none of them.

## 2. The minimum package contract

A package is a `DomainPackage` (`backend/domain_packages/__init__.py`) with a manifest and
five optional registrations:

```python
DomainPackage(
    manifest=DomainPackageManifest(
        package_id="eis",            # ^[a-z][a-z0-9_]*$
        version="1.0.0",             # ^\d+\.\d+\.\d+$
        label="…", description="…",
        core_contract="1.0",         # required Platform Core contract version
        requires=(),                  # other packages needed by this extension
        acceptance_tests=("tests/test_domain_packages.py",),
    ),
    data_types={"EISData": DataTypeDefinition(...)},
    tool_specs={"eis_basic_qc": ToolSpec(..., executor_ref="builtin:eis_basic_qc")},
    recipes={},                      # declarative AnalysisRecipe objects, optional
    recipe_domains=(),               # domain names this package owns
    migrations={"human_decision": "review_policy"},
    register_executors=lambda registry: registry.register("builtin:eis_basic_qc", eis_basic_qc),
)
```

Loading rules (`DomainPackageLoader` / `DomainPackageSet`), all fail-closed:

- an unknown `package_id` is rejected;
- a package whose `core_contract` differs from the running `CORE_CONTRACT_VERSION` is rejected;
- a package cannot redeclare another package's data type, tool id, recipe id, legacy tool id or
  recipe domain;
- a package cannot redeclare a platform tool id (`ToolRegistry(package_specs=...)`);
- a workspace custom type cannot replace a package type (`compose_type_registry`);
- a recipe whose `domain` no loaded package owns is rejected at proposal time
  (`WorkspaceRuntime.propose_analysis_recipe`).

**Package form.** The first implementation is an in-repository plugin
(`backend/domain_packages/<id>.py` with a `build_package()` factory), because it keeps the
contract reviewable in the same test run. Independent distributions are supported without a
Core change: advertise a factory under the `matflow.domain_packages` entry-point group, and
`DomainPackageLoader.discover_installed()` will load it. This was an explicitly unresolved
decision in `OPEN_ISSUES.md`; it is recorded here as the reversible first choice.

## 3. The executor seam

`backend/executors.py` owns the single dispatch point:

- `ExecutorRegistry.resolve(executor_ref)` — exact match first, then the longest registered
  prefix. `recipe:` is registered as a prefix because a declarative recipe Tool is created per
  proposal and its ref cannot be enumerated in advance.
- `NodeExecution(runtime, state, node, spec)` — the bounded context an executor receives.
  `ExecutorHost` (the protocol) exposes only `model_adapter_configured`, `complete_with_model`,
  `node_input`, `node_inputs`, `dataset_frame`, `inspect_dataset`, `data_type_registry`.
- `ExecutionOutcome(output, stop)` — an executor may request that downstream work stop. This is
  how a data-driven gate halts a branch without Core evaluating `if domain == …`.

`WorkspaceRuntime._run_node` contains no domain branch: it resolves the validated `ToolSpec`'s
`executor_ref`, runs it, builds the preview and applies `review_policy.after_run`.

## 4. Generic control semantics

These four platform Tools carry no scientific vocabulary and are reusable by any package:

| Tool | Ports | Semantics |
| --- | --- | --- |
| `join` | `items: Artifact` (**multi-input**) → `combined: Artifact` | Collects every connected artifact, in edge order, with its source node ids |
| `aggregate` | `items: Artifact` (**multi-input**) → `summary: Artifact` | Summarizes same-named numeric fields (nested objects are flattened; lists are not) |
| `quality_report` | `data: Artifact` → `report: QualityReport` | Evaluates declared `required_keys` and an optional `metric_key` range; **declaring no check fails closed** |
| `conditional_gate` | `data: Artifact`, `report: QualityReport` → `data: Artifact` | Passes the artifact through while the report passes, recording `gate` and `decision` inside the passed payload; a failing report ends the run with the gate node `cancelled` and `execute_workflow` reporting `stopped: true` |

`ToolSpec.multi_input` lists the input ports that accept more than one incoming edge. Every other
input port keeps the single-occupancy rule, which is still enforced by `GraphValidator` and
covered by a test. A port declared multi-input must be read through `node_inputs`; the single-input
accessor refuses a port that carries several edges instead of silently using the first one.

`ToolSpec.open_params` marks a Tool whose parameter *keys* are user data rather than a declared
vocabulary. The platform column-mapping Tool is the reference case, so Core never spells out a
measurement column name; the executor still fails closed because every mapped name must exist in
the uploaded file.

Boundary guard rails, each with a test: a custom node cannot shadow a platform or package tool id;
a hand-built `ExecutorRegistry` cannot claim the `builtin:`, `custom:` or `recipe:` namespace; a
package cannot redeclare a platform tool, another package's data type, recipe id, legacy tool id or
recipe domain; a custom type cannot replace a package type; and a package whose Tool declares a port
type it does not contribute fails with an error that names the package.

The reuse evidence is `tests/test_generic_control_nodes.py`: the same four nodes run over a plain
cast artifact and over an `EISQCReport` produced by the EIS package. That composition works
because the EIS package declares `EISQCReport(parents=["Artifact"])` — the package, not Core,
decides that its report is an artifact.

## 5. Bundled packages

| Package | Contributes | Notes |
| --- | --- | --- |
| `eis` | `EISData`, `EISQCReport` (child of `Artifact`), `eis_basic_qc`, `plot_nyquist`, legacy `human_decision`, executors, the `review_policy` migration for `human_decision` | Formerly hardcoded in Core |
| `xrd` | `XRDPeaks`, `xrd_peak_extraction`, `xrd_reference_match`, XRD recipe domain and reference recipes | Tools are selectable; reference recipes remain hidden evaluation assets |
| `ftir` | `FTIRPeaks`, `ftir_peak_extraction`, `ftir_band_assignment`, FTIR recipe domain and reference recipe | Tools are selectable; the reference recipe remains a hidden evaluation asset |
| `qe` | QE data types, structure validation, `pw.x` input generation and output parsing | Does not execute QE or submit Slurm jobs |
| `qe_demo` | Archived QE stdout fixture source | Depends on `qe`; non-selectable and used only by the historical replay demo |

The shipped application enables `eis`, `xrd`, `ftir`, `qe`, and `qe_demo`.
`qe_demo` declares that it requires `qe`. `MATFLOW_DOMAIN_PACKAGES` overrides the composition,
including to an empty value for a domain-free Core; tests use the same reference composition.

A **Domain Package** is a loadable extension and lifecycle boundary. It can contribute multiple
atomic Tools or declarative recipes. A **Tool** is the atomic executable capability selected for a
workflow node. XRD and FTIR are separate packages because they own independent method vocabularies.
`ToolSpec.agent_selectable=False` keeps demo or infrastructure nodes executable in validated
workflows while excluding them from natural-language Router candidates.

## 6. How to verify

```powershell
Set-Location D:\Projects\matflow
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe -m unittest tests.test_domain_packages tests.test_generic_control_nodes -v
```

Empty-Core evidence lives in `tests/test_domain_packages.py::EmptyCoreTests`; package-restores-
capability evidence in `LoadedPackageTests`; the manifest/loader rules in `ManifestContractTests`
and `RecipeDomainOwnershipTests`.

## 7. Known gaps after this change

- Per-method reviewed recipes are evaluation assets, not currently published as selectable Tools.
  The recipe engine exposes generic recipe execution but does not yet materialize each recipe as
  an independent Tool.
- QE replay uses a historical fixture, not a calculation. Real QE/Slurm execution remains absent.
- `aggregate` summarizes same-named numeric fields from nested objects only. List-valued
  payloads are intentionally not flattened, so a per-row summary needs a dedicated package Tool.
- Packages are validated structurally, not signed: `core_contract` is a version gate, not a
  trust boundary. Tool publication, withdrawal, sandboxing and resource limits (MF-008) remain
  outstanding.
- Executor registration is eager during workspace construction and has no rollback, so one
  conflicting package aborts construction entirely. Fail-closed, but coarse (MF-008 covers the
  policy work).

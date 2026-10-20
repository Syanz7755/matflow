# MatFlow Open Issues

## Portfolio update — 2026-10-19

- Local MIT licensing is now present; MF-010's earlier statement that the backend lacks a LICENSE is superseded. Cross-repository publication remains pending.
- The [routing diagnostic](../evaluation/README.md) records three repeats on one synthetic request; it does not close MF-006 or MF-020. Jev on/off comparison is still open.
- The [explicit offline replay](../../examples/cases/A1-qe-mgo/README.md) provides a key-free demonstration. Full EBrick EIS integration, frontend acceptance and DSH comparison remain open.
- The dated tables below are retained as historical maintenance context. Current feature status is in [Project status](../PROJECT_STATUS.md).

**Updated:** 2026-10-07, after removing keyword routing and adding the prompt -> workflow planner.

## Closed in the P0 boundary pass

| ID | Issue | Closure evidence |
| --- | --- | --- |
| MF-001 | Core was contaminated with EIS/XRD/FTIR semantics | `contracts.DATA_TYPES` and `tool_registry.builtin_specs()` are domain-neutral; method content lives in separate Domain Packages; `tests/test_domain_packages.py::EmptyCoreTests` fails if any of it returns to Core |
| MF-002 | Domain execution logic had duplicate paths | The dead compatibility cluster in `backend/main.py` (`run_node_in_state`, `run_skill_node`, `node_input`, `inspect_upload`, `dataframe_for_upload`, `load`/`save`, `registry()`, `validate_patch`/`apply_patch`/`standard_node`) was verified unreachable and deleted; `POST /api/execute` reaches `WorkspaceRuntime.execute_node` only |
| MF-003 | Domain Package was only a concept | `DomainPackageManifest`, `DomainPackage`, `DomainPackageSet`, `DomainPackageLoader` and `ExecutorRegistry` exist, with the contract documented in `docs/DOMAIN_PACKAGES.md` and acceptance tests in `tests/test_domain_packages.py` |
| MF-004 | Generic join, quality report and conditional gate were missing | `join`, `aggregate` (multi-input through `ToolSpec.multi_input`), `quality_report` and `conditional_gate` (cancels downstream through `ExecutionOutcome.stop`) are platform Tools, reused over a plain artifact and an EIS artifact in `tests/test_generic_control_nodes.py` |
| MF-005 | The backend workspace contained uncommitted documentation changes | Recorded in `CURRENT_STATE.md` §3 and §6: HEAD `696b607`, branch ahead by 6, the 21 modified Markdown files, the untracked handoff directory, and the frozen regression baseline. One real defect was found and fixed on the way: `scripts/start_model_services.ps1` lost its readiness probe whenever its output was captured |
| MF-013 | Recipe results in Core used XRD-specific result keys | `backend/analysis_recipes.py` now emits `best_match`, `match_scores`, and `matched_count` from `match_reference_values`; the evaluator uses generic criteria names |
| MF-014 | XRD and FTIR shared one package despite independent method boundaries | `backend/domain_packages/xrd.py` and `ftir.py` own separate recipe domains and recipes; package validation enforces ownership |
| MF-017 | QE replay fixture was published as a selectable scientific capability | The fixture moved to `qe_demo`, requires `qe`, and is excluded from Router candidates by `ToolSpec.agent_selectable=False` |
| MF-016 | `backend/main.py` kept a second settings read/write path | `main.py` reads and writes settings only through `workspace.read_settings()` / `write_settings()`; the prompt normalizer resolves the open save through `backend/saves.py`; one save is one folder under `data/saves/` |

## Live issues

| ID | Priority | Issue | Current Evidence | Closure Criteria |
| --- | --- | --- | --- | --- |
| MF-006 | P1 | Multi-branch planning from long and Chinese requests is not yet reliable enough to run unattended | Keyword retrieval was removed (2026-10-07): `POST /api/plan` decomposes with the LLM, routes each action by Jev or the LLM over type-compatible candidates, connects typed edges and keeps only parameters the request states. The live suite `tests/test_prompt_to_workflow_online.py` passed 16/16 long prompts in its last run on 2026-10-07 (the previous run passed 15/16, failing on MF-019); results vary between runs (MF-020) | Repeated live runs pass every case of `tests/suites/prompt_to_workflow.json`, and every `planned` workflow executes on its fixture |
| MF-007 | P1 | Prompt normalizer is not yet integrated into the formal Task chain | A standalone script and five tests exist, but the runtime does not consume it generally | A Task stores the original text, derived structure, and fidelity diff together; failures automatically fall back to the original |
| MF-008 | P1 | Tool publication and arbitrary-code isolation are incomplete | The declarative Recipe lifecycle works; general code execution is incomplete. Domain Packages are validated structurally, not signed, so `core_contract` is a version gate rather than a trust boundary | Review, publication, withdrawal, sandboxing, resource limits, and audit all have contract tests |
| MF-009 | P1 | The current state model supports only a single local-file workspace | There is no multi-project database, tenancy, or permission isolation | Establish explicit requirements and an ADR before adding a Project/Run Store; do not rewrite prematurely while the Core boundary is unstable |
| MF-010 | P1 | Repository licensing entry points are incomplete | The frontend workspace package declares ISC, but no unified root LICENSE was found in either repository | Both repositories have explicit LICENSE/NOTICE files; any GPL-derived frontend is physically isolated with provenance recorded |
| MF-011 | P2 | Jev-like fine-tuning lacks a real training-data loop | A configurable decision model and logs exist, but there is no stable labeled dataset | Accumulate and version `(state, candidates, model choice, final choice)`; train only after a baseline outperforms the current rules |
| MF-012 | P2 | Security for public-network, multi-user, and remote execution is undefined | The current system is loopback-only and single-user | After the product truly requires these capabilities, separately design identity, permissions, secrets, quotas, and a remote-execution threat model |
| MF-015 | P1 | The backend test suite is not hermetic | An independent review could not isolate some new tests in a copied tree because `tests/test_contracts.py` exercises the live `backend.main` workspace and reads state relative to the working directory; several suites also rely on the repository's `data/` path | Every test module builds its own workspace under a temporary root (or an explicit `MATFLOW_DATA_ROOT`), so a copied tree behaves identically |
| MF-018 | P2 | The repo-local FlowView tool is committed but not covered by CI, and one documented gap remains | Committed on 2026-10-06 together with `examples/long_prompt_cases.json`; no `.github/` workflow exists and its 252-test suite is run by hand; `doctor --format mermaid` prints the text report | The 252-test suite runs in CI, and `doctor --format mermaid` emits a real diagram (or the format is explicitly unsupported by that subcommand) |
| MF-019 | P1 | EIS spectra cannot pass through generic control nodes | `EISData` has no `Artifact` parent, while `conditional_gate`, `join` and `aggregate` carry `Artifact`; a plan such as 'QC, gate on the report, then plot' therefore leaves the plot without a type-compatible tool (seen in the 2026-10-07 live run of `long_eis_01_full_context`) | Decide whether `EISData` inherits `Artifact` (as every other domain type does) or the gate becomes type-preserving, and a gated EIS plot plans and runs |
| MF-020 | P2 | Live planning is slow and varies between runs | A long prompt takes 5-10 LLM calls and 80-300 s with four cases in parallel on the SJTU gateway (deepseek-chat); the same prompt can end as `planned`, `needs_confirmation` or `clarify` on different runs; Jev (port 4079) was not running, so every route came from the LLM | Repeat-run statistics per case are recorded, and latency is measured with Jev enabled |

## Unresolved Decisions

- Whether a generic Gate is exposed through review policy, a control node, or a Runtime conditional edge. The P0 pass chose a control node plus `review_policy.after_run` for human gates, and documented it in `docs/DOMAIN_PACKAGES.md`; a Runtime-level conditional edge remains open.
- Whether multi-project state remains file-based or introduces a database and event log.
- The final license for the independently implemented UI, and whether to create a separate GPL-ComfyUI-derived client.
- Whether MatFlow and `synsimul2` follow a platform-plus-domain-package relationship or integrate only loosely through files/APIs.

**Settled in this pass:** a Domain Package is an in-repository plugin first, while independent
distributions are supported through the `matflow.domain_packages` entry-point group; the decision
and its consequences are recorded in `docs/DOMAIN_PACKAGES.md` §2 rather than only here.

These decisions affect long-term compatibility. Create an ADR only when a choice is difficult to reverse, presents a real tradeoff, and future readers are likely to ask why it was made. Do not turn a conversation conclusion into an established fact.

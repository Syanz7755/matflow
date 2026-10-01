# MatFlow Open Issues

**Updated:** 2026-10-02

| ID | Priority | Issue | Current Evidence | Closure Criteria |
| --- | --- | --- | --- | --- |
| MF-001 | P0 | Core is contaminated with EIS/XRD/FTIR semantics | `DATA_TYPES`, built-in Tools, executors, and Recipes all contain domain hardcoding | An empty Core exposes no scientific-domain types; the corresponding capabilities appear only after a package is loaded |
| MF-002 | P0 | Domain execution logic has duplicate paths | Both compatibility execution in `main.py` and `WorkspaceRuntime` contain EIS branches | The HTTP layer calls a single Runtime; domain execution is resolved through a registry |
| MF-003 | P0 | Domain Package is only a concept and lacks a complete loading contract | The three-layer boundary is documented, but the code has no stable manifest/loader | Types, Tools, Recipes, and executors can be independently registered and unloaded by a versioned package |
| MF-004 | P0 | Generic join, quality report, and conditional gate are missing | The current DAG supports parallelism, but case-specific quality gates still require domain-level assembly | A generic gate containing no EIS terminology is reused by two different domain packages |
| MF-005 | P0 | The backend workspace contains uncommitted documentation changes | The 2026-10-02 baseline showed the branch ahead by 4 commits with dirty documentation | Existing changes are separately reviewed, committed, or explicitly archived; the worktree state is explainable |
| MF-006 | P1 | Retrieval and multi-branch planning are unreliable for complex Chinese requests | The original Chinese text often yields no candidates; whole-prompt translation improves only English lexical recall | Preserve the original text; derive a separate multilingual retrieval query; fixed Chinese cases consistently generate the expected topology |
| MF-007 | P1 | Prompt normalizer is not yet integrated into the formal Task chain | A standalone script and five tests exist, but the runtime does not consume it generally | A Task stores the original text, derived structure, and fidelity diff together; failures automatically fall back to the original |
| MF-008 | P1 | Tool publication and arbitrary-code isolation are incomplete | The declarative Recipe lifecycle works; general code execution is incomplete | Review, publication, withdrawal, sandboxing, resource limits, and audit all have contract tests |
| MF-009 | P1 | The current state model supports only a single local-file workspace | There is no multi-project database, tenancy, or permission isolation | Establish explicit requirements and an ADR before adding a Project/Run Store; do not rewrite prematurely while the Core boundary is unstable |
| MF-010 | P1 | Repository licensing entry points are incomplete | The frontend workspace package declares ISC, but no unified root LICENSE was found in either repository | Both repositories have explicit LICENSE/NOTICE files; any GPL-derived frontend is physically isolated with provenance recorded |
| MF-011 | P2 | Jev-like fine-tuning lacks a real training-data loop | A configurable decision model and logs exist, but there is no stable labeled dataset | Accumulate and version `(state, candidates, model choice, final choice)`; train only after a baseline outperforms the current rules |
| MF-012 | P2 | Security for public-network, multi-user, and remote execution is undefined | The current system is loopback-only and single-user | After the product truly requires these capabilities, separately design identity, permissions, secrets, quotas, and a remote-execution threat model |

## Unresolved Decisions

- Whether a Domain Package is an in-repository plugin, an independent Python package, or supports both forms;
- Whether a generic Gate is represented as a Tool, a control node, or a Runtime conditional edge;
- Whether multi-project state remains file-based or introduces a database and event log;
- The final license for the independently implemented UI, and whether to create a separate GPL-ComfyUI-derived client;
- Whether MatFlow and `synsimul2` follow a platform-plus-domain-package relationship or integrate only loosely through files/APIs.

These decisions affect long-term compatibility. Create an ADR only when a choice is difficult to reverse, presents a real tradeoff, and future readers are likely to ask why it was made. Do not turn a conversation conclusion into an established fact.

# EBrick case 05 MatFlow evaluation

This folder freezes a prompt, hidden tool-node definitions, a ten-node portable workflow, and the pre-run expected result for an end-to-end MatFlow evaluation.

Scope: this is an EBrick Reference Case. Generic planning, DAG, review, and audit observations may inform Platform Core; Cp/G conversion, impedance types, thresholds, furnace metadata, and scientific expectations belong to an EIS Domain Package or this case and must not become default core behavior.

Recorded artifacts:

- `prompt.txt`: the exact prompt submitted to the router.
- `hidden_tool_nodes.json`: reviewed node aliases prepared before the router was allowed to see them.
- `workflow.matflow.json`: the portable ten-node workflow.
- `expected.json`: the expectation frozen before routing or execution.
- `actual.json`: the captured route, workflow, review, and scientific-check outcomes.
- `comparison-and-next-steps.md`: the Chinese expected-versus-actual assessment and prioritized changes.

Order of operations:

1. Create `hidden_tool_nodes.json`, `workflow.matflow.json`, `prompt.txt`, and `expected.json` without submitting them to the router.
2. Freeze the expectation using `data-raw` plus the existing independent `analysis/config01/results/05` report.
3. Publish the reviewed aliases to the local registry without copying their IDs or definitions into the user prompt.
4. Route `prompt.txt` with `RawData` available.
5. Import and save `workflow.matflow.json`, run from the start, approve the final structural-review gate, and capture the actual server state.
6. Compare actual behavior with `expected.json` and record improvement actions.

The aliases deliberately reuse bounded built-in executors. This makes the orchestration test executable while preserving an explicit negative scientific control: Cp and G must not be treated as the real and imaginary components of impedance.

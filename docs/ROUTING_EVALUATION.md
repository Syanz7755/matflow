# Routing evaluation (online, model-based)

The default test suite proves the deterministic shell: type filtering, graph validation, contracts. It cannot say how good the *model* part of routing is. This document describes a reproducible online evaluation of that part and how to read its numbers.

Script: `examples/evaluate_routing_online.py` - reports: `examples/reports/routing_online_evaluation.{json,md}` - tests: `tests/test_routing_online_eval.py`.

## What is measured

The script drives the production planning path, not a lookalike:

```
prompt (+ uploaded fixture files)
  -> WorkspaceRuntime.plan_workflow          (the entry behind POST /api/plan)
     -> LLM decomposition into action units  (WorkflowPlanner)
     -> per action: CandidateRetriever (type filter) -> ToolSelector
          Jev gateway when enabled and answering, else LLMToolSelector
     -> typed edges
```

against the **shipped reference tool catalogue** (`tests/reference_composition.registry()`: platform tools plus the EIS, XRD, FTIR and QE packages). The model under test serves *every* LLM call of the plan (decomposition, routing, parameter binding), exactly as `planner_model` does in production, with the same endpoint and temperature (0.2). Nothing is keyword-routed; there is no lexical fallback to measure.

Because the catalogue only contains EIS, XRD, FTIR and QE capabilities, most teaching-lab prompts (UV-Vis, TGA, DSC, tensile, ...) ask for something the platform does not have. For those the **correct answer is a capability gap** (router returns `null`) and a generic `skill_node` standing in for the computation counts as a miss. This makes "correct gap" as important as "correct tool" and is why the class balance below is skewed toward gaps.

## Gold labels and their provenance

Gold labels are *derived*, not newly invented, from files already in the repository:

| Source | Cases | Gold derived from |
|---|---|---|
| `tests/suites/teaching_lab_prompt_suite.json` (15 scenarios x 4 styles + 4 cross-cutting) | 64 | scenario `registry_target_id`; present in the shipped catalogue -> that tool; target served by a shipped pipeline (`xrd_phase_identification` -> `xrd_peak_extraction` + `xrd_reference_match`, `ftir_functional_group_assignment` -> `ftir_peak_extraction` + `ftir_band_assignment`) -> that pipeline; otherwise **gap**. A scenario missing from `teaching_lab_expected_results.json` would be excluded. Cross-cutting `human_confirmation` cases expect escalation. |
| `tests/suites/prompt_stability_suite.json` | 23 (3 safety) | `expected_registered_id` mapped the same way; `safety` level -> escalation |
| `tests/suites/long_prompt_cases.json` + `tests/suites/prompt_to_workflow.json` | 16 | the suite's own `required_tools`, `forbidden_tools` (fnmatch) and allowed plan statuses; no required tools + `clarify`/`refused` only -> escalation, otherwise gap |
| `evaluate_jev_routing.CASES` (5 known-answer prompts) | 5 | `expected_tool`, mapped the same way |

Exact duplicate (prompt, fixtures) pairs are removed; cases without a derivable gold label are excluded and counted in the report (`dataset.excluded_count`). Forbidden tools for a case are `skill_node` plus every tool of a family (EIS, XRD, FTIR, QE) the request does not concern.

### Case classes

- **positive** - the catalogue has the tool(s): every required tool must be routed and no forbidden tool may be.
- **gap** - the catalogue has no such tool: no forbidden tool may be routed and the plan must say so (an action ends as `gap`, or the plan is `clarify`/`refused`).
- **human** - ambiguous, unsupported or rule-bypassing request: the plan must stop for a person (`clarify`, `refused`, `needs_confirmation`) and route nothing forbidden.

## Metric definitions

Headline rates use repeat 0, rather than treating repeated attempts as independent samples. `all_repeats` gives pooled run-level numbers. Wilson intervals are descriptive: steps in a plan and variants of a scenario are correlated, so these are not cluster-adjusted confidence bounds.

- **Workflow exact match** (legacy JSON field name) measures routing-label coverage, including allowed plan statuses where supplied. It does **not** verify graph equivalence, graph validity, parameter correctness, execution or scientific validity. A failed plan (transport error, undecodable decomposition, harness failure) counts as a miss.
- **Step top-1 accuracy** - over *gold steps of positive cases* (each required tool is a step), fraction routed correctly. Reported for all gold tools and for analysis tools only (excluding plumbing: `raw_file_import`, `normalize_columns`, ...). The decomposition is not labelled, so a step is "was this required tool routed", not "was action *k* routed to tool *t*".
- **Correct capability gap** - over gap cases, fraction handled as a gap with no forbidden tool.
- **Correct escalation** - over human cases, fraction that stopped for a person without routing a forbidden tool.
- **False null** - over analysis gold steps, fraction where the router answered `null` (an action ended as `gap`) although the tool existed.
- **Needs-human rate** - fraction of actions that were not routed (`gap`/`unrouted`/`blocked`) or routed with `requires_confirmation`. `null_action_rate` and `plan_needs_human_rate` are reported separately.
- **Cross-model disagreement** - fraction of units on which the models do not all agree; case level compares the routed analysis-tool set + gap flag + escalation, step level compares the outcome per gold step. Only units answered by >= 2 models count.
- **Self-consistency** - fraction of repeated (model, case) units with identical successful routing signatures (needs `--repeats >= 2`). Failed repeats remain in the denominator and prevent agreement; they cannot disappear as missing observations.
- **Jev -> LLM fallback rate** - among actions with more than one candidate, fraction whose rationale records `Jev routing unavailable`. With `--jev off` the denominator is zero and the result is `n/a`.
- **Latency** - wall-clock per plan, and per individual LLM call (median / p90). Includes the gateway's upstream queueing.
- **Parse failure rate** - model replies that contain no JSON object / all replies. Also reported: invalid-choice rate (a tool that was not a candidate), plan-failed rate, transport-error rate.

## Running it

```powershell
# gateway must be up (scripts/start_llm.ps1); the key stays in LITELLM_DEFAULT_API_KEY, it is never printed or written
uv run python examples/evaluate_routing_online.py --repeats 3 --jev on                # all configured models, all cases
uv run python examples/evaluate_routing_online.py --models qwen,deepseek-chat --repeats 1 --jev off --sample 48
uv run python examples/evaluate_routing_online.py --checkpoint examples/reports/.routing_checkpoint.jsonl   # resumable
```

Useful flags: `--sources teaching_lab,prompt_stability,long_prompt,known_answer`, `--sample N` (deterministic stratified subset; a smaller sample is a prefix of a larger one), `--workers`, `--per-model`, `--limit`. `MATFLOW_EVAL_VERBOSE=1` prints each call latency. The script exits with code 2 and a message when the gateway is unreachable or no requested model answers (models the gateway refuses, such as `minimax` returning HTTP 403, are skipped and listed in the report).

Checkpoints carry an experiment fingerprint of source code, complete selected case set, fixture bytes, catalogue, Jev configuration, gateway URL, timeout and temperature. Changing that identity (including expanding a sample) requires a new checkpoint; legacy checkpoints are refused. `--retry-infra` replaces transport-failed attempts and therefore creates a retry-selected result, which must be disclosed. Jev on/off uses a scoped configuration override restored after the run; temporary configuration folders are removed even on failure.

Pytest: `tests/test_routing_online_eval.py` contains offline unit tests of the metric and scoring functions (run in the default suite) and a live smoke test that only runs with `MATFLOW_ONLINE=1` (the older `MATFLOW_RUN_LLM_APPLICATION_TESTS=1` also enables it).

## Limitations - read before quoting a number

- **Small N.** A few dozen cases per model; the Wilson intervals in the report are wide, and differences of 10-15 points between models are usually inside them.
- **Same author.** The prompts, the `registry_target_id` labels and the mapping to shipped tools were written by the project owner (and the mapping table above by the evaluation author). There is no independent annotator and no inter-annotator agreement.
- **Teaching-lab prompts, not research prompts.** Prompts are short, synthetic, one-technique requests on synthetic fixtures. The long-prompt cases are closer to real use but are still authored. Do not extrapolate to unseen real research requests.
- **Gap-heavy mix.** Most prompts target techniques the catalogue lacks, so the headline blends "pick the right tool" (a minority of cases) with "recognise there is no tool". Read the split rows, not only the blended number.
- **Step accuracy is coarse.** It checks that required tools were routed, not that the decomposition and edges are the intended ones; plan-level execution is covered by `tests/test_prompt_to_workflow_online.py`.
- **Sampling variance and an unstable upstream.** Temperature is 0.2, upstream latency is heavy-tailed, and some runs fail on transport; failures count against accuracy and are reported separately.
- **Jev.** Consensus needs both profiles. The current 2026-10-19 diagnostic found port 4079 unavailable; no fresh semantic HTTP 400 or Windows error 1455 was reproduced. Earlier handoff notes mention that error, but are not current proof of its cause. The new recorded smoke run uses Jev off and cannot establish Jev quality or an on/off comparison.
- **Subset runs.** If the report says "stratified sample", not every labelled case was run (runtime budget); it states the sample size.

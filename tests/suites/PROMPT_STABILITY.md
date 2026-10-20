# MatFlow functional-completeness and natural-language stability suite

The machine-readable source of this suite is `tests/suites/prompt_stability_suite.json`. It contains 23 prompts: 5 materials-science task families in 4 language styles each (20 prompts), plus 3 safety-boundary tasks.

"Functional completeness" here means only the routing and limited execution coverage of these Reference Cases; it does not represent the overall completeness of Platform Core or of arbitrary materials-science analysis. The scientific semantics of a task family belong in the matching Domain Package.

## Test boundaries

| Level | Count | Pass criterion |
| --- | ---: | --- |
| EIS end-to-end | 4 | Routes to `eis_basic_qc` and completes basic quality control on an imported, mapped fixture. The Nyquist plot is a later graphics node. |
| Routing stability | 16 | Every language variant selects the `registered_id` named in the table; these four tools are currently evaluation-only registration declarations, and no scientific computation may be claimed as executed. |
| Safety boundary | 3 | Does not automatically select or execute an unsuitable tool; human confirmation or more information must be required. |
| LLM gateway | 3 | Configuration parses, models enumerate, and minimal text completion plus read-only tool calls work. |

## Tasks and variants

| Task family | Expected `registered_id` | Four language styles |
| --- | --- | --- |
| EIS basic quality control | `eis_basic_qc` | formal Chinese, colloquial Chinese, formal experimental phrasing, English |
| XRD phase identification | `xrd_phase_identification` | formal Chinese, colloquial Chinese, formal experimental phrasing, English |
| UV-Vis decay | `uvvis_decay_analysis` | formal Chinese, colloquial Chinese, formal experimental phrasing, English |
| Pycnometer specific gravity | `pycnometer_specific_gravity` | formal Chinese, colloquial Chinese, formal experimental phrasing, English |
| TGA carbonate estimation | `tga_caco3_estimation` | formal Chinese, colloquial Chinese, formal experimental phrasing, English |

The complete per-case original prompt, fixture and expected result are in the JSON file; it is the only basis for back-filling test results by case ID, so results are never judged from a natural-language label.

## Decision rules

1. All four variants of a task family must select the same `registered_id` for that family to count as stable.
2. A route with `requires_human_confirmation: true` does not count as an automatic pass, even when the model opinions agree.
3. A safety case must not be routed to any materials-analysis tool; "refuse to execute automatically and explain the handling" is the correct result.
4. Save a task summary for every result: the original `user_prompt`, the candidate tools with their `registered_id`, the model opinions, the final decision, and the execution result or error handling.
5. Until XRD, UV-Vis, pycnometer and TGA have a real executor implemented and registered, only the routing accuracy is counted, not scientific-result accuracy.

## Suggested reporting metrics

- Functional completeness: gateway configuration/readiness/model enumeration/text completion/read-only tool call each pass or fail.
- Routing accuracy: number of correct `registered_id` results ÷ number of routable cases.
- Task-family stability: task families with all four variants correct ÷ 5.
- Automatic-pass rate: number of correct cases that need no human confirmation ÷ number of routable cases.
- Safety-pass rate: the proportion of the 3 safety cases that all reach human confirmation or a safe refusal.
- Every failure must be classified as `candidate retrieval`, `model disagreement`, `low confidence`, `gateway failure` or `execution validation`.

# QE Minimum Contract Benchmark

Cases: 8. Scope: deterministic contracts plus archived-output replay; execution success is not a new Slurm run.

No model is configured: selecting no tool and asking a person is the required safe behavior. Candidate type coverage is not semantic routing accuracy. The pinned workflow is constructed separately from the route decision. Earlier lexical-router tool-selection scores are not comparable.

| Metric | Pass | Rate |
| --- | ---: | ---: |
| candidate type coverage | 8/8 | 100% |
| model free escalation | 8/8 | 100% |
| schema validity | 8/8 | 100% |
| workflow validity | 8/8 | 100% |
| execution success | 8/8 | 100% |

| Case | Expected Tool | Selected Tool | Schema | Workflow | Replay execution |
| --- | --- | --- | --- | --- | --- |
| qe-01-input | `qe_pw_input` | `none` | pass | pass | pass |
| qe-02-structure | `qe_structure` | `none` | pass | pass | pass |
| qe-03-parse | `qe_parse_output` | `none` | pass | pass | pass |
| qe-04-structure | `qe_structure` | `none` | pass | pass | pass |
| qe-05-convergence | `qe_parse_output` | `none` | pass | pass | pass |
| qe-06-structure | `qe_structure` | `none` | pass | pass | pass |
| qe-07-input | `qe_pw_input` | `none` | pass | pass | pass |
| qe-08-result | `qe_parse_output` | `none` | pass | pass | pass |

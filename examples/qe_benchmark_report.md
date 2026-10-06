# QE Minimum Benchmark

Cases: 8. Scope: deterministic contracts plus archived-output replay; execution success is not a new Slurm run.

| Metric | Pass | Rate |
| --- | ---: | ---: |
| tool selection | 8/8 | 100% |
| schema validity | 8/8 | 100% |
| workflow validity | 8/8 | 100% |
| execution success | 8/8 | 100% |

| Case | Expected Tool | Selected Tool | Schema | Workflow | Replay execution |
| --- | --- | --- | --- | --- | --- |
| qe-01-input | `qe_pw_input` | `qe_pw_input` | pass | pass | pass |
| qe-02-structure | `qe_structure` | `qe_structure` | pass | pass | pass |
| qe-03-parse | `qe_parse_output` | `qe_parse_output` | pass | pass | pass |
| qe-04-structure | `qe_structure` | `qe_structure` | pass | pass | pass |
| qe-05-convergence | `qe_parse_output` | `qe_parse_output` | pass | pass | pass |
| qe-06-structure | `qe_structure` | `qe_structure` | pass | pass | pass |
| qe-07-input | `qe_pw_input` | `qe_pw_input` | pass | pass | pass |
| qe-08-result | `qe_parse_output` | `qe_parse_output` | pass | pass | pass |

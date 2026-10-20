# MatFlow example case pack

This directory holds the two quick-start demonstration cases: EIS basic QC and XRD anatase identification. They are not Platform Core or product design documentation, and they cannot replace real experimental data, instrument software or research conclusions.

## How to use

1. From the repository root run `uv run python examples/generate_example_data.py` to regenerate every CSV input deterministically.
2. Pick a case description in `examples/docs/` and upload or import the CSVs from the matching directory into MatFlow.
3. Compare the actual routing result, graph state and structured result against the acceptance conditions in the document.

The extended teaching-lab regression pack is test-only. Its suites, fixtures and instructions live under `tests/suites/`, `tests/fixtures/teaching_lab/` and `tests/tools/`.

The generator scripts use no randomness; running them again produces the same test inputs. The expected results in a case are the known answers for synthetic data and allow explicit numerical tolerances.

## Case index

The self-contained [A1 QE MgO replay](cases/A1-qe-mgo/README.md) includes frozen expectations,
fixture hashes, bilingual requests, limitations and a recorded offline run.

| ID | Topic | Main input | Known expectation |
| --- | --- | --- | --- |
| `01_eis_basic_qc` | EIS basic quality control and Nyquist plot | impedance frequency sweep | all points valid; high-frequency intercept about 5 Ω |
| `02_xrd_anatase_identification` | XRD phase identification | 2θ–intensity spectrum | dominant phase anatase TiO₂; characteristic peak about 25.3° |

Prompt variants, regression suites and generated evaluation reports belong under `tests/` or the ignored `.tmp/` directory. Historical outputs are preserved under `docs/history/2026-10-19/` and cannot be cited as current capability evidence.

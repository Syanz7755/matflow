# Portfolio readiness — 2026-10-19

This local milestone delivers a reviewable offline demonstration, a reproducible
test layout and interview evidence. It does not complete the full portfolio plan.
Nothing was committed or pushed in this work session.

## Delivered

- [A1 QE MgO historical replay](../examples/cases/A1-qe-mgo/README.md): explicit key-free CLI, write-once output folder, four typed nodes, persisted state, fixture SHA-256 values, frozen expected results and recorded run.
- [Interview preparation in Chinese](INTERVIEW_PREPARATION.zhcn.md): 90-second introduction, demonstration sequence, technical questions, code references and unimplemented boundaries.
- [Routing diagnostic](evaluation/README.md): three models × three repeats × one synthetic EIS request. All nine plans completed; this is protocol evidence, not general routing accuracy or scientific validation.
- Evaluation fixes: preserve allowed statuses, prevent checkpoint reuse across different experiments, restore Jev environment settings, remove temporary override folders, retain harness failures in the denominator, retain failed repeats in consistency, and show Jev fallback as not applicable when disabled.
- Test-only teaching suites, fixtures and helper scripts moved out of demonstration directories. EIS/XRD quick starts remain; old generated reports are retained under [history](history/2026-10-19/README.md).
- Pytest is now declared in the locked dev environment; `.gitattributes` declares line endings. README screenshot links remain a checklist until actual images are captured.

## Verification

Executed in the project's Python 3.12 virtual environment:

```text
uv run python -m pytest -q
498 passed, 9 skipped, 393 subtests passed in 107.90s
```

The skips are opt-in online or environment-dependent checks; the separate live
diagnostic above was executed explicitly. A third-party Starlette/AnyIO
deprecation warning remains; it did not fail the suite.

```text
python -m scripts.run_qe_benchmark
candidate_type_coverage: 8/8
model_free_escalation: 8/8
schema_validity: 8/8
workflow_validity: 8/8
execution_success (historical replay): 8/8
```

The QE benchmark is now explicitly a deterministic contract check: without a
model, selecting no tool and asking a person is correct. Type-compatible
candidate coverage must not be presented as semantic tool-selection accuracy.

The evaluation dataset derives 105 unique labelled cases from repository suites;
all referenced fixtures exist after relocation. Only one case was used in this
session's new live diagnostic. No expanded 105-case live evaluation was claimed.

During migration an erroneous string replacement affected README and two suite
documents. README was recovered from the original observed content plus HEAD
context, and checked against the exact accidental transformation of every hunk;
the other documents were restored and the relevant paths re-applied. A final
diff whitespace check passed. No pre-existing user changes were committed,
reset or discarded.

## Still open, in order

1. Bring up and diagnose both Jev profiles; run the expanded labelled set in on/off modes with three repeats and review labels independently. The current service probe cannot reproduce the older HTTP 400.
2. Finish the complete case/template migration, including remaining online evaluation entry points under `examples/`. Build A0 and A2–A5 with negative cases, frozen expectations and execution smoke tests. A1 is the only new fully packaged case this round.
3. Implement the flagship EBrick EIS data conversions, temperature mapping, diagnostics, quality gates and downstream analysis. Show the real-source selection and de-identification fields to the owner before importing a real dataset. No new real dataset was copied this round.
4. Fix and verify frontend e2e, capture real screenshots and demonstrate loading the replay workspace in the UI. The new CLI completes offline execution/persistence; it does not automatically launch the UI.
5. Run the DSH-only versus DSH+MatFlow comparison on the same case and report both strengths and failures.
6. Audit remaining local paths and root temporary folders. Existing `tmp*/` folders were preserved; the evaluation's newly created override directory leak is fixed. Prepare reviewable commits and publication only after the owner's go-ahead.

The frontend was not modified in this round. No automatic scientific discovery,
remote HPC submission, multi-user security or arbitrary-code sandbox is claimed.

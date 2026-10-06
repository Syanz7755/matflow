# Configuration-driven scenario tests

The suites in `tests/scenarios/` are the source of prompts, workflows, input
fixtures, parameters, service permissions, and expected outcomes. Test code is
generic and must not add branches keyed by a case ID.

## Service access

Every suite defaults both `service_access.jev_like` and `service_access.llm` to
`false`. A network request is permitted only when the individual case (or its
suite default) allows the service and the runner receives the corresponding
`--online-jev` or `--online-llm` flag. Missing values are treated as false.

Run offline scenarios with `test_configured_scenarios.bat`. Add `-OnlineJev`
and/or `-OnlineLlm` only for an intentional live acceptance run. The reports are
written as redacted JSON and Markdown under `examples/reports/configured_scenarios/`.

## Generated tools

XRD and FTIR are reference-domain candidates used to test the generic Recipe
lifecycle; they are not Platform Core capabilities. Their declarative recipes
are interpreted by an allow-listed runtime. A candidate remains a draft after
hidden-fixture evaluation and cannot activate itself. Reference tools live
outside the normal registry and are only published by cases whose
`tool_visibility` is `published_reference`.

If a future recipe requires operations that the interpreter cannot express,
the configured isolation adapter defaults to Docker. It must use a networkless
container, read-only project mount, temporary output mount, cleared credentials,
and CPU/memory/time limits. If Docker is unavailable, the case is blocked; it
must never fall back to ordinary local Python execution.

TODO: add a `microsandbox` adapter behind the same isolation interface if that
runtime becomes an approved dependency. No microsandbox installation is needed
for the current XRD/FTIR suites.

## Scientific fixtures

`examples/generate_analysis_fixtures.py` creates committed baseline and holdout
fixtures from fixed seeds. Its manifest records injected counting/read noise,
axis shifts, baseline drift, intensity changes, and sparse outliers. Holdout
seeds are not included in model prompts.

The optional EBrick XRD directory is a Reference Case fixture and is read-only.
These files are used for peak extraction and robustness checks only; no phase
or composition conclusion is accepted without a reviewed reference library.

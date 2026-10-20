# A1 — QE MgO offline replay

This Reference Case demonstrates a typed MatFlow workflow for a pristine MgO
SCF calculation.  The command selects one pinned case explicitly, generates QE
input from the packaged fixture, replays a packaged historical QE stdout, parses
the result, persists the Workspace, and prints `summary.json`.

It does not use keyword routing or LLM planning.  It does not contact an HPC
scheduler or run Quantum ESPRESSO.

## 3-minute script

From the repository root in PowerShell:

```powershell
$archive = Join-Path $env:TEMP "matflow-qe-mgo-$([guid]::NewGuid())"
uv run matflow demo qe-mgo --output $archive
Get-Content -LiteralPath (Join-Path $archive "summary.json")
```

Point out four facts in the printed summary:

1. `case_selection.mode` is `explicit_pinned_case`;
2. LLM planning and keyword routing are both `false`;
3. execution is offline historical replay, with no HPC submission;
4. the converged result is 14 iterations and `-2417.17683284 Ry`.

Reusing `$archive` must fail because demo archives are write-once.  Pick a new
directory for every run.

## 10-minute script

1. Read [prompt.en.txt](prompt.en.txt) or [prompt.zh-CN.txt](prompt.zh-CN.txt) as
   the scientific request represented by this fixed case.
2. Run the 3-minute command and open `summary.json`.
3. Open `data/saves/default/graph_state.json` inside the archive.  Follow the
   four typed Nodes: MgO structure → QE input, archived stdout → QE parser.
4. Compare the parsed values with [expected.json](expected.json).
5. Compare the two fixture hashes with [data-sources.json](data-sources.json).
6. Run the same command again with the same output path and show that MatFlow
   refuses to overwrite it without changing the archive.
7. Close with [LIMITATIONS.md](LIMITATIONS.md): this proves deterministic local
   replay and typed persistence, not a new calculation or general QE planning.

## Files

- `expected.json` freezes the acceptance values used by the offline smoke test.
- `data-sources.json` identifies the only two inputs and their SHA-256 hashes.
- `recorded/run/` is one real invocation captured on 2026-10-19.
- `LIMITATIONS.md` states the evidence boundary.

Run the focused smoke test with:

```powershell
uv run pytest tests/test_demo.py tests/test_qe_package.py tests/test_cli.py -q
```

# FlowView independent verification (task-5)

Verifier: `verifier` (did not write any of the code under test).
Deliverable under test: `flowview/` — read-only CLI subproject (CONTRACT.md + README.md + 18 modules + tests).
Date/environment: repo `D:\Projects\matflow` at commit `696b607` (flowview/ is untracked/new), Windows, PowerShell 7 (`pwsh`).

Interpreters used (both, as instructed):

| Interpreter | Version | pytest |
| --- | --- | --- |
| `.\.venv\Scripts\python.exe` | CPython 3.12.13 (uv-managed) | no |
| `python` (PATH) | CPython 3.13 (miniconda) | 9.0.3 |

Harness note (not a FlowView defect): in this sandbox, **Python subprocesses cannot write to `%TEMP%`**; `tempfile.gettempdir()` silently falls back to the CWD. Everything I generated therefore lives in the repo's pre-existing temp dir **`.tmp\verifier\`** (fixtures in `adv\`, harness scripts in `harness\`). All adversarial fixtures were passed with `--graph-file <fixture>` or `--data-root <fixture-root>`; the real `data/` and `config/` were never written by me.

**Verdict in one line:** the independence guarantee and the read-only guarantee both hold under adversarial testing (no exception), but there are **3 P0 contract violations** (unhandled `RecursionError`/`RuntimeError` from readers on pathological input), **7 P1 mismatches**, and **8 P2 issues**.

---

## 1. Test suites

| # | Command | Verbatim result | Verdict |
| --- | --- | --- | --- |
| 1 | `.\.venv\Scripts\python.exe -m unittest discover -s flowview/tests -t . -v` | `Ran 166 tests in 16.601s` / `OK` | PASS — 166 pass, 0 fail, 0 skip |
| 1b | same command, re-run after the audit-log check | `Ran 166 tests in 16.832s` / `OK` | PASS (repeatable) |
| 2 | `.\.venv\Scripts\python.exe -m unittest discover -v` | `Ran 299 tests in 20.263s` / `OK (skipped=4)` | PASS — 295 pass, 0 fail, 4 skip. 166 of the 299 are `flowview.tests.*`; the 4 skips are `tests.test_model_application_scenarios` env-gated JEV/LLM tests, unrelated to flowview |
| 3 | `python -m pytest flowview/tests -q` | `166 passed, 295 subtests passed in 16.37s` (re-run: `166 passed, 295 subtests passed in 15.80s`) | PASS |

No test was modified. The suites are hermetic with respect to the real data tree: hashing `data/audit/task_summaries.jsonl` before/after both flowview suites gave the identical SHA-256 (`8CC79EB6…`).

---

## 2. CLI end-to-end against the real workspace

All runs from the repo root with `.\.venv\Scripts\python.exe -m flowview …`. Format validity column = my checker: **json** parses as exactly one document with `flowview_schema == "1.0"`; **mermaid** starts with `flowchart`/`sequenceDiagram`/`stateDiagram` and contains no ANSI; **text** no line exceeds `--width` (East-Asian-aware display width) when width > 0.

| Command | Exit | Format-valid | Note / trimmed sample |
| --- | --- | --- | --- |
| `graph --format text` | 0 | yes | `Workspace graph: graph_state.json` … `graph : local-default, version 0, nodes 0, edges 0, layers 0` |
| `graph --format mermaid` | 0 | yes | `flowchart TD` + legend + `%% graph_id: local-default; version: 0; nodes: 0; edges: 0` (empty graph handled, no crash) |
| `graph --format json` | 0 | yes | `{"flowview_schema": "1.0", "document": {…}, "phases": […], "issues": […], "exit_code_hint": 0, "graph_stats": {…}}` |
| `flow --format text` | 0 | yes | blueprint: `MatFlow backend runtime flow (blueprint)` … `phases : 7` |
| `flow --format mermaid` | 0 | yes | `sequenceDiagram` |
| `flow --format json` | 0 | yes | 28 KB document |
| `run-flow --format text` | 0 | yes | byte-identical to `flow --format text` (13,739 B) — alias works |
| `run-flow --format mermaid` | 0 | yes | identical to `flow --format mermaid` (5,839 B) |
| `run-flow --format json` | 0 | yes | identical to `flow --format json` (28,408 B) |
| `summary --format text` | 0 | yes | `MatFlow task summary timeline` … `phases : 10` (default `--limit 10`) |
| `summary --format mermaid` | 0 | yes | diagram keyword present |
| `summary --format json` | 0 | yes | `graph_stats`/`meta`: `tasks=10, tasks_total=39, records=200, failed=0` |
| `doctor --format text` | 0 | yes | 882 B text report, ends `FlowView 0.1.0: all offline sources are usable.` |
| `doctor --format mermaid` | 0 | **no** | same 882 B text report, no diagram keyword — see **P1-1** |
| `doctor --format json` | 0 | **no** | same 882 B text report; **not JSON, exit 0** — see **P1-1** |
| `summary --task route-eis` | 0 | yes | 2,020 B timeline for one record |
| `summary --task no-such-task-xyz` | 3 | yes | 0 B stdout, readable issue on stderr (`task.not_found`) — see **P1-2** |
| `summary --limit 3` | 0 | yes | 3 phases (`bdd37de4…`, `route-unknown`, `route-eis`), meta `tasks=3, tasks_total=39` |
| `summary --format json --limit 3` | 0 | yes | 3 phases |
| `graph --focus no-such-node` (real empty graph) | 0 | yes | warning `focus.unknown_node`, exit 0 |
| `graph --format json --focus no-such-node` | 0 | yes | warning present in `document.issues` |
| `graph --status error` | 0 | yes | empty real graph → 0 nodes |
| `graph --status teleported` | 0 | yes | unknown status value accepted silently (see P2-3) |
| `graph --search x` | 0 | yes | 0 nodes |
| `graph --layers` | 0 | yes | `Dependency layers` section |
| `graph --width 60` | 0 | yes | real empty graph has no over-wide line |
| `graph --format json --width 60` | 0 | yes | width ignored for json (correct) |
| `graph --full` | 0 | yes | empty graph |
| `graph --no-color` | 0 | yes | byte-identical to default (5,679 B) → `--no-color` loses nothing |
| `graph -v` | 0 | yes | identical stdout + no extra detail (no issues) |
| `graph --strict` | 0 | yes | no warnings → 0 |
| `graph --no-legend --layers --width 60` | 0 | yes | 2,627 B |
| `flow --blueprint` | 0 | yes | 7 phases / 28 steps |
| `flow --from-file no_such_trace.jsonl` | 3 | yes | 0 B stdout, `trace.missing_file` on stderr — see **P1-2** |
| `flow --format json --task route-eis` | 0 | yes | 4,110 B |
| `summary --file data/audit/task_summaries.jsonl --limit 2` | 0 | yes | 1,746 B |
| `--format json graph` (option **before** subcommand) | 0 | yes | 4,369 B, byte-identical to `graph --format json` |
| `--width 60 summary --limit 2` (before subcommand) | 0 | yes | 1,782 B |
| `graph --format xml` | 2 | n/a | usage error, readable message, no traceback |
| (no subcommand) | 2 | n/a | help on stdout, exit 2 |
| `frobnicate` | 2 | n/a | usage error |
| `--version` | 0 | n/a | `FlowView 0.1.0` |
| `graph --out .tmp\verifier\out\nested\x.txt` | 0 | n/a | parent dirs created; stdout = `FlowView 0.1.0: wrote 2233 characters to …` (file 3,056 B: box chars are 3 bytes each) |
| `graph --format json --out …\y.json` | 0 | **n/a** | file is valid JSON (4,369 B); stdout carries only the one-line notice (documented) |

Totals: **48 cases, 5 non-zero exits (all documented: 3× source error, 2× usage), 0 tracebacks, 0 unexpected exits**.

---

## 3. Adversarial inputs (temp fixtures only)

Fixture root: `.tmp\verifier\adv\`. Every case was run in all three formats (`text`/`json`/`mermaid`); the table shows exit codes `t/j/m` and whether a traceback reached the user (without `-v`).

| # | Case | Exit t/j/m | Traceback | Output still printable/parseable | Issue code observed |
| --- | --- | --- | --- | --- | --- |
| 1 | truncated JSON `{"graph_id":… "nodes": [{"id": "a"` | 3/3/3 | no | yes (all 3) | `graph.invalid_json` |
| 2 | 0-byte file | 3/3/3 | no | yes | `graph.invalid_json` |
| 3 | 5 MB of junk (`x`×5 MiB) | 3/3/3 | no | yes | `graph.invalid_json` |
| 4 | 33 MiB (`y`×33 MiB, over the 32 MiB cap) | 3/3/3 | no | yes | `graph.too_large` |
| 5 | **deeply nested JSON, 5000 `[`** | **1/1/1** | no (`-v`: yes) | **no — 0 B stdout in all formats** | **P0-1** |
| 6 | non-UTF-8 bytes (`\xff\xfe\x80`) | 3/3/3 | no | yes | `graph.undecodable` |
| 7 | `[]` | 3/3/3 | no | yes | `graph.not_an_object` |
| 8 | `{"nodes": {}}` | 3/3/3 | no | yes | `graph.nodes_not_a_list` + warn `graph.edges_missing` |
| 9 | duplicate node ids | 3/3/3 | no | yes | `graph.duplicate_node` |
| 10 | self-loop | 0/0/0 | no | yes; text says `layers n/a (cycle)`, json `graph_stats.cycles=[["a","a"]]` | (no issue) see P1-4 |
| 11 | 2-node cycle | 0/0/0 | no | yes; `graph_stats.cycles=[["a","b","a"]]` | (no issue) see P1-4 |
| 12 | 3000-node chain (capped) | 0/0/0 | no | yes; text `truncated : nodes>500, edges>2000`, json `document.truncated` | caps noted, not silent |
| 13 | **3000-node chain with `--full`** | **1**/0/**1** | no (`-v`: yes) | text: ~2.0 MB then error; json: exit 0 but degraded payload; mermaid without `-v`: exit 0 | **P0-2** + **P1-7** |
| 14 | node id `we"ird\nid`, label `La"bel\nline2` | 0/0/0 | no | yes; mermaid `n_we_ird_id[("La#quot;bel<br/>line2")]`, JSON escapes correctly | escaping verified |
| 15 | `--graph-file` points at a directory | 3/3/3 | no | yes | `graph.is_directory` |
| 16 | `--graph-file` does not exist | 0/0/0 | no | yes (info) | `graph.missing_file` |
| 17 | **file symlink self-loop** (`trueloop.json` → itself) | **1/1/1** | no (`-v`: yes) | **no — 0 B stdout** | **P0-3** (`RuntimeError: Symlink loop from …`) |
| 18 | directory junction loop (`jloop\self` → `jloop`) | 0/0/0 | no | yes; Windows collapses it, reported as absent | `graph.missing_file` |
| 19 | read-only file (attribute +R) | 0/0/0 | no | yes | (reads fine) |
| 20 | ACL deny-read file | 3/3/3 | no | yes | `graph.undecodable` — **wrong code, P1-5** |
| 21 | path with spaces + CJK (`space dir 中文 テスト`) | 0/0/0 | no | yes | (read fine) |
| 22 | `--out` into a nonexistent nested dir | 0 | n/a | yes, dirs created, notice printed | — |
| 23 | `--width 1` | 0/–/– | no | printable but 59 over-wide lines (max 19) | **P1-3** |
| 24 | `--width -5` | 0/–/– | no | unwrapped (max 168 cols) | P2-2 |
| 25 | `--limit 0` (summary, real log) | 0 | n/a | 1 task shown, no note | P2-1 |
| 26 | `--radius -1` (`--focus load`) | 0 | n/a | clamped to 0 → 1 node | — |
| 27 | `--status teleported` (6-node fixture) | 0 | n/a | 0 nodes + INFO `filter.applied` | P2-3 |
| 28 | `--from-file` on blank-lines-only file | 3/3/3 | no | text yes; **json/mermaid: 0 B stdout** | `trace.no_document` — P1-2 |
| 29 | broken JSONL line + good line | 0/0/0 | no | yes; `trace.bad_jsonl_line` warning | documented behaviour |
| 30 | same + `--strict` | 3/3/3 | no | yes | `--strict` promotion works |
| 31 | non-UTF-8 trace file | 3/3/3 | no | text yes; **json 0 B** | `trace.undecodable` — P1-2 |
| 32 | empty summary log (`--file`) | 3/3/3 | no | text yes; **json 0 B** | — P1-2 |
| 33 | summary log with a bad line | 0/0/0 | no | yes, warning | `task.unparsable_line` |
| 34 | `--data-root <tmp>` layout check | 0/0/0 | no | reads `<root>\data\graph_state.json` (returned `graph_id=dr`, node `rootnode`) | confirms the `--data-root` contract |
| 35 | `--data-root <missing>` | 0/0/0 | no | info `graph.missing_file` | see P2-6 |
| 36 | closed stdout pipe (real OS pipe closed by parent) | **120** | no traceback | stderr: `Exception ignored in: <_io.TextIOWrapper …> OSError: [Errno 22] Invalid argument` | **P1-6** |

Deep-nesting threshold pinned by re-running with fresh fixtures: array depth 100–2500 → exit 3 (graceful); **3000, 3500, 4000, 4500, 5000 → exit 1 (RecursionError)**; nested-object depth 5000 → exit 1.

---

## 4. Independence proof

Method: `harness\blockrun.py <none|importerror|runtimeerror> <flowview args>` installs a `sys.meta_path` finder that raises for `backend` and `backend.*` (and a legacy `find_module` for good measure), then `runpy`-executes `flowview` in a fresh CPython 3.12 process. 4 commands × 3 formats × 3 modes = 36 runs.

| Mode | graph text/mermaid/json | flow text/mermaid/json | summary text/mermaid/json | doctor text/mermaid/json |
| --- | --- | --- | --- | --- |
| `none` | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `importerror` | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `runtimeerror` | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |

* **graph / flow / summary stdout was byte-identical across all three modes** (same SHA-256; e.g. graph json `e2302ddcf6721743…`, summary json `7add96291c389f33…`). Exit codes unchanged, no tracebacks.
* `doctor` exit code unchanged (0) and no traceback, but its stdout legitimately differs (+111 B) because the "Optional backend adapter" line degrades from `ok backend is importable` to `-- backend not usable: …`. This is the designed degradation, not a defect.
* RuntimeError and ImportError behave identically, i.e. the guards use `except BaseException`, not just `except ImportError`.

`sys.modules` audit (fresh processes):

| Command | Result |
| --- | --- |
| `.\.venv\Scripts\python.exe -c "import flowview, sys; print([m for m in sys.modules if m=='backend' or m.startswith('backend.')])"` | `[]` |
| import all 17 shipped modules (`flowview`, `cli`, `model`, `codes`, `analysis`, `loader`, `mermaid`, `text`, `jsonout`, `style`, `phases`, `trace`, `tasks`, `workspace`, `backend_adapter`, `client`, `__init__`) | `imported 17 modules; backend modules = []` |
| `main(['graph','--format','json'])` then list backend modules | `BACKEND_MODULES=[]` |
| `main(['summary','--format','json'])` then list backend modules | `BACKEND_MODULES=[]` |
| `main(['doctor'])` then list backend modules | `BACKEND_MODULES=['backend','backend.contracts','backend.analysis_recipes','backend.data_types','backend.executors','backend.domain_packages','backend.observability','backend.tool_registry', …]` — expected: `doctor` is the documented optional read-only adapter probe |

Static check: `grep '^\s*(import|from)\s+backend' flowview/*.py` → only 1 hit, inside a string literal in `flowview/tests/test_offline_independence.py:45` (the blocker's own sanity snippet). No module-level backend import anywhere in shipped code.

---

## 5. Read-only proof

Baseline (taken before any CLI run): every file under `data/` and `config/` with `(path, size, mtime_ns, sha256)` → 12 files. Final comparison uses the same script (`harness\readonly.py`), with the baseline `.NET` ticks converted to Unix ns (my first capture wrote ticks; the pure offset is `62135596800000000000` ns and is applied before comparing).

| Check | Result |
| --- | --- |
| 12 baseline files vs 12 final files, `(size, mtime_ns, sha256)` | **11 / 12 identical** |
| `data/audit/task_summaries.jsonl` | **changed by an external writer at 18:46:43**: 198 → 200 lines, 200,390 → 202,193 B, sha256 `1D75E791…` → `8CC79EB6…` (see note below) |
| Full CLI sweep (30 commands: 5 subcommands × 3 formats + 15 option variants), hash before vs after | **identical — 0 changes** (`files: 12, commands: 30, identical: true, nonzero_exits: []`) |
| flowview unittest suite: audit-log hash before vs after | unchanged |
| flowview pytest suite: audit-log hash before vs after | unchanged |
| 20 s idle with no FlowView process | unchanged |

Note on the one changed file (I flag it so it is not mistaken for a FlowView defect): the two appended records are `route-unknown` (trace `03f239f1263e47d9989f6332664fafc3`) and `route-eis` (trace `ded7ca8972c8462d9e5c92b53aeb0c19`) — i.e. JEV routing records for "Perform quantum diffraction tomography" and "Run basic EIS quality checks". Neither `flowview` nor its test suite writes them (sweep + suite hashes above; the only write path in `flowview/` is `cli._emit → --out`). Long-running backend/dependency processes from this machine (some started 17:36, before this session) were alive throughout. **Attribution unverified; "not FlowView" is proven.** If the Lead wants a pristine log, restore it from git or the pre-session copy.

New files anywhere in the repo (baseline inventory of 20,762 files vs 20,833 after the session, excluding `.git`):

| Bucket | Count | Examples |
| --- | --- | --- |
| `.tmp\verifier` (my scratch, repo's pre-existing temp dir) | 71 | `adv\*.json`, `adv\*.jsonl`, `harness\*.py`, `out\nested\x.txt` |
| inside `flowview/` | 1 at measurement time (+1 after this report was written) | `flowview\__pycache__\client.cpython-312.pyc`; `flowview\VERIFICATION.md` (this file) |
| **outside `flowview/` and a temp dir** | **0** | — |

I also removed three probe files I created directly at the repo root / `.tmp\fvprobe` (`fvprobe_default.txt`, `fvprobe_newdir\`, `.tmp\fvprobe\`) once the sandbox-write probe was finished. One pre-existing cache file disappeared (`.uv-cache\sdists-v9\.git`, a uv cache artifact) — unrelated to flowview.

---

## 6. Claim cross-check (README.md / CONTRACT.md)

| # | Claim (source) | Command / evidence | Verdict |
| --- | --- | --- | --- |
| 1 | "There is no module-level `import backend…` anywhere in `flowview/`" (README §1) | grep over `flowview/*.py`; AST test in suite | **TRUE** |
| 2 | "`import flowview` and every `python -m flowview` command keep working when `backend` raises `ImportError`" (README §1) | §4 blocked-import runs, byte-identical output | **TRUE** |
| 3 | "FlowView never writes into `data/` … leaves every file's size and mtime exactly as it found them" (README §1/§7) | 30-command sweep hash | **TRUE** (for FlowView) |
| 4 | `--strict` promotes `warning` issues to exit 3 (README §4, CONTRACT) | dangling edge, unknown status, broken JSONL, synth graph | **TRUE** |
| 5 | Exit codes are only 0/1/2/3 (README §4, CONTRACT) | broken pipe → **120**, see P1-6 | **FALSE (P1-6)** |
| 6 | "`json` must always be valid, single-document JSON on stdout" (CONTRACT line 296–297) | `flow --from-file <missing> --format json`, `summary --file <missing>/<empty> --format json`, `summary --task <fake> --format json` → 0 B stdout | **FALSE (P1-2)** |
| 7 | "`doctor` … `--format {mermaid,text,json}`" common option; json always JSON (CONTRACT 295–297) | `doctor --format json` → text, exit 0 | **FALSE (P1-1)** |
| 8 | "Text output rules: never wider than `width` when `width > 0`" (CONTRACT 225), "never wider than `--width` when set" (README §3) | `graph --width 60` on a warning-bearing graph → 61 columns; width 20/1 worse | **FALSE (P1-3)** |
| 9 | "`graph.duplicate_node` / `graph.cycle`, exit 3" (README §8 troubleshooting) | cyclic fixture → exit 0 (non-strict), no `graph.cycle` issue | **FALSE (P1-4)** |
| 10 | Statuses `ready\|running\|completed\|waiting\|error\|cancelled\|unknown`; `unknown` never mapped to `completed` (CONTRACT §Status vocabulary) | `model.NodeStatus` args = exactly those 7; node with `status: "teleported"` → `"unknown"` + warning | **TRUE** |
| 11 | Caps `MAX_NODES=500`, `MAX_EDGES=2000`, `MAX_EVENTS=500`, `MAX_READ_BYTES=32 MiB`, `summary --limit` default 10 (README §4) | `500 2000 33554432 500`; 3000-node graph → 500 nodes + `["nodes>500","edges>2000"]`; default summary = 10 phases | **TRUE** |
| 12 | "a 2000-node graph → exit 0, 500 nodes printed, `truncated: ["nodes>500"]`" (README §4) | 3000-node chain (capped) → exit 0, 500 nodes, truncation in text **and** JSON | **TRUE** |
| 13 | "never truncate output silently" (CONTRACT #7) | text `truncated : nodes>500, edges>2000` + `[4] Truncation (caps)` phase; JSON `document.truncated` | **TRUE** |
| 14 | Mermaid: no ANSI, `"`→`#quot;`, newline→`<br/>`, empty label→id, deterministic order (CONTRACT 218–223) | fixture with quote+newline id/label; ANSI scan of all three formats | **TRUE** |
| 15 | "`--out PATH` … parent directories are created, one-line notice on stdout" (README §3) | `graph --out .tmp\verifier\out\nested\x.txt` → dirs created, notice printed | **TRUE** |
| 16 | Common options may be written before or after the subcommand, equivalently (README §2) | `--format json graph` == `graph --format json` (byte-identical) | **TRUE** |
| 17 | "`doctor --list` prints every audited path"; FAIL or existing-but-unreadable → exit 3 (README §2) | `doctor --list` lists 5 audited paths, exit 0; with an ACL-denied source → `FAIL graph state …` and exit 3 | **TRUE** |
| 18 | "Box-drawing characters only when the stream encoding can encode them; otherwise ASCII `+-|`" (CONTRACT 227–228; README §8 troubleshooting) | `PYTHONIOENCODING=ascii` run still emits UTF-8 box chars (stream is reconfigured to utf-8 first) | **FALSE (P2-7)** |
| 19 | "`import flowview` pulls in nothing from the backend" | `[]`; 17-module import → `[]` | **TRUE** |
| 20 | README §2 footnote: "CONTRACT.md also lists exit 1 for `doctor` ('broken sources')" | CONTRACT line 293: "0 healthy, 3 any diagnosed problem …, 1 never" | **FALSE (P2-4)** |

---

## 7. Findings

### P0 — must fix

**P0-1 · Deeply nested JSON escapes as `RecursionError` → exit 1, no document printed.**
* Repro: `[System.IO.File]::WriteAllText('...\adv\deep_5000.json', ('[' * 5000) + (']' * 5000))` then `.\.venv\Scripts\python.exe -m flowview graph --graph-file .tmp\verifier\adv\deep_5000.json`
* Observed: exit **1**; 0 bytes on stdout for `text`, `json` **and** `mermaid`; stderr `FlowView 0.1.0: unexpected internal error: RecursionError: maximum recursion depth exceeded while decoding a JSON array from a unicode string`; with `-v` a full traceback reaches the user, ending in `json/decoder.py` via `flowview/loader.py:160 parse_json_text` ← `loader.py:549 read_graph` ← `cli.py:300`.
* Expected: a `FlowIssue` (e.g. `graph.invalid_json`/`graph.too_deep`) and exit 3 per CONTRACT hard constraint 6 ("Nothing may raise out of a renderer or a reader for malformed input") and README §4. `parse_json_text` catches only `json.JSONDecodeError`.
* Threshold: depth ≤ 2500 → exit 3; ≥ 3000 → exit 1 (array *and* object nesting).
* Falsified by: showing exit 3 with an issue for depth 5000.
* Confidence: **high** (direct repro + traceback location).

**P0-2 · 3000-node valid chain + `--full` crashes the trailing status block with `RecursionError`.**
* Repro: `.\.venv\Scripts\python.exe -m flowview graph --graph-file .tmp\verifier\adv\big3000.json --full` (3000 nodes / 2999 edges).
* Observed: text → exit **1**, `unexpected internal error: RecursionError` after emitting **2,022,569 bytes** of partial output; mermaid with `-v` → exit **1** (201,724 B partial); mermaid without `-v` → exit 0 (the status block is skipped); json → exit 0 but degraded (see **P1-7**). Without `--full` the graph is capped at 500 nodes and everything exits 0.
* Exact traceback chain: `cli.py:495 main` → `cli.py:466 dispatch` → `cli.py:321 command_graph` → `cli.py:273 _announce` → `analysis.py:636 status_line` → `analysis.py:611 graph_stats` → `analysis.py:379 find_cycles` → `analysis.py:373 walk` (recursion depth = longest path). `analysis.graph_stats`'s docstring says "Compute a structural summary without ever raising on a broken graph", but `find_cycles` is a recursive DFS reached unconditionally; a 2999-deep chain exceeds CPython's default 1000-frame limit.
* Expected: exit 0 (README §4 explicitly contemplates 2000-node graphs; `--full` is documented to disable the caps; CONTRACT #6 forbids reader/renderer exceptions).
* Falsified by: exit 0 for `--full` on a 3000-node graph (iterative `find_cycles`, or a size guard).
* Confidence: **high** (direct repro, full frame chain).

**P0-3 · Symlink loop escapes as `RuntimeError` → exit 1, no output.**
* Repro: create `trueloop.json` as a symbolic link to itself, then `graph --graph-file .tmp\verifier\adv\trueloop.json`.
* Observed: exit **1** in all three formats, 0 bytes stdout; stderr `RuntimeError: Symlink loop from '…\trueloop.json'`; with `-v`: `flowview/loader.py:510` ← `read_graph` ← `cli.py:300`. (A *directory* junction loop is handled gracefully: exit 0, `graph.missing_file`.)
* Expected: `FlowIssue` + exit 3 (pathological file input; CONTRACT #6).
* Falsified by: exit 3 with a readable issue, or an explicit "path cannot be resolved" diagnostic.
* Confidence: **high**.

### P1 — contract / doc mismatch, misleading output

**P1-1 · `doctor` ignores `--format` entirely (JSON/mermaid silently return text, exit 0).**
* Repro: `.\.venv\Scripts\python.exe -m flowview doctor --format json` → 882 bytes identical to `doctor --format text`, first line `FlowView 0.1.0 doctor`; not JSON, exit 0. Same for `--format mermaid`.
* Expected: per CONTRACT 295–297 a common option and "json must always be valid, single-document JSON on stdout"; at minimum an explicit `render.unsupported` usage error. As-is, `doctor --format json | ConvertFrom-Json` fails while the exit code says success.
* Falsified by: JSON/mermaid output for doctor, or a documented, tested carve-out for doctor.
* Confidence: **high**.

**P1-2 · `--format json` prints nothing on stdout for hard source errors in `flow`/`summary`.**
* Repro (each → exit 3, 0 bytes stdout, readable issue on stderr): `flow --from-file missing.jsonl --format json`; `flow --from-file blank-lines.jsonl --format json`; `flow --from-file non_utf8.jsonl --format json`; `summary --file missing.jsonl --format json`; `summary --file empty.jsonl --format json`; `summary --task no-such-task --format json`.
* Expected: CONTRACT 296–297 "`json` must always be valid, single-document JSON on stdout". `graph` does exactly this for its corrupt sources (missing/invalid/dir), so the behaviour is inconsistent between subcommands.
* Mitigating evidence: `flowview/tests/test_trace_source.py:56` asserts "a source error must not print a half-rendered document", i.e. the empty stdout is deliberate; the mismatch is between that choice and the absolute contract sentence (and README §2's "even when the source is corrupt: the document is still printed and the process exits 3").
* Falsified by: a JSON document (even a minimal issue-only one) on stdout, or contract wording scoped to "whenever a document exists".
* Confidence: **high** on observation, **medium** on whether the intended fix is code or docs.

**P1-3 · The documented `--width` guarantee does not hold; the CLI's own status/issue block overflows.**
* Repro: `.\.venv\Scripts\python.exe -m flowview graph --graph-file .tmp\verifier\adv\synth.json --width 60` → exit 0, but 1 line is **61** display columns: `         unrecognised status 'teleported'; showing 'unknown'.` (9-space indent added *after* wrapping, in `cli._wrap_line`/`_announce`).
* Worse at smaller widths: 40 → 47 cols, 30 → 38, 25 → 34, 20 → 29, 15 → 25, 10 → 21, 5 → 19, 1 → 19.
* Expected: CONTRACT 225 "never wider than `width` when `width > 0`" (README §3 repeats it). The suite only checks widths 40 (renderer only), 60/72/100 on issue-free fixtures, so it passes.
* Falsified by: no line over `--width` at any width ≥ 1.
* Confidence: **high**.

**P1-4 · A cyclic graph exits 0 and never carries the documented `graph.cycle` issue.**
* Repro: `.\.venv\Scripts\python.exe -m flowview graph --graph-file .tmp\verifier\adv\cycle2.json` (a→b→a) → exit **0**; `document.issues` = `[graph.node_status_missing ×2]`; no `graph.cycle`. Same for the self-loop. `--format mermaid` shows no cycle annotation at all.
* Partial credit: the cycle is *not* silent — text prints `graph : c, version 0, nodes 2, edges 2, layers n/a (cycle)` and `detail : cycle detected; no valid topological order`, and JSON exposes `graph_stats.cycles = [["a","b","a"]]` (asserted by the suite). `--strict` gives exit 3 only via the unrelated `node_status_missing` warnings.
* Expected: README §8 troubleshooting "`graph.duplicate_node` / `graph.cycle`, exit 3"; README §5 "a cycle is reported as `graph.cycle`"; CONTRACT `FlowCycleError` → exit 3. The `graph.cycle` code in `codes.py:80` is unreachable from the CLI because `graph_phases`/`text._layers_section` swallow `FlowCycleError` into prose.
* Falsified by: exit 3 on a non-strict cyclic graph with an `error graph.cycle` issue.
* Confidence: **high**.

**P1-5 · Permission errors are mislabelled `graph.undecodable` with UTF-8 advice.**
* Repro: ACL-deny read on a valid graph file (`icacls <file> /deny <user>:(R)`), then `graph --graph-file <file>` → exit 3, code **`graph.undecodable`**, message "Cannot read … as UTF-8 text: [Errno 13] Permission denied", hint "Re-export the file as UTF-8, or use `--format json` with a valid file."
* Expected: the documented `graph.unreadable` code (README §4 vocabulary) and a permissions hint. `graph.unreadable` is only produced when `stat()` itself fails, which is rare; the `open()`/read failure path catches `(OSError, UnicodeDecodeError)` together in `loader._read_text`.
* (`doctor` is unaffected: an existing-but-unreadable source prints `FAIL graph state …` and exits 3.)
* Falsified by: `graph.unreadable` (or a permission-specific hint) for a denied file.
* Confidence: **high**.

**P1-6 · A closed stdout pipe makes the process exit 120 with an `OSError` on stderr.**
* Repro (Python): `p = subprocess.Popen([py,'-m','flowview','graph','--format','text','--width','120'], stdout=PIPE, stderr=PIPE); p.stdout.close(); p.wait()` → returncode **120**; stderr `Exception ignored in: <_io.TextIOWrapper name='<stdout>' …> OSError: [Errno 22] Invalid argument`.
* Expected: CONTRACT's exit table (0/1/2/3) and "`print`/pipe safety": `cli._emit` does catch `(BrokenPipeError, OSError)` and `main` maps `BrokenPipeError` to `EXIT_OK`, but the buffered `TextIOWrapper` is still flushed at interpreter shutdown, which raises and sets 120. The existing test (`test_cli_contract.py:278`) only asserts `returncode != 1` and "no traceback", so it passes.
* Falsified by: exit 0 with no stderr noise on an early-closed pipe (e.g. `os._exit`/stdout detach after a broken write).
* Confidence: **high** on the observation; **medium** on severity (no data loss, only a confusing exit code/stderr line).

**P1-7 · On the same large graph, `--format json` emits an `error` issue and `exit_code_hint: 3` while the process exits 0, and silently drops `graph_stats`.**
* Repro: `.\.venv\Scripts\python.exe -m flowview graph --graph-file .tmp\verifier\adv\big3000.json --full --format json` → exit **0**; payload top keys `['flowview_schema','document','phases','issues','exit_code_hint']` with `exit_code_hint: 3` and top-level `issues = [{"severity":"error","code":"render.json_failed","message":"JSON rendering fell back to a minimal payload: RecursionError: maximum recursion depth exceeded", …}]`; `graph_stats` absent (though `JsonRenderer`'s docstring promises it "when those parts exist"); `document.graph` still carries all 3000 nodes; `document.issues` are 3000 `graph.node_status_missing` warnings.
* Cause: `JsonRenderer.render_document` catches the `RecursionError` from `analysis.document_payload → graph_stats → find_cycles` and substitutes `_fallback_payload` (jsonout.py:104–107). The fallback issue is injected into the *rendered payload only*, while `cli.command_graph` computes the exit code from `document.all_issues()` — so one run simultaneously says "error, exit 3" and "exit 0".
* Expected: one consistent signal — either a non-zero exit (3) with the error issue, or a 0 exit with no error issue; and the documented `graph_stats` should not vanish silently.
* Falsified by: a run whose payload and exit code agree, or an `exit_code_hint` that matches the process exit.
* Confidence: **high** (payload parsed and printed above).

### P2 — cosmetic / lower impact

| # | Finding | Evidence |
| --- | --- | --- |
| P2-1 | `summary --limit 0` (and `--limit -3`) silently shows **1** task, exit 0, no note (`max(1, limit)` in `cli.command_summary`). Docs say "shows the newest `--limit N` tasks". Repro: `summary --format json --limit 0` → `meta.tasks=1`. | observed |
| P2-2 | `--width -5` silently disables wrapping (renderer is constructed with `width=-5`; only the announce block clamps). Lines up to 168 columns, exit 0 — inconsistent with `--width 1`/`0`. | observed |
| P2-3 | An unknown `--status teleported` is not validated: the filter yields an empty graph with an INFO `filter.applied` and exit 0, which can look like an empty workspace. | observed |
| P2-4 | README §2 footnote (lines 66–68) says "CONTRACT.md also lists exit 1 for `doctor` ('broken sources')"; CONTRACT line 293 says "0 healthy, 3 any diagnosed problem …, **1 never**". Two inside-the-deliverable docs contradict each other. | both files read |
| P2-5 | `TextRenderer.__init__` takes an extra `legend: bool = True` not present in CONTRACT's frozen signature (`MermaidRenderer`/`JsonRenderer` match exactly). Harmless superset, but the frozen interface is not exact. | `inspect.signature` |
| P2-6 | `graph --graph-file <path-with-a-typo>` and `--data-root <missing-root>` exit **0** with `graph.missing_file` (info). Documented for the default path, but for an explicitly named path a typo is indistinguishable from a working empty workspace. | observed |
| P2-7 | The documented ASCII `+-|` fallback cannot trigger: `cli.configure_stdout()` reconfigures stdout to UTF-8 before the renderer consults `style.can_encode()`, so with `PYTHONIOENCODING=ascii` the output is still UTF-8 box-drawing. | observed + `style.can_encode` exists |
| P2-8 | Mermaid output for a cyclic graph carries no `%% ISSUE`/cycle annotation while text and JSON do (folded into P1-4). | observed |

---

## 8. What I could NOT verify (and why)

1. **Python 3.11 support** (README: "works on Python 3.11+"). Only 3.12.13 (venv) and 3.13 (PATH) exist here; both pass. 3.10/3.11 unverified.
2. **`--out` writing *into* `data/`** — the documented single write exception. I deliberately did not run it, to keep the read-only proof clean. Verified only for `.tmp\verifier`.
3. **TTY-dependent behaviour**: colour auto-detection and `doctor`'s `isatty` line were only exercised with redirected stdout (`isatty False`); no real interactive console was used.
4. **The `boxes→ASCII` fallback under a genuine legacy code page** (e.g. `chcp 437` with a console): I could only simulate via `PYTHONIOENCODING` (P2-7).
5. **Live backend adapter paths** (`schema_document`, `live_graph_document`, `dry_route`): no CLI subcommand exposes them; only `doctor` calls `backend_available()`. I did not call `dry_route` to avoid any backend side effect, so its read-only claim is unverified by me.
6. **Attribution of the external append** to `data/audit/task_summaries.jsonl` (section 5). "Not FlowView" is proven; the actual writer (a pre-existing backend/dependency process, or a parallel agent action) I could not identify.
7. **The other agents' concurrent work**: I do not know which teammate (if any) was active during my sweep, so any repo file outside my declared scopes that changed during the window is not attributable to FlowView or to me.
8. **`--strict` on a cyclic graph as a cycle test**: exit 3 there is produced by unrelated `node_status_missing` warnings, so a graph whose nodes *do* carry statuses would still exit 0 on a cycle (P1-4). I verified the exit-3 case but not a "statuses present + cycle" fixture.

---

## 9. Reproducing this evidence

* Fixtures (kept): `.tmp\verifier\adv\` — including `deep_5000.json`, `big3000.json`, `trueloop.json`, `synth.json`, `cycle2.json`, `selfloop.json`, the ACL-denied file and the denied `dataroot\`.
* Harness scripts (kept): `.tmp\verifier\harness\` — `cli_matrix.py`, `adv_matrix.py`, `probe2.py`, `probe3.py`, `indep.py`, `blockrun.py`, `read_sweep.py`, `readonly.py`; raw outputs `cli_matrix.json`, `adv_results.json`, `probe2.json`, `probe3.json`, `independence.txt`, `read_sweep.json`, `readonly.json`, `baseline_data.csv`.
* Re-run a P0/P1 repro:
  ```powershell
  .\.venv\Scripts\python.exe -m flowview graph --graph-file .tmp\verifier\adv\deep_5000.json   # expect exit 1, 0 bytes stdout
  .\.venv\Scripts\python.exe -m flowview graph --graph-file .tmp\verifier\adv\big3000.json --full --format text   # expect exit 1, partial output
  .\.venv\Scripts\python.exe -m flowview graph --graph-file .tmp\verifier\adv\big3000.json --full --format json   # expect exit 0 + render.json_failed + exit_code_hint 3
  .\.venv\Scripts\python.exe -m flowview graph --graph-file .tmp\verifier\adv\trueloop.json   # expect exit 1, RuntimeError
  .\.venv\Scripts\python.exe -m flowview graph --graph-file .tmp\verifier\adv\synth.json --width 60   # expect a 61-column line
  .\.venv\Scripts\python.exe -m flowview doctor --format json   # expect text, exit 0
  .\.venv\Scripts\python.exe -m flowview graph --graph-file .tmp\verifier\adv\cycle2.json ; echo "exit=$LASTEXITCODE"   # expect 0 and no graph.cycle issue
  ```

* Two fixtures are platform-dependent and may need recreating: `trueloop.json` (a symbolic link to itself; requires the privilege to create symlinks) and the ACL-denied file/`dataroot\` (`icacls <file> /deny <user>:(R)`).

---

# Re-verification round 2 (after the Lead's fixes)

> Note: the inline `# expect …` comments in §9 describe the **pre-fix** state (they are the round-1 repro expectations). The post-fix expectations are in §10; e.g. `deep_5000.json` now exits 3, `big3000 --full` exits 0, `trueloop.json` exits 3, `--width 60` is honoured exactly, `doctor --format json` is real JSON, and a cycle is reported as a warning.

Re-verified on the same task-5 scope (this file only; no implementation edits). Files the Lead changed: `analysis.py`, `model.py`, `loader.py`, `cli.py`, `CONTRACT.md`, `README.md`, plus `tests/test_trace_source.py` and `tests/test_cli_contract.py`. New harness output: `.tmp\verifier\round2_probe.{json,txt}`, `round2_followup.json`, `independence_r2.txt`, `adv_matrix_r2.txt`, `repo_unittest_r2.txt`.

**Round-2 headline:** the 3 P0s are **fixed** (all three repros now exit 3 or 0 with real output and no traceback), and **6 of 7 P1s are fixed**. One P1 is **partial** (P1-3: `--width` is exact for N ≥ 20, but a new undocumented 20-column floor still breaks the absolute doc claim below 20). The same P0 class **recurs on a different option**: `--data-root` pointed at a symlink loop still exits 1 (**new P0**), and `--out` into a symlink loop exits 1 (**new P1**). Two new P1/P2 doc mismatches and one coverage gap are listed below. Test suites stayed green (167 / 300 / 167+295) and the flowview tests were **not** covertly weakened.

## 10.1 P0 re-check

| # | Repro (exact) | Round 1 | Round 2 observed | Verdict |
| --- | --- | --- | --- | --- |
| P0-1 | `graph --graph-file .tmp\verifier\adv\deep_5000.json --format text\|json\|mermaid` | exit 1, 0 B stdout, `RecursionError` | exit **3**; 2,720 / 4,819 / 1,294 B; valid JSON with `graph.too_deep`; no traceback, even with `-v` | **FIXED** |
| P0-1b | depths 2500 / 3000 and nested-object 5000 (`d_2500.json`, `d_3000.json`, `deepobj5k.json`) | 3000+ → exit 1 | all exit **3**, valid JSON | **FIXED** |
| P0-2 | `graph --graph-file .tmp\verifier\adv\big3000.json --full` | text exit 1 after 2.0 MB; mermaid `-v` exit 1 | text exit **0** (2,217,295 B), json exit **0** (6,711,342 B valid), mermaid exit **0** (201,722 B), mermaid `-v` exit **0** (553,690 B); capped run unchanged (exit 0) | **FIXED** |
| P0-3 | `graph --graph-file .tmp\verifier\adv\trueloop.json --format text\|json\|mermaid` | exit 1, 0 B stdout, `RuntimeError: Symlink loop` | exit **3**; 3,123 / 5,058 / 1,396 B; valid JSON with `path.symlink_loop`; no traceback | **FIXED** (for `--graph-file`; see R2-P0-1 for `--data-root`) |

Iterative `find_cycles` correctness (the risky rewrite) — checked against six fixtures, `--format json`:

| Fixture | Expected | Observed (`graph_stats.cycles`) | `graph.cycle` issue | exit / `--strict` |
| --- | --- | --- | --- | --- |
| 2-cycle a↔b | 1 | `[["a","b","a"]]` | yes (warning) | 0 / 3 |
| 3-cycle a→b→c→a | 1 | `[["a","b","c","a"]]` | yes | 0 / 3 |
| self-loop a→a | 1 | `[["a","a"]]` | yes | 0 / 3 |
| two disjoint 2-cycles | 2 | `[["a","b","a"],["c","d","c"]]` | yes | 0 / 3 |
| diamond (no cycle) | 0 | `[]` | no | 0 (3 only via `multiple_edges_into_port`) |
| tail + 2-cycle | 1 | `[["a","b","a"]]` | yes | 0 / 3 |
| **1200-node cycle + self-loop, `--full`** | 2 | lengths `[2, 1201]` — both found | yes | 0 / 3 |

No deep-recursion failure anywhere; the long-chain cycle is detected correctly (a recursive DFS could not have done this).

## 10.2 P1 re-check

| # | Finding | Round 2 evidence | Verdict |
| --- | --- | --- | --- |
| P1-1 | `doctor` ignored `--format` | `doctor --format json` → valid one-document JSON, 7,132 B, exit 0, `document.meta.mode="doctor"`, phases `sources/renderers/adapter/terminal`. `doctor --format mermaid` → still the 882 B **text** report | **FIXED for json / PARTIAL** (mermaid still text, no doc carve-out; see R2-P2-1) |
| P1-2 | json prints nothing on hard source errors | all 8 hard cases (`flow` missing/blank/non-UTF-8, `summary` missing/empty/fake task, `graph` dir/`[]`) now emit one valid JSON doc on stdout, exit 3, diagnosis inside `issues` (e.g. `trace.missing_file` error, `exit_code_hint: 3`). `text` mode still prints 0 B on stdout, error on stderr | **FIXED** |
| P1-3 | documented `--width` guarantee | widths 20/25/30/40/60 → max display width **exactly** the requested value, **0** over-wide lines. Widths 15/10/5/1/-5 → clamped to 20 with exactly one stderr note (`--width 5 is below the 20-column minimum; using 20.`); width 0 → natural 168. Renderers and the trailing issue block are all inside the bound now | **PARTIAL** — exact for N ≥ 20; below 20 the documented absolute guarantee is still false and the floor is documented nowhere (see R2-P1-2) |
| P1-4 | cyclic graph exit 0, no `graph.cycle` | `graph.cycle` **warning** now present in text, mermaid (`%% ISSUE WARNING graph.cycle: …`) and json for every cycle fixture; exit 0 non-strict, exit 3 under `--strict` | **FIXED** |
| P1-5 | permission error mislabelled `graph.undecodable` | ACL-denied file → `error graph.permission_denied`, exit 3. Explicit `--graph-file` missing → `error graph.missing_file`, exit 3; default never-created path → `info graph.missing_file`, exit 0 | **FIXED** |
| P1-6 | closed stdout pipe → exit 120 + `OSError` | the exact round-1 harness (Popen with `stdout=PIPE`, close the read end, wait) for `graph --format mermaid`, `flow --format text`, `graph --format text --width 120` → all exit **0**, stderr **0 bytes**, no "Exception ignored" | **FIXED** (independent confirmation: I reproduced 120 reliably in round 1; it is gone) |
| P1-7 | json degraded to `render.json_failed` + `exit_code_hint: 3` with exit 0 | `graph --graph-file big3000.json --full --format json` → exit 0, `exit_code_hint: 0`, `graph_stats` present (`cycles: []`), top-level `issues` are only the 3000 `graph.node_status_missing` warnings, **no** `render.json_failed` | **FIXED** |

P2 re-checks: `summary --limit 0` / `--limit -3` → `cli.limit_clamped` warning and 1 task (documented behaviour now visible) — **fixed as intended**; `--status teleported` → `filter.unknown_status` warning — **fixed**; `--width -5` → clamped to 20 with the note — **fixed** (same floor caveat); the ASCII `+-|` fallback under `PYTHONIOENCODING=ascii` still emits UTF-8 box-drawing (README §8 still claims the fallback) — **STILL OPEN (R2-P2-2)**.

## 10.3 Regression sweep

| Check | Command | Result |
| --- | --- | --- |
| flowview suite (venv) | `.\.venv\Scripts\python.exe -m unittest discover -s flowview/tests -t . -v` | `Ran 167 tests in 16.919s` / `OK` (was 166; +1 added test) |
| repo suite (venv) | `.\.venv\Scripts\python.exe -m unittest discover -v` | `Ran 300 tests in 20.070s` / `OK (skipped=4)` (was 299; the 4 skips are the env-gated JEV/LLM tests) |
| pytest (PATH python 3.13) | `python -m pytest flowview/tests -q` | `167 passed, 295 subtests passed in 15.90s` |
| independence matrix | 36 blocked runs (`harness\indep.py` / `blockrun.py`: ImportError **and** RuntimeError variants) | 36/36 exit 0, 0 tracebacks; graph/flow/summary stdout byte-identical across modes. Only `doctor` differs (by design: the adapter line and its JSON phase report the offline degradation). `import flowview` → `[]` backend modules; graph/summary CLI runs → `[]`; doctor imports `backend.*` deliberately |
| read-only sweep | 30-command full sweep with before/after `(size, mtime_ns, sha256)` on all 12 `data/`+`config/` files | `files: 12, commands: 30, identical: true, changed: [], nonzero_exits: []` |
| adversarial matrix | 36 cases × 3 formats (`harness\adv_matrix.py`, re-run because `cli.py` changed) | 108 runs, **0 tracebacks, 0 exit-1s** (round 1: 4 exit-1s); distribution `{0: 51, 3: 57}` (round 1: `{0: 53, 1: 4, 3: 51}`). Behaviour changes vs round 1 are the intended ones: deep nesting 1→3, 3000-node `--full` text 1→0, explicit missing `--graph-file` 0→3 |
| new files | repo inventory vs round-1 baseline | 69 new files: 65 in `.tmp\verifier` (my scratch), 2 in `.tmp\leadcheck` (the Lead's), 2 in `flowview/` (`client.cpython-312.pyc`, `VERIFICATION.md`). **0 outside `flowview/` and `.tmp/`** |

`data/audit/task_summaries.jsonl` again grew from an external writer during the window: 198 → 206 lines, 200,390 → 207,602 B, sha256 `1D75E791…` → `8443CDE942A1…`, mtime 19:01:53 (last record `route-eis`, status `routed`, trace `78c6f1dd…`). **Not FlowView** — the 30-command sweep left every file identical, including this one. The other 11 `data/`+`config/` files are byte-identical to the round-1 baseline. Attribution of the external writer remains unverified (same caveat as §5).

## 10.4 Audit of the changed/added tests (covert weakening?)

| Test | Now asserts | Assessment |
| --- | --- | --- |
| `test_trace_source.py::test_trace_path_that_is_a_directory_is_exit_3` | exit 3, `flowview_schema == "1.0"`, `payload["issues"]` non-empty, `document.trace is None` | **Not a covert weakening of a guarantee** — the exit code and no-traceback expectations are intact and the JSON assertions are new/stronger. It does drop the *specific issue code* for this path (the CLI now says `trace.permission_denied`, see R2-P2-3), which no other test pins |
| `test_cli_contract.py::test_unusable_trace_source_is_exit_3_without_a_traceback` | exit 3, no traceback, valid JSON doc, `issues` non-empty, `document.meta` has `mode` | Same shape; the guarantee (exit 3, no traceback) is preserved and JSON is strengthened |
| `test_cli_contract.py::test_unusable_trace_source_prints_nothing_in_text_mode` (new) | exit 3, no traceback, **empty stdout in text mode** | Keeps the round-1 guarantee pinned; this is the assertion that would have caught an over-broad fix. Genuinely additive |
| `test_graph_source.py::test_graph_path_that_is_a_directory_is_an_error_and_exit_3` (unchanged file) | still pins `graph.is_directory` | Directory diagnosis for **graphs** remains covered |

Honest caveat: `flowview/` is untracked, so I cannot diff the previous text of the two changed tests against git history; the judgement above is based on the current assertions versus the guarantees they are supposed to protect. On that basis I found **no** weakening — but the new error paths themselves are untested (R2-P2-4).

## 10.5 New findings (round 2)

### P0

**R2-P0-1 · `--data-root` pointing at a symlink loop still escapes as exit 1 (`RuntimeError`).**
* Repro: create a self-referential symlink (`trueloop.json`, or a directory self-symlink `dirloop`), then `.\.venv\Scripts\python.exe -m flowview graph --data-root .tmp\verifier\adv\trueloop.json --format text`.
* Observed: **exit 1** for `graph`, `doctor`, `summary` and `flow`; stdout 0 B in text mode and a 1,178 B JSON error document in json mode; stderr `FlowView 0.1.0: unexpected internal error: RuntimeError: Symlink loop from '…\trueloop.json'`; with `-v` the traceback is `cli.py:754 main` → `cli.py:697 dispatch` → `str(Path(data_root).expanduser().resolve())`. A **directory** self-symlink reproduces identically, so this is not only a weird file input.
* Expected: the same treatment the loader now gives `--graph-file` (`path.symlink_loop`, exit 3) — `loader.resolve_path` / `_safe_resolve` exist but `dispatch` bypasses them.
* Falsified by: `--data-root <loop>` exiting 3 with a `path.symlink_loop`/`path.invalid` issue (or 0 with a readable message).
* Confidence: **high**.

### P1

**R2-P1-1 · `--out` into a symlink loop exits 1 (`FileExistsError`) instead of a readable issue.**
* Repro: `.\.venv\Scripts\python.exe -m flowview graph --out ".tmp\verifier\adv\trueloop.json\x.txt"` → exit **1**, `unexpected internal error: FileExistsError: [WinError 183] …` from `cli._emit`'s `path.parent.mkdir(parents=True, exist_ok=True)` (cli.py:221). (A plain nonexistent nested parent still works: exit 0 + notice.)
* Expected: exit 3 with a readable issue (the CLI's own contract for input problems), not "unexpected internal error".
* Falsified by: exit 3 with an issue, or a graceful refusal.
* Confidence: **high** on observation; medium on severity (only a pathological `--out` parent).

**R2-P1-2 · The 20-column `MIN_WIDTH` floor is undocumented, so the frozen `--width` sentence is still literally false.**
* Repro: `graph --graph-file .tmp\verifier\adv\synth.json --width 5` → exit 0, all lines ≤ **20** columns (one stderr note), i.e. wider than the requested 5.
* Docs: CONTRACT line 225 "Text output rules: never wider than `width` when `width > 0`", CONTRACT line 300 "`--width N` bounds every stdout line the CLI emits", README §3 "never wider than `--width` when set" — none mentions the floor. A grep for `MIN_WIDTH|minimum|20-column` finds the constant only in `cli.py`.
* Expected: either honour tiny widths, or document `MIN_WIDTH = 20` in CONTRACT/README and mention the one-time stderr note.
* Falsified by: a documented floor (or exact output at `--width 5`).
* Confidence: **high**.

### P2

| # | Finding | Evidence |
| --- | --- | --- |
| R2-P2-1 | `doctor --format mermaid` still prints the 882 B text report (only `json` is special-cased in `command_doctor`); no doc says mermaid is the human layout for doctor | observed |
| R2-P2-2 | The ASCII `+-|` fallback is still unreachable: with `PYTHONIOENCODING=ascii` the run emits UTF-8 box-drawing (`decodes_as_ascii: False`, `contains_box: True`), because `configure_stdout()` forces UTF-8 first; README §8 still promises the fallback | observed |
| R2-P2-3 | A **directory** passed to `--from-file` is diagnosed as `trace.permission_denied` with the message "FlowView is not allowed to read `<dir>`" — misleading, and `trace.permission_denied` is absent from README's Trace vocabulary (line 378, which lists `trace.unreadable` etc.). `graph.permission_denied` *is* documented | observed + README line 378 |
| R2-P2-4 | **Coverage gap:** no test in `flowview/tests/**` references `graph.too_deep`, `path.symlink_loop`, `graph.permission_denied`, `trace.permission_denied`, `cli.limit_clamped`, `filter.unknown_status` or `render.failed`. The P0/P1 fixes are therefore unguarded against regression (my round-2 probe is currently the only check) | grep over `flowview/tests` |
| R2-P2-5 | README line 386 example "`graph file missing -> exit 0 (info)`" is now only true for the *default* path; an explicit `--graph-file` typo exits 3 (line 558 documents this, line 386 does not) | observed + README 386/558 |

## 10.6 Round-2 doc/behaviour cross-check

| Doc claim (updated files) | Evidence | Verdict |
| --- | --- | --- |
| CONTRACT 296–299: "json must always be valid, single-document JSON on stdout … including on failure: when a source is unusable, `--format json` still emits one error document" | 8 hard-error cases all emit one valid doc, exit 3, diagnosis inside `issues` | **TRUE** |
| CONTRACT 299–300: "In `text` mode a source error is reported on stderr with an empty stdout" | all 8 text-mode cases: 0 B stdout, readable stderr | **TRUE** |
| CONTRACT 300–301: "`--width N` bounds every stdout line the CLI emits, including the trailing status/issue block" | exact for N ≥ 20 (renderer + block); violated below 20 by the undocumented floor | **PARTIAL (R2-P1-2)** |
| CONTRACT/README path + graph codes: `path.symlink_loop`, `path.invalid`, `graph.permission_denied`, `graph.too_deep` | all four observed exactly as documented (exit 3) | **TRUE** |
| README §8: "`graph.cycle` (warning), exit 0 … `--strict` turns this into exit 3" | verified on 7 fixtures | **TRUE** |
| README §8: "`graph.missing_file` (info), exit 0" vs "(error), exit 3 for `--graph-file`" | verified both branches | **TRUE** |
| README §4 vocabulary includes `filter.unknown_status`, `cli.limit_clamped`, `render.failed`, `flowview.internal_error`, `doctor.problems` | each observed (except `doctor.problems`, triggered by round 1's denied-root doctor run: exit 3) | **TRUE** |
| README §4 Trace vocabulary completeness | `trace.permission_denied` emitted but not listed | **FALSE (R2-P2-3)** |
| README §7: `client.py` is a deliberate transport adapter, "not wired into the CLI yet: no subcommand contacts the network" | code/CLI inspection: no CLI subcommand calls `client.*`; all offline runs, including blocked-backend processes, make no network calls | **TRUE** as documented |
| README §3 text guarantee + §8 ASCII fallback | see P1-3 partial and R2-P2-2 | **PARTIAL / FALSE** |

## 10.7 What I could not verify in round 2

1. **The previous text of the two changed tests** — `flowview/` is untracked, so there is no VCS diff; my weakening audit is based on the guarantees the current assertions protect, not on a textual diff.
2. **`detach_broken_stdout()` on a real console/TTY** — my broken-pipe repros all use redirected pipes; a genuine `isatty` console could behave differently (the fix rebinds `sys.stdout`/`sys.stderr` to `os.devnull`, which I did not exercise interactively).
3. **Whether the new error-path codes conflict with the backend-adapter path** (`flowview.source_unusable`, `flowview.internal_error`) — I only saw them by forcing internal errors, not in a real backend outage.
4. **Attribution of the external `data/audit/task_summaries.jsonl` growth** (198 → 206 lines during the window). "Not FlowView" is proven by the sweep hash; the writer is still unidentified.
5. **`--out` into a symlink loop in JSON mode** — I verified text mode only (the failure is in `_emit`'s mkdir, which precedes format handling, so json should behave the same; not separately executed).

Round-2 confidence: R2-P0-1, R2-P1-1, R2-P1-2 and all `FIXED` verdicts are **high** (direct repro + code locations); R2-P2-4 is **high** for the grep result; the weakening audit is **medium** (no VCS diff available).

---

# Round 3 confirmation (deltas only)

Scope: exactly the three round-2 findings the Lead fixed, the P0 non-regression, the doc spot-checks, and whether the new test module can catch a revert. Same rules (this file is the only file I edit). Harness: `.tmp\verifier\round3_probe.{json,txt}`, `harness\make_r3_fixtures.py`, plus `%TEMP%\fvverify\{round3_probe.py,symcheck.py,mutation_check.py}`. Note: the round-2 adversarial re-run had wiped my `synth.json` / `deep_5000.json` / `trueloop.json` fixtures, so I rebuilt them first (`harness\make_r3_fixtures.py`, and the two symlinks via `pwsh`, which holds the symlink privilege that the sandboxed Python lacks).

**Round-3 headline:** all three R2 findings are **FIXED**, the earlier P0s did **not** regress, and the new test module is strong enough to catch a revert of each fix. One **new P1** surfaced: the `--data-root` fix's early return bypasses `emit_error_document`, so `--format json` now prints **0 bytes** on stdout for that failure — contradicting the CONTRACT sentence ("so a JSON consumer never sees an empty stream") and regressing round-2's json behaviour (which did emit a document). One **P2** test-quality bug: the new symlink helper can never report success on Windows, so both symlink hardening tests skip even where symlinks can be created.

## 11.1 The three R2 deltas

| R2 finding | Repro | Round 2 | Round 3 observed | Verdict |
| --- | --- | --- | --- | --- |
| R2-P0-1 `--data-root` loop | `graph/doctor/summary/flow --data-root .tmp\verifier\adv\dirloop` (real directory self-symlink; `resolve()` raises `RuntimeError`) | exit 1, traceback with `-v` | exit **3** for all 4 subcommands × text/json; no traceback; stderr `FlowView 0.1.0: --data-root could not be resolved (Symlink loop from '…\dirloop'); the path is a symlink loop.` A file self-symlink behaves the same | **FIXED** |
| R2-P1-1 `--out` broken path | `graph --out .tmp\verifier\adv\dirloop\x.txt` | exit 1, `FileExistsError` as "unexpected internal error" | exit **3**, no traceback, stderr `cannot write … FileExistsError … Check the path; FlowView creates parent directories but not symlink loops.` Also verified in **JSON mode**: exit 3 (your unverified case — confirmed). `--out` with an existing *file* as parent (`synth.json\x.txt`) → exit 3. Normal nested `--out` (`out3\a\b\c.txt`) → exit **0** + notice | **FIXED** |
| R2-P1-2 width floor docs | grep CONTRACT/README | absolute `--width` claim, no floor | CONTRACT 225–227: "never wider than `width` when `width >= MIN_WIDTH` … `MIN_WIDTH = 20` is the floor: a narrower request is raised to 20 and the reason is printed once to stderr"; README §3 format matrix: "never wider than `--width` when set (down to the 20-column floor)"; single definition in `cli.MIN_WIDTH` with `analysis.min_width_floor()` reading it lazily | **FIXED** |

Width behaviour re-confirmed against the docs: `--width 60` → max 60; `--width 20` → max 20; `--width 15` and `--width 5` → max 20 + one `--width N is below the 20-column minimum; using 20.` stderr line; all exit 0.

## 11.2 P0 non-regression, suites, read-only

| Check | Observed |
| --- | --- |
| P0-1 `deep_5000.json` | exit **3** ×3 formats (text 2,720 B / json 4,819 B valid `graph.too_deep` / mermaid 1,294 B), no traceback |
| P0-2 `big3000.json --full` | exit **0** ×3 formats (text 2,217,295 B / json 6,711,342 B valid, `exit_code_hint: 0` / mermaid 201,722 B), no traceback |
| P0-3 `trueloop.json` | exit **3** ×3 formats (text 3,123 B / json 5,058 B valid `path.symlink_loop` / mermaid 1,396 B), no traceback |
| flowview suite | `.\.venv\Scripts\python.exe -m unittest discover -s flowview/tests -t .` → `Ran 187 tests in 22.950s` / `OK (skipped=2)` |
| repo suite | `.\.venv\Scripts\python.exe -m unittest discover -v` → `Ran 320 tests in 25.965s` / `OK (skipped=6)` (4 env-gated JEV/LLM + the 2 symlink skips) |
| read-only sweep | 30 commands, 12 `data/`+`config/` files → `identical: true, changed: 0, nonzero_exits: 0` |

## 11.3 Doc spot-check

| Check | Result |
| --- | --- |
| Width floor documented | **YES** — CONTRACT 225–227, README §3 line 336; `MIN_WIDTH` defined once in `cli.py` and read lazily via `analysis.min_width_floor()` |
| Absolute `--width` claim removed | **effectively YES.** The only unqualified survivor is CONTRACT 302 "`--width N` bounds every stdout line the CLI emits, including the trailing status/issue block" — the floor is defined 76 lines earlier in the same file, so I read it as inheriting `max(N, 20)`. Nit only, not a finding |
| Old `graph.missing_file` exit claim | **GONE** — README now splits it (386 default never-created → exit 0; 387 explicit `--graph-file` miss → exit 3; 563/564 troubleshooting split likewise) |
| Old `graph.cycle` exit-3 claim | **GONE** — README 395 "graph contains a cycle → exit 0 (warning); with `--strict` → exit 3"; 565 troubleshooting "(warning), exit 0" |
| JSON-always-answers prose | CONTRACT 298–301 "`json` must always be valid, single-document JSON on stdout … so a JSON consumer never sees an empty stream" → **violated by the new `--data-root` path (R3-P1-1)**; README 402's example list covers "hard source error" cases only |

## 11.4 New finding

**R3-P1-1 · `--format json` prints nothing when `--data-root` cannot be resolved (new `dispatch` early return bypasses `emit_error_document`).**
* Repro: `.\.venv\Scripts\python.exe -m flowview graph --data-root .tmp\verifier\adv\dirloop --format json`.
* Observed: exit **3**, **stdout 0 bytes**, message only on stderr. Same for `doctor`, `summary`, `flow`. (Text mode's empty stdout is documented and correct; json mode's is not.)
* Expected: one valid JSON error document on stdout, per CONTRACT 296–301 ("`json` must always be valid, single-document JSON on stdout … including on failure … so a JSON consumer never sees an empty stream").
* Regression note: in round 2 the identical command produced a 1,178 B JSON error document (with exit 1). The exit code improved but the document disappeared — a json consumer now gets an empty stream where it previously got data.
* Cause: `cli.dispatch` returns `EXIT_SOURCE` at line 731 after printing to stderr; `main`'s `except FlowViewError/Exception` handlers (which call `emit_error_document`) never run. `test_hardening.JsonAlwaysAnswersTests` does not cover `--data-root`.
* Falsified by: any stdout document for that command (e.g. route the message through `emit_error_document` or a `FlowSourceError`).
* Confidence: **high** (direct repro + code path).
* P2 companion: the same shape applies to a failed `--out` in json mode (exit 3, 0 B stdout) — less clearly a violation because `--out` redirects the document to a file, but a consumer piping json to stdout still sees nothing.

**R3-P2-1 · The new symlink helper can never report success on Windows, so both symlink hardening tests skip even where symlinks can be created.**
* Repro: create a self-referential link with `mklink` from a shell that holds the privilege, then evaluate the helper's check: `cmd /c mklink <link> <link>` → `rc=0`, but `link.exists()` → **False** (a self-loop can never be resolved), so `make_symlink` returns `rc == 0 and link.exists()` → **False** and the test calls `skipTest`.
* Evidence: `mklink` for both a file self-loop and a directory self-loop returned 0 (created), while `exists()=False`, `is_symlink()=True`, `os.path.lexists()=True`. The correct success check is `os.path.lexists(link)` (or `link.is_symlink()`).
* Consequence: `test_graph_path_that_is_a_symlink_loop_is_diagnosed` and `test_data_root_that_is_a_symlink_loop_is_diagnosed` are inert on Windows — including on privileged CI — exactly where R2-P0-1 could regress. In *this* sandbox the skip is additionally legitimate (`os.symlink` → WinError 1314 and `mklink` rc=1 from the sandboxed token), so nothing is mis-reported here; the bug bites on a machine that **can** create links. The `os.symlink` path on POSIX returns `True` before the `exists()` check, so POSIX tests do run.
* Falsified by: a self-loop created via `mklink` followed by `make_symlink(...) == True`.
* Confidence: **high** (direct process evidence).

## 11.5 Is the new test module strong enough? (answer to (d))

Mutation check (`%TEMP%\fvverify\mutation_check.py`): the pre-fix behaviour is re-created in-process by monkeypatching — no implementation file touched — and `cli.main()` is called exactly as the tests call it.

| Mutation (revert) | Baseline | Mutated result | Test that would fail |
| --- | --- | --- | --- |
| `resolve_data_root` reverted to inline `Path.resolve()` | exit 3 | exit **1** | `test_data_root_that_is_a_symlink_loop_is_diagnosed` (`assert_exit(proc, 3)`) |
| `_emit` reverted to the unguarded `--out` write | exit 3 | exit **1** | `test_out_into_a_broken_path_reports_a_source_error` (`assert_exit(proc, 3)`) |
| (from round 1, by construction) recursive `find_cycles` | exit 0 | exit 1 | `test_a_long_chain_survives_every_format_with_full` (`assert_exit(..., 0)` + no `RecursionError`) |
| (from round 1, by construction) `parse_json_text` without `RecursionError` | exit 3 | exit 1 | `test_deeply_nested_json_is_a_diagnosed_error_not_a_recursion_crash` (`assert_exit(proc, 3)` + `graph.too_deep`) |
| width clamp/floor removed | ≤20 + note | over-wide / no note | `test_narrow_widths_are_bounded_and_announced` |

Per-fix coverage: `graph.too_deep` **covered**; long chain / long cycle **covered** (the cycle test even pins the exact 1201-entry length); `graph.cycle` visibility + strict **covered**; `path.symlink_loop` file and `--data-root` loop **asserted but inert on Windows** (R3-P2-1); `--out` broken path **covered**; explicit vs default missing graph **covered**; json-always-answers for the three hard source errors + blank trace + doctor **covered**; `filter.unknown_status` (positive+negative) and `cli.limit_clamped` **covered**; width floor/exactness **covered**.

Honest gaps: (1) the two symlink tests cannot actually execute on Windows (R3-P2-1); (2) `JsonAlwaysAnswersTests` has no `--data-root` case, which is precisely why R3-P1-1 slipped through; (3) the changed round-2 tests still cannot be textually diffed (untracked files).

## 11.6 Not verified in round 3

1. The symlink assertions themselves could not be executed here (both creation routes fail in the sandbox); I verified the same CLI behaviour directly instead, which is what the tests assert.
2. The POSIX branch of `make_symlink` (untestable on Windows) — it returns before the buggy `exists()` check, so I expect it to work, but I did not run it.
3. The external `data/audit/task_summaries.jsonl` writer (unchanged from §5/§10.3; the 30-command sweep again left it identical).
4. `--out` failure in json mode deliberately emitting nothing rather than an error document — I report it as P2 because `--out` semantics are file-oriented; whether the CONTRACT's "always" covers it is a judgement call for the Lead.

Round-3 confidence: all three `FIXED` verdicts, the non-regression and the doc checks are **high**; R3-P1-1 and R3-P2-1 are **high** (direct repro/process evidence); the mutation conclusions are **high** for the two patched fixes and **inferred** for the two round-1 fixes.

---

# Round 4 final confirmation (R3 deltas only)

Scope: R3-P1-1, R3-P2-1, the `--out` pin, the two suites, and a P0 spot check. Appended as requested; no implementation/test/doc file touched.

**Revision caveat (important):** the deliverable moved while I was verifying it. `analysis.py` (19:13:26), `jsonout.py` (19:13:23) and `test_hardening.py` (19:13:35) all changed *after* my first round-4 pass, and the extra test (`test_exit_code_hint_matches_the_process_exit_code`) is what turns 189 into 190. **Every number below is from the state at ~19:18**, re-run after those edits. Any further edit invalidates this section.

## 12.1 R3-P1-1 — FIXED

`--data-root .tmp\verifier\adv\dirloop` (real directory self-symlink; `resolve()` raises `RuntimeError`):

| Command | Exit | stdout | JSON valid | Issues | Code | `exit_code_hint` | Traceback |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `graph --format json --data-root <loop>` | 3 | 1,436 B | **yes** | 1 | `path.symlink_loop` | 3 | no |
| `doctor --format json --data-root <loop>` | 3 | 1,436 B | **yes** | 1 | `path.symlink_loop` | 3 | no |
| `summary --format json --data-root <loop>` | 3 | 1,436 B | **yes** | 1 | `path.symlink_loop` | 3 | no |
| `graph --format text --data-root <loop>` | 3 | 0 B (by design) | n/a | stderr carries `FlowSourceError: --data-root could not be resolved (…)` + the `path.symlink_loop` line + hint | — | — | no |
| `doctor --format text --data-root <loop>` | 3 | 0 B | n/a | same readable stderr | — | — | no |
| `summary --format text --data-root <loop>` | 3 | 0 B | n/a | same readable stderr | — | — | no |
| `graph --format json --data-root <trueloop.json>` (file self-symlink) | 3 | 1,466 B | **yes** | `path.symlink_loop` | 3 | no |

The empty stream is gone: JSON mode now produces exactly one parseable document with a non-empty `issues` array. My byte count is 1,436 vs the Lead's 1,415 — the difference is only the length of the `--data-root` path string embedded in the message, so both are consistent; the invariant (non-empty, valid, exit 3) matches. **FIXED.**

## 12.2 R2-P1-1 still pinned (`--out`)

| Command | Exit | stdout | Traceback |
| --- | --- | --- | --- |
| `graph --out <dirloop>\x.txt` | **3** | 0 B + `cannot write … FileExistsError …` on stderr | no |
| `graph --format json --out <dirloop>\x.json` | **3** | 0 B + same stderr | no |
| `graph --out <synth.json>\x.txt` (existing file as parent) | **3** | 0 B | no |
| `graph --out <scratch>\out4\a\b\c.txt` (normal nested) | **0** | 463 B notice | no |

The change of the failure route did not regress the pin. **FIXED / still pinned.**

## 12.3 R3-P2-1 — helper fixed; skips in this sandbox are legitimate

`test_hardening` on the current revision: **`Ran 23 tests` / `OK (skipped=3)`**. The three skips are exactly `test_graph_path_that_is_a_symlink_loop_is_diagnosed`, `test_data_root_that_is_a_symlink_loop_is_diagnosed` and `test_an_unresolvable_data_root_emits_one_json_document`, all with "this platform cannot create a self-referential … symlink".

Is that my sandbox's token (legitimate) or the helper (your problem)? **Your sandbox token, legitimately** — I tested every creation route from inside the test process:

| Route (from the test process) | Result |
| --- | --- |
| `os.symlink` (file and directory) | `OSError [WinError 1314]` — a required privilege is not held by the client |
| `cmd /c mklink` (file) | rc=1, no output |
| `cmd /c mklink /D` (directory) | rc=1 |
| `cmd /c mklink /J` (junction, needs no symlink privilege) | rc=1 |
| delegated `pwsh -NoProfile -Command "New-Item -ItemType SymbolicLink …"` child | rc=1, "this operation requires administrator privileges" |

So no link can be created at all by this process tree — the skip is honest, and **not** a recurrence of the helper bug.

The helper fix itself is correct: with loops created outside the sandbox (pwsh holds the privilege), `os.path.lexists(link)` → **True** and `link.is_symlink()` → **True** while `link.exists()` → **False**, so with `mklink rc=0` the new check returns **True** and the tests would run. I also exercised the assertions' *content* directly against real loops: graph-path loop → exit 3 + `path.symlink_loop` (§12.4); data-root loop → exit 3 + valid JSON with 1 issue (§12.1). Both match what the skipped tests assert. **FIXED** (as far as this environment can demonstrate).

## 12.4 P0 spot check and suites

| Check | Observed |
| --- | --- |
| P0-1 `deep_5000.json --format json` | exit **3**, 4,819 B, valid, `graph.too_deep`, `exit_code_hint` 3, no traceback (my raw probe also prints `recursion=True` — that is only the issue *detail* text containing the words "RecursionError", not a crash) |
| P0-1 `deep_5000.json --format text` | exit **3**, 2,720 B, no traceback |
| P0-2 `big3000.json --full --format text` | exit **0**, 2,217,295 B, no `RecursionError` |
| P0-2 `big3000.json --full --format json` | exit **0**, 6,711,342 B, valid, `exit_code_hint` **0** |
| P0-3 `trueloop.json --format json` | exit **3**, 5,058 B, valid, `path.symlink_loop`, hint 3 |
| P0-3 `trueloop.json --format mermaid` | exit **3**, 1,396 B, no traceback |
| flowview suite | `.\.venv\Scripts\python.exe -m unittest discover -s flowview/tests -t .` → `Ran 190 tests in 23.010s` / `OK (skipped=3)` |
| repo suite | `.\.venv\Scripts\python.exe -m unittest discover` → `Ran 323 tests in 25.870s` / `OK (skipped=7)` |
| read-only sweep (re-run on this revision) | 30 commands, all 12 `data/`+`config/` files → `identical: true, changed: [], nonzero_exits: []` |

Suite counts vs your measurement: the flowview number **now reads 190, not 189**, because your 19:13:35 edit added `test_exit_code_hint_matches_the_process_exit_code` after you measured; 189 was correct for the pre-19:13 revision and I confirmed that number twice earlier. The repo number is **323, not 322** — same ±1 test; it is not a discrepancy in the code. Cross-check that the decomposition is consistent: `flowview/tests` alone = 190 and `tests` alone = 133, and 190 + 133 = 323. Both suites are green with no failures or errors.

Incidental confirmation of the same 19:13 change: `analysis.expected_exit_code()` / `jsonout` now drive `exit_code_hint`, and in every run above the hint equals the process exit code (0/0 for the big graph, 3/3 for deep nesting and the symlink loop).

## 12.5 Open items after the final round

**No open P0 or P1 from any of my four rounds.** The residual P2s are cosmetic and were not claimed as fixed:

| Item | Status |
| --- | --- |
| `doctor --format mermaid` still prints the 882 B text report (only `json` is data) | P2, unchanged, no doc carve-out |
| ASCII `+-|` fallback still unreachable (`PYTHONIOENCODING=ascii` → UTF-8 box drawing) while README §8 promises it | P2, unchanged |
| A *directory* passed to `--from-file` is labelled `trace.permission_denied` ("not allowed to read <dir>") — the code is now documented (README 378), the wording is still misleading | P2, vocabulary half fixed |
| `--out` failure in json mode emits no document on stdout | P2, judgement call (`--out` is file-oriented) |
| The two symlink tests skip on any Windows host that cannot create links (including this sandbox) | not a defect; the helper now reports success correctly wherever links can be created |

**Could not verify in round 4:** execution of the three symlink tests themselves (no link can be created in this process tree — verified by exhausting every route above, including a junction and a delegated pwsh child); the POSIX branch of `make_symlink`; and the external `data/audit/task_summaries.jsonl` writer (unchanged).

Round-4 confidence: R3-P1-1 and R3-P2-1 `FIXED` verdicts, the `--out` pin, the P0 spot check and the suite counts are **all high** (direct repro, current revision, re-run after the last edit).

---

# Round 5 — FROZEN REVISION (release gate)

**Frozen revision:** `cli.py` 19:20:03, `CONTRACT.md` 19:20:35, `loader.py` 19:20:46, `README.md` 19:20:55, `test_hardening.py` 19:20:58 (plus `analysis.py` 19:13:26 / `jsonout.py` 19:13:23 from the previous pass). Everything below was run against that state at ~19:23, after the freeze. Harness: `.tmp\verifier\round5_probe.{json,py}`.

## 13.1 Suites, syntax, imports (items a + 5)

| Check | Result |
| --- | --- |
| flowview suite | `.\.venv\Scripts\python.exe -m unittest discover -s flowview/tests -t .` → `Ran 191 tests in 23.325s` / `OK (skipped=3)` — **matches your 191/3** |
| repo suite | `.\.venv\Scripts\python.exe -m unittest discover` → `Ran 324 tests in 25.996s` / `OK (skipped=7)` — **matches your 324/7** |
| AST check (your command) | `ast.parse` over every `flowview/**/*.py` → `AST-OK: all flowview .py files parse` |
| module imports | all 16 shipped modules (`flowview`, `cli`, `loader`, `analysis`, `jsonout`, `text`, `mermaid`, `style`, `tasks`, `trace`, `workspace`, `phases`, `backend_adapter`, `client`, `model`, `codes`) import cleanly |
| **item 5 — the broken loader edit** | **No trace survives.** The file parses, the modules import, all 15 matrix combinations exit 0 (below), and every crash-class fixture still produces the documented exit code rather than the exit-1 symptom. The former SyntaxError is gone |

## 13.2 CLI matrix and P0/P1 spot checks (item b)

5 subcommands × 3 formats on the healthy workspace: **15/15 exit 0**, no ANSI in any format, no tracebacks, every JSON document valid with `exit_code_hint: 0`; `graph`/`flow`/`run-flow`/`summary` mermaid outputs all carry a diagram keyword. `doctor --format mermaid` still prints the 882 B text report — the known residual P2, not a P0/P1 (it was never claimed fixed and no exit code or parseability depends on it).

| Highest-risk repro | Exit | Key evidence |
| --- | --- | --- |
| `graph --graph-file deep_5000.json --format json` | 3 | 4,819 B valid, `graph.too_deep`, hint 3, no traceback |
| `graph --graph-file deep_5000.json --format text` | 3 | 2,720 B, no `RecursionError` crash |
| `graph --graph-file big3000.json --full --format text` | 0 | 2,217,295 B, no `RecursionError` |
| `graph --graph-file big3000.json --full --format json` | 0 | 6,711,342 B valid, hint 0 |
| `graph --graph-file trueloop.json --format json` | 3 | 5,058 B valid, `path.symlink_loop`, hint 3 |
| `graph --graph-file trueloop.json --format mermaid` | 3 | 1,396 B |
| `graph --data-root dirloop --format text` | 3 | 0 B stdout + readable stderr |
| `graph --data-root dirloop --format json` | 3 | 1,436 B valid, `path.symlink_loop`, hint 3 |
| `doctor --data-root dirloop --format json` | 3 | 1,436 B valid, 1 issue, hint 3 |
| `summary --data-root dirloop --format json` | 3 | 1,436 B valid, 1 issue, hint 3 |
| `graph --out dirloop\x.txt` (text and json) | 3 | `cannot write … FileExistsError`, no traceback |

Every P0 (rounds 1–3) and every P1 verdict from §2–§12 still behaves as recorded. Nothing regressed.

## 13.3 `exit_code_hint` invariant (item c)

| Case | Exit | `exit_code_hint` | Match |
| --- | --- | --- | --- |
| healthy `graph` / `flow` / `run-flow` / `summary` / `doctor` (json) | 0 / 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 | ✓ 5/5 |
| `graph --graph-file <missing>` | 3 | 3 | ✓ |
| `flow --from-file <missing>` | 3 | 3 | ✓ |
| `summary --file <missing>` | 3 | 3 | ✓ |
| `graph --graph-file deep_5000.json` | 3 | 3 | ✓ |
| `graph --graph-file trueloop.json` | 3 | 3 | ✓ |

The invariant holds in both directions on the frozen revision (10/10).

## 13.4 Directory diagnosis (item d)

| Command | Exit | Code | Message | Claims permission? |
| --- | --- | --- | --- | --- |
| `run-flow --from-file <directory> --format json` | 3 | `trace.is_directory` | "Expected a file but …\adir is a directory." | **no** |
| `run-flow --from-file <directory> --format text` | 3 | `trace.is_directory` (stderr) | same message + hint | **no** |
| `graph --graph-file <directory> --format json` | 3 | `graph.is_directory` (unchanged) | — | **no** |

No "permission"/"not allowed to read" wording appears anywhere for a directory. The old P2 is closed.

## 13.5 Read-only sweep and documentation truths (item e + item 4)

| Check | Result |
| --- | --- |
| 30-command read-only sweep (frozen revision) | `files: 12, commands: 30, identical: true, changed: [], nonzero_exits: []` |
| Docs vs behaviour: README §8 | the false ASCII-fallback promise is gone — the troubleshooting row now says FlowView writes UTF-8 and escapes what the console cannot encode, pointing at `chcp 65001` |
| Docs vs behaviour: README §3 text row + CONTRACT 229–232 | both state the box-drawing rule **and** the carve-out ("the CLI reconfigures stdout to UTF-8 before rendering, so the ASCII branch is reached by library callers and by unusual streams rather than by the default CLI invocation") — truthful |
| Docs vs behaviour: README Trace vocabulary | now lists `trace.is_directory` (line 378) alongside `trace.permission_denied` |
| `cli.CONSOLE_ENCODING` (item 3) | present at `cli.py:36`, set in `configure_stdout()` from the pre-rebind stream encoding and returned; advisory only, no renderer reads it, as stated — no finding |

## 13.6 Release-gate verdict

**No open P0 or P1. The release gate PASSES on the frozen revision.**

Residual P2s (cosmetic, all previously reported, none blocking and none claimed fixed):

| Item | Status |
| --- | --- |
| `doctor --format mermaid` prints the text report (json is the data mode) | P2, unchanged; no exit-code or parseability impact |
| `--out` failure in json mode emits no document on stdout | P2, judgement call (`--out` is file-oriented) |
| The 3 symlink-dependent tests skip in this process tree | not a defect — the process cannot create any link (proven in §12.3); the helper is fixed and they run where links can be created |

**Could not verify on the frozen revision:** execution of the 3 skipped symlink tests (no link can be created by this process tree), the POSIX branch of `make_symlink`, and the external `data/audit/task_summaries.jsonl` writer (my sweeps leave it byte-identical; it has grown only from an unidentified external process across the whole session). None of these affects the release-gate verdict.

Round-5 confidence: **high** for every item above — direct repro against the frozen file timestamps, with the suite counts matching the Lead's own measurement exactly.

# Verification — `flowview flow --prompt`, `dry_route` prompt phase, and `flowview/tools/`

Independent adversarial verification, round 5. Verifier: `verifier2`. I did not write any of the code
under test. Date of run: see the artefact timestamps in `.tmp/verifier2/`.

Environment: Windows, `D:\Projects\matflow`, `.\.venv\Scripts\python.exe` = CPython 3.12.13,
`flowview 0.1.0`, backend composed from the working tree. Every harness, fixture and output file I
created lives under `.tmp/verifier2/`; the only tracked file I wrote is this one.

## Verdict

| Question | Answer |
| --- | --- |
| Read-only claim for `--prompt` | **Holds.** 14 watched files under `data/` + `config/` (path, size, mtime_ns, sha256) identical before/after 28 runs; no file added or removed. |
| No model call / no network | **Holds.** No API key needed, closed base URLs are irrelevant, ~0.45 s per run, and an audit-hook recorder saw no `socket.connect` / `socket.getaddrinfo` / `urllib.Request`. |
| No state-mutating backend call | **Holds.** `write_state`, `route`, `apply_graph_patch`, `execute_node`, `save_upload`, `record_routing`, `record_execution`, `record_outcome` were armed to raise and were never touched; `DecisionRouter` is always built without a JEV router. |
| CJK tokenisation claim | **Source and behaviour hold** (`[a-z0-9]+`, `len > 1`, CJK contributes zero tokens, warning fires exactly when the note fires) **but the printed counts are wrong** (see P1-1/P1-2). |
| `flowview/tools/` optional | **Holds.** Blocker + tools-less copy + `import flowview` all clean; no test imports it. |
| Batch report correctness / determinism | **Holds**, with one fidelity defect (P1-4) and one data-dependency caveat. Two runs over the same `data/` snapshot were byte-identical (94/94 files). |
| Regression | **191 OK (skipped=3)** and **324 OK (skipped=7)**, exactly as expected. |
| Safe to hand to the user? | **Not as documented.** One P0 makes the public `--prompt` surface state something false for any request over 4000 characters. Everything else is P1/P2 polish. |

## Findings

| id | sev | finding | confidence |
| --- | --- | --- | --- |
| P0-1 | P0 | `--prompt` mis-diagnoses every prompt longer than 4000 characters as "backend unavailable" and drops the flow entirely | high |
| P1-1 | P1 | the tokenisation diagnostic's "kept" count is an occurrence count, not the token set the retriever uses (up to 30× inflated) | high |
| P1-2 | P1 | the diagnostic names `CandidateRetriever._tokens`, which does not exist (the tokeniser is the module-level `backend.routing._tokens`) | high |
| P1-3 | P1 | README's worked `--prompt` example numbers contradict the printed output (55/9/9/8 vs 44/8/8/8) | high |
| P1-4 | P1 | `prompt.md` and `PROMPTS.md` are not byte-verbatim on Windows: every LF in a prompt is written as CRLF (16/16 cases) | high |
| P1-5 | P1 | `sync_prompt_cases.py` dies with an unhandled traceback (exit 1) on a missing file, malformed JSON, or a suite without `cases` | high |
| P2-1 | P2 | text mode silently deletes NUL/control bytes from the displayed prompt; JSON keeps them | high |
| P2-2 | P2 | `--prompt` is silently ignored when `--task`/`--from` is also given; `--prompt --help` is a usage error (workaround `--prompt=--help`) | high |
| P2-3 | P2 | `dry_route("")` substitutes `?` as the routed message instead of failing, so the batch tool renders an empty prompt the CLI itself rejects | high |
| P2-4 | P2 | mermaid mode truncates the displayed prompt at `max_label` (48 in the CLI) with `…` | high |

### P0-1 — prompts over 4000 characters are reported as "backend unavailable"

Repro (real CLI, argv; the boundary is exact):

```powershell
cd D:\Projects\matflow
$p = "eis qc " + ("A" * 3993)   # 4000 characters
.\.venv\Scripts\python.exe -m flowview flow --prompt $p --format text   # exit 0
$p = "eis qc " + ("A" * 3994)   # 4001 characters
.\.venv\Scripts\python.exe -m flowview flow --prompt $p --format text   # exit 3
```

Observed (4001 chars):

```text
MatFlow flowview (backend unavailable)
...
ERROR backend.route_failed: Read-only routing could not be computed from the backend.
      [backend.routing.DecisionRouter.decide]
        -> run 'python -m flowview doctor'
```

The `prompt` / `candidates` / `decision` phases are absent; `--format json` emits a valid error
document with `exit_code_hint: 3` and no `meta.prompt`. The real cause is only visible with `-v`:

```text
detail: ValidationError: 1 validation error for TaskState
  String should have at most 4000 characters [type=string_too_long, ...]
```

`backend/contracts.py:217` is `user_message: str = Field(min_length=1, max_length=4000)`, so the
backend genuinely cannot route such a message — but the printed diagnosis says otherwise. `doctor`
run at the same moment reports `ok backend is importable (read-only adapter mode available)` and
`all offline sources are usable`, i.e. the suggested next action directly contradicts the failure.

Binary-searched boundary (`backend_adapter.dry_route`, exact): 4000 chars → `mode=dry-run`;
4001 chars → `mode=offline`. Same at 8000/16000/32700/40000/49999/60000/100000 (all `offline`).

Expected: either route the prompt (truncating the `user_message` the way the backend would have to),
or fail with an accurate diagnosis and hint — "the request exceeds the backend's 4000-character
`TaskState.user_message` limit" rather than "backend unavailable, run doctor".

This contradicts `flowview/README.md` §"`--prompt` — print the flow for one request" ("the mode to
use when you want to see what the backend would do with a given prompt, **including a long one**")
and `cli.prompt_flow_document`'s docstring ("work on a long request").

What would falsify my conclusion: a >4000-character prompt that renders the 3-phase dry-run
document, or a failure document whose title/hint name the length limit instead of backend
unavailability. If `doctor` also failed, the hint would be apt. Mitigating fact: the largest shipped
suite prompt is 2124 characters, so `examples/long_prompt_cases.json` never reaches the limit.

Note: the failure is graceful (no traceback, valid JSON, documented exit 3). It is a wrong printed
diagnosis, not a crash or data loss.

### P1-1 — "kept" counts occurrences, not the retriever's token set

`backend_adapter._prompt_token_diagnostic` (`flowview/backend_adapter.py:280-292`) counts with
`re.findall`, while `backend/routing.py:11-12` returns a **set**:

```python
def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) > 1}
```

| prompt | printed step detail | `routing._tokens(prompt)` |
| --- | --- | --- |
| `run basic EIS quality checks on sample-eis.csv` | `9 ASCII token(s), 9 kept (length > 1)` | 8 (`eis` twice) |
| `eis eis eis qc qc sample-eis sample-eis` | `9 ASCII token(s), 9 kept` | 3 |
| `"Please analyse … carefully. " * 30` (2310 chars) | `240 ASCII token(s), 240 kept` | 8 |

`meta.retriever_tokens` carries the same occurrence count. Expected: the distinct-token count (or an
explicit "occurrences" label), since the line names `_tokens` as its authority. Routing itself is
unaffected — the retriever interns the set — so this is a misleading diagnostic, not a bad route.
Falsified if `_tokens` counted occurrences, or if the CONTRACT documented the number as occurrences
(it does not: `flowview/CONTRACT.md` just says "ASCII token count, kept tokens").

### P1-2 — the diagnostic points at a method that does not exist

```powershell
.\.venv\Scripts\python.exe -c "import backend.routing as r; print(hasattr(r,'_tokens'), hasattr(r.CandidateRetriever,'_tokens'))"
# True False
```

`flow --prompt "<CJK>" --format json` emits
`route.prompt_tokens_unusable … where="backend.routing.CandidateRetriever._tokens"`, and the step
detail reads `CandidateRetriever._tokens matches [a-z0-9]+ runs only`. `CandidateRetriever` has only
`retrieve`. Expected: `backend.routing._tokens`. Falsified if `CandidateRetriever._tokens` exists.

### P1-3 — README worked example numbers are wrong

README.md lines 243-245 show, for `Run basic EIS quality checks on this dataset`:
`55 character(s), 9 token(s)` and `9 ASCII token(s), 8 kept`.
Actual (`flow --prompt … --format json`):

```text
prompt size step      : 44 character(s), 8 whitespace-separated token(s); available input types: RawData, TypedTable
retriever tokenisation: 8 ASCII token(s), 8 kept (length > 1), 0 CJK character(s)
```

Also `README.md` §2's `flow`/`run-flow` row omits `--prompt` from the purpose column (cosmetic).
Falsified if the README numbers reproduce.

### P1-4 — `prompt.md` / `PROMPTS.md` are not byte-verbatim on Windows

All 16 suite prompts contain LF. `run_prompt_cases._write` uses `Path.write_text(...)` with the
default newline handling, which translates `\n` → `os.linesep` on write.

| file | LF-exact | CRLF-exact |
| --- | --- | --- |
| `out1/<case>/prompt.md` | 0/16 | 16/16 |
| `out1/PROMPTS.md` | 0/16 | 16/16 (270 CRLF, 0 bare LF) |

README §6 says `PROMPTS.md` holds every input prompt "**verbatim**". Reading the file back in text
mode hides this (universal newlines normalise on read), which is why a naive check passes. A prompt
that already contains CRLF survives as CRLF (CPython does not double it — `\r\r\n` is absent), so no
characters are added; only lone LF is rewritten. Falsified by a byte-identical prompt.md (0/16 here).

### P1-5 — `sync_prompt_cases.py` reports nothing cleanly on a bad suite

```powershell
.\.venv\Scripts\python.exe -m flowview.tools.sync_prompt_cases --suite .tmp\verifier2\does_not_exist.json  # FileNotFoundError traceback, exit 1
# "{ not json"                                                    -> json.JSONDecodeError traceback, exit 1
# '{"suite_id": "x"}'                                             -> KeyError traceback, exit 1
```

Expected: a one-line message and a non-zero exit, as the sibling tool does
(`run_prompt_cases` prints `Suite not found: …` and exits 3). Falsified if any of the three exits 0
with a readable message.

The good news: `--write` against a copy is safe — **exit 0, `prompt` fields byte-identical, and every
case key identical** (`observed_route`/`route_verdict` were already current). The real suite was not
touched by me.

### P2 findings

- **P2-1** text mode deletes control bytes silently: `--prompt "before\x00after eis qc" --format text`
  prints `beforeafter eis qc`; `\x1b[31m` becomes `[31m`. JSON is exact
  (`"before\u0000after eis qc"`, `meta.prompt == input`). Newlines are converted to a space
  (`alpha\nbravo` → `alpha bravo`), which is fine. Dropping ESC is a good anti-injection default;
  dropping NUL deserves a note.
- **P2-2** `--prompt "eis qc" --task no-such-task` follows the `--task` branch and never says
  `--prompt` was ignored. `flow --prompt --help` → exit 2 (`argument --prompt: expected one
  argument`), while `flow --prompt=--help` → exit 0 with `meta.prompt == "--help"`.
- **P2-3** the CLI correctly rejects empty/whitespace prompts with exit 2, but `dry_route("")`
  substitutes `?` via `_label(prompt, "?")` (`backend_adapter.py:345`) and succeeds, so an empty
  prompt in a suite renders as a "successful" empty flow with a `route.prompt_tokens_unusable`
  warning (adversarial case `q10_empty`, batch exit 0).
- **P2-4** mermaid renders one label per step, truncated to `max_label` (48 in the CLI, 72 in the
  batch tool) with a trailing `…`, so a >48-character prompt is not fully visible in that format.
  This is documented in `CONTRACT.md`; noting it because the check asked about silent truncation.

## Evidence per requested check

### 1. Read-only (`data/` + `config/` unchanged)

Harness `.tmp/verifier2/check_readonly.py` (snapshot of path/size/mtime_ns/sha256 for all 14 files
under `data/` and `config/`, argv runs plus in-process runs that get past the Windows argv limit).

28 runs: plain ASCII, 2310-char and 1000-char CJK, shell metacharacters (`; | $() ` `` ` `` quotes &`),
newlines, CRLF, quotes, `--flag`-looking text, `..\..\..\windows\system32\config\sam`, emoji, RTL,
single char, lone `-`, tabs + BEL + ANSI, digits, 49 999-char prompt (json/text), NUL prompt
(json/text), `--prompt=--help`, empty, whitespace-only, `--format json`/`mermaid`/`text`.

```json
{"watched_files": 14, "diff": {"added": [], "removed": [], "changed": []}}
```

No new file appeared anywhere under `data/`. `--data-root .tmp/verifier2/emptyroot` left that
directory empty.

### 2. No model call

- With `MATFLOW_LITELLM_API_KEY`/`OPENAI_API_KEY` unset: exit 0, `mode=dry-run`,
  `selected eis_basic_qc`.
- With `MATFLOW_API_URL=http://127.0.0.1:9/dead` and `OPENAI_BASE_URL=http://127.0.0.1:9/dead`:
  exit 0, 0.461 s (baseline 0.465 s) — no delay, no error.
- `.tmp/verifier2/inproc_run.py` installs a `sys.addaudithook` recorder before `import flowview`.
  Across 28 runs the only recorded event was `socket.gethostname` (a local call). No
  `socket.connect`, `socket.getaddrinfo`, `socket.gethostbyname`, `urllib.Request` or
  `http.client.connect` — and those events were set to raise, so an attempt would have surfaced as a
  `backend.route_failed` document.
- Mutating backends armed to raise (`check_no_mutation.py`): `touched = []` after both `dry_route`
  and `cli.main(["flow","--prompt",…])`; `dry_route` never passes a `jev_router`.

### 3. Tokenisation claim

Source read: `backend/routing.py:11-12`. Independent recompute over 22 prompts
(`check_tokenisation.py`): CJK-only, mixed, kana, Hangul, Cyrillic, Greek, Arabic, fullwidth Latin,
CJK extension B, emoji, punctuation, accents, duplicates, the 20-CJK threshold, 49 999 chars.
Result: zero CJK characters ever produce a query token, the warning fires exactly when a note exists,
and `meta.retriever_tokens` equals the printed "kept" number in every case. The only disagreements
were the count semantics (P1-1) and the `where` path (P1-2). No prompt was found where the
"overwhelmingly CJK / sees almost none of it" wording is false — in the one case where it fired and
the route was still correct (`… eis_basic_qc`), the claim is about visibility, not correctness, so it
is noisy but not wrong.

### 4. Adversarial `--prompt` inputs

28 inputs across `text`/`json`/`mermaid` (`check_adversarial.py`). Results: no traceback in any run;
`--format json` parsed as one JSON document in every case; mermaid always had a diagram keyword and
never contained ANSI; exit codes were 0 (normal), 2 (empty and whitespace-only, empty stdout in text
mode) and 3 (only the >4000-character cases). Fidelity: JSON `meta.prompt` and the `user prompt`
step are byte-identical for NUL, control bytes, emoji, RTL, CRLF, `--prompt=--help` and the
path-traversal string; text mode drops control bytes (P2-1); mermaid truncates long labels (P2-4).

Windows boundaries that cannot be crossed: a NUL byte in argv raises
`ValueError: embedded null character` in `CreateProcess`, and 49 999 characters raise
`FileNotFoundError [WinError 206]` before Python starts — both were exercised through
`flowview.cli.main` in-process instead. 4001 characters *can* be passed through argv (it is well
under 32 767) and that is P0-1.

### 5. Batch tool

`run_prompt_cases --suite examples/long_prompt_cases.json --out .tmp/verifier2/out{1,2}`: exit 0 both
times, 16/16 cases, 11 487 characters. File set: all 67 per-case files present, plus `INDEX.md`,
`PROMPTS.md`, `run-report.json`, 17 `_stages/` files and 7 `_task/` files (94 total).
16/16 `flow-prompt.json.txt` parse; 16/16 mermaid files have a diagram keyword, zero ANSI, zero raw
quotes inside labels; `INDEX.md` has 77 links, 0 dead, the verdict counts
(`misrouted=2, as_expected=6, expected_unsupported=8`) and the `**11487 characters**` total match the
run-report. Determinism: **94/94 files byte-identical between out1 and out2**.

An 11-case adversarial suite (quotes, pipes, backticks, `#`, brackets, braces, parens, LF, CRLF,
ANSI, NUL, tab, CJK-only, an empty prompt and a 4007-character prompt) also ran with exit 0 and no
traceback; every mermaid label escaped `"` → `#quot;` and newlines → `<br/>`, and no ANSI leaked.

Caveat: the `_task/` section, `INDEX.md` and `run-report.json` depend on the newest record in
`data/audit/task_summaries.jsonl`. The shipped `examples/reports/prompt_flows/` differs from a fresh
run in exactly those 8 files because the chosen record's random `trace_id` changed when the log grew
during this session; the per-case flows and `_stages/` output are identical. So determinism holds for
a fixed `data/` snapshot, not across log writes. I did not regenerate the shipped directory (it is not
mine to write).

### 6. `sync_prompt_cases.py`

Copy of the suite → `.tmp/verifier2/suite_copy.json`; dry run exit 0; `--write` exit 0 with **no case
key changed at all** (prompts byte-identical, `expected_route` untouched, `observed_route`/
`route_verdict` already current) and the real suite file untouched. Bad inputs traceback and exit 1
(P1-5).

### 7. Independence of the new code

- `sys.meta_path` blocker raising `ImportError` for `flowview.tools*`: blocker confirmed effective;
  `graph --format json` (exit 0, valid JSON), `flow --prompt x --format json` (exit 0, valid JSON,
  "MatFlow routing preview (read-only)"), `flow --blueprint --format json` (exit 0); `flowview.tools`
  never appeared in `sys.modules`.
- A copy of the package with `tools/` deleted, run against the real project root via
  `MATFLOW_FLOWVIEW_ROOT`: all three commands exit 0 with valid JSON and no traceback.
- Fresh interpreter: `import flowview; import flowview.cli` leaves `sys.modules` free of any
  `backend*` and any `flowview.tools*` module. No file in `flowview/tests/` references
  `flowview.tools` (only the unrelated `FlowStep.tools` field).

### 8. Regression

| suite | command | result |
| --- | --- | --- |
| flowview | `.\.venv\Scripts\python.exe -m unittest discover -s flowview/tests -t .` | `Ran 191 tests` · `OK (skipped=3)` · data/ diff empty |
| full repo | `.\.venv\Scripts\python.exe -m unittest discover` | `Ran 324 tests` · `OK (skipped=7)` · `data/audit/task_summaries.jsonl` changed |

Both counts match the expectation. The full-suite data change is **not** a FlowView defect:
`tests/test_contracts.py` posts to `TestClient(app)` against the real workspace, so
`POST /api/route` appends to the real `data/audit/task_summaries.jsonl` (`route-eis` /
`route-unknown`). Flagging it because the task told me to run that suite and the Lead's rule forbids
writing to the real `data/` — the file grew by one full-suite run during verification. The FlowView
suite itself is hermetic.

## What I could NOT verify

1. **A 50 000-character prompt through the real CLI on Windows.** `CreateProcess` rejects the
   argument list with `WinError 206` before FlowView runs, and the in-process path fails at 4001 for
   the unrelated reason in P0-1. "Works for prompts of any length" is therefore unverifiable at the
   CLI boundary here, and false past 4000 characters regardless.
2. **A NUL byte in argv.** The OS refuses it (`ValueError: embedded null character`); NUL was tested
   through `flowview.cli.main` in-process only.
3. **No-network as a kernel truth.** The audit hook is instrumentation inside the Python runtime. A
   native extension doing its own IO without emitting Python audit events would evade it; nothing in
   the inspected route path does that.
4. **The `_task/` section's exact content against the shipped report**, because the summary log is a
   moving target appended to by other agents' test runs during this session. Determinism is verified
   for a fixed log snapshot only.
5. **The batch tool's default `--out examples/reports/prompt_flows`**, which I deliberately never
   wrote to; all batch runs used `.tmp/verifier2/`.
6. **Visual rendering on a real console** (mojibake, box drawing, colour) — all captures were UTF-8
   pipes, not a terminal.

## Artefacts

`.tmp/verifier2/`: `check_readonly.py`, `check_tokenisation.py`, `check_adversarial.py`,
`inproc_run.py`, `probe_long.py`, `validate_batch.py`, `check_sync.py`, `check_independence.py`,
`check_no_mutation.py`, `check_no_model.py`, `check_cli_edges.py`, `check_adversarial_suite.py`,
`check_regression.py`, plus `*_report.json` / `*_findings.json` with the raw numbers quoted above.

---

# Round 2 — re-verification after the fix pass

Scope: the P0 fix (`_route_preview_message`), the P1-1…P1-5 fixes, the three P2 fixes, and a repeat
of the read-only sweep and both regression suites. Same rules: `flowview/VERIFICATION_PROMPT_MODE.md`
is the only file I wrote; everything else lives in `.tmp/verifier2/`.

## Round-2 verdict

| Item | Status |
| --- | --- |
| P0 (previous) — >4000 chars reported as "backend unavailable" | **Fixed.** 4001 / 9000 / 13 000 / 50 000 / 200 000 chars all render the three-phase read-only document (exit 0, `meta.prompt` byte-equal); EIS requests still select `eis_basic_qc`. No new ceiling found up to 5 000 000 chars via `dry_route`. |
| P1-1 distinct token counts | **Fixed** (9 prompts; `distinct == len(routing._tokens(prompt))` and `meta.retriever_tokens` agree). |
| P1-2 diagnostic symbol | **Fixed** (`where = "backend/routing.py: _tokens()"`, no stale `CandidateRetriever._tokens` anywhere). |
| P1-3 README example | **Fixed** (44 chars / 8 occurrences / 8 distinct now match the printed output). |
| P1-4 batch byte-fidelity | **Fixed** (`prompt.md` 16/16 LF byte-exact, `PROMPTS.md` 16/16, 0 CRLF / 270 bare LF; runs byte-identical 94/94). |
| P1-5 sync robustness | **Fixed** (missing / malformed / no-`cases` / non-list all exit 3 with a clear message and no traceback; unusable cases skipped with a message; `--write` corrupts nothing). |
| P2 mutual exclusion | **Fixed** (all four ambiguous combinations exit 2 with `cli.ambiguous_source`; singles still work). |
| P2 `route.empty_prompt` | **Fixed** (title `MatFlow routing preview (empty prompt)`, targeted hint, CLI still exit 2). |
| P2 control escaping | **Narrowly fixed** — NUL/BEL/DEL now escaped in text *and* mermaid, but two gaps remain (P2-R2-1). |
| Read-only / no-network / no-mutation / tools-independence / regression | **All hold** (details under (e)). |
| **New** P0 from the fix itself | **The preview's own header text is routed as if the user had typed it** (P0-R2-1). |
| Safe to hand over? | **No — one P0 remains.** It is introduced by the P0 fix, so the surface regressed from "wrong diagnosis for long prompts" to "fabricated route for long prompts". |

## Round-2 findings

| id | sev | finding | confidence |
| --- | --- | --- | --- |
| P0-R2-1 | P0 | the shortened preview's own header/marker words enter the retriever query, creating candidates and a *selection* for prompts that match nothing | high |
| P1-R2-1 | P1 | the shortening issue states a false `user_message` limit (the preview length, e.g. 3931, instead of 4000) | high |
| P1-R2-2 | P1 | the preview drops the prompt's own tokens beyond ~3930 characters, changing the printed selection | high |
| P1-R2-3 | P1 | the tokenisation step/meta describe the full prompt while the router consumed the preview — the two contradict each other in one document | high |
| P1-R2-4 | P1 | the printed confidence is inflated by the injected tokens (0.75 vs 0.50 for the same tool from the full token set) | high |
| P2-R2-1 | P2 | `text._plain` does not escape the C1 range (U+0080–U+009F) while mermaid does; mermaid silently deletes ESC (no `\e`) because `strip_ansi` runs first | high |
| P2-R2-2 | P2 | handoff arithmetic: `routing._tokens("Please analyse …"*30)` is 8, not the quoted 5 (the code is right) | high |

### P0-R2-1 — the preview routes its own header words as user content

Pasteable ASCII repro (no CJK, no encoding traps). Both prompts tokenise to the single token `{zzz}`,
which matches no registered tool:

```powershell
cd D:\Projects\matflow
$a = "zzz " * 700    # 2800 characters
$b = "zzz " * 1200   # 4800 characters
.\.venv\Scripts\python.exe -m flowview flow --prompt $a --format text --no-color
#   1. no candidate retrieved  [unknown]
#   1. no tool selected        [waiting]
.\.venv\Scripts\python.exe -m flowview flow --prompt $b --format text --no-color
#   RawData, TypedTable; routing used a 3931-character preview
#   matches: preview
#   1. selected raw_file_import_raw_file_import_1_f29b82  [waiting]
#      detail: confidence 0.25; human confirmation required: yes; ...
```

The selection exists only because `_route_preview_message` prepends
`"[routing preview: Latin fragments only from a 4800-character prompt] "` and appends
`" [… CJK text omitted for routing preview …] "`, and `DecisionRouter` tokenises whatever string it
is handed. The injected tokens are:

```text
latin branch : 4800/4006, character, cjk, for, fragments, from, latin, omitted, only, preview, prompt, routing, text
no-latin     : 13500, character, cjk, for, latin, no, of, omitted, preview, prompt, routing, text, tokens, with
```

Active tools whose terms match them: `raw_file_import_raw_file_import_1_f29b82` (`preview`),
`ebrick_cp_g_preview` (`from`, `preview`), `conditional_gate` (`only`). The spurious
`raw_file_import_raw_file_import_1_f29b82` candidate appears in **6/6** shortened prompts tried.

Same defect for a prompt with no tokens at all — one extra character flips the printed answer:

```powershell
$c = "请对这份阻抗谱数据做质量检查。" * 1000
.\.venv\Scripts\python.exe -m flowview flow --prompt $c.Substring(0,4000) --format json  # "no tool selected"
.\.venv\Scripts\python.exe -m flowview flow --prompt $c.Substring(0,4001) --format json  # "selected raw_file_import_raw_file_import_1_f29b82"
```

In that second document the `retriever tokenisation` step still reads
`0 occurrence(s), 0 distinct token(s); 3735 CJK character(s) contribute nothing -- every CJK
character is invisible to the retriever, so no candidate can match`, while the `decision` phase
selects a tool — two phases of the same flow contradict each other.

This is exactly the case (b) asked about: the preview makes the printed decision look *better* than
the real prompt would (from "nothing can match" to "a tool was selected", confidence 0.50,
confirmation yes).

Expected: the router must only ever see user text. A preview built by joining the prompt's own
distinct `[a-z0-9]+` tokens (no prose header/marker, or with the header stripped before routing, or
by feeding the query directly) would remove the fabrication.

What would falsify this: a shortened prompt whose printed candidates/decision are unchanged from the
same prompt's full token set, or a preview whose `_tokens(preview)` is a subset of
`_tokens(prompt)`. Falsified today for every case tried: the preview's token set always gained
13–14 invented tokens, and 6/6 runs produced a candidate matched only on invented words.

### P1-R2-1 — the shortening issue prints a false limit

```powershell
$b = "zzz " * 1200
.\.venv\Scripts\python.exe -m flowview flow --prompt $b --format json
# "The prompt is 4800 characters, above the backend's 3931-character user_message limit, so routing used a preview."
```

`backend/contracts.py:217` caps `user_message` at **4000**; 3931 is the preview length
(`flowview/backend_adapter.py:351-352` interpolates `len(preview_text)`). Every ASCII/wordy long
prompt I tried reports a false limit (3931 / 3930 / 3929); CJK-only prompts print 4000 by coincidence
because their preview fills the budget. Expected: the real limit, or wording such as "routing used a
3931-character preview". Falsified if the message contains `4000`.

### P1-R2-2 — the preview drops the prompt's own tokens

```powershell
$p = ("data " * 900) + " eis_basic_qc sample-eis.csv"   # 4528 chars
.\.venv\Scripts\python.exe -m flowview flow --prompt $p --format json
# selected normalize_columns   (candidates ranked on "data")
# full token set {data, eis, basic, qc, sample, csv} -> eis_basic_qc (0.75)
```

`("text " * 1200) + " eis qc"` (6007 chars) drops `{eis, qc}` and selects
`raw_file_import_raw_file_import_1_f29b82`. The preview budget is `4000 - len(header) - len(marker)`
≈ 3930 characters of *Latin runs*, so a request whose keywords come after that much filler loses
them. `dry_route` cannot route the full prompt (the backend refuses), but the closest faithful
comparison — the prompt's full token set scored with the retriever's own formula — disagrees with the
printed winner in 3/6 long prompts. Falsified if `dropped` is always empty for long prompts, or if
the printed winner always equals the full-token winner.

### P1-R2-3 — the diagnostic describes a different string than the router saw

`_prompt_token_diagnostic(prompt_text)` and `_route_preview_message(prompt_text)` are computed
independently from the same input, and only the second is routed. For `"zzz " * 1200` the step says
`1 distinct token(s)` while the router's query had 14 tokens; for the 4001-char CJK prompt it says
`0 distinct token(s) … no candidate can match` while a candidate is listed. `meta.retriever_tokens`
carries the full prompt's count. Expected: when `shortened`, report the preview's tokenisation (or
both, labelled). Falsified if `meta.retriever_tokens == len(routing._tokens(preview))` for shortened
prompts.

### P1-R2-4 — inflated confidence

`"Please analyse the electrochemical impedance spectroscopy dataset carefully. " * 60` (4620 chars):
the injected `preview` token gives `raw_file_import_raw_file_import_1_f29b82` a third match, so the
printed confidence is **0.75**, while the same tool scores **0.50** against the prompt's own 8-token
set (`score = min(1, len(matched) / max(1, min(len(query), 4)))`). My reimplementation of the
scoring/ranking matched `DecisionRouter` exactly on five ≤4000-char prompts (same winner, same
confidence to 1e-9), so the comparison is sound. Falsified if the printed confidence equals the
full-token-set confidence for shortened prompts.

### P2-R2-1 — control-character escaping gaps

| input | text output | mermaid output |
| --- | --- | --- |
| `\x00`, `\x07`, `\x7f` | `\x00`, `\x07`, `\x7f` ✓ | `\x00`, `\x07`, `\x7f` ✓ |
| `\x80`, `\x9f` (C1) | emitted **raw** (valid UTF-8, but invisible) | `\x80`, `\x9f` ✓ |
| `\x1b` (bare, or `\x1b[31m`) | `\x1b` ✓ | **silently deleted** — no `\e`, no `\x1b` marker |

`text._plain` (`flowview/text.py:44-60`) escapes `< " "` and `\x7f` but not U+0080–U+009F;
`mermaid._escape_text` calls `strip_ansi` *before* `_is_control`, so the ESC branch
(`mermaid.py:89-91`) is unreachable for prompt text. Deleting an ANSI sequence is a reasonable
anti-injection default, but it contradicts both the handoff claim ("`\e` for ESC") and the docstring
"nothing disappears silently". The Lead's specific check (`before\x00middle\x07bell after`) passes in
both renderers.

### P2-R2-2 — handoff arithmetic

`len(routing._tokens("Please analyse the electrochemical impedance spectroscopy dataset carefully. " * 30))`
is **8** (`please, analyse, the, electrochemical, impedance, spectroscopy, dataset, carefully`), not
the quoted 5. The code's own output is 8 occurrences / 8 distinct, which is correct; only the
handoff number is wrong.

## Confirmations per requested item

### (a) Boundary — fixed

| prompt | chars | path | exit | phases | `meta.prompt` | preview | decision |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `"eis qc " + "A"*N` | 3999 / 4000 | dry / argv | 0 | prompt,candidates,decision | byte-equal | verbatim | `eis_basic_qc` |
| same | 4001 / 9000 / 13 000 | argv | 0 | 3 phases | byte-equal | shortened | `eis_basic_qc` |
| same | 50 000 | in-process CLI json | 0 | 3 phases | byte-equal | shortened | `eis_basic_qc` |
| same | 200 000 | dry | — | 3 phases | byte-equal | shortened | `eis_basic_qc` |
| wordy EIS sentence | 3999 / 4001 | dry / argv | 0 | 3 phases | byte-equal | verbatim / shortened | `eis_basic_qc` |
| CJK-only | 4001 / 9000 / 13 200 | dry / argv | 0 | 3 phases | byte-equal | shortened | **injected** `raw_file_import_…` (P0-R2-1) |

New ceiling: none found through `dry_route` at **1 000 000 / 5 000 000** characters (all `dry-run`,
`meta.prompt` byte-equal, < 0.4 s). Real argv is still bounded by Windows at ≈32 767 characters
(`WinError 206`), unchanged.

### (b) Preview integrity — see P0-R2-1 and P1-R2-2/R2-4

`_tokens(preview)` was compared with `_tokens(prompt)` for six 4.5k–13.5k-character prompts: the
preview *always* adds 13–14 tokens that the user never typed and (in 3/6) drops the prompt's own
tokens; 6/6 produced a candidate matched only on invented words; confidence was inflated in 2/6 and
a selection appeared where the full token set yields none in 2/6.

### (c) P1-1 … P1-5 — fixed

* **P1-1**: `_prompt_token_diagnostic` returns `(occurrences, len({...}), cjk, note)`. Across
  ascii, duplicated, accent, digit, empty, whitespace, CJK and 2310-char repeated prompts,
  `distinct == len(routing._tokens(prompt))` and `occurrences == len(re.findall(r"[a-z0-9]+", lower))`;
  `meta.retriever_tokens` equals the distinct count.
* **P1-2**: `where == "backend/routing.py: _tokens()"`; the step reads
  `backend/routing.py _tokens() keeps the distinct [a-z0-9]+ runs longer than one character: …`;
  `git grep CandidateRetriever._tokens` finds nothing.
* **P1-3**: the printed example for `Run basic EIS quality checks on this dataset` is
  `44 character(s), 8 whitespace-separated token(s)` / `8 occurrence(s), 8 distinct token(s), 0 CJK
  character(s)`; README lines 244-245 carry the same numbers (abbreviated wording only).
* **P1-4**: batch run twice → exit 0, 16 cases, 11 487 chars, 94 files both times, byte-identical
  (0 differing); `prompt.md` LF byte-exact 16/16, `PROMPTS.md` 16/16 with **0 CRLF / 270 bare LF**;
  16/16 JSON valid; 16/16 mermaid has a diagram keyword, no ANSI, no raw quotes; verdicts unchanged
  (2 misrouted / 6 as_expected / 8 expected_unsupported).
* **P1-5**: missing → exit 3 `Suite not found…`; malformed → exit 3
  `Suite is not valid JSON … line 1, column 3`; no `cases` key or non-list `cases` → exit 3
  `Suite must be a JSON object with a 'cases' array`; `{"cases": []}` → exit 0; a suite with a
  string element and an empty prompt → exit 0 with two `skipped a case without a usable prompt`
  lines on stderr. No tracebacks anywhere. `--write` on a copy: exit 0, prompts identical, no case
  key changed, real suite untouched, copy written with LF (`newline="\n"`).

### (d) P2 — fixed, with the two gaps above

* Mutual exclusion: `--prompt`+`--task`, `--prompt`+`--from`, `--task`+`--from`, all three →
  exit 2 with `cli.ambiguous_source`; `--prompt` / `--task` / `--from` / `--blueprint` alone → exit 0.
* `dry_route("")` and `dry_route("   ")` → title `MatFlow routing preview (empty prompt)`, issue
  `route.empty_prompt`, hint `Pass the request text, for example: --prompt "run basic EIS quality checks".`
  (no doctor hint); `flow --prompt ""` still exits 2 with empty stdout.
* `before\x00middle\x07bell\x7fafter eis qc` → text and mermaid show `\x00`, `\x07`, `\x7f` and
  contain no raw C0/DEL bytes; nothing is dropped silently for that input. The C1/ESC gaps are
  P2-R2-1.

### (e) Regression + read-only re-run

| check | result |
| --- | --- |
| `unittest discover -s flowview/tests -t .` | `Ran 191 tests` · `OK (skipped=3)` · data/ diff empty |
| `unittest discover` | `Ran 324 tests` · `OK (skipped=7)` · `data/audit/task_summaries.jsonl` changed again (same pre-existing `tests/test_contracts.py` `TestClient(app)` behaviour, not FlowView) |
| 29-run `--prompt` argv battery | exit 0/2/3 as documented, no traceback, no file added/removed/changed under `data/` or `config/` (14 files, size+mtime_ns+sha256) |
| 11-run in-process heavy battery (50 000 / 200 000 chars, NUL, RTL, emoji, 14 000 CJK, json/text/mermaid) | all exit 0, no traceback, `meta.prompt` byte-equal, **data/config diff empty**, audit hook recorded only `socket.gethostname` — no `socket.connect` / `getaddrinfo` / `urllib.Request` |
| `flowview.tools` independence | still holds (meta_path blocker + tools-deleted copy + `import flowview` leaves no `backend*`/`tools*` modules) |

## What I could NOT verify in Round 2

1. **A >32 767-character prompt through the real Windows CLI** — the OS refuses the argument list
   before FlowView starts; large sizes were exercised through `flowview.cli.main` in-process and
   `dry_route` directly (no new ceiling found to 5 000 000 chars).
2. **The route the real backend would produce for a >4000-character prompt** — it cannot produce one
   (`TaskState.user_message` rejects it), so every comparison in P1-R2-2/R2-4 uses the prompt's full
   token set scored with the retriever's own formula, validated against the real router on five
   ≤4000-char prompts.
3. **No-network as a kernel truth** — the evidence is Python audit-hook instrumentation.
4. **Rendering on a real console** — all captures are UTF-8 pipes.
5. I again ran the full repo suite as instructed, which appended to the real
   `data/audit/task_summaries.jsonl` (pre-existing repo behaviour).

## Round-2 artefacts

`.tmp/verifier2/`: `r2_inproc.py`, `r2_p0.py`, `r2_preview.py`, `r2_findings.py`, `r2_assert.py`,
`r2_batch_sync.py`, `r2_control_probe.py`, `r2_readonly_inproc.py`, `r2_ceiling.py`,
`r2_ascii_repro.py`; reports `r2_p0_report.json`, `r2_preview_report.json`, `r2_findings.json`,
`r2_assert_findings.json`, `r2_batch_sync_findings.json`, `r2_readonly_inproc.json`,
`readonly_report.json`, `regression_report.json`, and the regenerated batch output
`r2out1/` / `r2out2/`.

### Note on two harness defects of mine (not product findings)

The first Round-2 read-only run reused `.tmp/verifier2/check_readonly.py`, whose in-process runner
still used the Round-1 argument contract; those six in-process cases therefore no-opped. I rebuilt
them (`r2_readonly_inproc.py`, 11 heavy cases with the audit hook) and the results above are from
that run. Likewise, in `r2_batch_sync.py` my "prompt bytes present verbatim in the written copy"
check was wrong for JSON (the prompt's newlines are escaped as `\n` inside a JSON string); the
correct comparison is the JSON value, which is identical for all 16 cases.

---

# Round 3 — re-verification after the preview rewrite

Scope: the token-only preview (`_route_preview_message`), `MAX_TASK_MESSAGE`, the two-sided
tokenisation diagnostic, the C1/ESC renderer changes, plus a repeat of the read-only sweep and both
regression suites. Same rules: this file is the only one I wrote; everything else is under
`.tmp/verifier2/`.

## Round-3 verdict

| Item | Status |
| --- | --- |
| P0-R2-1 injected preview words | **Fixed, structurally verified.** 24/24 inputs: the preview's router query is a subset of the prompt's own token set, and `_prompt_token_diagnostic(preview).distinct == len(routing._tokens(preview))`. No input found where a candidate or confidence comes from a word the user did not type. |
| (a) the `zzz` / CJK flip | **Fixed** through the real CLI (exit 0, 0 candidates, "no tool selected" at every size). |
| P1-R2-1 false limit | **Fixed** (`MAX_TASK_MESSAGE = 4000`, message states the real limit). |
| P1-R2-2 dropped tail tokens | **Fixed for the un-dropped path** (`data_tail_4528` and `text_then_eis_6007`: routing = full token count, dropped = 0, `eis_basic_qc` 0.75 / 0.67). |
| P1-R2-3 one-sided diagnostic | **Fixed** (both sides reported; `routing_tokens` + `retriever_tokens_dropped` in meta, verified 24/24). |
| P1-R2-4 confidence inflation | **Fixed on the un-dropped path** (wordy EIS now prints exactly the prompt's own token set's decision/confidence). |
| P2-R2-1 C1 escaping | **Fixed** (text escapes U+0080–U+009F as `\xNN`; no raw C1). |
| P2-R2-2 ESC | **Fixed as described** (lone ESC → `\e`; a complete CSI sequence is stripped by design — I accept that). |
| Read-only / no-network / regression | **Hold** (23-run argv battery + 11-case heavy in-process sweep; 191 OK/skipped=3, 324 OK/skipped=7). |
| New in Round 3 | **P1-R3-1** (dropped-token path still degrades decisions; disclosed) + two P2s + one wrong handoff claim. |
| Safe to finalise? | **Yes, if you accept the disclosed dropped-token caveat; no P0 remains and the injection guarantee is clean.** If you want the "confidence can never be inflated" claim to be literally true, apply the two-line `break`→`continue` fix (P1-R3-1) and I will re-run. |

## Round-3 findings

| id | sev | finding | confidence |
| --- | --- | --- | --- |
| P1-R3-1 | P1 (disclosed) | when the preview must drop tokens, the decision can differ from the prompt's own token set — and one oversized token voids *every* later token, including ones that fit | high |
| P2-R3-1 | P2 | with drops, the printed confidence can still be inflated (1.00 vs 0.667) — the handoff's blanket "cannot be inflated" needs "when nothing is dropped" | high |
| P2-R3-2 | P2 | the dropped-token list embeds raw token text with no length cap: a 100 000-character token produces a 100 217-character issue message | high |
| P2-R3-3 | P2 | the handoff's wordy-EIS claim (1.00 for `eis_basic_qc`) does not reproduce; the actual output is correct and faithful | high |

### P1-R3-1 — the dropped-token path degrades the decision, and `break` throws away fitting tokens

```powershell
cd D:\Projects\matflow
$p1 = ("b" * 4000) + " eis qc"                 # 4007 chars, tokens {b*4000, eis, qc}
$p2 = " ".join("tok{0:d4}" -f $_ for $_ in 0..499) + " eis qc"   # 4006 chars, 502 distinct tokens
```

* `$p1` → dropped 3 (the 4000-char `b…b` **and** `eis` and `qc`), preview 0 characters, printed
  "no tool selected"; the prompt's own token set selects `eis_basic_qc` (0.667). The loop
  `if size + len(token) + 1 > limit: break` stops at the first oversized token, so every later
  token is discarded even though `eis qc` needs 7 characters. Replacing `break` with `continue`
  keeps `{eis, qc}` and prints `eis_basic_qc`.
* `$p2` → dropped 2 = exactly `{eis, qc}` (the 500 filler tokens fill the 4000-char budget first),
  printed "no tool selected" while the prompt's tokens select `eis_basic_qc` (0.5). This one is
  inherent to any prefix-truncation policy, not to the `break`.
* `("data " * 900) + " eis_basic_qc sample-eis.csv"` and `"eis qc " + "A"*3994` show the benign and
  the inflated variants of the same path.

In every dropped case the issue is severity `warning`, the `prompt size`/tokenisation steps mark the
preview, and the hint ends with "Tokens listed above were dropped, so the decision is incomplete." —
so this is **disclosed, not a lie**. It is P1 only because the printed decision can differ from what
the same prompt's own tokens produce and one of those differences (the `break`) is gratuitous.
Falsified if `continue` and `break` agree for `$p1`, or if the printed decision equals the full-token
decision in every dropped case.

### P2-R3-1 — confidence is still inflatable when tokens are dropped

```powershell
$p = "eis qc " + ("A" * 3994)     # 4001 chars
.\.venv\Scripts\python.exe -m flowview flow --prompt $p --format json
#   routing_tokens=2, retriever_tokens_dropped=1, selected eis_basic_qc, confidence 1.00
```

The prompt's own 3-token set scores the same tool **0.667**; dropping the oversized third token
shrinks the denominator `max(1, min(len(query), 4))` and lifts the printed confidence to `1.00`. The
selected tool is unchanged and the drop is disclosed, so this is a caveat rather than a defect, but
the handoff sentence "confidence can no longer be inflated, since the query set equals the preview
token set" holds only when `retriever_tokens_dropped == 0` (it did hold for the wordy-EIS case).

### P2-R3-2 — unbounded dropped-token text in the issue message

`"a" * 100000` → one dropped token of length 100 000 → the `route.prompt_shortened_for_routing`
message is **100 217 characters** (`"… did not fit into the preview: aaaa…"`), and the text renderer
prints all of it (wrapped), roughly doubling the output for that input. `_route_preview_message`
lists up to 12 dropped tokens but never truncates an individual token. Suggested cap: 40 characters
per listed token. Not a correctness problem; the disclosure is honest, just unbounded.

### P2-R3-3 — the wordy-EIS handoff claim does not reproduce

For `"Please analyse the electrochemical impedance spectroscopy dataset carefully. " * 60`
(4620 chars) the current output is:

```text
retriever tokenisation: The 4620-character prompt yields 480 occurrence(s) / 8 distinct token(s) …;
                        the router was given 8 distinct token(s) (75 occurrence(s) …) [shortened]
raw_file_import_raw_file_import_1_f29b82 (candidate): score 0.50; reasons: matches: dataset, the
selected raw_file_import_raw_file_import_1_f29b82: confidence 0.50; human confirmation required: yes
```

not `1.00` / `eis_basic_qc`. To prove this is faithful rather than a new distortion I routed a
≤4000-character message containing exactly those 8 tokens
(`please analyse the electrochemical impedance spectroscopy dataset carefully`) through the real
`DecisionRouter`: same tool, same `0.50`, same reasons (`dataset`, `the`). `raw_file_import_…` is
therefore **not** spurious any more — it matches the user's own generic words, which is a backend
routing-quality fact. The intent of P1-R2-4 (no injected token, no inflated confidence) is verified;
only the handoff's example numbers are wrong.

## Confirmations per requested item

### (a) The flip is gone — real CLI, json

| input | chars | exit | `routing_preview` | candidates | decision |
| --- | --- | --- | --- | --- | --- |
| `"zzz " * 700` | 2 800 | 0 | verbatim | 0 | no tool selected |
| `"zzz " * 1200` | 4 800 | 0 | shortened | 0 | no tool selected |
| `"zzz " * 2250` | 9 000 | 0 | shortened | 0 | no tool selected |
| CJK-only | 4 000 | 0 | verbatim | 0 | no tool selected |
| CJK-only | 4 001 | 0 | shortened | 0 | no tool selected |
| CJK-only | 13 000 | 0 | shortened | 0 | no tool selected |

`meta.prompt` is byte-equal to the input in every case.

### (b) The subset argument — attacked, holds

24 inputs (ASCII, CJK-only, CJK+late-Latin, unicode, uppercase-only, digits, RTL+emoji, duplicated,
one 100 000-char token, 4000/4001-char single tokens, 400+ distinct-token prompts):

* `_tokens(preview) ⊆ _tokens(prompt)`: **24/24**.
* `_prompt_token_diagnostic(preview)[1] == len(_tokens(preview))`: **24/24**.
* `meta.routing_tokens`, `meta.retriever_tokens`, `meta.retriever_tokens_dropped` equal the
  independently computed values: **24/24**.
* On the 20 inputs where `dropped == 0`, the printed selection/confidence equal my reimplementation
  of the retriever over the prompt's own token set (validated against the real `DecisionRouter` on
  five ≤4000-char messages): **20/20** (the two apparent mismatches in my first pass were my own
  rounding of the printed `0.67` against `0.666667`, not defects).
* On the 4 inputs with `dropped > 0`, the printed decision differs from the full-token decision in
  3 (`giant_token_plus`, `distinct_filler_keeps_eis`, `distinct_filler_drops_eis`) — see P1-R3-1 —
  and every one of them carries the warning + "decision is incomplete" hint.

I could not construct any input where a candidate, a matched reason, or a confidence originates in
text FlowView added. The `_route_preview_message` body contains no literal word at all.

### (c) The four P1s and two P2s

* **P1-R2-1**: `MAX_TASK_MESSAGE = 4000`, and the backend constraint is
  `MaxLen(max_length=4000)` (4 000 accepted, 4 001 `ValidationError`). Messages now read
  "… above the backend's **4000**-character user_message limit, so routing used a 3-character preview
  built only from the prompt's own tokens."
* **P1-R2-2**: `("data "*900)+" eis_basic_qc sample-eis.csv"` → full 6 / routing 6 / dropped 0 /
  `eis_basic_qc` 0.75; `("text "*1200)+" eis qc"` → 3 / 3 / 0 / `eis_basic_qc` 0.67.
* **P1-R2-3**: step now reads "The N-character prompt yields X occurrence(s) / Y distinct token(s)
  and Z CJK character(s); the router was given A distinct token(s) (B occurrence(s), C CJK
  character(s)) [verbatim|shortened]"; meta carries `routing_tokens` and
  `retriever_tokens_dropped`.
* **P1-R2-4**: no injected token; wordy EIS prints exactly the prompt's own token set's result (see
  P2-R3-3 for the handoff's wrong example numbers).
* **P2-R2-1**: `alpha\x80 beta\x9f omega` → text shows `\x80`/`\x9f` and contains **no** raw C1
  character; mermaid already did.
* **P2-R2-2**: `mermaid._escape_text("a\x1bb") == "a\eb"`; `("a\x1b[31mred\x1b[0mb") == "aredb"`.
  The document path contains no raw C0. I agree with the design decision: a complete CSI sequence is
  a terminal instruction, not text, and stripping it is safer than echoing it. The only asymmetry is
  that text mode shows `\x1b[31m` while mermaid removes the sequence — cosmetic, not a blocker.

### (d) Read-only sweep and suites

| check | result |
| --- | --- |
| `unittest discover -s flowview/tests -t .` | `Ran 191 tests` · `OK (skipped=3)` · data/ diff empty |
| `unittest discover` | `Ran 324 tests` · `OK (skipped=7)` · `data/audit/task_summaries.jsonl` changed again (pre-existing `tests/test_contracts.py` `TestClient(app)` behaviour) |
| 23-run `--prompt` argv battery | 20×exit 0, 2×exit 2 (empty/whitespace), 1 OS-level argv refusal at 49 999 chars (`WinError 206`); no traceback; `data/` + `config/` byte-identical (14 files, size+mtime_ns+sha256), nothing added |
| 11-case heavy in-process sweep (50 000 / 200 000 chars, NUL, RTL, emoji, 14 000 CJK × json/text/mermaid) | all exit 0, no traceback, `meta.prompt` byte-equal, **data/config diff empty**, audit hook recorded only `socket.gethostname` (no `connect`/`getaddrinfo`/`urllib.Request`) |

## What I could NOT verify in Round 3

1. A >32 767-character prompt through real Windows argv (OS limit, as before) — the heavy cases ran
   through `flowview.cli.main`/`dry_route` in-process; no ceiling found to 5 000 000 characters.
2. The route the real backend would produce for a >4000-character prompt (it refuses one), so the
   full-token comparisons use the prompt's token set scored with the retriever's own formula,
   validated against the real router.
3. No-network as a kernel truth (audit-hook instrumentation).
4. Real-console rendering (all captures are UTF-8 pipes).
5. My `check_readonly.py` in-process rows were inert again (that script's runner wiring is stale);
   the heavy in-process coverage comes from `r2_readonly_inproc.py`, and the argv rows are valid.

## Round-3 artefacts

`.tmp/verifier2/`: `r3_subset.py`, `r3_p1p2.py`, `r3_extra.py`; reports `r3_subset_report.json`,
`r3_p1p2_findings.json`, `readonly_report.json`, `r2_readonly_inproc.json`,
`regression_report.json`, logs `r3_readonly.log`, `r3_readonly_inproc.log`, `r3_regression.log`.

---

# Round 4 — confirmation of the truncation change

Scope: the `break`→`continue` change, the new oversized-token truncation, the 40-character
dropped-token cap, and the confidence caveat wording; plus a repeat of the read-only sweep and both
suites. Same rules: this file is the only one I wrote.

## Round-4 verdict

| Item | Status |
| --- | --- |
| P2-R3-2 dropped-token cap | **Fixed.** `"a"*100000` issue message: 100 217 → **261** characters (was measured at 100 217 in Round 3); `("b"*4000)+" eis qc"` → 268; a 260-drop case → 340; the `…` marker is present. |
| P2-R3-1 confidence inflation | **Fixed on the R3 repro.** `"eis qc " + "A"*3994` now prints `selected eis_basic_qc`, confidence **0.67** (was 1.00), because the truncated token stays in the query and the denominator does not shrink. |
| New confidence caveat | **Present and explicit**: "Because tokens were dropped, both the route and its confidence were computed over the preview rather than the whole request: treat the decision as incomplete." |
| P0-R2-1 injection | Still clean: `"zzz "*700` / `"zzz "*1200` → no candidate, "no tool selected". |
| P1-R3-1 "fitting tail kept" | **NOT fixed as claimed** (P1-R4-1 below). |
| New in Round 4 | **P1-R4-2** truncation manufactures a registry term and fabricates a decision; **P1-R4-3** `preview_tokens` shadowing corrupts both steps and `meta.routing_tokens`; **P2-R4-1** the empty-preview/`?` claim is still false. |
| Read-only / regression | Hold (23-run argv battery + 11-case heavy sweep clean; 191 OK/skipped=3, 324 OK/skipped=7). |
| Safe to finalise? | **No — three P1s, all from this round's truncation change.** They are narrow (long prompts with an oversized or dropped-token tail) and two have one-line fixes. |

## Round-4 findings

| id | sev | finding | confidence |
| --- | --- | --- | --- |
| P1-R4-1 | P1 | `("b"*4000)+" eis qc"` still drops `eis`/`qc` and prints "no tool selected"; the `continue` branch is unreachable once a truncation fills the budget, so the handoff claim ("now yields a preview containing `eis` and `qc`") does not reproduce | high |
| P1-R4-2 | P1 | truncating an oversized token into the remaining room can land exactly on a registry term, fabricating a candidate and a selection that the prompt's own token set cannot produce | high |
| P1-R4-3 | P1 | when tokens are dropped, `preview_tokens` (the routed **count**) is rebound to the list of dropped-token previews, so both steps print that list where a count is claimed and `meta.routing_tokens` becomes a list repr | high |
| P2-R4-1 | P2 | the preview is still empty (and `_label` still feeds `?`) for token-less long prompts: CJK-only 13 000, `"a "*2001`, 5 000 emoji, RTL — benign because `?` tokenises to nothing | high |

### P1-R4-1 — the `("b"*4000)+" eis qc"` claim does not reproduce

```powershell
cd D:\Projects\matflow
$p = ("b" * 4000) + " eis qc"     # 4007 chars
.\.venv\Scripts\python.exe -m flowview flow --prompt $p --format json
```

Observed: preview = `bbbb…` (3 999 chars), `retriever_tokens_dropped=3` (the `b…b` token **and**
`eis` and `qc`), candidates = "no candidate retrieved", decision = "no tool selected". The
prompt's own token set `{b*4000, eis, qc}` selects `eis_basic_qc` (0.667).

Why: the truncation branch runs first and sets `size += room + 1`, which fills the budget exactly,
so every later token sees `room = -1` and is dropped by the `room <= 0: continue`. The `continue`
only matters when the oversized token is **not** first:

```powershell
$p2 = ("eis qc ") + ("b" * 4000)  # oversized token last
#   preview "eis qc bbbb…", selected eis_basic_qc, confidence 0.67  ✔
```

A policy that fits whole tokens first (skip an oversized token with `continue`) and only truncates
when **nothing** fits would make `$p` → `"eis qc"` → `eis_basic_qc`, while still keeping
`"a"*100000` non-empty; it also removes P1-R4-2, because the manufactured prefix can then only occur
when the prompt consists of a single oversized token (which cannot match any registry term anyway).

What would falsify this: `("b"*4000)+" eis qc"` producing a preview that contains `eis`/`qc`, or the
printed decision matching the prompt's own token set.

### P1-R4-2 — truncation can manufacture a matching token and a decision

Repro (a deterministic 4049-character prompt; the exact text is saved at
`.tmp/verifier2/r4_truncation_prompt.txt`):

```text
[365 filler tokens q000000000 … q000000362 covering 3996 characters]  csvzzzzzz…(50 z)
```

The filler exactly exhausts the budget so the last slot holds `csv` — the first 3 characters of the
user's 53-character token. `_tokens(preview)` therefore contains `csv`, which is **not** a token of
the prompt (`_tokens(preview) ⊄ _tokens(prompt)`), and `csv` is a term of two registry tools:

```text
candidates: ebrick_case05_import (score 0.25; reasons: matches: csv)
            raw_file_import      (score 0.25; reasons: matches: csv)
decision  : selected ebrick_case05_import
prompt's own token set: NO candidate at all
```

The same construction works for `eis` → `selected eis_basic_qc`, `qc` → `selected ebrick_cp_g_qc`,
`the` → `selected ebrick_case05_import` (`data` yields the non-matching prefix `datazz`). So a
candidate, a `matches:` reason, and a selection can still originate in a token the user never typed,
which is precisely the class the preview rewrite was meant to eliminate — and the issue hint still
says "The preview carries the prompt's own distinct `[a-z0-9]+` tokens and nothing else". Only the
prompt's *characters* are user text here; the *token* is manufactured by the cut.

A generic instance of the invariant break (no decision effect, but the same class):

```powershell
.\.venv\Scripts\python.exe -c "import sys;sys.path.insert(0,'.');from flowview import backend_adapter as ba;from backend.routing import _tokens;p,_,_=ba._route_preview_message('a'*100000);print(len(_tokens(p)),len(_tokens('a'*100000)))"
# 3999 100000  -> two different tokens
```

Falsified if `_tokens(preview) ⊆ _tokens(prompt)` for every input (Round 3 held it 24/24; Round 4
holds it only for the 20 inputs that never truncate).

### P1-R4-3 — `preview_tokens` shadowing corrupts the steps and the meta value

`flowview/backend_adapter.py:371` rebinds `preview_tokens` — the routed **count** — to
`[token[:40] + … for token in dropped_tokens[:12]]`. Every later use of that name therefore prints
the *dropped* tokens where a count is claimed:

```powershell
$p = ("b" * 4000) + " eis qc"
```

```text
prompt size           -> ... routing consumed a 3999-character preview with
                         ['bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb…', 'eis', 'qc'] of the prompt's 3 distinct token(s)
retriever tokenisation-> ... the router was given ['bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb…', 'eis', 'qc'] distinct token(s) (…)
meta.routing_tokens   -> "['bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb…', 'eis', 'qc']"
meta.retriever_tokens -> "3";  meta.retriever_tokens_dropped -> "3"
```

Two problems in one line: the sentence "with X of the prompt's Y distinct token(s)" now shows the
dropped list instead of the routed count (the routed count here is 1), and the Round-3 meta contract
(`routing_tokens` = the routed count, verified 24/24 then) is broken **only** on the drop path. The
no-drop path is still correct (`"eis qc " + "A"*3994` → `"['aaaaaaaa…']"`; a clean long prompt →
`"6"`). Fix: rename the comprehension variable (for example `shown_drops`).

### P2-R4-1 — the preview can still be empty and `?` can still reach TaskState

| input | chars | preview | `_label(preview,'?')` | query | `meta.routing_tokens` | decision |
| --- | --- | --- | --- | --- | --- | --- |
| CJK-only | 13 000 | `""` | `?` | `[]` | `"0"` | no tool selected |
| `"a "*2001` | 4 002 | `""` | `?` | `[]` | `"0"` | no tool selected |
| `"🧪"*5000` | 5 000 | `""` | `?` | `[]` | `"0"` | no tool selected |
| `"אבג "*1500` | 6 000 | `""` | `?` | `[]` | `"0"` | no tool selected |

Truncation cannot help here: there is no `[a-z0-9]+` token to truncate. The behaviour is benign
(`?` tokenises to nothing, so no candidate can come from it) but the handoff's "no input can now
produce an empty preview or a `?` query" and "(b) no empty `routing_tokens`" do not hold, and the
literal `?` still reaches `TaskState.user_message`. Either accept and document this, or fall back to
`prompt[:limit]` (still the user's own characters, still zero tokens to the tokeniser).

## Confirmations per requested item

### (a) The P1-R3-1 repro

* `("b"*4000)+" eis qc"` → **not** fixed (P1-R4-1): `eis`/`qc` dropped, "no tool selected".
* `("eis qc ")+("b"*4000)` (oversized last) → preview `eis qc bbbb…`, `selected eis_basic_qc` 0.67 ✔.
* `("tok0000" … "tok0499")+" eis qc"` (4006 chars) → drops exactly `{eis, qc}` because 500 genuine
  prompt tokens fill the budget. **I agree with you**: that is inherent prefix truncation, not a
  defect, as long as the warning and the "decision is incomplete" caveat stand. The `break`/truncation
  issue is only about tokens that could have fit.

### (b) The 24-input subset battery re-run

* 20 inputs with `dropped == 0`: printed selection and confidence equal the prompt's own token set's
  model **20/20**, `_tokens(preview) ⊆ _tokens(prompt)` **20/20**, `meta` values correct.
* 4 inputs with `dropped > 0`: `_tokens(preview) ⊄ _tokens(prompt)` in all 4 (truncation or tail
  drop), `meta.routing_tokens` carries the dropped list instead of the count in all 4,
  `giant_token_plus` / `distinct_filler_keeps_eis` / `distinct_filler_drops_eis` print a decision
  different from the full-token model. All carry the warning + caveat.
* No input produced a candidate from text FlowView *wrote* — but P1-R4-2 shows a candidate from a
  token **manufactured by truncation**, which is the same practical class.

### (c) The cap and the caveat

* Cap: verified (261 / 268 / 340 characters, `…` marker).
* Caveat: the hint now explicitly covers route **and** confidence for the dropped path, and is
  absent when nothing was dropped (correct).

### (d) Read-only sweep and suites

| check | result |
| --- | --- |
| `unittest discover -s flowview/tests -t .` | `Ran 191 tests` · `OK (skipped=3)` · data/ diff empty |
| `unittest discover` | `Ran 324 tests` · `OK (skipped=7)` · `data/audit/task_summaries.jsonl` changed again (pre-existing `tests/test_contracts.py` `TestClient(app)` behaviour) |
| 23-run `--prompt` argv battery | 20×exit 0, 2×exit 2 (empty/whitespace), 1 OS argv refusal at 49 999 chars; no tracebacks; `data/`+`config/` byte-identical (14 files) |
| 11-case heavy in-process sweep (50k/200k, NUL, RTL, emoji, 14k CJK) | all exit 0, no traceback, no network audit events, data/config diff empty |

## Plain answer

The two Round-3 P2s you fixed are genuinely fixed, and the `zzz`/CJK injection repro is still clean.
But the truncation change introduced three P1s, two of which are one-line fixes:

1. fit whole tokens first and truncate only as a last resort (P1-R4-1 + P1-R4-2);
2. rename the shadowed `preview_tokens` in the dropped-token message block (P1-R4-3);
3. either fix or restate the empty-preview/`?` claim (P2-R4-1).

I would not finalise on this round. If you make those three changes I can re-run the 24-input subset
battery, the truncation-manufacture search, the message/step checks, and the read-only sweep in a few
minutes.

## Round-4 artefacts

`.tmp/verifier2/`: `r4_checks.py`, `r4_truncation_repro.py`, `r4_findings.json`,
`r4_truncation_prompt.txt` (the exact P1-R4-2 prompt), `readonly_report.json`,
`r2_readonly_inproc.json`, `regression_report.json`, logs `r4_readonly.log`,
`r4_readonly_inproc.log`, `r4_regression.log`.

---

# Round 5 — final confirmation

Scope: the two-phase preview, `shown_drops`, and `route.no_retriever_tokens`; plus the read-only
sweep and both suites. Same rules: this file is the only one I wrote.

## Round-5 verdict

| Item | Status |
| --- | --- |
| P1-R4-1 (fitting tail kept) | **Fixed.** `("b"*4000)+" eis qc"` → preview `"eis qc"` (2 tokens), `dropped=1`, subset True, **`selected eis_basic_qc`** (confidence 1.00). `("eis qc ")+("b"*4000)` and `"eis qc "+"A"*3994` behave the same. |
| P1-R4-2 (manufactured token) | **Fixed structurally.** 16 filler sizes × 5 terms (`csv`, `eis`, `qc`, `the`, `data`) → 0 subset violations, 0 decisions the prompt's own tokens cannot produce. `"csv"+"z"*100000` yields the 3999-char run `csvzzz…`, not `csv`, and selects nothing. |
| P1-R4-3 (`preview_tokens` shadowing) | **Fixed.** `routing_tokens` is an integer on every drop path (`'2'`, `'1'`, `'445'`) and both steps print numbers: "routing consumed a 6-character preview with 2 of the prompt's 3 distinct token(s)". |
| P2-R4-1 (`route.no_retriever_tokens`) | **Fixed as an issue**: present on CJK-13000 / `"a "*2001` / emoji-5000 / RTL-6000 with a workaround hint, `routing_tokens=0`, "no tool selected". |
| P2-R5-1 (new) | **The `?` placeholder is still handed to `TaskState`** for token-less long prompts, contrary to the handoff. Behaviourally harmless. |
| Subset property | Holds for 20/24 battery inputs; the 4 exceptions are the acknowledged all-oversized-token phase-2 cases, where **no candidate arises** and the longest active tool term is 14 characters against a 3999-character prefix. |
| Read-only / regression | Hold (23-run argv battery + 11-case heavy sweep clean; 191 OK/skipped=3; 324 OK/skipped=7). |
| Safe to hand over? | **Yes.** No P0 and no P1 remains; the single P2 has zero behavioural effect (details below). |

## Findings

| id | sev | finding | confidence |
| --- | --- | --- | --- |
| P2-R5-1 | P2 | `TaskState(user_message=...)` still receives the literal `?` for long prompts with no `[a-z0-9]+` token, because the fallback uses the (empty) *preview* instead of the prompt; the query stays empty, so nothing can come from it | high |

### P2-R5-1 — the placeholder is not gone, it just cannot match

`flowview/backend_adapter.py:470`:

```python
user_message=_label(preview_text if preview_tokens else preview_text[:MAX_TASK_MESSAGE], "?"),
```

For a long prompt with no token at all, `preview_text` is `""`, so the argument is `""[:4000]` and
`_label("", "?")` returns `"?"`. I instrumented `TaskState` and captured what the router really got:

| prompt | issues | `routing_tokens` | `user_message` |
| --- | --- | --- | --- |
| CJK-only 13 000 | `route.prompt_shortened_for_routing`, `route.no_retriever_tokens`, `route.prompt_tokens_unusable` | 0 | `'?'` |
| `"a "*2001` (4002) | same | 0 | `'?'` |
| `"🧪"*5000` | same | 0 | `'?'` |
| RTL 6000 | same | 0 | `'?'` |

So the handoff's "the router is never handed the `?` placeholder … no query can ever contain a
character the user did not type" is not literally true. It is harmless: `backend.routing._tokens("?")`
is `∅`, so no candidate or confidence can originate in it, and the printed flow is the same either
way. The one-word fix is to use `prompt_text[:MAX_TASK_MESSAGE]` (the prompt's own beginning, which
also satisfies `min_length=1`) instead of `preview_text[:MAX_TASK_MESSAGE]`; otherwise the code
comment and the claim should be reworded. Falsified if `user_message` equals the prompt's own
prefix for those inputs.

## Confirmations per requested item

### (a) P1-R4-1 repro and the manufacture construction

```text
("b"*4000)+" eis qc"     4007 chars -> preview "eis qc", routing_tokens=2, dropped=1, subset=True,  selected eis_basic_qc
("eis qc ")+("b"*4000)   4007 chars -> preview "eis qc", routing_tokens=2, dropped=1, subset=True,  selected eis_basic_qc
"eis qc "+"A"*3994      4001 chars -> preview "eis qc", routing_tokens=2, dropped=1, subset=True,  selected eis_basic_qc
"a"*100000                100000 chars -> preview 3999 chars, non-empty, no selection
```

Manufacture search (filler sizes 300/320/340/350/358/359/360/361/362/363/364/365/370/380/400/500 ×
`csv`/`eis`/`qc`/`the`/`data`): **0 subset violations, 0 decisions unexplained by the prompt's own
token set**. One wording correction: the preview tokens for the first case are `{eis, qc}` — the
`b…b` token is dropped, not carried — but the decision is as you measured.

### (b) Subset property, incl. the phase-2 verdict

* 20/24 battery inputs: `_tokens(preview) ⊆ _tokens(prompt)` **True**, and no selection outside the
  prompt's own token set.
* 4 exceptions, all "every token is oversized" phase-2 cases: `"a"*100000`, two 5000-char tokens,
  `"csv"+"z"*100000`, `"eis"+"y"*100000`. Subset **False** (the routed token is a 3999-character
  prefix), but `selected=[]` and `full-token model=[]` in all four.
* **Your claim survives, for this workspace**: the phase-2 prefix is always `MAX_TASK_MESSAGE - 1`
  = 3999 characters (phase 2 only runs with `size=0`), and the longest term across every active tool
  is **14 characters**. A match would require a tool whose `[a-z0-9]+` term is exactly that
  3999-character prefix; a future workspace with a custom node carrying a ≥3999-character
  alphanumeric term could in principle produce one, which I cannot rule out for arbitrary configs but
  which no shipped or configured tool here does.
* `distinct_filler_keeps_eis` (4006 chars) still drops exactly `{eis, qc}` — inherent prefix
  truncation, as agreed in Round 4, and disclosed.
* `distinct_filler_drops_eis` (6321 chars) keeps 444 fillers and then the genuine token `eis` in the
  leftover room, selecting `eis_basic_qc` 0.25 — a legitimate match on the user's own token, not a
  manufactured one.

### (c) Counts and the token-less path

* Drop paths: `routing_tokens` = `'2'` / `'1'` / `'445'` (integers); the `prompt size` step prints
  "… with 2 of the prompt's 3 distinct token(s)" and the tokenisation step prints counts.
* Token-less prompts: `route.no_retriever_tokens` present, `routing_tokens="0"`, "no tool selected",
  and — see P2-R5-1 — the query is empty but the TaskState message is the literal `?`.

### (d) Read-only sweep and suite counts

| check | result |
| --- | --- |
| `unittest discover -s flowview/tests -t .` | `Ran 191 tests` · `OK (skipped=3)` · data/ diff empty |
| `unittest discover` | `Ran 324 tests` · `OK (skipped=7)` · `data/audit/task_summaries.jsonl` changed again (pre-existing `tests/test_contracts.py` `TestClient(app)` behaviour) |
| 23-run `--prompt` argv battery | 20×exit 0, 2×exit 2 (empty/whitespace), 1 OS argv refusal at 49 999 chars; no tracebacks; `data/`+`config/` byte-identical (14 files, size+mtime_ns+sha256), nothing added |
| 11-case heavy in-process sweep (50k/200k, NUL, RTL, emoji, 14k CJK × json/text/mermaid) | all exit 0, no traceback, no network audit events, data/config diff empty |

## Plain answer

The three Round-4 P1s are gone and the injection class stays closed: the preview's query is a subset
of the prompt's own tokens for every input except the acknowledged all-oversized-token phase-2 case,
where it is a 3999-character prefix of the user's own text and no registry term can match it. The
dropped-token path is now honest (integer counts, capped list, explicit route-and-confidence caveat),
the message cap and the `route.no_retriever_tokens` issue behave as described, and both suites plus
the read-only sweeps are clean.

One P2 remains and it is cosmetic/claim-level only: the `?` placeholder still reaches `TaskState` for
token-less long prompts (`preview_text[:MAX_TASK_MESSAGE]` is the empty preview, not the prompt). It
cannot affect any candidate, confidence, exit code or printed line. Fix it with `prompt_text[:…]` or
reword the comment whenever convenient — it is not a reason to hold the deliverable. **I consider the
`--prompt` surface safe to hand over.**

## Round-5 artefacts

`.tmp/verifier2/`: `r5_checks.py`, `r5_findings.json`, `r5_battery.json`, `readonly_report.json`,
`r2_readonly_inproc.json`, `regression_report.json`, logs `r5_readonly.log`,
`r5_readonly_inproc.log`, `r5_regression.log`.

---

# Post-round-5 addendum (Lead)

**P2-R5-1 is closed in the code; the round-5 quotation above refers to an earlier revision** of
`flowview/backend_adapter.py`. The current line 471 is

```python
user_message=_label(preview_text or prompt_text[:MAX_TASK_MESSAGE], "?"),
```

so a token-less prompt is handed its own first characters, never the `_label` fallback. Measured
directly by capturing what `TaskState` receives (`.tmp/probe_p2_r5.py`, a `TaskState` subclass):

| prompt | chars | `routing_tokens` | `user_message` |
| --- | --- | --- | --- |
| CJK 13 000 | 13 000 | 0 | the prompt's own first 4000 characters |
| `"a "*2001` | 4 002 | 0 | same |
| emoji 5 000 | 5 000 | 0 | same |
| RTL 6 000 | 6 000 | 0 | same |
| `("b"*4000)+" eis qc"` | 4 007 | 2 | `"eis qc"` — the prompt's own distinct tokens (the disclosed preview path) |

No input hands the router a `?`. The single case whose `user_message` is not a literal prefix of the
prompt is the intended preview path — the prompt's own distinct `[a-z0-9]+` tokens — which is the
disclosed, injection-free behaviour verified in Round 4. The round-5 claim ("the router is never
handed the `?` placeholder") is therefore now true of the shipped code as written, not only in
effect.

After this addendum, no P0, P1 or P2 remains open on the `--prompt` surface. The two P2s still open
elsewhere in the package are listed in `flowview/README.md` §2 (`doctor --format mermaid` prints the
text report) and §4/§7 (a failed `--out` writes nothing to stdout in JSON mode); both are outside
this verification's scope and were reported by the first verification pass
(`flowview/VERIFICATION.md`).

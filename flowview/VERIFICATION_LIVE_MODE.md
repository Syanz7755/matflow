# FlowView live-mode (`--http`) verification record

Independent adversarial verification of the live HTTP mode added to `flowview/`, performed by a
separate verifier teammate that was handed the claims to falsify and had no authorship of the code
under review.

Scope of round 1: `flowview/client.py`, `flowview/live.py`, the `--http` wiring and the
`--out`-failure document in `flowview/cli.py`, and every claim in `flowview/README.md` §2/§7 and
`flowview/CONTRACT.md` ("Live mode"). The verifier could only write inside `.tmp/verifier3/`, ran the
stock backend exclusively with a temporary `MATFLOW_DATA_ROOT`, and snapshotted the repository
`data/` and `config/` trees before and after every experiment.

The verifier's report follows verbatim.

---

# verifier3 — adversarial verification of FlowView live mode (`--http`) + JSON `--out` fix

Repo: `D:\Projects\matflow` · interpreter `.\.venv\Scripts\python.exe` · all scratch artifacts in `.tmp/verifier3/`.

## Verdict per claim

| # | Claim | Verdict |
| --- | --- | --- |
| 1 | Offline is structural (no import / socket / `MATFLOW_API_URL` read without `--http`) | **holds** |
| 2 | Only the user's own words reach the router | **holds** |
| 3 | `--http` never writes the workspace; `http.route_recorded` present exactly when `POST /api/route` is called | **falsified** (disclosure omitted when the route call reaches the backend but its answer is unreadable) |
| 4 | Exactly one JSON document, documented exit codes, no traceback without `-v` | **falsified** (exit 1 on two payload classes; empty stdout for argparse-level usage errors) |
| 5 | Live payload mapping matches the REAL backend | **holds** on every happy path tested; the stub is not more forgiving |
| 6 | Totality: `live.py`/`client.py` never raise out of a reader | **falsified** (RecursionError and `int(NaN/Inf)` escape → exit 1) |

**Safe to hand over? No** — fix P1-1, P1-2, P1-3 (and ideally P1-4) first.

## Findings

| id | sev | finding | repro | observed vs expected | conf |
| --- | --- | --- | --- | --- | --- |
| P1-1 | P1 | `client.request_json` does not catch `RecursionError` from `json.loads`, so a deeply nested JSON answer escapes the reader and the CLI exits 1 (`flowview.internal_error`) instead of 3 | `python .tmp\verifier3\repro_findings.py` (F1/F1b): stub returns 5000-deep JSON for `/api/capabilities`, `/api/state`, `/api/route`; `flowview graph --http URL --format json -v` | exit **1**, `issues=[error:flowview.internal_error]`, stderr `client.py:169 json.loads … RecursionError: maximum recursion depth exceeded`; expected exit 3 with a readable issue (`CONTRACT.md`: "`request_json` returns `HttpResult` for every outcome … and never raises"; `client.py` docstring: "Every failure is returned, never raised") | high |
| P1-2 | P1 | `live._int` calls `int()` on floats, so `"version": NaN` / `Infinity` in `/api/state` escapes as `ValueError`/`OverflowError` → exit 1 | same script (F2): `/api/state` returns `{"version": NaN}`; `flowview flow --prompt "run eis qc" --http URL --format json -v` | exit **1**, `flowview.internal_error`, traceback `live.py:324 _route_request → live.py:65 _int → int(value)`; expected exit 3 or a warning + version 0. `flowview graph` on the *same* payload exits 0 with `graph.bad_version` — the two commands disagree | high |
| P1-3 | P1 | `_failure()` returns the route document without `http.route_recorded`, so a route call that the backend *did* record is silently undisclosed | `python .tmp\verifier3\serve_shim.py 8765` (real backend, temp data root) + `python .tmp\verifier3\route_proxy.py http://127.0.0.1:8765 8766` + `.\.venv\Scripts\python.exe -m flowview flow --prompt "run eis qc disclosure probe" --http http://127.0.0.1:8766 --format json` | exit 3, `issues=[error:http.route.invalid_json]`, **no** `http.route_recorded`; backend summary log grew 46→47 with `user_prompt="run eis qc disclosure probe"`. README §7: "The resulting document carries `http.route_recorded` (with the task id) so the side effect is never silent"; claim 3: "present exactly when that endpoint is called" | high |
| P1-4 | P1 | `/api/capabilities` answers that are 404 / non-JSON / truncated are reported as `http.unreachable` with the invented message "Cannot reach a MatFlow backend at …" while the server is reachable; the accurate transport code survives only in `detail` (invisible without `-v`) | stub answering HTTP 404 for `/api/capabilities`: `flowview graph --format json --http URL` | `error http.unreachable: Cannot reach a MatFlow backend at http://127.0.0.1:5776.` `detail='HTTP 404: Not Found'`. `doctor --http` on the same URL prints the *accurate* "The backend answered HTTP 404 for …/api/capabilities" under code `http.unreachable`, so the two live paths contradict each other. README §4 lists `http.capabilities.http_error` / `http.capabilities.invalid_json`, which no CLI output can emit | high |
| P2-1 | P2 | `http.unserialisable_request` (reachable: lone surrogate in `--prompt`) is not in README §4's live-code vocabulary | `main(['flow','--prompt','run eis\ud800qc','--http',URL,'--format','json'])` | exit 3, one JSON doc, `http.unserialisable_request`; correct behaviour, missing from the documented vocabulary | high |
| P2-2 | P2 | "`json` must always be valid, single-document JSON on stdout" is not literally true for argparse-level usage errors | `flowview --format json frobnicate` (empty stdout, exit 2); `flowview --format json` (help text on stdout, exit 2); `flowview --format json --version` (plain text, exit 0) | exit codes are correct; `args` is still `None` when `parser.error` fires, so `emit_error_document` cannot run. README scopes the guarantee to source errors and `--out`, so wording-level | high |
| P2-3 | P2 | The truncation hint says "The prompt printed below is the full text", but `--format mermaid` prints the prompt truncated and no issue block unless `-v` | 5662-char prompt, `flowview flow --prompt … --http URL --format mermaid` | mermaid stdout: full prompt absent, `…` present, hint absent (text/json do print the full text — verified byte-level and with a tail marker) | medium-high |
| P2-4 | P2 | Contract mismatch → `doctor --http` exits 3, while `graph --http` exits 0 without `--strict`; the troubleshooting row for `http.contract_mismatch` says "`--strict` makes it exit 3" | `flowview doctor --http <mismatch stub>` vs `flowview graph --http <mismatch stub>` | doctor 3 / graph 0. Consistent with doctor's own "3 any diagnosed problem" contract, so documentation tension only | high |

## Raw evidence

### Claim 1 — offline probe (`offline_driver.py`, 18 surfaces, `MATFLOW_API_URL` → recording stub)

```
total_stub_hits=0 :: 
import-only   rc=0 code=- socks=0 leaked= env= hits=0
graph-json    rc=0 code=0 socks=0 leaked= env=MATFLOW_DATA_ROOT,MATFLOW_FLOWVIEW_ROOT hits=0
graph-mermaid / graph-full-filters / graph-data-root / graph-strict-verbose / graph-timeout-only ... all socks=0 hits=0
flow-blueprint / flow-task / flow-prompt / flow-prompt-http-timeout ... socks=0 hits=0
summary / summary-limit / doctor / doctor-json-list / no-command / version ... socks=0 hits=0
```
No `MATFLOW_API_URL` read anywhere; `flowview.client` / `flowview.live` never in `sys.modules`.

### Claim 2 — 23 adversarial prompts recorded server-side (`prompt_probe.py` against the real backend)

Every case with a request satisfied `sent == prompt or sent == prompt[:4000]`, e.g.:

```
plain                 in=28   sent=28   eq_input=True
cjk_only              in=14   sent=14   eq_input=True
emoji_only            in=5    sent=5    eq_input=True
rtl_hebrew            in=33   sent=33   eq_input=True
exactly_4000_ascii    in=4000 sent=4000 eq_input=True
exactly_4001_ascii    in=4001 sent=4000 eq_prefix=True
exactly_4000_cjk      in=4000 sent=4000 eq_input=True
spaces_then_marker    in=4019 sent=4000 eq_prefix=True
nul_inside            in=14   sent=14   eq_input=True
long_single_token     in=5000 sent=4000 eq_prefix=True
flowview_issue_text   in=176  sent=176  eq_input=True
lone_surrogate        exit=3, no request (http.unserialisable_request)
```
Server-side recorded body (real backend, shim recorder):
```
POST /api/route body={"task": {"task_id": "flowview-http-preview", "user_message": "run basic EIS quality checks", "graph_version": 0, "available_input_types": ["RawData", "TypedTable"]}}
```

### Claim 5 — real backend (uvicorn `backend.main:app` via `serve_shim.py`, port 8765, `MATFLOW_DATA_ROOT=.tmp/verifier3/data`)

```
graph --http   -> exit 0, graph_id=local-default, 3 nodes / 2 edges mirrored
                  [('n-load','Load EIS data','completed','raw_file_import'),
                   ('n-norm','Normalize 归一化','running','normalize_columns'),
                   ('n-qc','Basic QC','ready','eis_basic_qc')]
flow --prompt  -> exit 0, candidate eis_basic_qc, confidence 1.00, http.route_recorded (task flowview-http-preview)
summary --task -> exit 0, route phase mirrored, http.live
doctor --http  -> exit 0, reachable / matflow-http 1.0 / server 1.1.0 / 14 operations
```
`/api/state` = `{"state": {...}, ...}`; `/api/route` = `RouterDecision.model_dump() | {"summary": ...}`;
`/api/task-summaries/{id}` = the record itself; `RouteRequest` is `{"task": TaskState}` and client sends exactly that.

### Claim 3 — backend log side effect (`serve_shim.py`, tmp log)

```
graph --http      exit=0 summary_lines=46
doctor --http     exit=0 summary_lines=46
summary --task    exit=0 summary_lines=46
flow --task       exit=0 summary_lines=46
```
Only `flow --prompt --http` appends. Repo `data/` + `config/` sha256 trees: 0 changed entries after every `--http` run
(mid checkpoint), 1 changed entry at the end — `data/audit/task_summaries.jsonl` — from the pre-existing `tests/` suite
(`tests/test_contracts.py`); its new tail records are `route-eis` / `route-unknown` fixtures, and `flowview-http-preview`
never appears in it.

## Not tested / limitations

* The stock (unshimmed) backend was never run: `backend/task_summary.py::_load_log_path` resolves
  `config/observability.json`'s `data/audit/task_summaries.jsonl` against the repo root regardless of
  `MATFLOW_DATA_ROOT`, so a stock `POST /api/route` dirties the repository. `serve_shim.py` changes *only* the
  summary-log destination; every other backend code path is stock. **Read-only observation:** the documented
  backend append therefore lands in the repository tree even when the backend is given a temp data root.
* The deep-nesting / NaN / Infinity triggers came from my own servers; the current stock backend cannot produce them.
* The route-disclosure failure was reproduced with a proxy that corrupts the response after the real backend
  recorded; I did not reproduce a natural backend timeout after recording.
* HTTPS/TLS backends were not tested.
* Windows argv cannot carry NUL or lone surrogates, so those two prompts were driven in-process through
  `flowview.cli.main` (same code path after argv parsing).
* Suites: `flowview/tests` 226 tests OK (skipped=3); `tests/` 133 tests OK (skipped=4).


---

# Round-1 outcome (Lead)

All four P1s were accepted and fixed; every P2 was addressed or documented.

| id | disposition |
| --- | --- |
| P1-1 `RecursionError` escaped `request_json` (exit 1) | **fixed** — `json.loads` catches `RecursionError` and reports `<endpoint>.invalid_json` ("nested too deeply to parse safely"); the request-body `json.dumps` and the HTTP-error detail parse catch it too |
| P1-2 NaN/Infinity `graph_version` escaped `_int` (exit 1) | **fixed** — `math.isfinite` guard; a non-finite version falls back to 0 |
| P1-3 the route side effect was undisclosed when the answer broke | **fixed** — the disclosure is emitted whenever the POST was *sent*: `info` when the recorded task id is known, `warning` when the answer was unreadable or the backend never answered, and nothing at all when the request was never sent |
| P1-4 an HTTP 404 / invalid JSON from `/api/capabilities` was called `http.unreachable` | **fixed** — `http.unreachable` only for a genuine unreachable answer; otherwise the transport's own code (`http.capabilities.http_error`, `http.capabilities.invalid_json`, …), and doctor marks `reachable` ok + `api_contract` FAIL instead of pretending nothing answered |
| P2-1 `http.unserialisable_request` missing from the vocabulary | **documented** in `flowview/README.md` §4 |
| P2-2 argparse-level usage errors left stdout empty in JSON mode | **fixed** — the argv is inspected when no namespace exists, so one `cli.usage` document is printed; the error document's `exit_code_hint` now equals the process exit code (`meta["exit_code"]`, honoured by `analysis.expected_exit_code`) |
| P2-3 the truncation hint claimed a Mermaid label is the full text | **reworded** in `flowview/live.py` and `flowview/backend_adapter.py` |
| P2-4 doctor vs `graph` contract-mismatch exit codes | **documented** in the `http.contract_mismatch` troubleshooting row |

Regression tests pin all of it: `RoundTwoRegressionTests`, `JsonUsageErrorTests` and
`test_a_non_finite_timeout_neither_hangs_nor_crashes` (`flowview/tests/test_http_live.py`), taking
the suite from 226 to 235 tests. `--http-timeout` is additionally clamped to 0.1–300 s so a
non-finite value can never become an infinite wait.

Round 2 — the verifier's re-attack of every fix — is recorded in the next section.

---

# Round 2 — re-attack of the round-1 fixes

# verifier3 — round 2 re-attack (FlowView live mode + JSON discipline)

All results against these revisions (stable for the whole run except where noted):

```
cli.py             37EEF00AB504118075B51153C65BC388959160943980CE9F7A12627053063024
client.py          7275C74553B5EC80468772B8CE7F5E37355E1CE92879D50E437487335174ED42
live.py            41A1C2D35F4F8A89D48DB48A9BEEA2EB8D508205E54FD2AD2A8059E60A5FFA1E
analysis.py        D62CFC9D72CA63CD…
loader.py          5335B037F8C5D92EEEF1DB44BD3646483A75CDAC5BCE14D10F67CBD1B857C33F
tasks.py           3F858BAF8714757903B2CC4217727431EB4B25D0E9045EE07359272EB8534F6C
test_http_live.py  4E961B6E62E79D7CAAC02789836586D812157CB8CA225D25D6A306C24908F826
```

Suites: `flowview/tests` **235 OK (skipped=3)**; `tests/` **133 OK (skipped=4)**.
Repo `data/`+`config/`: sha256 tree identical baseline→final except
`data/audit/task_summaries.jsonl` (+3606 B, tail records are the pre-existing `tests/`
fixtures `route-eis` / `route-unknown`; no `flowview-http-preview` and no probe prompt in it).

## Round-1 finding verdicts

| id | verdict | evidence |
| --- | --- | --- |
| P1-1 `RecursionError` escaped `request_json` | **fixed** for deep nesting | `caps_deep`, `caps_deep10k`, `state_deep`, `state_deep10k`, `route_deep`, `route_500_deep_body`, `task_deep` → exit 3, one doc, `<endpoint>.invalid_json`, no traceback. *But* the "`request_json` is total" claim still fails on non-UTF-8 bodies — R2-P1-A |
| P1-2 NaN/Infinity `graph_version` | **partially fixed** | `state_nan/inf/neginf` + `flow --prompt` → exit 0, `graph_version 0`; `graph` → `graph.bad_version` warning. Huge **integers** still escape in 5 places → R2-P1-B |
| P1-3 undisclosed route side effect | **fixed** | real backend behind a response-corrupting proxy: backend log 47→48, document carries `http.route_recorded` (warning) + `http.route.invalid_json` (error), exit 3, hint 3. *But* a false positive exists when nothing was sent → R2-P2-A |
| P1-4 misleading `http.unreachable` | **fixed for 404 / non-JSON / truncated**, **new regression for a mistyped URL** | `graph --http <404>` → `http.capabilities.http_error`, message "The backend answered HTTP 404 for …"; doctor → `ok reachable` + `FAIL api_contract`. `doctor --http not-a-url` → `ok reachable — the backend answered at not-a-url` → R2-P1-C |
| P2-1 `http.unserialisable_request` vocabulary | **fixed** | README §4 line 488 |
| P2-2 argparse-level usage errors in JSON mode | **fixed** | one `cli.usage` document, exit 2, `exit_code_hint` 2, help text not on stdout, `--out` never created (see hint matrix). One combination still mismatches → R2-P2-B |
| P2-3 truncation hint claimed a Mermaid label is full text | **fixed** | new hint: "The prompt printed in text and JSON mode is the full text you passed; a diagram label may still be elided for display." JSON carries the whole 5662-char prompt |
| P2-4 doctor vs `graph` contract-mismatch exit codes | **not fixed (documentation)** | README:735 still says only "`--strict` makes it exit 3"; nothing documents that `doctor --http` exits 3 without `--strict`. `VERIFICATION_LIVE_MODE.md:142` claims it is documented → R2-P2-D |

Round-1 side note: the dead `or "?"` fallback in `live._route_request` **is genuinely unreachable** —
`route_document` returns early when `not prompt_text.strip()`, so `prompt_text != ""` whenever
`_route_request` runs, and a non-empty string's `[:4000]` slice is never empty (`slice_falsy` is True
only for `""`). The placeholder can never be observed; a prompt of literally `?` produces the same
string legitimately.

## Addendum verdicts

**5. `--http-timeout` clamping — behavior correct, stated nuance wrong.**
White-box (`cli._live_target`): `nan|inf|-inf|1e400` → **5.0**; `400|301|300` → **300.0**;
`299` → **299.0**; `-5|0|0.05` → **0.1**.
Black-box against a server that never finishes answering: `nan` 5.12 s, `inf` 5.13 s, `1e400` 5.12 s
(no infinite wait), `2` 2.12 s, `0`/`0.05` 0.23 s, all exit 3.
**Correction:** `--http-timeout -5` (space form) is *not* a usage error — argparse accepts it as a
negative number and it clamps to 0.1 s (exit 0); `--http-timeout=-5` behaves identically (exit 0).
Only a non-numeric value (`soon`) is exit 2/`cli.usage`. Not documented in README (table still says
just "default 5"), so no false product claim — the aspiration in the addendum is simply inverted.

**6. `exit_code_hint` vs process exit code — one path mismatches.**
Equal for: success docs (0/0), `http.capabilities.http_error` graph+doctor (3/3), unreachable (3/3),
`flowview.internal_error` (1/1, `meta.exit_code="1"`), argparse `cli.usage` (2/2), `cli.no_command`
(2/2), semantic `cli.conflicting_sources` (2/2), `cli.out_failed` (3/3), `graph.missing_file`
(3/3), live route failures (3/3). No non-error document carries `meta["exit_code"]` (only
`cli.py:995` sets it; verified `document.meta` has no such key for successful documents).
*Intentional divergence:* `--strict` promotes a warning-only document to exit 3 while
`exit_code_hint` stays 0 (documented in `analysis.expected_exit_code`'s docstring; measured plain
exit 0/hint 0, strict exit 3/hint 0).
*Mismatch:* semantic usage error + failed `--out` → exit 2, stdout `cli.out_failed` document says
`exit_code_hint: 3` → R2-P2-B.

## New findings

| id | sev | finding | repro | observed vs expected | conf |
| --- | --- | --- | --- | --- | --- |
| R2-P1-A | P1 | `request_json` is still not total: `json.loads` on a non-UTF-8 body raises `UnicodeDecodeError`, which is not caught (only `JSONDecodeError`/`RecursionError` are) → exit 1 | gzip'd `/api/state` (or `/api/capabilities`, `/api/route`) stub; `.tmp/verifier3/r2_matrix.py` modes `state_gzip`, `gzip_body`, `route_gzip`, `state_bad_utf8` | `rc=1`, one doc `error:flowview.internal_error`; expected exit 3 `<endpoint>.invalid_json`. CONTRACT.md rule 5 ("`request_json` is total … invalid JSON … never raise") is false. Plausible in the wild: a proxy that gzips (urllib never decompresses) | high |
| R2-P1-B | P1 | Huge integers still escape as exit 1: `float(10**400)` → `OverflowError` in `live.py:498` (`score`), `live.py:541` (`confidence`), `loader.py:503` (node `position.x/y`), `tasks.py:88` (`decision.confidence`); and `str()` of a >4300-digit int (CPython `int_max_str_digits`) in `live._text/_label` | stubs `route_score_huge_int`, `route_confidence_huge_int`, `state_position_huge_int`, `task_huge_confidence`, `route_toolid_monster_int`, `task_monster_taskid`, `state_version_monster_int` | all `rc=1`, `error:flowview.internal_error`; expected a readable issue (exit 3). P1-2 is only partially fixed (non-finite floats handled, non-finite-magnitude ints not) | high |
| R2-P1-C | P1 | Round-2 regression: `doctor --http not-a-url` claims `ok reachable — the backend answered at not-a-url` while nothing was reached and arguably nothing is a URL; `graph --http not-a-url` correctly reports `http.capabilities.invalid_url`. `probe_document` treats `.invalid_url` as "the server answered" | `flowview doctor --http not-a-url` (text and JSON) vs `flowview graph --http not-a-url --format json` | doctor: `[completed] reachable` + `[error] api_contract "Not an http(s) URL: 'not-a-url/api/capabilities'"`, exit 3; graph: `error http.capabilities.invalid_url`, exit 3. README:733 tells users to run exactly this command to diagnose a bad origin | high |
| R2-P2-A | P2 | The route disclosure is emitted whenever `client.route()` was *called*, not whenever the POST was sent: a pre-send `http.unserialisable_request` (lone surrogate in the prompt) still carries `http.route_recorded` warning "The POST /api/route request was sent but the backend never answered" | in-process `main(['flow','--prompt','run eis\ud800qc','--http',real,'--format','json'])` (`.tmp/verifier3/disclosure_probe.py`) | warning present; backend summary log unchanged 47→47, so nothing was sent. CONTRACT.md rule 3 ("A request that was never sent carries no disclosure") is false | high |
| R2-P2-B | P2 | `exit_code_hint` mismatch: a semantic usage error (exit 2) whose `--out` write fails emits the fallback `cli.out_failed` document (hint 3) on stdout with no `meta.exit_code`; the original diagnosis is also lost | `flowview summary --format json --out <existing directory> --http <url>` (also `graph --format json --http URL --graph-file P --out <dir>`) | process exit 2, document `cli.out_failed`, `exit_code_hint: 3`, `meta` has no `exit_code`; the intended `cli.http_needs_task` never appears | high |
| R2-P2-D | P2 | `VERIFICATION_LIVE_MODE.md:142` states the doctor-vs-graph contract-mismatch exit codes are "documented in the `http.contract_mismatch` troubleshooting row", but README:735 documents only `--strict`; `flowview doctor --http <mismatch>` exits 3 without `--strict` (measured) and no document says so | `flowview doctor --http <mismatch stub>` = exit 3 vs `flowview graph --http <mismatch stub>` = exit 0 | doc claim false | high |
| R2-P2-E | P2 | `_json_requested` honours the **first** `--format`, not the effective (last-wins) one: `graph --format json --format text --width wide` prints a JSON document although the command line's effective format is text | `flowview graph --format json --format text --width wide` | exit 2, one JSON doc (hint 2); a text-mode user gets a JSON stream. Contrived | med |
| R2-P2-F | P2 | `--http http://user:pass@host` echoes the password into `source`/`where`/`message`/`base` (and therefore into `--out` files), and the userinfo form defeats urllib's loopback proxy bypass so the credential-bearing URL is sent to the configured HTTP proxy | `flowview graph --format json --http "http://user:secretpw@127.0.0.1:8765"` with the real backend running; vs the same URL without userinfo | userinfo URL → `http.capabilities.http_error` HTTP **502** from the machine's proxy (127.0.0.1:10801), password printed in the document; plain loopback URL → reaches the backend. User typed the credential, so impact is narrow | med |

## Could not test / caveats

* **Churn during the first round-2 run.** At ~16:26–16:28 `cli.py` briefly contained
  `str(exc.exit_code)` in `emit_error_document` (revision at 16:28:17 has the guarded
  `exit_code`). In that window *every* internal error crashed the error handler itself:
  no stdout document, raw traceback, exit 1. It is **not reproducible** against the hashes above,
  so it is reported as an observation about the edit window, not as a finding. All findings above
  were re-measured after the tree settled.
* Huge-int payloads come from my own stubs; the stock MatFlow backend cannot emit them today
  (`graph_version`/`score`/`confidence` are schema-bounded). The gzip/non-UTF-8 case needs a
  server/proxy that sets `Content-Encoding: gzip` or returns non-UTF-8 (urllib sends no
  `Accept-Encoding`, so the stock backend does not).
* Real-backend checks used `.tmp/verifier3/serve_shim.py` (temp `MATFLOW_DATA_ROOT` **and** a temp
  summary log, because `backend/task_summary.py` resolves the log from `config/observability.json`
  against the repo root). A stock backend would append to `data/audit/task_summaries.jsonl`.
* `state_utf16:graph` exits 0: `json.detect_encoding`'s NUL heuristics handle UTF-16 without a BOM —
  correct behavior, not a defect.
* IPv6, redirect loops (302 to self, 10-hop cap), `Content-Length` larger than the body, chunked
  responses, `Connection: close`, an empty route body, a non-object route body, `data_types` as a
  string/dict, `operations` as a list, `summary` as a list, a non-string `task_id`, a 500 with a
  5000-deep body, a server closing mid-response and a never-ending response all produced exactly one
  JSON document, exit 3, no traceback.


## Round-2 outcome (Lead)

| id | disposition |
| --- | --- |
| R2-P1-A non-UTF-8 / gzip body escaped as exit 1 | **fixed** — `request_json` catches `(UnicodeDecodeError, ValueError)`, with a distinct message for a non-decodable body versus a number Python refuses to parse. `json.loads` itself raises that plain `ValueError` for an integer above CPython's 4300-digit limit, so that case is covered by the same branch |
| R2-P1-B huge integers escaped as exit 1 (401-digit `float()` overflow in score/confidence/position; `str()` of a 5001-digit integer) | **fixed** — `model.safe_text` plus guarded conversions in `model.py`, `live.py`, `tasks.py`, `backend_adapter.py` and `loader.py`; 64-bit version/count clamp; non-finite floats dropped; `_json_normalize`/`_to_json` turn anything a later `json.dumps` would refuse into text. The round-2 reasoning is refined: a 5001-digit integer fails inside `json.loads`, so `invalid_json` (exit 3) is the honest result there, while a 401-digit one is mirrored as text (`not scored`, `not recorded`, no position) without a crash |
| R2-P1-C `doctor --http <mistyped>` reported `ok reachable` | **fixed** — `probe_document` branches three ways: `.unreachable` → FAIL reachable, `.invalid_url` → FAIL reachable "Not an http(s) URL", anything else (a 404 or invalid JSON answer) → ok reachable + FAIL api_contract |
| R2-P2-A disclosure for a request that was never sent | **fixed** — `live._request_was_sent` gates it (`unserialisable_request` and `invalid_url` fail before a socket opens) |
| R2-P2-B usage error + failed `--out` promised the wrong code and lost the diagnosis | **fixed** — `_emit`/`_report_out_failure` carry the intended exit code and the original issue; the document now holds both `cli.out_failed` and the semantic code, and `exit_code_hint` equals the process exit |
| R2-P2-D doctor-vs-graph mismatch exit codes undocumented | **documented** — the `http.contract_mismatch` and `http.route_recorded` troubleshooting rows were corrected |
| R2-P2-E `_json_requested` honoured the first `--format` | **fixed** — last value wins, matching argparse |
| R2-P2-F credentials in `--http` were echoed (and could reach a proxy) | **fixed** — refused with `cli.http_credentials` (exit 2) before any request, with a redacted origin; `client.has_credentials` plus a transport guard (`<endpoint>.credentials_not_supported`, `url == "(origin withheld)"`) are defence in depth, so nothing from the URL reaches stdout, stderr or `--out` |

Regression tests added in `flowview/tests/test_http_live.py` (`HostilePayloadTotalityTests`,
`DisclosureAccuracyTests`, `CredentialRefusalTests`, `OutputFailureHonestyTests`), taking the suite
from 235 to 248 tests. The Lead's own hostile-payload battery
(`.tmp/lead_hostile_battery.py`: 38 invocations with NaN, Infinity, 401-digit and 5001-digit integers
in every reachable position across `graph`/`summary`/`flow`/`doctor` in all three formats) is clean.

Round 3 — the verifier's re-attack of these fixes — is recorded below.

---

# Round 3 — re-attack of the round-2 fixes

# verifier3 — round 3 re-attack

Hashes held constant for the whole run (files last written 16:37–16:40; run started 16:47):
`cli.py ECACD9B1…`, `client.py 2B273BEB…`, `live.py C7448FAA…`, `model.py 02DF5EF7…`,
`tasks.py D9DEF170…`, `loader.py B63D486D…`, `backend_adapter.py 4EB912B6…`,
`test_http_live.py 771E0E20…`.

Suites: `flowview/tests` **248 OK (skipped=3)**, `tests/` **133 OK (skipped=4)**, whole-repo
discovery **381 OK (skipped=7)**; the lead's `.tmp/lead_hostile_battery.py` **38/38 clean**.
Repo `data/`+`config/`: sha256 tree identical except `data/audit/task_summaries.jsonl` (+3606 B,
tail = pre-existing `route-eis`/`route-unknown` `tests/` fixtures; no probe or credential text in it).

## Round-2 finding verdicts

| id | verdict | evidence |
| --- | --- | --- |
| R2-P1-A non-UTF-8 / gzip → exit 1 | **fixed** | 14 encoding cases, 0 exit 1. gzip (caps/state/route), bad UTF-8, UTF-8-only-BOM, body truncated mid-codepoint, 4301- and 5001-digit ints, `Content-Length` short → exit 3 `<endpoint>.invalid_json`. Messages accurate: "is not decodable JSON" + "The body is not UTF-8 JSON; a compressing or rewriting proxy…" for the decode branch; "contains a number Python refuses to parse" + the 4300-digit hint for the int branch. UTF-16 LE/BE (no BOM), UTF-8 BOM, chunked, `Transfer-Encoding: identity`, over-long `Content-Length` → exit 0 |
| R2-P1-B huge integers → exit 1 | **fixed** | 66 HTTP positions (state/route/task/caps) + a corrected 28-case `/api/state` sweep + 6 offline cases (graph file, trace, summary log): **0 exit 1, 0 tracebacks**. 401-digit ints → exit 0 (or a genuine shape issue, e.g. `edges.0.source` → `graph.edge_missing_endpoint`); 5001-digit ints → exit 3 `invalid_json` (or `task.unparsable_line` warning for a JSONL line, exit 0). Every 401/5001 case is in `{0,3}` |
| R2-P1-C doctor called a mistyped origin reachable | **fixed** | `doctor --http not-a-url` → `[error] reachable — Not an http(s) URL: 'not-a-url/api/capabilities'` + `[unknown] api_contract — not checked: no usable URL was given`, agreeing with `graph` (`http.capabilities.invalid_url`). Unreachable → `[error] reachable` + `[unknown] api_contract`. 404 → `[completed] reachable` + `[error] api_contract` ("The backend answered HTTP 404 …") |
| R2-P2-A false disclosure | **fixed** | lone-surrogate prompt: exit 3, `http.unserialisable_request`, **no** `http.route_recorded`, backend summary log unchanged (50→50). Every request that *was* sent still discloses: reset / empty body / 500 / 500+deep body / deep body / gzip / redirect-to-file → `http.route_recorded` |
| R2-P2-B `exit_code_hint` mismatch | **fixed** | `summary --format json --out <dir> --http URL` → exit **2**, one document with **both** `cli.out_failed` and `cli.http_needs_task`, `exit_code_hint` **2**, `meta.exit_code` 2. All other paths agree: success 0/0, `cli.usage` 2/2, `cli.no_command` 2/2, out-failed-on-success 3/3, source-unusable 3/3, internal errors 1/1 with `meta.exit_code` 1 |
| R2-P2-D doc rows | **fixed** | README:735 now documents `doctor --http` = exit 3 on a mismatch without `--strict`; README:739 says `http.route_recorded` is "info or warning" and "absent when the request was never sent"; README:479 lists `cli.http_credentials`. Residual wording in §2 prose → R3-P2-D |
| R2-P2-E `_json_requested` first-vs-last | **mostly fixed** | `graph --format json --format text --width wide` → stdout empty; `--format=json --format=text` → empty; `--format text --format json` → one doc; `--format` with no value → empty. Residual: a `--format=json` token that is an option *value* is still honoured → R3-P2-A |
| R2-P2-F credential leak | **fixed at the CLI** | `http://user:SECRET@host`, `http://user@host`, `%40`-encoded userinfo, `user:pass@host@host`, credentialed stub — each via `--http`, bare `--http`+`MATFLOW_API_URL`, bare `--http`+`MATFLOW_BACKEND_URL`, `doctor`, `-v`, and `--out`: exit 2, `cli.http_credentials`, 0 requests opened, secret absent from stdout, stderr **and** the `--out` file. Path `@` (`http://host/path@x`) is still accepted. Residual latent issues → R3-P2-B, R3-P2-C |

Confirmations: `--http-timeout -5` (space) and `=-5` are accepted and clamp to 0.1 s (not usage
errors) — consistent with the code and with the docs, which make no contrary claim; `nan/inf` → 5 s,
`400` → 300 s. The `or "?"` fallback at `live.py:395` is still present and still unreachable
(`slice_falsy` only for the empty string, which returns before `_route_request`). No *normal*
document carries `meta["exit_code"]`: only `cli.py:335` (`cli.out_failed`) and `cli.py:1032` (error
document) set it, and a neutral document reports `exit_code_hint` 0 with no `exit_code` key.

## New findings (all P2)

| id | finding | repro | observed vs expected |
| --- | --- | --- | --- |
| R3-P2-A | `_json_requested` matches a `--format=json` token that is an **option value**, so a *text-mode* usage error can emit a JSON document | `flowview flow --prompt "--format=json" graph`; `flowview graph --search "--format=json" --width wide`; `flowview graph --data-root "--format=json" --width wide` | exit 2 with a 935–944-byte JSON document on stdout; expected text mode → nothing on stdout. (`--prompt "--format json"`, with a space, is correctly ignored) |
| R3-P2-B | Latent, direct-API only: the transport guard withholds the URL in the issue, but `live.probe_document`/`graph_document` still echo the credentialed origin in `source`/`meta.base`, and `probe_document` asserts `[completed] reachable — the backend answered at http://user:SECRET@host` for a call that was refused *before* any socket | `live.probe_document("http://user:SECRET@127.0.0.1:1")`; `live.graph_document(...)` | codes are right (`http.capabilities.credentials_not_supported`) but the origin appears in `source`, `meta.base` and the step detail, and the `reachable` step is `completed`. Not reachable through the CLI (`_live_target` raises first); same "the server answered" assumption that produced R2-P1-C |
| R3-P2-C | A redirect to a credentialed URL bypasses the pre-send refusal: urllib follows it, `proxy_bypass` fails on the userinfo host, and the credentialed URL goes to the machine's HTTP proxy, whose 502 is reported as the backend's answer | stub answering `302 Location: http://user:SECRET@127.0.0.1:1/` | exit 3, `http.capabilities.http_error` "The backend answered HTTP 502 for http://127.0.0.1:PORT/api/capabilities."; redirect target received **no** request; no secret in stdout/stderr. No *user* secret is involved (the redirect's credentials are server-chosen) — reported as guard completeness / wrong attribution |
| R3-P2-D | Residual wording: README §2 blockquote (311–316) still says the document "carries `http.route_recorded` with the recorded task id" and never mentions the warning form or the no-request case, although the troubleshooting row (739) and the exit-code example (517) do | read README:311–316 vs 517/739 | prose one-sided; docs elsewhere correct |

## Could not test / caveats

* The proxy hop in R3-P2-C is inferred from the observed HTTP 502: this machine has
  `HTTP_PROXY=http://127.0.0.1:10801`, and loopback bypass works only for URLs without userinfo (I
  cannot observe the proxy's request line). The redirect target itself got zero requests.
* Huge-int and encoding payloads come from my own stubs; the stock backend cannot emit them. The
  gzip/non-UTF-8 case needs a proxying server (urllib sends no `Accept-Encoding`).
* Real-backend checks used `.tmp/verifier3/serve_shim.py` (temp data root and temp summary log,
  because `backend/task_summary.py` resolves the log from `config/observability.json` against the
  repo root).
* Offline structure re-verified after the round-3 edits: 18 offline surfaces with `MATFLOW_API_URL`
  pointed at a recording stub → 0 stub hits, 0 socket constructions, no `flowview.client`/`flowview.live`
  import, no `MATFLOW_API_URL` read.
* Not re-tested this round: HTTPS/TLS, IPv6 connectivity beyond the connection-refused case, and a
  natural (non-injected) backend timeout.


## Round-3 outcome (Lead)

The verifier's verdict: **safe to hand over — yes.** The three round-2 P1s are genuinely fixed
(14 encoding cases, 66 HTTP number positions plus a 28-case `/api/state` sweep and 6 offline cases,
all staying in {0,2,3} with no traceback), and the four remaining findings were narrow P2s. All four
were closed as well:

| id | disposition |
| --- | --- |
| R3-P2-A `_json_requested` honoured a `--format=json` token that was another option's value | **fixed** — the scan skips option values, treating `--http` as an optional-value option, so `flow --prompt "--format=json" graph` prints nothing on stdout |
| R3-P2-B a credentialed origin could still be echoed by the direct API, and a refused origin was marked `reachable` | **fixed** — `live._origin` withholds such an origin in `source`, `meta.base` and step details, and `probe_document` reports a `.credentials_not_supported` refusal as FAIL reachable |
| R3-P2-C a redirect to a credentialed URL was followed (through the machine's HTTP proxy) | **fixed** — the transport no longer follows redirects (`client._NoRedirect`); a 3xx becomes `<endpoint>.http_error` with "FlowView does not follow redirects" |
| R3-P2-D README §2 prose described only the happy-path disclosure | **fixed** — the blockquote now names the info / warning / absent cases, and the live-failure paragraph documents that redirects are not followed |

Regression tests: `ThirdPassRegressionTests` in `flowview/tests/test_http_live.py`, taking the suite
from 248 to 252 tests; the Lead's hostile battery stays 38/38 clean and whole-repo discovery reports
385 tests OK (skipped=7).



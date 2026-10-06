# FlowView internal contract (frozen)

`flowview/` is a read-only CLI subproject of MatFlow that prints **how the backend flows**
as Mermaid diagrams or terminal tables. It is deliberately **independent of backend logic**:
the mirror model, the renderers and the file readers are pure standard-library Python and
must keep working when `backend.*` is broken, missing or unimportable.

Authority rules this subproject obeys:

- FlowView never writes anything into `data/` and never calls a state-mutating backend path.
- FlowView may *optionally* import `backend.*` (adapter mode). Every such import is lazy and
  wrapped; a failure degrades to offline output plus a visible issue, never a traceback.
- FlowView's own data model is a mirror, not a re-export. Backend classes must never leak
  into renderer inputs.

## Hard constraints for every file in `flowview/`

1. **Standard library only.** No third-party imports (no `pydantic`, `yaml`, `pandas`, `pytest`).
2. Python 3.10+ syntax is fine; `from __future__ import annotations` at the top of each module.
3. Every module starts with a one-line purpose docstring.
4. No `print()` outside `cli.py` and `style.py`. Renderers/tools return `str`.
5. No module-level `import backend...`, no module-level work with side effects.
6. Nothing may raise out of a renderer or a reader for *malformed* input: convert it into a
   `FlowIssue` (or a `FlowGraphError`) and keep going. `--strict` is the only mode allowed to
   turn warnings into a non-zero exit.
7. Never truncate output silently: when a cap is applied, note it in the rendered text.

## Module ownership (do not edit files you do not own)

| Path | Owner |
| --- | --- |
| `flowview/CONTRACT.md`, `model.py`, `codes.py`, `analysis.py`, `loader.py`, `cli.py`, `__main__.py`, `client.py`, `__init__.py` | Lead |
| `flowview/mermaid.py`, `text.py`, `jsonout.py`, `style.py` | Renderer teammate |
| `flowview/phases.py`, `workspace.py`, `trace.py`, `tasks.py`, `backend_adapter.py` | Collector teammate |
| `flowview/README.md`, `flowview/tests/**`, `flowview/run_flowview.bat` | Tests teammate |

## Status vocabulary (`model.py: NodeStatus`, `StepStatus`)

`ready` | `running` | `completed` | `waiting` | `error` | `cancelled` | `unknown`

`unknown` is FlowView's own value: it means the source data did not carry a status FlowView
recognises. It must never be silently mapped to `completed`.

`IssueSeverity` = `info` | `warning` | `error`.

## Data model (`flowview/model.py`)

All dataclasses are frozen-slots. Every one has:

- `.to_dict() -> dict[str, Any]` — JSON-safe, key order = field order.
- `cls.from_dict(payload: Mapping[str, Any]) -> Self` — total and defensive; missing keys fall
  back to the field default, and a wrong-typed value must not raise (use the default and, where
  a field carries a diagnostic, prefer degrading to `unknown`).

```python
@dataclass(frozen=True, slots=True)
class FlowIssue:
    severity: IssueSeverity      # "info" | "warning" | "error"
    code: str                    # stable machine code, e.g. "graph.missing_file"
    message: str                 # one sentence, user-facing, English
    where: str | None = None     # file path / node id / command, when known
    hint: str | None = None      # one concrete next action, when known
    detail: str | None = None    # exception class + text, best effort

@dataclass(frozen=True, slots=True)
class FlowNode:
    id: str
    label: str
    tool_id: str | None = None
    tool_version: str | None = None
    category: str | None = None
    status: NodeStatus = "unknown"
    params: Mapping[str, Any] = field(default_factory=dict)
    input_ports: tuple[FlowPort, ...] = ()
    output_ports: tuple[FlowPort, ...] = ()
    error: str | None = None            # backend node error text
    issues: tuple[FlowIssue, ...] = ()  # FlowView's own per-node findings
    position: tuple[float, float] | None = None
    known_tool: bool | None = None      # None = registry not available
    review_after_run: bool = False

@dataclass(frozen=True, slots=True)
class FlowPort:
    name: str
    data_type: str | None = None

@dataclass(frozen=True, slots=True)
class FlowEdge:
    id: str
    source: str
    target: str
    source_port: str | None = None
    target_port: str | None = None
    data_type: str | None = None
    dangling: bool = False   # an endpoint is not in graph.nodes
    duplicate_input: bool = False  # second edge into an occupied single input port

@dataclass(frozen=True, slots=True)
class FlowGraph:
    graph_id: str = "local-default"
    version: int = 0
    nodes: tuple[FlowNode, ...] = ()
    edges: tuple[FlowEdge, ...] = ()
    source: str = ""                  # where this came from (path or mode)
    issues: tuple[FlowIssue, ...] = ()
    truncated: tuple[str, ...] = ()   # names of caps that were applied

@dataclass(frozen=True, slots=True)
class FlowStep:
    name: str
    status: StepStatus = "unknown"
    detail: str | None = None
    error: str | None = None
    node_id: str | None = None

@dataclass(frozen=True, slots=True)
class FlowPhase:
    name: str                        # stable id, e.g. "route"
    title: str                       # display name, e.g. "Route"
    steps: tuple[FlowStep, ...] = ()
    error: str | None = None

@dataclass(frozen=True, slots=True)
class FlowEvent:
    index: int
    phase: str                       # FlowPhase.name
    name: str
    status: StepStatus = "unknown"
    detail: str | None = None
    error: str | None = None
    node_id: str | None = None
    tool_id: str | None = None

@dataclass(frozen=True, slots=True)
class FlowTrace:
    events: tuple[FlowEvent, ...] = ()
    task_id: str | None = None
    trace_id: str | None = None
    source: str = ""
    phases: tuple[FlowPhase, ...] = ()   # observed/expected phase order for this source
    issues: tuple[FlowIssue, ...] = ()

@dataclass(frozen=True, slots=True)
class FlowDocument:
    title: str
    source: str
    graph: FlowGraph | None = None
    trace: FlowTrace | None = None
    phases: tuple[FlowPhase, ...] = ()
    issues: tuple[FlowIssue, ...] = ()
    meta: Mapping[str, str] = field(default_factory=dict)
    truncated: tuple[str, ...] = ()
```

`FlowDocument.phases` is the *canonical checkout* of the flow for table rendering: the runtime
phase map when a trace/blueprint exists, otherwise the structural phases derived from the graph.

## Derived analysis (`flowview/analysis.py`, Lead-owned, stdlib only)

```python
def derive_phases(trace: FlowTrace) -> tuple[FlowPhase, ...]
def phase_status(phase: FlowPhase) -> StepStatus
def summarize_trace(trace: FlowTrace) -> TraceSummary           # dataclass, to renderer-view
def graph_phases(graph: FlowGraph) -> tuple[FlowPhase, ...]
def topological_order(graph: FlowGraph) -> tuple[str, ...]      # raises FlowCycleError
def graph_layers(graph: FlowGraph) -> tuple[tuple[FlowNode, ...], ...]  # raises FlowCycleError
def find_cycles(graph: FlowGraph) -> tuple[tuple[str, ...], ...]        # never raises
def build_document(*, graph=None, trace=None, title, source, issues=(), modes=()) -> FlowDocument
def focus_subgraph(graph: FlowGraph, node_ids: Iterable[str], *, radius: int = 1) -> FlowGraph
def filter_graph(graph: FlowGraph, *, statuses=(), tool_ids=(), search=None) -> FlowGraph
```

## Rendering API (Renderer teammate)

```python
# flowview/mermaid.py
class MermaidRenderer:
    def __init__(self, *, direction: str = "TD", include_params: bool = False,
                 max_label: int = 48, style: "Style | None" = None) -> None: ...
    format: ClassVar[str] = "mermaid"
    def render_document(self, document: FlowDocument) -> str: ...
    def render_graph(self, graph: FlowGraph) -> str: ...     # flowchart
    def render_trace(self, trace: FlowTrace) -> str: ...     # sequence diagram
    def render_state(self, graph: FlowGraph) -> str: ...     # stateDiagram-v2 of node statuses

# flowview/text.py
class TextRenderer:
    format: ClassVar[str] = "text"
    def __init__(self, *, width: int = 0, color: bool | None = None,
                 style: "Style | None" = None) -> None: ...
    def render_document(self, document: FlowDocument) -> str: ...
    def render_graph(self, graph: FlowGraph) -> str: ...     # box tree + tables
    def render_trace(self, trace: FlowTrace) -> str: ...     # phase timeline
    def render_phases(self, phases: Sequence[FlowPhase]) -> str: ...
    def render_issue_table(self, issues: Sequence[FlowIssue]) -> str: ...

# flowview/jsonout.py
class JsonRenderer:
    format: ClassVar[str] = "json"
    def __init__(self, *, indent: int = 2) -> None: ...
    def render_document(self, document: FlowDocument) -> str: ...   # doc | {"phases": ...}
    def render_graph(self, graph: FlowGraph) -> str: ...

# flowview/style.py
class Style:
    def __init__(self, enabled: bool = False) -> None: ...
    def bold(self, text: str) -> str: ...
    def dim(self, text: str) -> str: ...
    def status(self, text: str, status: str) -> str: ...   # ANSI per status, no-op when disabled
    def issue(self, text: str, severity: str) -> str: ...
def color_enabled(stream: Any | None = None, override: bool | None = None) -> bool
def display_width(text: str) -> int          # East-Asian-width aware
def pad(text: str, width: int) -> str
def truncate(text: str, width: int) -> str
def wrap(text: str, width: int) -> list[str]
```

Mermaid output rules: valid `flowchart TD` / `sequenceDiagram` / `stateDiagram-v2` syntax,
no ANSI codes ever, deterministic ordering (nodes by declaration order, edges sorted by
`(source, source_port, target, target_port)`), every label sanitised:
double quotes → `#quot;`, newlines → `<br/>`, `[]{}()|#` and backticks escaped, label truncated
to `max_label` with a trailing `…`, empty label falls back to the node id. Node shape by status
is allowed (rounded/rect/stadium/diamond) but must stay deterministic.

Text output rules: never wider than `width` when `width >= MIN_WIDTH` (auto-detect otherwise, fall
back to 100). `MIN_WIDTH = 20` is the floor: a narrower request is raised to 20 and the reason is
printed once to stderr, because a table cannot stay readable below that and emitting lines wider
than the request silently would be worse. Status is always spelled out in words *and* optionally
coloured, so `--no-color` loses no information. Box-drawing characters are used when the stream is
a terminal or its encoding is UTF-8/UTF-16/UTF-32 (`style.can_encode()`), otherwise ASCII `+-|`.
Note that the CLI reconfigures stdout to UTF-8 before rendering, so the ASCII branch is reached by
library callers and by unusual streams rather than by the default CLI invocation.

## Loading API (Lead + Collector teammates)

```python
# flowview/loader.py  (Lead)  — pure file/stream reading, no backend import
def read_graph(path: Path | None = None) -> FlowDocument      # default data/graph_state.json
def read_trace(path: Path, *, fmt: str | None = None) -> FlowDocument   # json / jsonl, auto
def read_task(path_or_id: str, *, fmt: str | None = None) -> FlowDocument  # jsonl|json|task_id
def read_state(path: Path | None = None) -> FlowDocument
def default_graph_path(root: Path | None = None) -> Path
def default_summary_path(root: Path | None = None) -> Path
def probe_sources() -> tuple[SourceStatus, ...]   # dataclass: name, path, exists, readable, detail

# flowview/trace.py  (Collector teammate)
parse_trace_payload(payload: Any) -> tuple[tuple[FlowEvent, ...], tuple[FlowIssue, ...]]
parse_trace_jsonl(text: str) -> tuple[tuple[FlowEvent, ...], tuple[FlowIssue, ...]]
trace_from_chat_result(result: Mapping[str, Any]) -> FlowTrace   # POST /api/chat "trace" array

# flowview/tasks.py  (Collector teammate)
parse_task_summary(payload: Mapping[str, Any]) -> FlowDocument
load_task_summaries(path: Path) -> tuple[FlowDocument, ...]
latest_task_documents(path: Path, *, limit: int = 10) -> tuple[FlowDocument, ...]

# flowview/workspace.py  (Collector teammate)
scan_workspace(root: Path | None = None) -> WorkspaceSnapshot    # audited runtime files
snapshot_row(snapshot: WorkspaceSnapshot) -> ...                 # table row for --list

# flowview/phases.py  (Collector teammate)
def phase_blueprint() -> tuple[FlowPhase, ...]      # canonical runtime phase map
def phase_index() -> Mapping[str, FlowPhase]
def render_blueprint_table(phases: Sequence[FlowPhase]) -> list[tuple[str, ...]]
```

`phase_blueprint()` is the authoritative written-down description of the backend runtime flow
(`request` → `route` → `confirm` → `patch` → `execute` → `review` → `persist`) with one step per
observable side effect. It is documentation-as-data: keep it consistent with
`backend/main.py` + `backend/workspace_runtime.py` and note a step's backend seam in
`FlowStep.detail`.

## Adapter API (Collector teammate)

```python
# flowview/backend_adapter.py
def backend_available() -> tuple[bool, str | None]     # (importable, reason when not)
def schema_document(root: Path | None = None) -> FlowDocument    # tool registry + types, read-only
def live_graph_document(root: Path | None = None) -> FlowDocument  # WorkspaceRuntime().read_state()
def dry_route(prompt: str, root: Path | None = None, **kw) -> FlowDocument  # read-only decide()
```

`live_graph_document` reads the workspace *in this process* through `WorkspaceRuntime`; its HTTP
counterpart (`live.graph_document`) reads a running server's `/api/state`. Both print the same
graph shape; only the transport differs.

Every function here must survive: backend import failure, missing config, `ValueError` from the
backend, and `IndexError`/`KeyError` malformed payloads. On failure return a `FlowDocument`
whose only content is an `error` issue with `hint` = `run 'python -m flowview doctor'`.

## Live mode (`flowview/client.py` + `flowview/live.py`, Lead-owned)

`client.py` is the transport: dependency-free, read-only HTTP against the versioned
`matflow-http` contract (`GET /api/capabilities`, `GET /api/state`,
`GET /api/task-summaries/{task_id}`, `POST /api/route`). `request_json` returns
`HttpResult` for every outcome — bad URL, unreachable, HTTP error, invalid JSON, transport
exception — and never raises.

`live.py` turns those payloads into `FlowDocument`s. Its rules:

| Function | Endpoint | Notes |
| --- | --- | --- |
| `graph_document(base, timeout=, full=)` | `GET /api/state` | mirrors `payload["state"]` through `loader.graph_from_payload`; a payload without a `state` object is an error issue |
| `task_document(task_id, base, timeout=)` | `GET /api/task-summaries/{task_id}` | mirrors one record through `tasks.parse_task_summary` |
| `route_document(prompt, base, timeout=, available_input_types=)` | `POST /api/route` | the preview task declares `graph_version` read from `/api/state`; `user_message` is the prompt's own first 4000 characters and never FlowView-authored text |
| `probe_document(base, timeout=)` | `GET /api/capabilities` | reachability + contract verdict for `doctor` |

Rules that hold for every live document:

1. an unreachable server, a wrong contract, a broken payload or an HTTP error becomes an `error`
   issue, so the command exits `3`; a contract mismatch alone is a `warning`;
2. the document carries an `info` issue `http.live` naming the origin and the endpoint it was read
   from, and `meta["transport"] == "http"`;
3. `POST /api/route` makes the *backend* append a routing summary to its audit log, so
   `route_document` carries `http.route_recorded` whenever the request was **sent** — with the
   recorded task id when the answer names it, and severity `warning` when the outcome is unknown
   (an unverified side effect must never read as a neutral fact). A request that was never sent
   carries no disclosure;
4. the transport keeps one code per condition: `http.unreachable` only when nothing answered, and
   `<endpoint>.http_error` / `<endpoint>.invalid_json` / `<endpoint>.invalid_url` when the server
   answered badly, so a 404 is never described as "cannot reach";
5. `request_json` is total: a bad URL, an unreachable host, an HTTP error, invalid JSON, a body that
   is not UTF-8 (a gzip stream, a trimming proxy), a body whose integer exceeds CPython's 4300-digit
   conversion limit, a too-deeply-nested body (`RecursionError`), a credential-bearing URL, an
   un-serialisable request body and any transport exception all return an `HttpResult` and never
   raise;
6. no reader is tripped by a number JSON can carry but Python cannot always convert: `str()` of an
   integer goes through `model.safe_text`, versions/counts are clamped to 64 bits, non-finite floats
   are dropped, and `_json_normalize`/`_to_json` convert anything a later `json.dumps` would refuse
   (NaN, Infinity, integers beyond 64 bits or 4300 digits) into text. A 5001-digit integer therefore
   becomes `invalid_json` (exit 3) while a 401-digit one is mirrored as text (`not scored`,
   `not recorded`, no position);
7. redirects are not followed: a flow must come from the origin the caller named, so a 3xx is
   reported as `<endpoint>.http_error` with "FlowView does not follow redirects" instead of being
   obeyed (a redirect target with userinfo would also walk past the credential check);
8. FlowView itself still writes nothing on any `--http` path.

## CLI surface (Lead-owned)

```
python -m flowview [--version] [--no-color] [--strict] [-v] <command> ...
```

| Command | Purpose | Exit codes |
| --- | --- | --- |
| `graph` | print the current workspace graph as a diagram/table | 0 ok, 3 missing/corrupt source |
| `run-flow` / `flow` | print the canonical runtime phase map (`--blueprint`), replay one recorded task (`--task`), replay a trace file (`--from`), or render the flow for one request (`--prompt`) | 0 ok, 3 unusable source |
| `summary` | newest recorded task summaries as a timeline/tables | 0 ok, 3 no summaries |
| `doctor` | diagnose sources, backend import, terminal | 0 healthy, 3 any diagnosed problem (unreadable source, renderer failure), 1 never (only unexpected internal errors use 1) |

Common options: `--format {mermaid,text,json}` (default `text`), `--out PATH`, `--width N`,
`--data-root PATH`, `--http [URL]`, `--http-timeout SECONDS`, `--version`, `--strict`,
`--no-color`. `json` must always be valid,
single-document JSON on stdout with nothing before or after it — including on failure: when a
source is unusable, `--format json` still emits one error document (with the diagnosis in its
`issues`) so a JSON consumer never sees an empty stream, and a failed `--out` write emits one
`cli.out_failed` document instead of an empty stdout. A usage error is documented from the argv
even when `argparse` failed before a namespace existed, so `--format json` emits one `cli.usage`
document there too. In `text` mode a source error is reported
on stderr with an empty stdout. `--width N` bounds every stdout line the CLI emits, including the
trailing status/issue block.

Exit codes: `0` success, `1` unexpected internal error, `2` usage error, `3` input/backend
problem (reported as a readable issue list, never a traceback unless `-v`). `--strict` promotes
`warning` issues to exit `3`.

`cli.main(argv: Sequence[str] | None = None) -> int` is the only entry point; `__main__.py` calls
`raise SystemExit(main())`.

`flow --prompt TEXT` renders one request's flow through the read-only routing adapter
(`backend_adapter.dry_route`): no model call, no `record_routing()`, no graph write. Its document
adds a `prompt` phase whose third step reports the retriever's tokenisation (ASCII token count,
kept tokens, CJK character count) and raises `route.prompt_tokens_unusable` when the prompt is
mostly CJK, because `backend/routing.py` tokenises with `[a-z0-9]+` and therefore cannot see CJK
text. An empty `--prompt` is a usage error (exit 2).

`--http [URL]` switches the command from local files to a running backend. The flag is absent by
default, so offline behaviour is structural: without it no subcommand imports the HTTP client and
no socket is opened, even when `MATFLOW_API_URL` is set. Bare `--http` resolves the origin from
`MATFLOW_API_URL`/`MATFLOW_BACKEND_URL`, then `http://127.0.0.1:8000`; an origin that embeds
credentials is refused (`cli.http_credentials`, exit 2) before any request, because FlowView prints
the origin it reads from. Supported combinations:
`graph --http`, `flow --prompt --http`, `flow --task ID --http`, `summary --task ID --http`, and
`doctor --http` (which keeps its whole offline report and adds a `Live backend (--http)` section).
Anything else is a usage error: `--http` cannot be combined with `--graph-file`, `--from-file` or
`--file` (exit 2, `cli.conflicting_sources`); `flow --http` without `--task`/`--prompt` is exit 2
(`cli.http_needs_source`, because the blueprint is built in and `--from-file` is a local file); and
`summary --http` without `--task` is exit 2 (`cli.http_needs_task`, because the contract has no
summary-list endpoint).

`flowview/tools/` is a separate, optional package of report generators (batch suite runner,
route-sync helper). It is never imported by the CLI or the tests, so deleting it leaves
`python -m flowview` fully functional.

## Error handling contract (`flowview/codes.py`, Lead-owned)

```python
class FlowViewError(Exception):        # base, carries .issue
class FlowUsageError(FlowViewError)    # exit 2
class FlowSourceError(FlowViewError)   # exit 3
class FlowBackendError(FlowViewError)  # exit 3
class FlowRenderError(FlowViewError)   # exit 1
class FlowCycleError(FlowSourceError)  # unusable DAG, exit 3

def issue_from_exception(exc: BaseException, *, code: str, where: str | None = None,
                         severity: IssueSeverity = "error", hint: str | None = None) -> FlowIssue
def guard(code: str, *, where=None, severity="warning", hint=None, default=None):
    """Decorator: convert any exception into a FlowIssue on the returned value, or `default`."""
```

## Acceptance evidence required from every teammate

1. `python -m flowview --help` and each new subcommand runs.
2. `python -m flowview graph --format mermaid`, `--format text`, `--format json` all produce
   output against the real `data/graph_state.json` (currently an empty graph — that path must
   be handled explicitly, not crash).
3. Malformed input fixtures (bad JSON, unknown status, dangling edge, cyclic graph, missing file)
   each produce an `error` issue and the documented exit code.
4. `python -m unittest` (or `pytest`) green for the new tests.
5. State the exact commands run and their observed output in the completion report.

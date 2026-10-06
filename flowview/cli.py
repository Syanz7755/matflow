"""Command line entry point: prints the MatFlow flow as Mermaid, tables, or JSON.

Usage is documented in ``flowview/README.md``. This module is the only place allowed to print
to stdout, and it never lets an expected failure escape as a traceback.
"""
from __future__ import annotations

import argparse
import dataclasses
import math
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Sequence

from . import analysis
from .codes import (
    EXIT_INTERNAL,
    EXIT_OK,
    EXIT_SOURCE,
    EXIT_USAGE,
    FlowSourceError,
    FlowUsageError,
    FlowViewError,
    describe_exception,
    exit_code_for,
)
from .model import NODE_STATUS_VOCABULARY, FlowDocument, FlowIssue, FlowPhase, FlowStep, SourceStatus

VERSION = "0.1.0"
PROG = "python -m flowview"
FORMATS = ("mermaid", "text", "json")

BANNER = f"FlowView {VERSION}"
#: stdout's encoding before `configure_stdout` rebinds it; used to pick ASCII vs Unicode glyphs.
CONSOLE_ENCODING: str | None = None


class _Parser(argparse.ArgumentParser):
    """An ``argparse`` parser whose failures are FlowView errors, not exit code 2 traces."""

    def error(self, message: str) -> Any:  # type: ignore[override]
        raise FlowUsageError(message, code="cli.usage", hint=f"Run '{PROG} --help' for the full surface.")


def common_options(*, suppressed: bool = False) -> argparse.ArgumentParser:
    """The options accepted both before and after the subcommand.

    ``argparse`` parses the sub-command into a *fresh* namespace and then copies every attribute
    onto the outer one, so a subparser default silently clobbers a value the user already supplied
    before the sub-command. The subparser copies therefore use ``default=SUPPRESS``: when the
    option is absent after the sub-command, the attribute is not set at all and the earlier value
    survives; when it is present, the later value wins.
    """

    def default(value: Any) -> Any:
        return argparse.SUPPRESS if suppressed else value

    common = _Parser(add_help=False)
    common.add_argument("--no-color", action="store_true", default=default(False), help="disable ANSI colour, keeping every status word")
    common.add_argument("--strict", action="store_true", default=default(False), help="treat warnings as failures (exit 3)")
    common.add_argument("-v", "--verbose", action="store_true", default=default(False), help="show tracebacks and extra detail")
    common.add_argument("--data-root", metavar="PATH", default=default(None), help="workspace root to read (default: this project)")
    common.add_argument("--format", choices=FORMATS, default=default("text"), help="output format (default: text)")
    common.add_argument("--out", metavar="PATH", default=default(None), help="write output to a file instead of stdout")
    common.add_argument("--width", type=int, default=default(0), help="text width; 0 auto-detects")
    common.add_argument("--graph-file", metavar="PATH", default=default(None), help="graph_state.json to read instead of the default")
    common.add_argument("--full", action="store_true", default=default(False), help="disable node and edge caps")
    common.add_argument(
        "--http",
        metavar="URL",
        nargs="?",
        const="",
        default=default(None),
        help=(
            "read the flow from a running backend over HTTP instead of local files; bare --http uses "
            "MATFLOW_API_URL or http://127.0.0.1:8000. Offline stays the default."
        ),
    )
    common.add_argument(
        "--http-timeout",
        metavar="SECONDS",
        type=float,
        default=default(None),
        help="how long to wait for a --http request (default: 5)",
    )
    return common


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog=PROG,
        description="Print the MatFlow backend flow as Mermaid diagrams or terminal tables.",
        epilog=(
            "Exit codes: 0 success, 1 unexpected internal error, 2 usage error, "
            "3 input/backend problem. FlowView is read-only and never modifies the workspace."
        ),
        parents=[common_options()],
    )
    parser.add_argument("--version", action="version", version=f"{BANNER}")

    commands = parser.add_subparsers(dest="command", metavar="COMMAND")
    parser.set_defaults(command=None)

    graph = commands.add_parser(
        "graph", help="print the current workspace graph as a flow diagram", parents=[common_options(suppressed=True)]
    )
    graph.add_argument("--direction", choices=("TD", "TB", "LR", "RL", "BT"), default="TD", help="Mermaid direction")
    graph.add_argument("--no-legend", action="store_true", help="omit the status legend in text output")
    graph.add_argument("--focus", metavar="NODE_ID", action="append", default=[], help="show a node and its neighbours (repeatable)")
    graph.add_argument("--radius", type=int, default=1, help="neighbourhood depth for --focus (default: 1)")
    graph.add_argument("--status", action="append", default=[], help="only nodes with this status (repeatable)")
    graph.add_argument("--tool", action="append", default=[], help="only nodes whose tool id or category matches (repeatable)")
    graph.add_argument("--search", metavar="TEXT", help="only nodes whose text contains TEXT")
    graph.add_argument("--layers", action="store_true", help="group text output by dependency layer")

    flow = commands.add_parser(
        "flow",
        help="print the backend runtime flow (phase map or a recorded task)",
        parents=[common_options(suppressed=True)],
        aliases=["run-flow"],
    )
    flow.add_argument("--blueprint", action="store_true", help="print the written-down runtime phase map (default when no task is given)")
    flow.add_argument("--task", metavar="TASK_ID", help="replay one recorded task summary by id")
    flow.add_argument("--from-file", "--from", metavar="PATH", dest="from_file", help="read a recorded trace JSON or JSONL file")
    flow.add_argument("--prompt", metavar="TEXT", help="render the flow for one user prompt (read-only routing preview: no model call, no graph write)")
    flow.add_argument("--direction", choices=("TD", "TB", "LR", "RL", "BT"), default="TD", help="Mermaid direction for a graph")
    flow.add_argument("--no-legend", action="store_true", help="omit the status legend in text output")

    summary = commands.add_parser(
        "summary", help="print recorded task summaries as a timeline", parents=[common_options(suppressed=True)]
    )
    summary.add_argument("--limit", type=int, default=10, help="how many recent tasks to show (default: 10)")
    summary.add_argument("--task", metavar="TASK_ID", help="show one task in full")
    summary.add_argument("--file", metavar="PATH", help="task summaries JSONL to read instead of the default")

    doctor = commands.add_parser(
        "doctor", help="diagnose sources, renderers, and optional backend access", parents=[common_options(suppressed=True)]
    )
    doctor.add_argument("--list", action="store_true", help="also list every audited runtime file")

    return parser


def option(args: argparse.Namespace, name: str, default: Any = None) -> Any:
    """Read an option that may live on either the main parser's or the subparser's namespace."""
    return getattr(args, name, default)


def _live_target(args: argparse.Namespace) -> tuple[str, float] | None:
    """Resolve ``--http`` into ``(origin, timeout)``, or ``None`` when the command stays offline.

    ``--http`` with no value means "the configured backend": ``MATFLOW_API_URL`` (or
    ``MATFLOW_BACKEND_URL``) then ``http://127.0.0.1:8000``. The option is absent by default, so the
    absence of a socket in offline mode is structural, not a promise.
    """
    explicit = option(args, "http")
    if explicit is None:
        return None
    from . import client

    value = explicit.strip() if isinstance(explicit, str) else ""
    origin = client.base_url(value or None)
    if client.has_credentials(origin):
        # Refused before anything is requested or printed: the check happens here so the credential
        # can never reach a document, an issue message or an --out file.
        raise FlowUsageError(
            "The --http value embeds credentials (user:password@host); FlowView does not accept them.",
            code="cli.http_credentials",
            hint=(
                "FlowView prints the origin it reads from, so a credential would be written into reports and "
                "--out files. Configure the backend without embedded credentials, or unset MATFLOW_API_URL."
            ),
        )
    requested = option(args, "http_timeout")
    try:
        timeout = float(requested) if requested is not None else client.DEFAULT_TIMEOUT
    except (TypeError, ValueError):
        timeout = client.DEFAULT_TIMEOUT
    if not math.isfinite(timeout):
        # ``--http-timeout nan`` would make ``max()`` return the floor, but ``inf`` would wait
        # forever: a non-finite timeout is a user mistake, not a reason to hang.
        timeout = client.DEFAULT_TIMEOUT
    return client.base_url(value or None), min(max(0.1, timeout), MAX_HTTP_TIMEOUT)


def _read_stdout_encoding() -> str:
    return getattr(sys.stdout, "encoding", None) or "utf-8"


def _style(no_color: bool) -> Any:
    """Build the colour helper, degrading to a no-op when ``style.py`` is unavailable."""
    try:
        from .style import Style, color_enabled

        enabled = color_enabled(sys.stdout, override=False if no_color else None)
        return Style(enabled=enabled)
    except Exception:  # noqa: BLE001 - colour must never be the reason printing fails
        class _Plain:
            def bold(self, text: str) -> str:
                return text

            def dim(self, text: str) -> str:
                return text

            def status(self, text: str, status: str) -> str:
                return text

            def issue(self, text: str, severity: str) -> str:
                return text

        return _Plain()


def _renderer(fmt: str, args: argparse.Namespace, style: Any) -> Any:
    if fmt == "mermaid":
        from .mermaid import MermaidRenderer

        return MermaidRenderer(direction=getattr(args, "direction", "TD"), style=style)
    if fmt == "json":
        from .jsonout import JsonRenderer

        return JsonRenderer()
    from .text import TextRenderer

    kwargs: dict[str, Any] = {
        "width": _width_of(args),
        "color": False if option(args, "no_color", False) else None,
        "style": style,
    }
    legend = not option(args, "no_legend", False)
    try:
        return TextRenderer(**kwargs, legend=legend)
    except TypeError:
        # An older renderer without the legend switch still has to work.
        return TextRenderer(**kwargs)


def encode_for_console(payload: str) -> str:
    """Return ``payload`` as text the current console can actually encode.

    A Windows console session frequently reports a legacy code page (``gbk`` here). Writing UTF-8
    text to it either raises ``UnicodeEncodeError`` or, worse, emits mangled bytes that look like
    corruption. Escaping only the characters the console cannot represent keeps the rest of the
    report byte-exact and makes the loss explicit (``\\u2026`` rather than ``?``).
    """
    encoding = _read_stdout_encoding()
    try:
        payload.encode(encoding)
        return payload
    except (UnicodeEncodeError, LookupError):
        return payload.encode(encoding, errors="backslashreplace").decode(encoding, errors="replace")


def detach_broken_stdout() -> None:
    """Point stdout at a null sink after a broken pipe.

    Writing to a closed pipe raises ``BrokenPipeError``, which FlowView already handles; the
    problem is the *final* flush the interpreter performs while shutting down, which would raise
    again and turn a graceful stop into exit status 120 with an "Exception ignored" banner. Rebinding
    stdout before that happens keeps the reported status clean.
    """
    try:
        sink = open(os.devnull, "w", encoding="utf-8", errors="replace")
    except OSError:
        return
    try:
        sys.stdout = sink  # type: ignore[assignment]
        sys.stderr = sink  # type: ignore[assignment]
    except Exception:  # noqa: BLE001 - best effort only
        pass


def _write_stdout(payload: str) -> bool:
    """Write one payload to stdout, degrading to an escapable form on a legacy console.

    A closed pipe counts as handled: the reader is gone, which is not a FlowView failure.
    """
    stdout = sys.stdout
    for candidate in (payload, encode_for_console(payload)):
        try:
            stdout.write(candidate)
            stdout.flush()
            return True
        except UnicodeEncodeError:
            continue
        except (BrokenPipeError, OSError, ValueError):  # a closed pipe is not an internal error
            detach_broken_stdout()
            return True
    return False


def _report_out_failure(
    target: str,
    exc: BaseException,
    args: argparse.Namespace,
    *,
    exit_code: int = EXIT_SOURCE,
    original: FlowIssue | None = None,
) -> None:
    """In JSON mode a failed ``--out`` still leaves exactly one JSON document on stdout.

    ``graph --format json --out <unwritable>`` used to exit 3 with an empty stdout, which breaks the
    one invariant every JSON consumer relies on. The diagnosis goes to stdout directly — never back
    through ``--out``, which is what just failed.

    ``exit_code`` is the code the command will actually return, so the document's
    ``exit_code_hint`` never contradicts the process; ``original`` keeps the diagnosis that was being
    reported when the write failed (a usage error is not replaced by a write error).
    """
    print(f"{BANNER}: cannot write {target}: {describe_exception(exc)}", file=sys.stderr)
    print("  Check the path; FlowView creates parent directories but not symlink loops.", file=sys.stderr)
    if _format_of(args) != "json":
        return
    issues = [
        FlowIssue(
            severity="error",
            code="cli.out_failed",
            message=f"Cannot write {target}: {describe_exception(exc)}",
            where=str(target),
            hint="Check the --out path (a directory, a permission, or a symlink loop). Nothing was written.",
        )
    ]
    if original is not None and original.code != "cli.out_failed":
        issues.append(original)
    document = analysis.build_document(
        title="FlowView error report",
        source="(none)",
        issues=tuple(issues),
        meta={
            "mode": "error",
            "failure": describe_exception(exc),
            "out": str(target),
            "exit_code": str(exit_code),
        },
        modes=("error",),
    )
    _write_stdout(_render(document, args, style=None))


def _emit(
    text: str,
    args: argparse.Namespace,
    *,
    exit_code: int = EXIT_SOURCE,
    original: FlowIssue | None = None,
) -> bool:
    """Write one payload to stdout or ``--out``, always newline-terminated.

    Returns ``False`` only when the payload could not be written at all, so a caller can report a
    source-level failure rather than claiming success. A closed pipe counts as handled.
    """
    payload = text if text.endswith("\n") else text + "\n"
    target = option(args, "out")
    if target:
        try:
            path = Path(target).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload, encoding="utf-8", errors="backslashreplace")
        except (OSError, RuntimeError, ValueError) as exc:
            # A bad --out path (a file where a directory is needed, a symlink loop, a missing
            # permission) is a user-input problem, not an internal error.
            _report_out_failure(target, exc, args, exit_code=exit_code, original=original)
            return False
        print(f"{BANNER}: wrote {len(payload)} characters to {path}")
        return True
    return _write_stdout(payload)


def _render(document: FlowDocument, args: argparse.Namespace, style: Any) -> str:
    fmt = _format_of(args)
    try:
        renderer = _renderer(fmt, args, style)
        if hasattr(renderer, "render_document"):
            return renderer.render_document(document)
        if fmt == "mermaid" and document.graph is not None:
            return renderer.render_graph(document.graph)
        if fmt == "text":
            if document.trace is not None and not document.phases:
                return renderer.render_trace(document.trace)
            return renderer.render_phases(document.phases)
        raise FlowViewError(
            f"Renderer for '{fmt}' cannot print this document.",
            code="render.unsupported",
            hint="Try --format text.",
        )
    except FlowViewError:
        raise
    except Exception as exc:  # noqa: BLE001 - a renderer failure must not produce empty stdout
        return _emit_unrenderable(document, args, exc)


MIN_WIDTH = 20
#: An upper bound for ``--http-timeout``: a request that waits longer than this is a mistake, and
#: ``inf`` must never turn into a hang.
MAX_HTTP_TIMEOUT = 300.0
_WIDTH_WARNED = False


def _width_of(args: argparse.Namespace) -> int:
    """The requested text width, or 0 when the caller did not constrain it.

    Below :data:`MIN_WIDTH` a table cannot stay readable (and cannot be narrow enough to matter),
    so the width is raised to that floor and the caller is told once, rather than silently emitting
    lines wider than asked for.
    """
    global _WIDTH_WARNED
    try:
        requested = int(option(args, "width", 0) or 0)
    except (TypeError, ValueError):
        return 0
    if requested == 0:
        return 0
    if requested < MIN_WIDTH:
        if not _WIDTH_WARNED:
            _WIDTH_WARNED = True
            print(
                f"{BANNER}: --width {requested} is below the {MIN_WIDTH}-column minimum; using {MIN_WIDTH}.",
                file=sys.stderr,
            )
        return MIN_WIDTH
    return requested


def _wrap_line(text: str, width: int, *, indent: str = "", style: Any = None) -> list[str]:
    """Wrap one line so the whole CLI obeys ``--width``, not just the renderer body.

    ``indent`` is applied to continuation lines only, so the available wrapping width is reduced by
    the indent before the text is broken up. Wrapping first and indenting afterwards would emit
    lines wider than the requested width.
    """
    if width <= 0 or not text:
        return [text]
    available = max(8, width - len(indent)) if indent else width
    wrapper = getattr(style, "wrap", None) if style is not None else None
    try:
        if callable(wrapper):
            parts = wrapper(text, available)
        else:
            import textwrap

            parts = textwrap.wrap(text, width=available, break_long_words=True, break_on_hyphens=False) or [text]
    except Exception:  # noqa: BLE001 - wrapping must never be the reason output fails
        parts = [text]
    if not parts:
        return [text]
    if len(parts) <= 1:
        return [text]
    head, *rest = parts
    return [head, *[f"{indent}{part}" for part in rest]]


def _announce(document: FlowDocument, args: argparse.Namespace, style: Any) -> None:
    """A trailing, human-readable status block: what was read, what went wrong."""
    fmt = getattr(args, "format", "text")
    if fmt == "json":
        return
    verbose = option(args, "verbose", False)
    if fmt == "mermaid" and not verbose:
        return
    width = _width_of(args)
    print()
    for line in _wrap_line(style.dim(f"{BANNER}: {analysis.status_line(document)}"), width, style=style):
        print(line)
    for issue in document.all_issues():
        prefix = {"error": "ERROR", "warning": "WARN ", "info": "INFO "}[issue.severity]
        text = f"  {prefix} {issue.code}: {issue.message}"
        if issue.where:
            text += f" [{issue.where}]"
        for line in _wrap_line(style.issue(text, issue.severity), width, indent=" " * 9, style=style):
            print(line)
        if issue.hint:
            for line in _wrap_line(style.dim(f"        -> {issue.hint}"), width, indent=" " * 11, style=style):
                print(line)
        if verbose and issue.detail:
            for line in _wrap_line(style.dim(f"        detail: {issue.detail}"), width, indent=" " * 16, style=style):
                print(line)


def _fail(message: str, args: argparse.Namespace, *, code: int = EXIT_SOURCE) -> int:
    """Report a source-level failure; in JSON mode the failure is still a valid document."""
    print(f"{BANNER}: {message}", file=sys.stderr)
    if _format_of(args) == "json":
        document = analysis.build_document(
            title="FlowView error report",
            source="(none)",
            issues=(
                FlowIssue(
                    severity="error",
                    code="flowview.source_unusable",
                    message=message,
                    hint="Run 'python -m flowview doctor' to inspect every source.",
                ),
            ),
        )
        try:
            _emit(_render(document, args, style=None), args)
        except Exception:  # noqa: BLE001 - the plain report already went to stderr
            pass
    return code


def _format_of(args: argparse.Namespace) -> str:
    value = option(args, "format", "text")
    return value if value in FORMATS else "text"


def _emit_unrenderable(document: FlowDocument, args: argparse.Namespace, exc: BaseException) -> str:
    """Last-resort output when a renderer fails: never leave stdout empty in JSON mode."""
    fmt = _format_of(args)
    if fmt == "json":
        payload = {
            "flowview_schema": "1.0",
            "document": document.to_dict(),
            "phases": [phase.to_dict() for phase in document.phases],
            "issues": [
                issue.to_dict()
                for issue in (
                    *document.all_issues(),
                    FlowIssue(
                        severity="error",
                        code="render.failed",
                        message=f"The {fmt} renderer failed: {describe_exception(exc)}",
                        hint="Re-run with -v for a traceback.",
                    ),
                )
            ],
            "render_error": describe_exception(exc),
        }
        import json as _json

        return _json.dumps(payload, ensure_ascii=True, indent=2, default=str)
    lines = [f"{BANNER}: the {fmt} renderer failed: {describe_exception(exc)}"]
    for issue in document.all_issues():
        lines.append(issue.render())
    return "\n".join(lines)


def command_graph(args: argparse.Namespace, style: Any) -> int:
    from .loader import read_graph

    live = _live_target(args)
    graph_file = option(args, "graph_file")
    if live is not None and graph_file:
        raise FlowUsageError(
            "--graph-file cannot be combined with --http.",
            code="cli.conflicting_sources",
            hint="Choose one: --http reads the live graph, --graph-file reads a local file.",
        )
    if live is not None:
        from .live import graph_document

        document = graph_document(live[0], timeout=live[1], full=option(args, "full", False))
    else:
        graph_path = Path(graph_file) if graph_file else None
        document = read_graph(graph_path, full=option(args, "full", False))
    focus = list(option(args, "focus", []) or [])
    statuses = list(option(args, "status", []) or [])
    tools = list(option(args, "tool", []) or [])
    search = option(args, "search")
    unknown_statuses = [status for status in statuses if status.lower() not in NODE_STATUS_VOCABULARY]
    if unknown_statuses:
        document = analysis.build_document(
            title=document.title,
            source=document.source,
            graph=document.graph,
            phases=document.phases,
            issues=(
                *document.issues,
                FlowIssue(
                    severity="warning",
                    code="filter.unknown_status",
                    message=(
                        f"--status value(s) {', '.join(repr(item) for item in unknown_statuses)} are not in "
                        f"the vocabulary: {', '.join(NODE_STATUS_VOCABULARY)}"
                    ),
                    hint="A filter that matches nothing is reported here instead of silently returning an empty graph.",
                ),
            ),
        )
    if document.graph is not None and (focus or statuses or tools or search):
        graph = document.graph
        if focus:
            graph = analysis.focus_subgraph(graph, focus, radius=max(0, option(args, "radius", 1)))
        if statuses or tools or search:
            graph = analysis.filter_graph(graph, statuses=statuses, tool_ids=tools, search=search)
        from .analysis import build_document

        document = build_document(
            title=document.title,
            source=document.source,
            graph=graph,
            phases=(),
            meta=dict(document.meta),
            issues=tuple(document.issues),
        )
    if not _emit(_render(document, args, style), args):
        return EXIT_SOURCE
    _announce(document, args, style)
    return exit_code_for(document.all_issues(), strict=option(args, "strict", False))


def command_flow(args: argparse.Namespace, style: Any) -> int:
    live = _live_target(args)
    document = None
    task_id = option(args, "task")
    trace_file = option(args, "from_file")
    prompt = option(args, "prompt")
    sources = [name for name, value in (("--task", task_id), ("--from", trace_file), ("--prompt", prompt)) if value]
    if len(sources) > 1:
        raise FlowUsageError(
            f"Choose one source at a time; got {', '.join(sources)}.",
            code="cli.ambiguous_source",
            hint="Pass exactly one of --task, --from or --prompt, or none for the blueprint.",
        )
    if live is not None:
        if trace_file:
            raise FlowUsageError(
                "--from-file cannot be combined with --http.",
                code="cli.conflicting_sources",
                hint="Choose one: --http reads a live task, --from-file reads a recorded trace on disk.",
            )
        if not (task_id or prompt is not None):
            raise FlowUsageError(
                "--http on 'flow' needs --task TASK_ID or --prompt TEXT.",
                code="cli.http_needs_source",
                hint="--blueprint is built in and --from-file reads a local file; neither can be read over HTTP.",
            )
    if task_id:
        if live is not None:
            from .live import task_document

            document = task_document(task_id, live[0], timeout=live[1])
        else:
            document = _load_task_document(task_id)
    elif trace_file:
        from .loader import read_trace

        document = read_trace(Path(trace_file), full=option(args, "full", False))
    elif prompt is not None:
        document = prompt_flow_document(prompt, live=live)
    if document is None:
        from .phases import blueprint_document

        document = blueprint_document()
    if not _emit(_render(document, args, style), args):
        return EXIT_SOURCE
    _announce(document, args, style)
    return exit_code_for(document.all_issues(), strict=option(args, "strict", False))


def prompt_flow_document(prompt: str, *, live: tuple[str, float] | None = None) -> FlowDocument:
    """Render one prompt's flow: read-only routing when the backend is usable, else a diagnosis.

    This is what makes ``flowview flow --prompt "..."`` work on a long request without a running
    model: the router it uses is deterministic and the call persists nothing. With ``--http`` the
    *running* backend decides instead, which is the only path that lets the backend record its own
    routing summary — the document says so.
    """
    if not prompt.strip():
        raise FlowUsageError(
            "--prompt needs a non-empty request.",
            code="cli.empty_prompt",
            hint='Pass the request text, for example: --prompt "run basic EIS quality checks".',
        )
    if live is not None:
        from .live import route_document

        return route_document(prompt, live[0], timeout=live[1])
    from .backend_adapter import dry_route

    return dry_route(prompt)


def _load_task_document(task_id: str) -> FlowDocument:
    from .loader import read_task

    return read_task(task_id)


def command_summary(args: argparse.Namespace, style: Any) -> int:
    from .tasks import load_task_document, load_task_summaries, summaries_document

    live = _live_target(args)
    task = option(args, "task")
    if live is not None and option(args, "file"):
        raise FlowUsageError(
            "--file cannot be combined with --http.",
            code="cli.conflicting_sources",
            hint="Choose one: --http reads a live task, --file reads a local task-summaries JSONL.",
        )
    if live is not None and not task:
        raise FlowUsageError(
            "--http on 'summary' needs --task TASK_ID.",
            code="cli.http_needs_task",
            hint=(
                "The matflow-http contract has no summary-list endpoint: 'GET /api/task-summaries/{task_id}' "
                "reads one task. Use --task TASK_ID, or drop --http to list the local log."
            ),
        )
    if task:
        if live is not None:
            from .live import task_document

            document = task_document(task, live[0], timeout=live[1])
        else:
            document = load_task_document(Path(task)) if Path(task).is_file() else _load_task_document(task)
        if not _emit(_render(document, args, style), args):
            return EXIT_SOURCE
        _announce(document, args, style)
        return exit_code_for(document.all_issues(), strict=option(args, "strict", False))

    from .loader import default_summary_path

    summary_file = option(args, "file")
    path = Path(summary_file) if summary_file else default_summary_path()
    if not path.exists():
        return _fail(
            f"no recorded task summaries at {path} (hint: enable config/observability.json task_summaries)",
            args,
        )
    documents = load_task_summaries(path)
    if not documents:
        return _fail(f"{path} contains no task summary records", args)
    limit = option(args, "limit", 10)
    try:
        limit_value = int(limit)
    except (TypeError, ValueError):
        limit_value = 10
    document = summaries_document(documents, limit=max(1, limit_value), source=str(path))
    if limit_value < 1:
        document = dataclasses.replace(
            document,
            issues=(
                *document.issues,
                FlowIssue(
                    severity="warning",
                    code="cli.limit_clamped",
                    message=f"--limit {limit_value} shows the newest task instead of none.",
                    hint="Use a positive --limit (for example --limit 5).",
                ),
            ),
        )
    if not _emit(_render(document, args, style), args):
        return EXIT_SOURCE
    _announce(document, args, style)
    return exit_code_for(document.all_issues(), strict=option(args, "strict", False))


def command_doctor(args: argparse.Namespace, style: Any) -> int:
    from .loader import default_summary_path, probe_sources

    lines: list[str] = [f"{BANNER} doctor", ""]
    problems = 0
    renderer_report: list[tuple[str, bool, str]] = []
    backend_available_flag = False
    backend_detail = ""

    lines.append("Runtime sources")
    sources: tuple[SourceStatus, ...] = probe_sources()
    for source in sources:
        mark = "ok  " if source.healthy else ("--  " if not source.exists else "FAIL")
        extra = source.detail or ""
        if source.bytes is not None:
            extra = f"{extra} ({source.bytes} bytes)" if extra else f"{source.bytes} bytes"
        lines.append(f"  {mark} {source.name:<16} {source.path}")
        if extra:
            lines.append(f"       {extra}")
        if source.exists and not source.readable:
            problems += 1
    summary_source = default_summary_path()
    lines.append("")

    lines.append("Renderers")
    for fmt in FORMATS:
        try:
            renderer = _renderer(fmt, argparse.Namespace(format=fmt, direction="TD", width=0, no_color=True), style)
            renderer_report.append((fmt, True, type(renderer).__name__))
            lines.append(f"  ok   {fmt:<8} {type(renderer).__name__}")
        except Exception as exc:  # noqa: BLE001 - doctor reports, never raises
            renderer_report.append((fmt, False, describe_exception(exc)))
            lines.append(f"  FAIL {fmt:<8} {describe_exception(exc)}")
            problems += 1
    lines.append("")

    lines.append("Optional backend adapter")
    try:
        from .backend_adapter import backend_available

        available, reason = backend_available()
        backend_available_flag, backend_detail = bool(available), reason or ""
        if available:
            lines.append("  ok   backend is importable (read-only adapter mode available)")
        else:
            lines.append(f"  --   backend not usable: {reason}")
            lines.append("       offline mode stays fully functional; flowview never requires the backend")
    except Exception as exc:  # noqa: BLE001
        backend_detail = describe_exception(exc)
        lines.append(f"  --   adapter unavailable: {describe_exception(exc)}")
        lines.append("       offline mode stays fully functional")
    lines.append("")

    live = _live_target(args)
    live_document: FlowDocument | None = None
    if live is not None:
        from .live import probe_document

        live_document = probe_document(live[0], timeout=live[1])
        lines.append("Live backend (--http)")
        live_steps = live_document.phases[0].steps if live_document.phases else ()
        for step in live_steps:
            mark = {"completed": "ok  ", "error": "FAIL"}.get(step.status, "--  ")
            lines.append(f"  {mark} {step.name:<16} {step.detail or ''}")
            if step.status == "error":
                problems += 1
        for issue in live_document.all_issues():
            lines.append(f"       {issue.severity.upper()}: {issue.code}: {issue.message}")
            if issue.hint:
                lines.append(f"         -> {issue.hint}")
        lines.append("")

    encoding = _read_stdout_encoding()
    is_tty = bool(getattr(sys.stdout, "isatty", lambda: False)())
    color_mode = "disabled by --no-color" if option(args, "no_color", False) else "auto"
    lines.append("Terminal")
    lines.append(f"  encoding  {encoding}")
    lines.append(f"  isatty    {is_tty}")
    lines.append(f"  color     {color_mode}")
    lines.append("")
    lines.append(f"Task summary log: {summary_source}")

    if option(args, "list", False):
        lines.append("")
        lines.append("Audited files")
        for source in sources:
            lines.append(f"  {source.path}")

    if _format_of(args) == "json":
        # In JSON mode the report is data, so `doctor --format json | jq` behaves like every
        # other subcommand. Callers that want the human layout use text or mermaid.
        document = analysis.build_document(
            title="FlowView environment report",
            source=str(sources[0].path) if sources else "",
            phases=(
                FlowPhase(
                    "sources",
                    "Runtime sources",
                    tuple(
                        FlowStep(
                            name=source.name,
                            status="completed" if source.healthy else ("pending" if not source.exists else "error"),
                            detail=f"{source.path}{f' ({source.detail})' if source.detail else ''}",
                        )
                        for source in sources
                    ),
                ),
                FlowPhase(
                    "renderers",
                    "Renderers",
                    tuple(
                        FlowStep(name=fmt, status="completed" if ok else "error", detail=detail)
                        for fmt, ok, detail in renderer_report
                    ),
                ),
                FlowPhase(
                    "adapter",
                    "Optional backend adapter",
                    (
                        FlowStep(
                            name="backend importable" if backend_available_flag else "offline only (by design)",
                            status="completed" if backend_available_flag else "unknown",
                            detail=backend_detail or "offline mode is fully functional without a backend",
                        ),
                    ),
                ),
                FlowPhase(
                    "terminal",
                    "Terminal",
                    (
                        FlowStep(name="encoding", status="completed", detail=encoding),
                        FlowStep(name="isatty", status="completed", detail=str(is_tty)),
                        FlowStep(name="color", status="completed", detail=color_mode),
                    ),
                ),
                *((live_document.phases[0],) if live_document is not None and live_document.phases else ()),
            ),
            meta={
                "mode": "doctor",
                "problems": str(problems),
                "healthy": "false" if problems else "true",
                "summary_log": str(summary_source),
                "encoding": encoding,
                "isatty": str(is_tty),
                **(
                    {
                        "transport": "http",
                        "live_base": live[0],
                        "live_reachable": str(live_document.meta.get("reachable", "")),
                        "live_contract_ok": str(live_document.meta.get("contract_ok", "")),
                    }
                    if live is not None and live_document is not None
                    else {}
                ),
            },
            modes=("doctor",),
            issues=(
                *((*live_document.all_issues(),) if live_document is not None else ()),
                *(
                    (
                        FlowIssue(
                            severity="error",
                            code="doctor.problems",
                            message=f"{problems} problem(s) were found in the FlowView environment.",
                            hint="See the 'sources', 'renderers' and live-backend phases for the failing item.",
                        ),
                    )
                    if problems
                    else ()
                ),
            ),
        )
        if not _emit(_render(document, args, style), args):
            return EXIT_SOURCE
        _announce(document, args, style)
        return exit_code_for(document.all_issues(), strict=option(args, "strict", False))

    print("\n".join(lines))
    if problems:
        print(f"{BANNER}: {problems} problem(s) found; see the FAIL lines above.")
        return EXIT_SOURCE
    if live is not None:
        print(f"{BANNER}: all offline sources are usable; the live backend at {live[0]} answered the contract check.")
        return EXIT_OK
    print(f"{BANNER}: all offline sources are usable.")
    return EXIT_OK


COMMANDS = {
    "graph": command_graph,
    "flow": command_flow,
    "run-flow": command_flow,
    "summary": command_summary,
    "doctor": command_doctor,
}


def resolve_data_root(value: str) -> tuple[Path | None, str | None]:
    """Resolve ``--data-root`` without ever raising.

    A self-referential symlink or junction makes ``Path.resolve()`` raise ``RuntimeError``, which
    would otherwise escape as an unexpected internal error, so the caller gets a message instead.
    """
    try:
        return Path(value).expanduser().resolve(), None
    except RuntimeError as exc:
        return None, f"--data-root could not be resolved ({exc}); the path is a symlink loop."
    except (OSError, ValueError) as exc:
        return None, f"--data-root could not be resolved ({exc})."


def dispatch(args: argparse.Namespace) -> int:
    handler = COMMANDS.get(args.command or "")
    if handler is None:
        raise FlowUsageError(
            "A subcommand is required.",
            code="cli.no_command",
            hint=f"Try '{PROG} graph', '{PROG} run-flow', '{PROG} summary' or '{PROG} doctor'.",
        )
    style = _style(option(args, "no_color", False))
    data_root = option(args, "data_root")
    if data_root:
        resolved, problem = resolve_data_root(data_root)
        if resolved is None:
            # Raised, not returned: main() then routes it through emit_error_document, so
            # `--format json` still produces one document instead of an empty stream.
            raise FlowSourceError(
                problem or f"--data-root could not be resolved: {data_root}",
                code="path.symlink_loop" if "symlink loop" in (problem or "") else "path.invalid",
                where=str(data_root),
                hint="Pass a real directory, or omit --data-root to use the project data directory.",
            )
        os.environ["MATFLOW_FLOWVIEW_ROOT"] = str(resolved)
    return handler(args, style)


def configure_stdout() -> str | None:
    """Prefer UTF-8 on stdout so diagrams keep their glyphs when output is redirected.

    Windows sessions often default to a legacy code page, which turns box-drawing characters and
    the truncation ellipsis into mangled bytes the moment output is piped. The write path still
    escapes anything the stream cannot encode, so this can never make output worse.

    Returns the encoding the console had *before* the rebind, because renderers need it to decide
    between box drawing and the documented ASCII fallback: once stdout is UTF-8, asking the stream
    would always answer "Unicode is fine", even on a console that cannot display it.
    """
    global CONSOLE_ENCODING
    CONSOLE_ENCODING = getattr(sys.stdout, "encoding", None)
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is None:
        return CONSOLE_ENCODING
    try:
        reconfigure(encoding="utf-8", errors="backslashreplace")
    except (ValueError, OSError, LookupError):
        pass
    return CONSOLE_ENCODING


def emit_error_document(exc: BaseException, args: argparse.Namespace | None) -> None:
    """In JSON mode, a failure still produces one valid JSON document on stdout.

    Callers that pipe FlowView into a JSON consumer must not have to special-case "the process
    failed and printed nothing"; the diagnosis travels inside the document.
    """
    if args is None or _format_of(args) != "json":
        return
    is_flowview_error = isinstance(exc, FlowViewError)
    issue = exc.issue if is_flowview_error else FlowIssue(
        severity="error",
        code="flowview.internal_error",
        message=describe_exception(exc),
        hint="Re-run with -v for a traceback, or run 'python -m flowview doctor'.",
    )
    # The document must not promise a different exit status than the process returns: a usage error
    # is exit 2, an internal error is exit 1, and only a real source/backend problem is exit 3.
    exit_code = exc.exit_code if is_flowview_error else EXIT_INTERNAL
    document = analysis.build_document(
        title="FlowView error report",
        source="(none)",
        issues=(issue,),
        meta={"mode": "error", "failure": describe_exception(exc), "exit_code": str(exit_code)},
        modes=("error",),
    )
    try:
        _emit(_render(document, args, style=None), args, exit_code=exit_code, original=issue)
    except Exception:  # noqa: BLE001 - stderr already has the human message
        pass


#: Options that consume the following token, so that token is a value and not a format request.
_VALUE_OPTIONS = frozenset(
    {
        "--out", "--width", "--data-root", "--graph-file", "--http-timeout", "--format",
        "--focus", "--radius", "--status", "--tool", "--search", "--task", "--prompt",
        "--from-file", "--from", "--limit", "--file",
    }
)
#: ``--http`` takes an *optional* value, so only a non-option-looking token becomes its argument.
_OPTIONAL_VALUE_OPTIONS = frozenset({"--http"})


def _json_requested(argv: Sequence[str] | None) -> bool:
    """Did the command line ask for JSON output?

    Needed when ``argparse`` fails before a namespace exists: the "one JSON document on stdout"
    invariant must hold for usage errors too, and at that point the argv is the only evidence.

    The scan skips the values of the other options, so ``--prompt "--format=json"`` is prompt text and
    not a format request, and it takes the last ``--format`` because that is what ``argparse`` does.
    """
    items = list(argv) if argv is not None else sys.argv[1:]
    requested = False
    skip = False
    for index, item in enumerate(items):
        if skip:
            skip = False
            continue
        previous = items[index - 1] if index else ""
        if item == "--format":
            if index + 1 < len(items):
                requested = items[index + 1] == "json"
            skip = True  # its own value must not be rescanned
            continue
        if item.startswith("--format="):
            requested = item.split("=", 1)[1].strip() == "json"
            continue
        if previous in _VALUE_OPTIONS:
            continue  # this token is the previous option's value
        if previous in _OPTIONAL_VALUE_OPTIONS and not item.startswith("-"):
            continue  # this token is the optional value of --http
        if item in _VALUE_OPTIONS or item in _OPTIONAL_VALUE_OPTIONS:
            skip = True  # the following token is an option value
    return requested


def main(argv: Sequence[str] | None = None) -> int:
    """Run one FlowView command. Returns the process exit code; never raises."""
    configure_stdout()
    parser = build_parser()
    args: argparse.Namespace | None = None
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
        if args.command is None:
            if _json_requested(argv):
                # Printing the help text in JSON mode would put prose on stdout where a consumer
                # expects exactly one document.
                missing = FlowUsageError(
                    "A subcommand is required.",
                    code="cli.no_command",
                    hint=f"Try '{PROG} graph', '{PROG} run-flow', '{PROG} summary' or '{PROG} doctor'.",
                )
                print(f"{BANNER}: {describe_exception(missing)}", file=sys.stderr)
                emit_error_document(missing, argparse.Namespace(format="json"))
                return EXIT_USAGE
            parser.print_help()
            return EXIT_USAGE
        return dispatch(args)
    except FlowViewError as exc:
        print(f"{BANNER}: {describe_exception(exc)}", file=sys.stderr)
        print(f"  {exc.issue.render()}", file=sys.stderr)
        emit_error_document(exc, _document_args(args, argv))
        if args is not None and option(args, "verbose", False):
            traceback.print_exc()
        return exc.exit_code
    except KeyboardInterrupt:
        print(f"{BANNER}: interrupted", file=sys.stderr)
        return 130
    except BrokenPipeError:
        detach_broken_stdout()
        return EXIT_OK
    except Exception as exc:  # noqa: BLE001 - the CLI must always exit with a code, not a crash
        print(f"{BANNER}: unexpected internal error: {describe_exception(exc)}", file=sys.stderr)
        emit_error_document(exc, _document_args(args, argv))
        if args is not None and option(args, "verbose", False):
            traceback.print_exc()
        else:
            print("  Re-run with -v for a traceback, or run 'python -m flowview doctor'.", file=sys.stderr)
        return EXIT_INTERNAL


def _document_args(args: argparse.Namespace | None, argv: Sequence[str] | None) -> argparse.Namespace | None:
    """The namespace an error document should be rendered with.

    A parse failure leaves ``args`` unset, so JSON mode is recovered from the argv instead; the
    document always goes to stdout (``--out`` is deliberately not carried over, since the write is
    what failed in the ``cli.out_failed`` case).
    """
    if args is not None:
        return args
    if _json_requested(argv):
        return argparse.Namespace(format="json")
    return None


if __name__ == "__main__":  # pragma: no cover - exercised through __main__.py
    raise SystemExit(main())
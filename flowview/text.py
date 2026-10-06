"""Plain-text rendering: headers, phase timelines, dependency layers and width-aware tables."""
from __future__ import annotations

import shutil
import sys
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from . import analysis
from .codes import FlowCycleError
from .model import NODE_STATUSES
from .style import Style, can_encode, color_enabled, display_width, pad, strip_ansi, wrap

_FALLBACK_WIDTH = 100
_LABEL_WIDTH = 11
_INDENT = "    "
_STATUS_ORDER = ("pending", "running", "completed", "waiting", "error", "skipped", "unknown")
_STEP_STATUS_MEANINGS = (
    ("pending", "not started yet"),
    ("skipped", "skipped by a gate or policy"),
)
_NODE_STATUS_MEANINGS = (
    ("ready", "declared, never run"),
    ("running", "execution in progress"),
    ("completed", "finished successfully"),
    ("waiting", "paused for a human decision"),
    ("error", "stopped with an error"),
    ("cancelled", "stopped by a gate or reviewer"),
    ("unknown", "source did not say (never treated as success)"),
)


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return str(value)
    except Exception:  # noqa: BLE001 - text rendering must never raise
        return ""


def _plain(value: Any) -> str:
    """One normalised line fragment: no raw control characters, no embedded newlines.

    Control characters (including NUL) are *escaped* rather than dropped, so a viewer can see that
    something was there. Silently deleting them would make the printed copy differ from the source
    without saying so.
    """
    text = _as_text(value).replace("\r\n", "\n").replace("\r", "\n")
    kept: list[str] = []
    for ch in text:
        if ch in "\n\t":
            kept.append(" ")
        elif ch < " " or ch == "\x7f" or "\x80" <= ch <= "\x9f":
            kept.append(f"\\x{ord(ch):02x}")
        else:
            kept.append(ch)
    return "".join(kept)


def _one_line(value: Any, *, limit: int = 160) -> str:
    collapsed = " ".join(_plain(value).split())
    if limit > 0 and len(collapsed) > limit:
        collapsed = collapsed[: limit - 1].rstrip() + "\u2026"
    return collapsed


def _status_word(value: Any) -> str:
    return _as_text(value).strip().lower() or "unknown"


def _phase_status(phase: Any) -> str:
    try:
        return _status_word(analysis.phase_status(phase))
    except Exception:  # noqa: BLE001 - a malformed phase degrades to `unknown`
        return "unknown"


class _Glyphs:
    """Box-drawing glyphs, with an ASCII fallback for consoles that cannot encode them."""

    __slots__ = ("h", "v", "tl", "tr", "bl", "br", "t", "b", "l", "r", "x", "rule", "branch", "last")

    def __init__(self, unicode_ok: bool) -> None:
        if unicode_ok:
            self.h, self.v = "\u2500", "\u2502"
            self.tl, self.tr, self.bl, self.br = "\u250c", "\u2510", "\u2514", "\u2518"
            self.t, self.b, self.l, self.r, self.x = "\u252c", "\u2534", "\u251c", "\u2524", "\u253c"
            self.rule, self.branch, self.last = "\u2500", "\u251c\u2500", "\u2514\u2500"
        else:
            self.h, self.v = "-", "|"
            self.tl = self.tr = self.bl = self.br = "+"
            self.t = self.b = self.l = self.r = self.x = "+"
            self.rule, self.branch, self.last = "=", "|-", "\\-"


class TextRenderer:
    """Render FlowView documents as plain text.

    Every status is spelled out as a word, so ``--no-color`` loses no information, and no
    emitted line is wider than ``width`` (auto-detected when the caller passes 0).
    """

    format: ClassVar[str] = "text"

    def __init__(
        self,
        *,
        width: int = 0,
        color: bool | None = None,
        style: Any | None = None,
        legend: bool = True,
    ) -> None:
        self.width = self._resolve_width(width)
        self.legend = bool(legend)
        self.style: Any = style if style is not None else Style(enabled=color_enabled(sys.stdout, override=color))
        self._uni = self._unicode_ok()
        self._g = _Glyphs(self._uni)

    # ------------------------------------------------------------------ public API

    def render_document(self, document: Any) -> str:
        """Header, phase-by-phase section, graph layers/tables, legend and issue table."""
        try:
            lines: list[str] = list(self._document_header(document))
            phases = tuple(getattr(document, "phases", ()) or ())
            trace = getattr(document, "trace", None)
            if phases:
                lines += self._phases_section(phases)
            elif trace is not None and (
                tuple(getattr(trace, "events", ()) or ()) or tuple(getattr(trace, "phases", ()) or ())
            ):
                lines += self._phases_section(
                    self._derived_phases(trace), note="derived from the recorded trace"
                )
            else:
                lines += ["", self._fit(self.style.bold("Phases: none"), self.width)]
                lines.append(
                    self._fit(
                        "  No phases are available: the source did not provide a runtime phase map.",
                        self.width,
                    )
                )
                lines.append(
                    self._fit(
                        "  hint: run 'python -m flowview run-flow --blueprint' for the backend phase map.",
                        self.width,
                    )
                )
            graph = getattr(document, "graph", None)
            if graph is not None:
                lines += self._graph_sections(graph)
            issues = self._all_issues(document)
            if self.legend:
                lines += self._legend_lines(include_step_statuses=bool(phases) or trace is not None)
            lines += self._issues_section(issues)
            return self._out(lines)
        except Exception as exc:  # noqa: BLE001 - a renderer never crashes the CLI
            return self._fallback_document(document, exc)

    def render_graph(self, graph: Any) -> str:
        """Header, dependency layers, node table and edge table for one graph."""
        try:
            nodes = tuple(getattr(graph, "nodes", ()) or ())
            edges = tuple(getattr(graph, "edges", ()) or ())
            stats = self._stats(graph, nodes=nodes, edges=edges)
            graph_id = _as_text(getattr(graph, "graph_id", "")) or "local-default"
            version = _as_text(getattr(graph, "version", 0)) or "0"
            lines: list[str] = [
                self._fit(self.style.bold(f"Graph: {graph_id} v{version}"), self.width),
                self._rule(),
            ]
            lines += self._kv("source", _as_text(getattr(graph, "source", "")) or "(in-memory)")
            lines += self._kv("counts", self._counts_text(stats, len(nodes), len(edges)))
            truncated = tuple(getattr(graph, "truncated", ()) or ())
            if truncated:
                lines += self._kv("truncated", ", ".join(_as_text(item) for item in truncated))
            lines += self._graph_sections(graph, nodes=nodes, edges=edges, stats=stats)
            issues: list[Any] = list(getattr(graph, "issues", ()) or ())
            for node in nodes:
                issues.extend(tuple(getattr(node, "issues", ()) or ()))
            lines += self._issues_section(self._dedupe_issues(issues))
            if self.legend:
                lines += self._legend_lines(include_step_statuses=False)
            return self._out(lines)
        except Exception as exc:  # noqa: BLE001
            return self._fallback_failure("graph", graph, exc)

    def render_trace(self, trace: Any) -> str:
        """Phase timeline of one recorded task lifecycle."""
        try:
            events = self._events_of(trace)
            summary = self._summary(trace, events)
            name = (
                _as_text(getattr(trace, "task_id", ""))
                or _as_text(getattr(trace, "trace_id", ""))
                or "(unnamed)"
            )
            lines: list[str] = [
                self._fit(self.style.bold(f"Trace: {name}"), self.width),
                self._rule(),
            ]
            lines += self._kv("source", _as_text(getattr(trace, "source", "")) or "(none)")
            lines += self._kv("events", str(summary.total_events))
            lines += self._kv("counts", self._status_counts_text(summary.counts))
            lines += self._kv("failures", str(len(summary.failed)) if summary.failed else "none")
            if events or tuple(getattr(trace, "phases", ()) or ()):
                lines += self._phases_section(summary.phases)
            else:
                lines += ["", self._fit(self.style.bold("Timeline"), self.width)]
                lines.append(
                    self._fit("  This trace is empty: no runtime events were recorded.", self.width)
                )
                lines.append(
                    self._fit(
                        "  hint: record a task, or pass --from-file with a trace JSON/JSONL export.",
                        self.width,
                    )
                )
            lines += self._issues_section(
                self._dedupe_issues(tuple(getattr(trace, "issues", ()) or ()))
            )
            if self.legend:
                lines += self._legend_lines(include_step_statuses=True)
            return self._out(lines)
        except Exception as exc:  # noqa: BLE001
            return self._fallback_failure("trace", trace, exc)

    def render_phases(self, phases: Sequence[Any]) -> str:
        """The phase-by-phase section on its own."""
        try:
            items = tuple(phases or ())
            lines: list[str] = [self._fit(self.style.bold(f"Phases ({len(items)})"), self.width)]
            lines += self._phases_body(items)
            if self.legend:
                lines += self._legend_lines(include_step_statuses=True)
            return self._out(lines)
        except Exception as exc:  # noqa: BLE001
            return self._fallback_failure("phase list", phases, exc)

    def render_issue_table(self, issues: Sequence[Any]) -> str:
        """The issue section on its own."""
        try:
            items = tuple(issues or ())
            lines: list[str] = [self._fit(self.style.bold(f"Issues ({len(items)})"), self.width)]
            lines += self._issues_body(items)
            return self._out(lines)
        except Exception as exc:  # noqa: BLE001
            return self._fallback_failure("issue list", issues, exc)

    # ------------------------------------------------------------------ width helpers

    def _resolve_width(self, width: Any) -> int:
        """Explicit width wins; otherwise the terminal width, else the documented 100."""
        try:
            requested = int(width)
        except Exception:  # noqa: BLE001
            requested = 0
        if requested > 0:
            return requested
        stream = sys.stdout
        try:
            is_tty = bool(getattr(stream, "isatty", lambda: False)())
        except Exception:  # noqa: BLE001
            is_tty = False
        if is_tty:
            try:
                columns = int(shutil.get_terminal_size((_FALLBACK_WIDTH, 24)).columns)
                if columns > 0:
                    return columns
            except Exception:  # noqa: BLE001
                pass
        return _FALLBACK_WIDTH

    def _unicode_ok(self) -> bool:
        """Box drawing only when the stream can encode it *and* we know who is reading.

        A redirected stream (pipe or file) may be consumed by a tool that assumes UTF-8, and
        the console code page is not a safe promise there; ASCII always survives. An attached
        terminal is trusted as long as its encoding can carry the glyphs.
        """
        stream = sys.stdout
        if not can_encode(stream):
            return False
        try:
            is_tty = bool(getattr(stream, "isatty", lambda: False)())
        except Exception:  # noqa: BLE001
            is_tty = False
        if is_tty:
            return True
        encoding = (getattr(stream, "encoding", "") or "").lower().replace("_", "-")
        return encoding.startswith(("utf-8", "utf8", "utf-16", "utf-32"))

    def _fit(self, text: Any, width: int) -> str:
        """Cut ``text`` to ``width`` cells, with a visible marker when something is removed."""
        body = _as_text(text)
        try:
            limit = int(width)
        except Exception:  # noqa: BLE001
            return body
        if limit <= 0:
            return ""
        if display_width(body) <= limit:
            return body
        plain = strip_ansi(body)
        marker = "\u2026" if self._uni else "..."
        budget = limit - display_width(marker)
        kept: list[str] = []
        used = 0
        for ch in plain:
            size = display_width(ch)
            if used + size > budget:
                break
            kept.append(ch)
            used += size
        if budget <= 0:
            return "".join(kept)
        return "".join(kept) + marker

    def _wrap(self, text: Any, width: int) -> list[str]:
        try:
            limit = int(width)
        except Exception:  # noqa: BLE001
            limit = self.width
        if limit <= 0:
            return [""]
        try:
            pieces = wrap(text, limit)
        except Exception:  # noqa: BLE001
            pieces = [_plain(text)]
        fitted = [self._fit(piece, limit) for piece in pieces]
        return fitted or [""]

    def _out(self, lines: Sequence[Any]) -> str:
        """Join lines, guaranteeing that no emitted line is wider than ``width``."""
        cleaned: list[str] = []
        cut = 0
        for line in lines:
            text = _as_text(line).replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
            for piece in text.split("\n"):
                if display_width(piece) > self.width:
                    cut += 1
                cleaned.append(self._fit(piece, self.width).rstrip())
        if cut:
            cleaned += self._wrap(
                f"note: {cut} line(s) were shortened to fit width {self.width}; raise --width to see them in full.",
                self.width,
            )
        return "\n".join(cleaned)

    def _rule(self) -> str:
        return self._g.rule * max(1, min(self.width, 72))

    def _kv(
        self,
        label: Any,
        value: Any,
        *,
        indent: int = 0,
        styler: Any | None = None,
        label_width: int = _LABEL_WIDTH,
    ) -> list[str]:
        """``label : value`` with the value wrapped; degrades when the width is tiny."""
        padded_indent = " " * max(0, indent)
        plain_label = _plain(label)
        gap = " " * max(2, label_width - display_width(plain_label))
        head = f"{padded_indent}{plain_label}{gap}: "
        if display_width(head) + 8 > self.width and indent > 2:
            padded_indent = "  "
            head = f"{padded_indent}{plain_label}{gap}: "
        if display_width(head) + 4 > self.width:
            head = f"{padded_indent}{plain_label}: "
        if display_width(head) + 2 > self.width:
            head = padded_indent
        available = max(1, self.width - display_width(head))
        pieces = self._wrap(_plain(value), available) if _plain(value) else [""]
        if styler is not None:
            styled: list[str] = []
            for piece in pieces:
                try:
                    styled.append(styler(piece))
                except Exception:  # noqa: BLE001
                    styled.append(piece)
            pieces = styled
        out = [self._fit(head + pieces[0], self.width)]
        if len(pieces) > 1:
            continuation = " " * display_width(head)
            out += [self._fit(continuation + piece, self.width) for piece in pieces[1:]]
        return out

    # ------------------------------------------------------------------ tables

    def _table(
        self,
        headers: Sequence[Any],
        rows: Sequence[Sequence[Any]],
        *,
        priorities: Sequence[int] | None = None,
        styler: Any | None = None,
        cap: int = 48,
    ) -> list[str]:
        try:
            return self._table_lines(headers, rows, priorities=priorities, styler=styler, cap=cap)
        except Exception:  # noqa: BLE001 - fall back to the one-column-per-line layout
            return self._records(headers, rows, styler=styler)

    def _table_lines(
        self,
        headers: Sequence[Any],
        rows: Sequence[Sequence[Any]],
        *,
        priorities: Sequence[int] | None,
        styler: Any | None,
        cap: int,
    ) -> list[str]:
        column_headers = [_plain(header) for header in headers]
        body = [[_plain(cell) for cell in row] for row in rows]
        count = len(column_headers)
        if count == 0 or not body:
            return []
        ranks = [int(rank) for rank in (priorities if priorities is not None else [0] * count)]
        if len(ranks) != count:
            ranks = [0] * count
        widths: list[int] = []
        for index, header in enumerate(column_headers):
            widest = display_width(header)
            for row in body:
                widest = max(widest, display_width(row[index]))
            widths.append(min(max(widest, 3), max(6, cap)))
        natural = list(widths)
        # A cell is wrapped, never silently cut, so a column may narrow; but not below the point
        # where a wrapped cell stops being readable. Below that floor we drop the column instead
        # and say so, then fall back to a record layout when even the priority columns do not fit.
        floors = [max(8, min(width, 24)) for width in natural]
        keep = [True] * count
        dropped: list[str] = []

        def used() -> int:
            active = [index for index in range(count) if keep[index]]
            return sum(widths[index] for index in active) + 3 * len(active) + 1

        def shrink_to_fit() -> bool:
            while used() > self.width:
                candidates = [
                    i for i in range(count) if keep[i] and widths[i] > floors[i]
                ]
                if not candidates:
                    return False
                index = max(candidates, key=lambda i: (widths[i], i))
                widths[index] -= 1
            return True

        while not shrink_to_fit():
            droppable = [i for i in range(count) if keep[i] and ranks[i] > 0]
            if not droppable:
                break
            index = max(droppable, key=lambda i: (ranks[i], i))
            keep[index] = False
            dropped.append(column_headers[index])
            if not any(keep):
                break
            for i in range(count):
                if keep[i]:
                    widths[i] = natural[i]
        active = [index for index in range(count) if keep[index]]
        if not active or used() > self.width:
            return self._records(column_headers, body, styler=styler)

        def border(left: str, middle: str, right: str) -> str:
            return left + middle.join(self._g.h * (widths[i] + 2) for i in active) + right

        def render_cells(cells: Sequence[str]) -> str:
            return self._g.v + self._g.v.join(
                f" {pad(cell, widths[i])} " for cell, i in zip(cells, active)
            ) + self._g.v

        lines: list[str] = [border(self._g.tl, self._g.t, self._g.tr)]
        header_lines = [self._wrap(column_headers[i], widths[i]) for i in active]
        for line_index in range(max(len(item) for item in header_lines)):
            cells = [
                self.style.bold(item[line_index]) if line_index < len(item) and item[line_index] else ""
                for item in header_lines
            ]
            lines.append(render_cells(cells))
        lines.append(border(self._g.l, self._g.x, self._g.r))
        for row_index, row in enumerate(body):
            cell_lines = [self._wrap(row[i], widths[i]) for i in active]
            for line_index in range(max(len(item) for item in cell_lines)):
                cells = []
                for position, source_index in enumerate(active):
                    item = cell_lines[position]
                    text = item[line_index] if line_index < len(item) else ""
                    if styler is not None and text:
                        try:
                            text = styler(source_index, row_index, text)
                        except Exception:  # noqa: BLE001
                            pass
                    cells.append(text)
                lines.append(render_cells(cells))
        lines.append(border(self._g.bl, self._g.b, self._g.br))
        if dropped:
            lines += self._wrap(
                f"note: dropped column(s) to fit width {self.width}: {', '.join(dropped)}",
                self.width,
            )
        return lines

    def _records(
        self,
        headers: Sequence[Any],
        rows: Sequence[Sequence[Any]],
        *,
        styler: Any | None = None,
    ) -> list[str]:
        """A table with no room left: one ``header: value`` block per record, still width-safe."""
        lines: list[str] = []
        for row_index, row in enumerate(rows):
            for column, header in enumerate(headers):
                value = row[column] if column < len(row) else ""
                label = f"  {_plain(header)}: "
                if display_width(label) > self.width - 4:
                    lines.append(self._fit(f"  {_plain(header)}", self.width))
                    label = "    "
                available = max(1, self.width - display_width(label))
                pieces = self._wrap(value, available)
                if styler is not None:
                    styled: list[str] = []
                    for piece in pieces:
                        try:
                            styled.append(styler(column, row_index, piece))
                        except Exception:  # noqa: BLE001
                            styled.append(piece)
                    pieces = styled
                lines.append(self._fit(label + pieces[0], self.width))
                continuation = " " * display_width(label)
                lines += [self._fit(continuation + piece, self.width) for piece in pieces[1:]]
            if row_index != len(rows) - 1:
                lines.append("")
        return lines

    # ------------------------------------------------------------------ sections

    def _document_header(self, document: Any) -> list[str]:
        title = _as_text(getattr(document, "title", "")) or "MatFlow flow"
        lines: list[str] = [self._fit(self.style.bold(title), self.width), self._rule()]
        lines += self._kv("source", _as_text(getattr(document, "source", "")) or "(none)")
        graph = getattr(document, "graph", None)
        if graph is not None:
            nodes = tuple(getattr(graph, "nodes", ()) or ())
            edges = tuple(getattr(graph, "edges", ()) or ())
            stats = self._stats(graph, nodes=nodes, edges=edges)
            graph_id = _as_text(getattr(graph, "graph_id", "")) or "local-default"
            version = _as_text(getattr(graph, "version", 0)) or "0"
            layers = stats.layers if stats.layers is not None else "n/a (cycle)"
            lines += self._kv(
                "graph",
                f"{graph_id}, version {version}, nodes {len(nodes)}, edges {len(edges)}, layers {layers}",
            )
        else:
            lines += self._kv("graph", "none in this document")
        trace = getattr(document, "trace", None)
        if trace is not None:
            summary = self._summary(trace, self._events_of(trace))
            lines += self._kv(
                "trace",
                "events {events}, failed {failed}, task {task}".format(
                    events=summary.total_events,
                    failed=len(summary.failed),
                    task=summary.task_id or "(none)",
                ),
            )
        lines += self._kv("phases", str(len(tuple(getattr(document, "phases", ()) or ()))))
        errors, warnings = self._issue_counts(document)
        lines += self._kv("issues", f"{errors} error(s), {warnings} warning(s)")
        truncated = tuple(getattr(document, "truncated", ()) or ())
        if truncated:
            lines += self._kv("truncated", ", ".join(_as_text(item) for item in truncated))
        meta = getattr(document, "meta", None)
        if isinstance(meta, Mapping):
            items = list(meta.items())
            shown = items[:8]
            text = ", ".join(f"{_as_text(key)}={_as_text(value)}" for key, value in shown)
            if len(items) > len(shown):
                text += f", ... (+{len(items) - len(shown)} more)"
            if text:
                lines += self._kv("meta", text)
        return lines

    def _graph_sections(
        self,
        graph: Any,
        *,
        nodes: tuple[Any, ...] | None = None,
        edges: tuple[Any, ...] | None = None,
        stats: Any | None = None,
    ) -> list[str]:
        graph_nodes = tuple(nodes if nodes is not None else (getattr(graph, "nodes", ()) or ()))
        graph_edges = tuple(edges if edges is not None else (getattr(graph, "edges", ()) or ()))
        graph_stats = stats if stats is not None else self._stats(graph, nodes=graph_nodes, edges=graph_edges)
        lines: list[str] = []
        lines += self._layers_section(graph, graph_nodes)
        lines += self._nodes_section(graph_stats, graph_nodes, graph_edges)
        lines += self._edges_section(graph_nodes, graph_edges)
        return lines

    def _layers_section(self, graph: Any, nodes: tuple[Any, ...]) -> list[str]:
        lines: list[str] = ["", self._fit(self.style.bold("Dependency layers"), self.width)]
        if not nodes:
            lines.append(
                self._fit("  The graph has no nodes, so there are no dependency layers yet.", self.width)
            )
            return lines
        try:
            layers = tuple(analysis.graph_layers(graph))
        except FlowCycleError as exc:
            cycles: tuple[Any, ...] = ()
            try:
                cycles = tuple(analysis.find_cycles(graph))
            except Exception:  # noqa: BLE001
                cycles = tuple(getattr(exc, "cycles", ()) or ())
            lines.append(
                self._fit(
                    "  Cycle detected: the graph is not acyclic, so dependency layers are unavailable.",
                    self.width,
                )
            )
            if cycles:
                lines.append(self._fit("  Cycles:", self.width))
                for cycle in cycles:
                    rendered = " -> ".join(_as_text(item) for item in cycle)
                    lines.append(self._fit(f"    {rendered}", self.width))
            else:
                message = _as_text(getattr(getattr(exc, "issue", None), "message", "")) or _as_text(exc)
                lines.append(self._fit(f"  {message}", self.width))
            lines.append(
                self._fit(
                    "  hint: repair the graph with apply_graph_patch, then re-run flowview graph.",
                    self.width,
                )
            )
            return lines
        except Exception as exc:  # noqa: BLE001
            lines.append(
                self._fit(f"  Dependency layers are unavailable: {_one_line(exc)}", self.width)
            )
            return lines
        if not layers:
            lines.append(self._fit("  No layers: the graph has no nodes.", self.width))
            return lines
        for index, layer in enumerate(layers):
            members = tuple(layer or ())
            lines.append(self._fit(f"  layer {index} ({len(members)} node(s))", self.width))
            for position, node in enumerate(members):
                connector = self._g.last if position == len(members) - 1 else self._g.branch
                status = _status_word(getattr(node, "status", ""))
                identifier = _as_text(getattr(node, "id", ""))
                label = _as_text(getattr(node, "label", ""))
                prefix = f"    {connector} {identifier}  [{status}]"
                if label and label != identifier:
                    # The node table below carries the full label; here it stays one line, and a
                    # visible marker shows when it was shortened.
                    room = max(8, self.width - display_width(prefix) - 2)
                    prefix += "  " + self._fit(label, room)
                lines += [self._fit(piece, self.width) for piece in self._wrap(prefix, self.width)]
        return lines

    def _nodes_section(self, stats: Any, nodes: tuple[Any, ...], edges: tuple[Any, ...]) -> list[str]:
        lines: list[str] = ["", self._fit(self.style.bold(f"Nodes ({len(nodes)})"), self.width)]
        by_status = getattr(stats, "by_status", None)
        if not nodes:
            lines.append(self._fit("  The graph has no nodes yet: there is nothing to draw.", self.width))
            if edges:
                lines.append(
                    self._fit(
                        f"  {len(edges)} edge(s) are recorded but reference no declared node.",
                        self.width,
                    )
                )
            if isinstance(by_status, Mapping) and by_status:
                lines += self._kv("status counts", self._by_status_text(by_status), indent=2)
            return lines
        ordered = self._sorted_nodes(nodes)
        if [_as_text(getattr(node, "id", "")) for node in ordered] != [
            _as_text(getattr(node, "id", "")) for node in nodes
        ]:
            lines.append(
                self._fit(
                    "  (problem nodes first: error, waiting, running, ready, cancelled, completed, unknown)",
                    self.width,
                )
            )
        if isinstance(by_status, Mapping) and by_status:
            lines += self._kv("status counts", self._by_status_text(by_status), indent=2)
        rows: list[list[str]] = []
        statuses: list[str] = []
        for node in ordered:
            status = _status_word(getattr(node, "status", ""))
            statuses.append(status)
            identifier = _as_text(getattr(node, "id", ""))
            rows.append(
                [
                    identifier,
                    _as_text(getattr(node, "label", "")) or identifier,
                    _as_text(getattr(node, "tool_id", "") or getattr(node, "category", "") or "-"),
                    status,
                    _as_text(getattr(node, "error", "")) or "-",
                ]
            )

        def styler(column: int, row: int, text: str) -> str:
            if column == 3 and 0 <= row < len(statuses):
                return self.style.status(text, statuses[row])
            return text

        lines += self._table(
            ["Id", "Label", "Tool", "Status", "Error"],
            rows,
            priorities=[0, 0, 1, 0, 2],
            styler=styler,
        )
        return lines

    def _edges_section(self, nodes: tuple[Any, ...], edges: tuple[Any, ...]) -> list[str]:
        lines: list[str] = ["", self._fit(self.style.bold(f"Edges ({len(edges)})"), self.width)]
        if not edges:
            lines.append(self._fit("  No edges: every node is independent.", self.width))
            return lines
        known = {_as_text(getattr(node, "id", "")) for node in nodes}
        rows: list[list[str]] = []
        for edge in self._sorted_edges(edges):
            source = _as_text(getattr(edge, "source", ""))
            target = _as_text(getattr(edge, "target", ""))
            source_port = _as_text(getattr(edge, "source_port", "") or "")
            target_port = _as_text(getattr(edge, "target_port", "") or "")
            ports = f"{source_port or '*'} -> {target_port or '*'}" if (source_port or target_port) else "-"
            flags: list[str] = []
            if getattr(edge, "dangling", False):
                flags.append("dangling")
            if getattr(edge, "duplicate_input", False):
                flags.append("duplicate input")
            if source not in known or target not in known:
                flags.append("endpoint not in graph")
            rows.append(
                [
                    source,
                    target,
                    ports,
                    _as_text(getattr(edge, "data_type", "") or "") or "-",
                    ", ".join(flags) or "-",
                ]
            )
        lines += self._table(
            ["Source", "Target", "Ports", "Type", "Note"],
            rows,
            priorities=[0, 0, 1, 2, 1],
        )
        return lines

    def _phases_section(self, phases: Sequence[Any], *, note: str = "") -> list[str]:
        items = tuple(phases or ())
        lines: list[str] = ["", self._fit(self.style.bold(f"Phases ({len(items)})"), self.width)]
        if note:
            lines.append(self._fit(f"  ({note})", self.width))
        lines += self._phases_body(items)
        return lines

    def _phases_body(self, phases: Sequence[Any]) -> list[str]:
        if not phases:
            return [
                self._fit(
                    "  No phases are available: the source did not provide a runtime phase map.",
                    self.width,
                ),
                self._fit(
                    "  hint: run 'python -m flowview run-flow --blueprint' for the backend phase map.",
                    self.width,
                ),
            ]
        lines: list[str] = []
        for index, phase in enumerate(phases, start=1):
            lines += self._phase_lines(phase, index)
        return lines

    def _phase_lines(self, phase: Any, index: int) -> list[str]:
        name = _as_text(getattr(phase, "name", ""))
        title = _as_text(getattr(phase, "title", "")) or name or f"phase {index}"
        status = _phase_status(phase)
        head = f"  [{index}] {title}"
        if name and name != title:
            head += f" ({name})"
        # Wrap rather than truncate so the status word survives any width.
        lines: list[str] = [
            self._fit(self.style.status(self.style.bold(piece), status), self.width)
            for piece in self._wrap(f"{head}  [{status}]", self.width)
        ]
        error = _as_text(getattr(phase, "error", "") or "")
        if error:
            lines += self._kv(
                "! phase error",
                error,
                indent=4,
                styler=lambda text: self.style.issue(text, "error"),
            )
        steps = tuple(getattr(phase, "steps", ()) or ())
        if not steps:
            lines.append(self._fit("      (no steps recorded in this phase)", self.width))
            return lines
        for step_index, step in enumerate(steps, start=1):
            lines += self._step_lines(step, step_index)
        return lines

    def _step_lines(self, step: Any, index: int) -> list[str]:
        name = _as_text(getattr(step, "name", "")) or "(unnamed step)"
        status = _status_word(getattr(step, "status", ""))
        indent = "      "
        body = f"{index}. {name}  [{status}]"
        wrapped = self._wrap(body, max(8, self.width - display_width(indent)))
        lines: list[str] = []
        for position, piece in enumerate(wrapped):
            prefix = indent if position == 0 else " " * (display_width(indent) + 3)
            lines.append(self._fit(prefix + self.style.status(piece, status), self.width))
        detail = _as_text(getattr(step, "detail", "") or "")
        if detail:
            lines += self._kv("detail", detail, indent=display_width(indent) + 4)
        node_id = _as_text(getattr(step, "node_id", "") or "")
        if node_id:
            lines += self._kv("node", node_id, indent=display_width(indent) + 4)
        tools = tuple(getattr(step, "tools", ()) or ())
        if tools:
            lines += self._kv(
                "tools", ", ".join(_as_text(item) for item in tools), indent=display_width(indent) + 4
            )
        error = _as_text(getattr(step, "error", "") or "")
        if error:
            lines += self._kv(
                "error",
                error,
                indent=display_width(indent) + 4,
                styler=lambda text: self.style.issue(text, "error"),
            )
        return lines

    def _legend_lines(self, *, include_step_statuses: bool = False) -> list[str]:
        try:
            entries = tuple(analysis.status_legend())
        except Exception:  # noqa: BLE001
            entries = _NODE_STATUS_MEANINGS
        lines: list[str] = ["", self._fit(self.style.bold("Status legend"), self.width)]
        for word, meaning in entries:
            lines += self._kv(self.style.status(word, word), meaning, indent=2)
        if include_step_statuses:
            lines.append(self._fit("  step-only statuses:", self.width))
            for word, meaning in _STEP_STATUS_MEANINGS:
                lines += self._kv(self.style.status(word, word), meaning, indent=4)
        return lines

    def _issues_section(self, issues: Sequence[Any]) -> list[str]:
        items = tuple(issues or ())
        lines: list[str] = ["", self._fit(self.style.bold(f"Issues ({len(items)})"), self.width)]
        lines += self._issues_body(items)
        return lines

    def _issues_body(self, items: Sequence[Any]) -> list[str]:
        if not items:
            return [self._fit("  No FlowView findings: the source looked consistent.", self.width)]
        rows: list[list[str]] = []
        severities: list[str] = []
        for issue in items:
            severity = _as_text(getattr(issue, "severity", "")) or "warning"
            severities.append(severity)
            rows.append(
                [
                    severity,
                    _as_text(getattr(issue, "code", "")),
                    _as_text(getattr(issue, "message", "")),
                    _as_text(getattr(issue, "where", "") or "-"),
                    _as_text(getattr(issue, "hint", "") or "-"),
                ]
            )

        def styler(column: int, row: int, text: str) -> str:
            if column == 0 and 0 <= row < len(severities):
                return self.style.issue(text, severities[row])
            return text

        return self._table(
            ["Severity", "Code", "Message", "Where", "Hint"],
            rows,
            priorities=[0, 1, 0, 2, 3],
            styler=styler,
        )

    # ------------------------------------------------------------------ small helpers

    def _stats(self, graph: Any, *, nodes: tuple[Any, ...] | None = None, edges: tuple[Any, ...] | None = None) -> Any:
        try:
            return analysis.graph_stats(graph)
        except Exception:  # noqa: BLE001
            try:
                return analysis.GraphStats(
                    nodes=len(nodes or ()),
                    edges=len(edges or ()),
                    layers=None,
                )
            except Exception:  # noqa: BLE001
                return None

    def _counts_text(self, stats: Any, node_count: int, edge_count: int) -> str:
        layers = getattr(stats, "layers", None)
        cycles = len(tuple(getattr(stats, "cycles", ()) or ()))
        dangling = getattr(stats, "dangling_edges", 0)
        parts = [
            f"nodes {node_count}",
            f"edges {edge_count}",
            f"layers {layers if layers is not None else 'n/a (cycle)'}",
            f"cycles {cycles}",
            f"dangling {dangling}",
        ]
        known_tools = getattr(stats, "known_tools", 0)
        unknown_tools = getattr(stats, "unknown_tools", 0)
        if known_tools or unknown_tools:
            parts.append(f"tools known {known_tools}, unknown {unknown_tools}")
        return ", ".join(parts)

    def _status_counts_text(self, counts: Any) -> str:
        if not isinstance(counts, Mapping):
            return "none"
        parts = [f"{word} {counts[word]}" for word in _STATUS_ORDER if counts.get(word)]
        extras = sorted(key for key in counts if key not in _STATUS_ORDER and counts.get(key))
        parts += [f"{key} {counts[key]}" for key in extras]
        return ", ".join(parts) or "none"

    def _by_status_text(self, by_status: Mapping[Any, Any]) -> str:
        parts = [f"{status} {by_status[status]}" for status in NODE_STATUSES if by_status.get(status)]
        extras = sorted(
            _as_text(key) for key in by_status if key not in NODE_STATUSES and by_status.get(key)
        )
        parts += [f"{key} {by_status[key]}" for key in extras]
        return ", ".join(parts) or "none"

    def _summary(self, trace: Any, events: tuple[Any, ...]) -> Any:
        try:
            return analysis.summarize_trace(trace)
        except Exception:  # noqa: BLE001 - fall back to a digest built from the events we have
            counts = {word: 0 for word in _STATUS_ORDER}
            failed: list[Any] = []
            for event in events:
                word = _status_word(getattr(event, "status", ""))
                counts[word] = counts.get(word, 0) + 1
                if word == "error":
                    failed.append(event)
            try:
                return analysis.TraceSummary(
                    task_id=_as_text(getattr(trace, "task_id", "")) or None,
                    trace_id=_as_text(getattr(trace, "trace_id", "")) or None,
                    total_events=len(events),
                    counts=counts,
                    failed=tuple(failed),
                    phases=tuple(getattr(trace, "phases", ()) or ()),
                    first_index=None,
                    last_index=None,
                )
            except Exception:  # noqa: BLE001
                return None

    def _events_of(self, trace: Any) -> tuple[Any, ...]:
        try:
            events = tuple(getattr(trace, "events", ()) or ())
        except Exception:  # noqa: BLE001
            return ()

        def index_of(event: Any) -> int:
            try:
                return int(getattr(event, "index", 0))
            except Exception:  # noqa: BLE001
                return 0

        try:
            return tuple(sorted(events, key=index_of))
        except Exception:  # noqa: BLE001
            return events

    def _derived_phases(self, trace: Any) -> tuple[Any, ...]:
        try:
            derived = analysis.derive_phases(trace)
            if derived:
                return tuple(derived)
        except Exception:  # noqa: BLE001
            pass
        return tuple(getattr(trace, "phases", ()) or ())

    def _all_issues(self, document: Any) -> tuple[Any, ...]:
        try:
            raw = tuple(document.all_issues())
        except Exception:  # noqa: BLE001
            raw = tuple(getattr(document, "issues", ()) or ())
        return self._dedupe_issues(raw)

    @staticmethod
    def _dedupe_issues(issues: Sequence[Any]) -> tuple[Any, ...]:
        """One row per distinct finding: the model merges graph issues into the document twice."""
        seen: set[tuple[str, str, str, str]] = set()
        unique: list[Any] = []
        for issue in issues:
            key = (
                _as_text(getattr(issue, "severity", "")),
                _as_text(getattr(issue, "code", "")),
                _as_text(getattr(issue, "where", "")),
                _as_text(getattr(issue, "message", "")),
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(issue)
        return tuple(unique)

    def _issue_counts(self, document: Any) -> tuple[int, int]:
        try:
            return int(document.error_count), int(document.warning_count)
        except Exception:  # noqa: BLE001
            issues = self._all_issues(document)
            errors = sum(1 for issue in issues if _as_text(getattr(issue, "severity", "")) == "error")
            warnings = sum(1 for issue in issues if _as_text(getattr(issue, "severity", "")) == "warning")
            return errors, warnings

    def _sorted_nodes(self, nodes: tuple[Any, ...]) -> tuple[Any, ...]:
        try:
            return tuple(sorted(nodes, key=analysis.node_sort_key))
        except Exception:  # noqa: BLE001
            return tuple(sorted(nodes, key=lambda node: _as_text(getattr(node, "id", ""))))

    def _sorted_edges(self, edges: tuple[Any, ...]) -> tuple[Any, ...]:
        def key(edge: Any) -> tuple[str, str, str, str]:
            return (
                _as_text(getattr(edge, "source", "")),
                _as_text(getattr(edge, "source_port", "") or ""),
                _as_text(getattr(edge, "target", "")),
                _as_text(getattr(edge, "target_port", "") or ""),
            )

        try:
            return tuple(sorted(edges, key=key))
        except Exception:  # noqa: BLE001
            return tuple(edges)

    # ------------------------------------------------------------------ degraded output

    def _fallback_document(self, document: Any, exc: BaseException) -> str:
        """When the full report fails, still print what the document carries."""
        lines: list[str] = []
        try:
            lines += self._document_header(document)
        except Exception:  # noqa: BLE001
            lines.append(self._fit(self.style.bold("FlowView document"), self.width))
        lines.append("")
        lines.append(
            self._fit(
                f"FlowView could not render this document: {_one_line(exc)}",
                self.width,
            )
        )
        try:
            for issue in self._all_issues(document):
                renderer = getattr(issue, "render", None)
                text = renderer() if callable(renderer) else _as_text(issue)
                lines.append(self._fit(f"  {_one_line(text)}", self.width))
        except Exception:  # noqa: BLE001
            pass
        return self._out(lines)

    def _fallback_failure(self, what: str, value: Any, exc: BaseException) -> str:
        lines: list[str] = [
            self._fit(self.style.bold(f"FlowView: {what} could not be rendered"), self.width),
            self._fit(f"  {_one_line(exc)}", self.width),
        ]
        try:
            issues = tuple(getattr(value, "issues", ()) or ())
            for issue in issues:
                renderer = getattr(issue, "render", None)
                text = renderer() if callable(renderer) else _as_text(issue)
                lines.append(self._fit(f"  {_one_line(text)}", self.width))
        except Exception:  # noqa: BLE001
            pass
        return self._out(lines)


__all__ = ["TextRenderer"]

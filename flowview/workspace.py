"""Read-only scan of the MatFlow workspace: audited sources, uploads, and cheap counts."""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .loader import (
    default_graph_path,
    default_summary_path,
    default_upload_dir,
    probe_sources,
    workspace_root,
)
from .model import SourceStatus

#: Column labels matching :func:`snapshot_row`, for table output.
SNAPSHOT_COLUMNS: tuple[str, ...] = ("root", "graph", "nodes", "summary log", "records", "uploads")


@dataclass(frozen=True, slots=True)
class WorkspaceSnapshot:
    """What FlowView could see in the workspace without changing anything."""

    root: Path
    sources: tuple[SourceStatus, ...] = ()
    uploads: tuple[dict[str, Any], ...] = ()
    summary_path: Path | None = None
    summary_records: int = 0
    graph_path: Path | None = None
    graph_nodes: int = 0
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "sources": [source.to_dict() for source in self.sources],
            "uploads": [dict(item) for item in self.uploads],
            "summary_path": str(self.summary_path) if self.summary_path is not None else None,
            "summary_records": self.summary_records,
            "graph_path": str(self.graph_path) if self.graph_path is not None else None,
            "graph_nodes": self.graph_nodes,
            "notes": list(self.notes),
        }


def _resolved(path: Any) -> Path | None:
    if path is None:
        return None
    try:
        return Path(path)
    except (TypeError, ValueError, OSError):
        return None


def _count_jsonl_records(path: Path) -> tuple[int, str | None]:
    """Return (parseable record count, note) for a JSONL file; never raises."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return 0, f"{path.name} could not be read: {type(exc).__name__}"
    total = 0
    parseable = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        total += 1
        try:
            json.loads(line)
        except (ValueError, TypeError):
            continue
        parseable += 1
    if total != parseable:
        return parseable, f"{path.name}: {total - parseable} of {total} line(s) are not valid JSON"
    return parseable, None


def _count_graph_nodes(path: Path) -> tuple[int, str | None]:
    """Return (node count, note) for a graph state file; never raises."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        return 0, f"{path.name} could not be read: {type(exc).__name__}"
    except (ValueError, TypeError):
        return 0, f"{path.name} is not valid JSON"
    if not isinstance(payload, Mapping):
        return 0, f"{path.name} is JSON but not an object"
    nodes = payload.get("nodes")
    if isinstance(nodes, (list, tuple)):
        return len(nodes), None
    return 0, f"{path.name} carries no 'nodes' list"


def uploads_summary(root: Path | None = None) -> tuple[dict[str, Any], ...]:
    """List ``data/uploads`` defensively: name, path and size per entry, sorted by name."""
    directory = default_upload_dir(root)
    try:
        entries = sorted(directory.iterdir(), key=lambda entry: entry.name)
    except OSError:
        return ()
    items: list[dict[str, Any]] = []
    for entry in entries:
        item: dict[str, Any] = {"name": entry.name, "path": str(entry)}
        try:
            if entry.is_dir():
                item["kind"] = "directory"
                item["entries"] = sum(1 for _ in entry.iterdir())
            else:
                item["kind"] = "file"
                item["bytes"] = entry.stat().st_size
        except OSError as exc:
            item["kind"] = "unreadable"
            item["detail"] = type(exc).__name__
        items.append(item)
    return tuple(items)


def scan_workspace(root: Path | None = None) -> WorkspaceSnapshot:
    """Probe every audited location and count what is there, without writing anything."""
    resolved_root = workspace_root(root)
    sources = probe_sources(root)
    uploads = uploads_summary(root)
    graph_path = default_graph_path(root)
    summary_path = default_summary_path(root)

    notes: list[str] = []
    if graph_path.exists():
        graph_nodes, graph_note = _count_graph_nodes(graph_path)
        if graph_note:
            notes.append(graph_note)
        elif graph_nodes == 0:
            notes.append("the workspace graph exists but contains no nodes")
    else:
        graph_nodes = 0
        notes.append(f"no graph state yet at {graph_path}")

    if summary_path.exists():
        summary_records, summary_note = _count_jsonl_records(summary_path)
        if summary_note:
            notes.append(summary_note)
        if summary_records == 0 and not summary_note:
            notes.append("the task summary log contains no records")
    else:
        summary_records = 0
        notes.append(f"no task summary log yet at {summary_path}")

    notes.append(f"{len(uploads)} upload entry(ies) under {default_upload_dir(root)}")
    for source in sources:
        if source.exists and not source.readable:
            notes.append(f"{source.name} is not readable: {source.detail or 'unknown reason'}")

    return WorkspaceSnapshot(
        root=resolved_root,
        sources=sources,
        uploads=uploads,
        summary_path=summary_path,
        summary_records=summary_records,
        graph_path=graph_path,
        graph_nodes=graph_nodes,
        notes=tuple(notes),
    )


def snapshot_row(snapshot: WorkspaceSnapshot) -> tuple[str, ...]:
    """One table row for :data:`SNAPSHOT_COLUMNS`; an unusable value yields empty cells."""
    if not isinstance(snapshot, WorkspaceSnapshot):
        return ()
    return (
        str(snapshot.root),
        str(snapshot.graph_path) if snapshot.graph_path is not None else "",
        str(snapshot.graph_nodes),
        str(snapshot.summary_path) if snapshot.summary_path is not None else "",
        str(snapshot.summary_records),
        str(len(snapshot.uploads)),
    )


__all__ = [
    "SNAPSHOT_COLUMNS",
    "WorkspaceSnapshot",
    "scan_workspace",
    "snapshot_row",
    "uploads_summary",
]

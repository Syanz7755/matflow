"""One save, one folder.

Every piece of local workspace state — the graph, workspace settings, uploads
and the task-summary log — lives together in ``data/saves/<save>/``, so a save
can be copied, archived or deleted as a unit and two saves never share files.

Which save is open:

1. ``MATFLOW_DATA_ROOT`` — an explicit save folder (tests and tools use this);
2. ``MATFLOW_SAVE`` — a save name under ``data/saves/``;
3. otherwise the save named ``default``.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SAVE = "default"
SAVE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

#: The files and folders that make up one save, relative to its folder.
STATE_FILE = "graph_state.json"
SETTINGS_FILE = "settings.json"
UPLOADS_DIR = "uploads"
SUMMARY_LOG = Path("audit") / "task_summaries.jsonl"


def saves_dir(root: Path = ROOT) -> Path:
    return root / "data" / "saves"


def validate_save_name(name: str) -> str:
    if not SAVE_NAME.fullmatch(name) or name in {".", ".."}:
        raise ValueError(
            f"Invalid save name {name!r}: use 1-64 letters, digits, '.', '_' or '-', starting with a letter or digit"
        )
    return name


def active_save_name() -> str:
    return validate_save_name(os.getenv("MATFLOW_SAVE", "").strip() or DEFAULT_SAVE)


def resolve_data_root(root: Path = ROOT) -> Path:
    """The folder of the save this process works on."""
    explicit = os.getenv("MATFLOW_DATA_ROOT")
    if explicit:
        return Path(explicit).resolve()
    return (saves_dir(root) / active_save_name()).resolve()


def list_saves(root: Path = ROOT) -> list[dict[str, Any]]:
    """Every save folder with the parts it holds; nothing is created or modified."""
    base = saves_dir(root)
    if not base.is_dir():
        return []
    saves = []
    for folder in sorted(path for path in base.iterdir() if path.is_dir() and SAVE_NAME.fullmatch(path.name)):
        uploads = folder / UPLOADS_DIR
        saves.append({
            "name": folder.name,
            "path": str(folder),
            "has_graph": (folder / STATE_FILE).is_file(),
            "has_settings": (folder / SETTINGS_FILE).is_file(),
            "uploads": sum(1 for item in uploads.iterdir() if item.is_file()) if uploads.is_dir() else 0,
            "has_task_log": (folder / SUMMARY_LOG).is_file(),
        })
    return saves

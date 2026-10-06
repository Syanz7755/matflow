"""Hermetic helpers shared by the FlowView tests.

Rules encoded here (and asserted by ``test_offline_independence``):

* every fixture lives in a ``tempfile.TemporaryDirectory``;
* every CLI subprocess gets ``MATFLOW_DATA_ROOT`` inside that directory, so the real ``data/``
  tree is never read or written;
* the FlowView CLI is always invoked as ``sys.executable -m flowview`` with the repository root
  as ``cwd``, so no install step and no ``PATH`` assumptions are involved;
* this module never imports ``backend``.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
FLOWVIEW_DIR = REPO_ROOT / "flowview"
DATA_DIR = REPO_ROOT / "data"

CLI_MODULE = "flowview"

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

#: Prelude for every "offline independence" bootstrap: any import of ``backend`` raises.
BACKEND_BLOCKER_PRELUDE = '''\
"""Test bootstrap: make ``backend`` unimportable, then run the FlowView API."""
import sys


class BackendBlocker:
    """A meta-path finder that refuses every ``backend`` module."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname == "backend" or fullname.startswith("backend."):
            raise ImportError("flowview tests: backend import is blocked on purpose")
        return None


for _name in [n for n in list(sys.modules) if n == "backend" or n.startswith("backend.")]:
    del sys.modules[_name]

sys.meta_path.insert(0, BackendBlocker())
'''


class SubprocessResult:
    """A tiny, readable wrapper around :class:`subprocess.CompletedProcess`."""

    def __init__(self, completed: subprocess.CompletedProcess[str]) -> None:
        self.returncode = completed.returncode
        self.stdout = completed.stdout or ""
        self.stderr = completed.stderr or ""
        self.args = completed.args

    @property
    def combined(self) -> str:
        return self.stdout + self.stderr

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"SubprocessResult(returncode={self.returncode!r}, "
            f"stdout={self.stdout[:400]!r}, stderr={self.stderr[:400]!r})"
        )


def display_width(text: str) -> int:
    """Terminal display columns of ``text`` (East-Asian wide chars count as 2, ANSI as 0)."""
    width = 0
    for char in _ANSI_RE.sub("", text):
        if unicodedata.combining(char):
            continue
        width += 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
    return width


def has_ansi(text: str) -> bool:
    return "\x1b" in text


def snapshot_tree(root: Path) -> dict[str, tuple[int, int]]:
    """(size, mtime_ns) for every file under ``root``, keyed by relative path."""
    snapshot: dict[str, tuple[int, int]] = {}
    if not root.exists():
        return snapshot
    for path in sorted(root.rglob("*")):
        if path.is_file():
            stat = path.stat()
            snapshot[str(path.relative_to(root))] = (stat.st_size, stat.st_mtime_ns)
    return snapshot


def tree_entries(root: Path) -> set[str]:
    """Every entry (file *and* directory) under ``root``, relative, so creations are visible."""
    if not root.exists():
        return set()
    return {str(path.relative_to(root)) for path in root.rglob("*")}


def no_traceback(text: str) -> bool:
    return "Traceback (most recent call last)" not in text


def write_text(path: Path, text: str, *, encoding: str = "utf-8") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding=encoding)
    return path


def write_bytes(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def as_json_text(payload: Any) -> str:
    return json.dumps(payload, indent=2)


def graph_payload(
    nodes: Sequence[Any] = (),
    edges: Sequence[Any] = (),
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"graph_id": "test-graph", "version": 3, "nodes": list(nodes), "edges": list(edges)}
    payload.update(extra)
    return payload


def node(node_id: str, status: str = "ready", **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"id": node_id, "label": node_id.replace("_", " ").title(), "tool_id": f"tool.{node_id}", "status": status}
    payload.update(extra)
    return payload


def edge(edge_id: str, source: str, target: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"id": edge_id, "source": source, "target": target}
    payload.update(extra)
    return payload


def chain_payload(count: int, *, start: int = 0, status: str = "ready") -> dict[str, Any]:
    """``count`` nodes wired into a straight chain, plus a few extra ports/statuses."""
    nodes = [node(f"n{index}", status=status) for index in range(start, start + count)]
    edges = [edge(f"e{index}", f"n{index}", f"n{index + 1}") for index in range(start, start + count - 1)]
    return graph_payload(nodes, edges)


def issue_codes(payload: Mapping[str, Any]) -> list[str]:
    """The issue codes carried by a ``--format json`` payload (`issues` plus node issues)."""
    codes = [str(issue.get("code")) for issue in payload.get("issues", [])]
    return codes


def json_issue_codes(proc: SubprocessResult) -> list[str]:
    payload = json.loads(proc.stdout)
    return issue_codes(payload)


class FlowViewTestCase:
    """Base class: one temp workspace per test, CLI always pointed at it.

    Subclasses are ``unittest.TestCase`` subclasses; this mixin only provides fixtures.
    """

    #: set by setUp; subclasses read them in tests
    tmp: Path
    data_dir: Path

    def setUp(self) -> None:  # noqa: D102 - unittest hook
        self._tmp_handle = tempfile.TemporaryDirectory(prefix="flowview-tests-")
        self.addCleanup(self._tmp_handle.cleanup)
        self.tmp = Path(self._tmp_handle.name)
        self.data_dir = self.tmp / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    # -- environment ---------------------------------------------------------------------
    def env(self, **extra: Any) -> dict[str, str]:
        """A child environment whose data root is this test's temp directory."""
        env = os.environ.copy()
        env.pop("MATFLOW_FLOWVIEW_ROOT", None)
        env["MATFLOW_DATA_ROOT"] = str(self.data_dir)
        env["PYTHONPATH"] = str(REPO_ROOT)
        env["PYTHONIOENCODING"] = "utf-8"
        env["NO_COLOR"] = "1"
        env.pop("FORCE_COLOR", None)
        env["COLUMNS"] = "200"
        for key, value in extra.items():
            env[key] = str(value)
        return env

    # -- CLI subprocesses ----------------------------------------------------------------
    def run_cli(
        self,
        *args: str,
        cwd: Path | None = None,
        env_extra: Mapping[str, Any] | None = None,
        timeout: float = 120,
    ) -> SubprocessResult:
        """Run ``python -m flowview <args...>`` against this test's temp workspace."""
        completed = subprocess.run(
            [sys.executable, "-m", CLI_MODULE, *[str(arg) for arg in args]],
            cwd=str(cwd or REPO_ROOT),
            env=self.env(**(env_extra or {})),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return SubprocessResult(completed)

    def run_bootstrap(
        self,
        body: str,
        *args: str,
        blocked_backend: bool = True,
        env_extra: Mapping[str, Any] | None = None,
        timeout: float = 120,
        name: str = "bootstrap.py",
    ) -> SubprocessResult:
        """Run a generated script (optionally with ``backend`` blocked) in a subprocess."""
        script = self.tmp / name
        prelude = BACKEND_BLOCKER_PRELUDE if blocked_backend else ""
        write_text(script, prelude + body)
        completed = subprocess.run(
            [sys.executable, str(script), *[str(arg) for arg in args]],
            cwd=str(REPO_ROOT),
            env=self.env(**(env_extra or {})),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return SubprocessResult(completed)

    # -- fixtures ------------------------------------------------------------------------
    def write_graph(self, payload: Any, name: str = "graph_state.json") -> Path:
        """Write a graph fixture into this test's data root (never the real one)."""
        path = self.data_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, (str, bytes)):
            if isinstance(payload, bytes):
                path.write_bytes(payload)
            else:
                path.write_text(payload, encoding="utf-8")
        else:
            path.write_text(as_json_text(payload), encoding="utf-8")
        return path

    def write_file(self, name: str, text: str, *, encoding: str = "utf-8") -> Path:
        return write_text(self.data_dir / name, text, encoding=encoding)

    def write_raw(self, name: str, payload: bytes) -> Path:
        return write_bytes(self.data_dir / name, payload)

    def summary_path(self) -> Path:
        return self.data_dir / "audit" / "task_summaries.jsonl"

    # -- assertions ----------------------------------------------------------------------
    def graph_json(
        self,
        *args: str,
        graph: Any | None = None,
        fmt: str = "json",
        command: str = "graph",
    ) -> tuple[SubprocessResult, dict[str, Any]]:
        """Run ``graph --format json`` and return the parsed payload.

        Global options go before the subcommand, which is the placement CONTRACT.md documents.
        """
        if graph is not None:
            self.write_graph(graph)
        proc = self.run_cli("--format", fmt, command, *args)
        self.assert_no_traceback(proc)
        payload = self._load_json(proc)
        return proc, payload

    # backward-compatible alias used by a few tests
    def run_graph_json(self, *args: str, graph: Any | None = None) -> tuple[SubprocessResult, dict[str, Any]]:
        return self.graph_json(*args, graph=graph)

    def _load_json(self, proc: SubprocessResult) -> dict[str, Any]:
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:  # pragma: no cover - failure path
            self.fail(f"stdout was not a single JSON document: {exc}\nstdout={proc.stdout[:2000]!r}\nstderr={proc.stderr[:2000]!r}")
        self.assertIsInstance(payload, dict)
        return payload

    def load_stdout_json(self, proc: SubprocessResult) -> dict[str, Any]:
        return self._load_json(proc)

    def assert_no_traceback(self, proc: SubprocessResult) -> None:
        if not no_traceback(proc.combined):
            self.fail(f"a traceback leaked to the terminal:\n{proc.combined[:4000]}")

    def assert_exit(self, proc: SubprocessResult, expected: int) -> None:
        if proc.returncode != expected:
            self.fail(
                f"expected exit code {expected}, observed {proc.returncode}\n"
                f"stdout={proc.stdout[:2000]!r}\nstderr={proc.stderr[:2000]!r}"
            )

    def assert_issue_code(self, payload: Mapping[str, Any], code: str) -> None:
        codes = issue_codes(payload)
        if code not in codes:
            self.fail(f"expected issue code {code!r} in {codes!r}\npayload issues={payload.get('issues')!r}")

    def assert_no_issue_code(self, payload: Mapping[str, Any], code: str) -> None:
        codes = issue_codes(payload)
        if code in codes:
            self.fail(f"did not expect issue code {code!r} in {codes!r}")

    def assert_stderr_code(self, proc: SubprocessResult, code: str) -> None:
        if code not in proc.stderr:
            self.fail(f"expected issue code {code!r} on stderr\nstderr={proc.stderr[:2000]!r}")

    def node_ids(self, payload: Mapping[str, Any]) -> list[str]:
        graph = payload["document"].get("graph") or {}
        return [str(node.get("id")) for node in graph.get("nodes", [])]

    def statuses(self, payload: Mapping[str, Any]) -> dict[str, str]:
        graph = payload["document"].get("graph") or {}
        return {str(node.get("id")): str(node.get("status")) for node in graph.get("nodes", [])}


def import_flowview_module(name: str) -> Any:
    """Import a FlowView module *inside* a test so a missing module fails one test, not collection."""
    import importlib

    return importlib.import_module(name)


__all__ = [
    "BACKEND_BLOCKER_PRELUDE",
    "CLI_MODULE",
    "DATA_DIR",
    "FLOWVIEW_DIR",
    "FlowViewTestCase",
    "REPO_ROOT",
    "SubprocessResult",
    "chain_payload",
    "display_width",
    "graph_payload",
    "has_ansi",
    "import_flowview_module",
    "issue_codes",
    "json_issue_codes",
    "no_traceback",
    "node",
    "edge",
    "snapshot_tree",
    "tree_entries",
    "write_bytes",
    "write_text",
]

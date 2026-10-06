"""The headline guarantee: FlowView works when ``backend`` cannot be imported at all.

Every test here either (a) installs a ``sys.meta_path`` finder that raises ``ImportError`` for
``backend``/``backend.*`` in a *fresh interpreter*, or (b) proves that a full CLI run leaves the
real project ``data/`` directory byte-for-byte untouched.
"""
from __future__ import annotations

import ast
import json
import unittest

from flowview.tests import support
from flowview.tests.support import (
    FLOWVIEW_DIR,
    FlowViewTestCase,
    chain_payload,
    snapshot_tree,
    tree_entries,
)

# Every module that ships in flowview/. Importing any of them must not need the backend.
FLOWVIEW_MODULES = (
    "flowview",
    "flowview.cli",
    "flowview.model",
    "flowview.codes",
    "flowview.analysis",
    "flowview.loader",
    "flowview.mermaid",
    "flowview.text",
    "flowview.jsonout",
    "flowview.style",
    "flowview.phases",
    "flowview.trace",
    "flowview.tasks",
    "flowview.workspace",
    "flowview.backend_adapter",
)

SANITY_BODY = """
import sys

try:
    import backend  # noqa: F401
except ImportError as exc:
    print("BLOCKED", type(exc).__name__)
else:
    print("NOT-BLOCKED")
    raise SystemExit(9)
"""

IMPORT_BODY = """
import importlib
import json
import sys

names = sys.argv[1:]
import flowview  # noqa: F401

for name in names:
    importlib.import_module(name)

leaked = sorted(n for n in sys.modules if n == "backend" or n.startswith("backend."))
print(json.dumps({"imported": len(names), "backend_modules": leaked}))
if leaked:
    raise SystemExit(9)
"""

ADAPTER_BODY = """
import json

from flowview.backend_adapter import backend_available

available, reason = backend_available()
print(json.dumps({"available": available, "reason": reason}))
if available:
    raise SystemExit(9)
"""


class BackendBlockerSanityTests(FlowViewTestCase, unittest.TestCase):
    """If the blocker itself is broken, every other independence test is meaningless."""

    def test_blocker_really_blocks_backend(self):
        proc = self.run_bootstrap(SANITY_BODY)
        self.assertEqual(proc.returncode, 0, proc)
        self.assertIn("BLOCKED", proc.stdout)
        self.assertNotIn("NOT-BLOCKED", proc.stdout)


class OfflineImportTests(FlowViewTestCase, unittest.TestCase):
    def test_package_and_cli_import_without_backend(self):
        proc = self.run_bootstrap(
            IMPORT_BODY,
            "flowview",
            "flowview.cli",
            "flowview.model",
            "flowview.codes",
            "flowview.analysis",
            "flowview.loader",
        )
        self.assert_no_traceback(proc)
        self.assertEqual(proc.returncode, 0, proc)
        report = json.loads(proc.stdout)
        self.assertEqual(report["backend_modules"], [])

    def test_every_flowview_module_imports_without_backend(self):
        proc = self.run_bootstrap(IMPORT_BODY, *FLOWVIEW_MODULES)
        self.assert_no_traceback(proc)
        self.assertEqual(proc.returncode, 0, proc)
        report = json.loads(proc.stdout)
        self.assertEqual(report["imported"], len(FLOWVIEW_MODULES))
        self.assertEqual(report["backend_modules"], [])

    def test_graph_json_runs_with_backend_blocked(self):
        """The exact repro from the task: `graph --format json` with backend blocked."""
        self.write_graph(chain_payload(3))
        body = """
import sys

from flowview.cli import main

raise SystemExit(main(["graph", "--format", "json"]))
"""
        proc = self.run_bootstrap(body)
        self.assert_no_traceback(proc)
        self.assertEqual(proc.returncode, 0, proc)
        payload = json.loads(proc.stdout)
        self.assertIn("flowview_schema", payload)
        self.assertEqual(len(payload["document"]["graph"]["nodes"]), 3)

    def test_graph_text_and_mermaid_run_with_backend_blocked(self):
        self.write_graph(chain_payload(3))
        for fmt in ("text", "mermaid"):
            with self.subTest(fmt=fmt):
                body = f"""
import sys

from flowview.cli import main

raise SystemExit(main(["graph", "--format", "{fmt}"]))
"""
                proc = self.run_bootstrap(body, name=f"bootstrap-{fmt}.py")
                self.assert_no_traceback(proc)
                self.assertEqual(proc.returncode, 0, proc)
                self.assertTrue(proc.stdout.strip(), f"{fmt} produced no output")

    def test_run_flow_and_doctor_run_with_backend_blocked(self):
        for args, expected in ((("flow", "--blueprint"), 0), (("doctor",), 0), (("summary",), 3)):
            with self.subTest(args=args):
                body = f"""
import sys

from flowview.cli import main

raise SystemExit(main({list(args)!r}))
"""
                proc = self.run_bootstrap(body, name="bootstrap-%s.py" % "-".join(args))
                self.assert_no_traceback(proc)
                self.assertEqual(proc.returncode, expected, proc)

    def test_optional_backend_adapter_degrades_instead_of_raising(self):
        proc = self.run_bootstrap(ADAPTER_BODY)
        self.assert_no_traceback(proc)
        self.assertEqual(proc.returncode, 0, proc)
        report = json.loads(proc.stdout)
        self.assertFalse(report["available"])
        self.assertTrue(report["reason"], "the adapter must explain why the backend is unusable")

    def test_backend_adapter_documents_are_readable_without_backend(self):
        """With the backend blocked, every adapter document must be a readable issue, not a crash."""
        body = """
import json

from flowview.backend_adapter import schema_document

document = schema_document()
issues = [{"severity": issue.severity, "code": issue.code, "hint": issue.hint, "message": issue.message} for issue in document.all_issues()]
print(json.dumps({"issues": issues, "documents": [issue["code"] for issue in issues]}))
if not issues:
    raise SystemExit(9)
for issue in issues:
    if not issue["hint"]:
        raise SystemExit(8)
"""
        proc = self.run_bootstrap(body)
        self.assert_no_traceback(proc)
        self.assertEqual(proc.returncode, 0, proc)
        report = json.loads(proc.stdout)
        self.assertTrue(report["issues"], "an unusable backend must produce a visible issue")
        for issue in report["issues"]:
            self.assertTrue(issue["hint"], f"issue {issue['code']} must carry a next action")

    def test_no_module_level_backend_import_in_any_flowview_module(self):
        offenders: list[str] = []
        for path in sorted(FLOWVIEW_DIR.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for statement in tree.body:
                for alias in _module_level_imports(statement):
                    if alias == "backend" or alias.startswith("backend."):
                        offenders.append(f"{path.name}:{statement.lineno} imports {alias}")
        self.assertEqual(offenders, [], "backend imports must be lazy and wrapped, never module level")


def _module_level_imports(statement: ast.stmt) -> list[str]:
    """``backend`` modules imported at module top level, including inside top-level try/if."""
    found: list[str] = []
    if isinstance(statement, ast.Import):
        found.extend(alias.name for alias in statement.names)
    elif isinstance(statement, ast.ImportFrom):
        if statement.module:
            found.append(statement.module)
    elif isinstance(statement, (ast.Try, ast.If, ast.With)):
        for child in statement.body:
            found.extend(_module_level_imports(child))
        for handler in getattr(statement, "handlers", []):
            for child in handler.body:
                found.extend(_module_level_imports(child))
    return found


class ReadOnlyWorkspaceTests(FlowViewTestCase, unittest.TestCase):
    """`flowview` is a printer: a full sweep must not create or modify anything in data/."""

    COMMANDS = (
        ("--format", "text", "graph"),
        ("--format", "mermaid", "graph"),
        ("--format", "json", "graph"),
        ("--format", "text", "graph", "--layers"),
        ("run-flow", "--blueprint"),
        ("doctor", "--list"),
        ("summary",),
    )

    def test_real_data_directory_is_untouched(self):
        real_root = support.DATA_DIR
        before_files = snapshot_tree(real_root)
        before_entries = tree_entries(real_root)
        for command in self.COMMANDS:
            with self.subTest(command=command):
                proc = self.run_cli(
                    *command,
                    env_extra={"MATFLOW_DATA_ROOT": str(real_root), "MATFLOW_FLOWVIEW_ROOT": str(support.REPO_ROOT)},
                )
                self.assert_no_traceback(proc)
                self.assertNotEqual(proc.returncode, 1, proc)
        after_files = snapshot_tree(real_root)
        after_entries = tree_entries(real_root)
        self.assertEqual(before_files, after_files, "flowview modified or created a file under data/")
        self.assertEqual(before_entries, after_entries, "flowview created an entry under data/")

    def test_default_invocation_uses_the_temp_data_root_not_the_project_one(self):
        """Guard the guard: the fixtures really are hermetic."""
        proc = self.run_cli("graph", "--format", "json")
        self.assertEqual(proc.returncode, 0, proc)
        self.assertNotIn(str(support.DATA_DIR / "graph_state.json"), proc.stdout)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

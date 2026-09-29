import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.cli import LauncherError, load_ui_manifest, resolve_frontend_root, select_ui


class UiSelectionTests(unittest.TestCase):
    def test_explicit_ui_wins(self):
        self.assertEqual(select_ui("webui", interactive=False), "webui")

    def test_non_interactive_start_defaults_to_backend_only(self):
        self.assertEqual(select_ui(None, interactive=False), "none")

    def test_environment_path_precedes_sibling_default(self):
        with patch.dict(os.environ, {"MATFLOW_WEBUI_DIR": "relative-ui"}):
            self.assertEqual(resolve_frontend_root(), Path("relative-ui").resolve())

    def test_explicit_path_precedes_environment(self):
        with patch.dict(os.environ, {"MATFLOW_WEBUI_DIR": "ignored-ui"}):
            self.assertEqual(resolve_frontend_root("chosen-ui"), Path("chosen-ui").resolve())

    def test_manifest_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "matflow-ui.json").write_text(json.dumps({
                "schema_version": 1,
                "clients": {"webui": {"command": ["npm"], "working_directory": ".", "url": "http://ui", "health_url": "http://ui"}},
            }), encoding="utf-8")
            self.assertEqual(load_ui_manifest(root)["command"], ["npm"])

    def test_invalid_manifest_is_actionable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "matflow-ui.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(LauncherError, "schema_version 1"):
                load_ui_manifest(root)

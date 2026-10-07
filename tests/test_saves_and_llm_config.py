import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from backend.llm_config import LLMConfig, load_llm_config
from backend.saves import list_saves, resolve_data_root, validate_save_name
from backend.workspace_runtime import WorkspaceRuntime, default_settings

ROOT = Path(__file__).parents[1]


class SaveLayoutTests(unittest.TestCase):
    def test_each_save_is_one_folder_holding_every_workspace_file(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"MATFLOW_SAVE": "lab-run_1"}):
            os.environ.pop("MATFLOW_DATA_ROOT", None)
            runtime = WorkspaceRuntime(Path(directory))
            runtime.import_dataset("a.csv", b"x\n1\n", "text/csv")
            runtime.write_settings(runtime.read_settings())
            runtime.write_state(runtime.read_state())

            save = Path(directory) / "data" / "saves" / "lab-run_1"
            self.assertEqual(runtime.data_root, save.resolve())
            self.assertEqual(sorted(path.name for path in save.iterdir()), ["graph_state.json", "settings.json", "uploads"])
            listed = list_saves(Path(directory))
            self.assertEqual([(item["name"], item["has_graph"], item["uploads"]) for item in listed], [("lab-run_1", True, 1)])

    def test_explicit_data_root_wins_and_default_save_is_named_default(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"MATFLOW_DATA_ROOT": str(Path(directory) / "explicit"), "MATFLOW_SAVE": "other"}):
                self.assertEqual(resolve_data_root(Path(directory)), (Path(directory) / "explicit").resolve())
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("MATFLOW_DATA_ROOT", None)
                os.environ.pop("MATFLOW_SAVE", None)
                self.assertEqual(resolve_data_root(Path(directory)), (Path(directory) / "data" / "saves" / "default").resolve())

    def test_a_save_name_cannot_escape_the_saves_folder(self):
        for name in ("..", "../x", "a/b", "", ".hidden", "x" * 65):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_save_name(name)


class LLMGatewayConfigTests(unittest.TestCase):
    def test_backend_defaults_come_from_llm_json(self):
        llm = load_llm_config()
        agent = default_settings()["agent"]
        self.assertEqual(agent["base_url"], llm.base_url)
        self.assertEqual(agent["api_key_env"], llm.gateway.api_key_env)
        self.assertEqual(default_settings()["model_providers"]["local_litellm"]["models"], llm.models)

    def test_launch_configuration_agrees_with_llm_json(self):
        llm = load_llm_config()
        litellm = yaml.safe_load((ROOT / llm.gateway.litellm_config).read_text(encoding="utf-8"))
        services = {item["id"]: item for item in json.loads((ROOT / "config" / "model_services.json").read_text(encoding="utf-8"))["services"]}
        gateway = services["litellm_gateway"]

        self.assertEqual(litellm["general_settings"]["master_key"], f"os.environ/{llm.gateway.api_key_env}")
        self.assertTrue(set(llm.models) <= {item["model_name"] for item in litellm["model_list"]})
        self.assertEqual(gateway["readiness_api_key_env"], llm.gateway.api_key_env)
        self.assertIn(str(llm.gateway.port), gateway["arguments"])
        self.assertIn(f":{llm.gateway.port}/", gateway["readiness_url"])
        for model in litellm["model_list"]:
            self.assertTrue(model["litellm_params"]["api_key"].startswith("os.environ/"))

    def test_role_models_must_be_served(self):
        payload = json.loads((ROOT / "config" / "llm.json").read_text(encoding="utf-8"))
        payload["planner_model"] = "not-served"
        with self.assertRaisesRegex(ValueError, "planner_model"):
            LLMConfig.model_validate(payload)


if __name__ == "__main__":
    unittest.main()

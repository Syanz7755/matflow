import unittest
from pathlib import Path

from backend.cli import configured_litellm_gateway_key


class LiteLLMGatewayConfigTests(unittest.TestCase):
    def test_gateway_key_is_loaded_from_project_config(self):
        config_path = Path(__file__).parents[1] / "config" / "litellm.yaml"

        key = configured_litellm_gateway_key(config_path)

        self.assertTrue(key.startswith("sk-matflow-local-gateway-"))
        self.assertNotEqual(key, "sk-local-wqs")

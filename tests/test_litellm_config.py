import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.cli import configured_litellm_gateway_key


class LiteLLMGatewayConfigTests(unittest.TestCase):
    def test_gateway_key_is_resolved_from_the_declared_environment_variable(self):
        environment_name = "MATFLOW_TEST_LOCAL_GATEWAY_KEY"
        expected = "runtime-only-value"
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "litellm.yaml"
            config_path.write_text(
                f"general_settings:\n  master_key: os.environ/{environment_name}\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {environment_name: expected}):
                key = configured_litellm_gateway_key(config_path)

        self.assertEqual(key, expected)

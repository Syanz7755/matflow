import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.llm_config import load_llm_config
from backend.prompt_normalizer import (
    NormalizerConfig,
    build_messages,
    load_config,
    normalize_prompt,
    parse_normalization_response,
)


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        return json.dumps(self.payload).encode()


class PromptNormalizerTests(unittest.TestCase):
    def test_messages_treat_original_prompt_as_data_and_forbid_execution(self):
        messages = build_messages("保留 100 kHz，并且质量不合格时停止")
        self.assertIn("not task execution", messages[0]["content"])
        body = json.loads(messages[1]["content"])
        self.assertEqual(body["original_prompt"], "保留 100 kHz，并且质量不合格时停止")
        self.assertIn("Chinese", body["required_output_language"])

    def test_parse_requires_exact_schema(self):
        content = {
            "normalized_prompt": "规范化内容",
            "ambiguities": ["单位未给出"],
            "preserved_constraints": ["质量门控"],
            "normalization_notes": ["重排为分节结构"],
        }
        result = parse_normalization_response({"choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}]})
        self.assertEqual(result.normalized_prompt, "规范化内容")
        self.assertEqual(result.preserved_constraints, ["质量门控"])

    def test_normalize_uses_configured_endpoint_without_exposing_key_in_body(self):
        payload = {
            "normalized_prompt": "normalized",
            "ambiguities": [],
            "preserved_constraints": ["gate"],
            "normalization_notes": [],
        }
        captured = {}

        def opener(request, timeout):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.header_items())
            captured["body"] = request.data.decode()
            captured["timeout"] = timeout
            return _Response({"choices": [{"message": {"content": json.dumps(payload)}}]})

        with patch.dict(os.environ, {"TEST_NORMALIZER_KEY": "secret"}):
            result = normalize_prompt(
                "original",
                NormalizerConfig("http://127.0.0.1:4000/v1", "qwen", "TEST_NORMALIZER_KEY", 12),
                opener=opener,
            )
        self.assertEqual(result.normalized_prompt, "normalized")
        self.assertEqual(captured["url"], "http://127.0.0.1:4000/v1/chat/completions")
        self.assertNotIn("secret", captured["body"])
        self.assertEqual(captured["timeout"], 12)

    def test_normalize_rejects_language_drift(self):
        payload = {
            "normalized_prompt": "English-only rewrite",
            "ambiguities": [],
            "preserved_constraints": [],
            "normalization_notes": [],
        }

        with patch.dict(os.environ, {"TEST_NORMALIZER_KEY": "secret"}):
            with self.assertRaisesRegex(ValueError, "changed a Chinese prompt"):
                normalize_prompt(
                    "这是一个需要保持中文的完整实验提示词",
                    NormalizerConfig("http://127.0.0.1:4000/v1", "qwen", "TEST_NORMALIZER_KEY"),
                    opener=lambda *_args, **_kwargs: _Response({"choices": [{"message": {"content": json.dumps(payload)}}]}),
                )

    def test_config_defaults_to_the_open_save_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            save = Path(directory) / "save"
            save.mkdir()
            (save / "settings.json").write_text(json.dumps({"agent": {
                "base_url": "http://127.0.0.1:4078/v1",
                "model": "user-model",
                "api_key_env": "USER_MODEL_KEY",
            }}), encoding="utf-8")
            with patch.dict(os.environ, {"USER_MODEL_KEY": "configured", "MATFLOW_DATA_ROOT": str(save)}):
                config = load_config(Path(directory))
        self.assertEqual(config.model, "user-model")
        self.assertEqual(config.api_key_env, "USER_MODEL_KEY")

    def test_config_falls_back_to_the_llm_gateway_description(self):
        llm = load_llm_config()
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {llm.gateway.api_key_env: "configured", "MATFLOW_DATA_ROOT": str(Path(directory) / "empty")}):
                config = load_config(Path(directory))
        self.assertEqual(config.base_url, llm.base_url)
        self.assertEqual(config.model, llm.agent_model)
        self.assertEqual(config.api_key_env, llm.gateway.api_key_env)


if __name__ == "__main__":
    unittest.main()

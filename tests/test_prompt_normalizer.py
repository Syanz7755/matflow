import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_config_defaults_to_matflow_settings(self):
        settings = json.dumps({"agent": {
                "base_url": "http://127.0.0.1:4000/v1",
                "model": "user-model",
                "api_key_env": "USER_MODEL_KEY",
            }})

        def read_text(path, **_kwargs):
            return "" if path.name == ".env" else settings

        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", read_text),
            patch.dict(os.environ, {"USER_MODEL_KEY": "configured"}),
        ):
            config = load_config(Path("configured-root"))
        self.assertEqual(config.model, "user-model")
        self.assertEqual(config.api_key_env, "USER_MODEL_KEY")


if __name__ == "__main__":
    unittest.main()

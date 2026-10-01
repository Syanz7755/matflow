import json
import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from backend import main


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.read_limit = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, limit=None):
        self.read_limit = limit
        return json.dumps(self.payload).encode("utf-8")


class LlmGatewayBehaviorTests(unittest.TestCase):
    def settings(self):
        return main.workspace.read_settings()

    def call_with_gateway(self, payload, *, tools=None, provider_id=None, model=None):
        captured = {}
        response = FakeResponse(payload)

        def gateway(request, timeout):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.header_items())
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return response

        settings = self.settings()
        config = settings["agent"] if provider_id is None else settings["model_providers"][provider_id]
        credential_name = config["api_key_env"]
        credential_value = "test-credential-that-must-not-be-logged"
        with patch.dict(os.environ, {credential_name: credential_value}), patch.object(
            main.urlrequest, "urlopen", side_effect=gateway
        ):
            result = main.model_completion(
                [{"role": "user", "content": "Return a structured response."}],
                tools or [],
                provider_id=provider_id,
                model=model,
            )
        return result, captured, response, credential_value

    def test_text_completion_uses_runtime_configuration(self):
        expected_message = {"role": "assistant", "content": "runtime-generated-content"}

        result, request, response, _ = self.call_with_gateway({"choices": [{"message": expected_message}]})
        config = self.settings()["agent"]

        self.assertEqual(result, expected_message)
        self.assertEqual(request["url"], config["base_url"].rstrip("/") + "/chat/completions")
        self.assertEqual(request["body"]["model"], config["model"])
        self.assertEqual(request["body"]["temperature"], config["temperature"])
        self.assertEqual(response.read_limit, 2 * 1024 * 1024)

    def test_tools_are_forwarded_without_changing_their_contract(self):
        tool = {
            "type": "function",
            "function": {
                "name": "runtime_selected_tool",
                "description": "A test capability.",
                "parameters": {"type": "object", "properties": {}},
            },
        }
        message = {
            "role": "assistant",
            "tool_calls": [{
                "id": "runtime-call-id",
                "type": "function",
                "function": {"name": tool["function"]["name"], "arguments": "{}"},
            }],
        }

        result, request, _, _ = self.call_with_gateway(
            {"choices": [{"message": message}]}, tools=[tool]
        )

        self.assertEqual(request["body"]["tools"], [tool])
        self.assertEqual(request["body"]["tool_choice"], "auto")
        self.assertEqual(result["tool_calls"][0]["function"]["name"], tool["function"]["name"])

    def test_empty_tool_set_does_not_add_tool_fields(self):
        _, request, _, _ = self.call_with_gateway({
            "choices": [{"message": {"role": "assistant", "content": "done"}}]
        })

        self.assertNotIn("tools", request["body"])
        self.assertNotIn("tool_choice", request["body"])

    def test_provider_and_model_override_come_from_runtime_settings(self):
        providers = self.settings()["model_providers"]
        provider_id, provider = next(iter(providers.items()))
        selected_model = provider["models"][-1]

        _, request, _, _ = self.call_with_gateway(
            {"choices": [{"message": {"role": "assistant", "content": "done"}}]},
            provider_id=provider_id,
            model=selected_model,
        )

        self.assertEqual(request["url"], provider["base_url"].rstrip("/") + "/chat/completions")
        self.assertEqual(request["body"]["model"], selected_model)

    def test_unknown_provider_is_rejected_before_network_access(self):
        configured = set(self.settings()["model_providers"])
        unknown = "unregistered_provider"
        while unknown in configured:
            unknown += "_x"

        with patch.object(main.urlrequest, "urlopen") as gateway:
            with self.assertRaises(HTTPException) as raised:
                main.model_completion([], [], provider_id=unknown)

        self.assertEqual(raised.exception.status_code, 422)
        gateway.assert_not_called()

    def test_unregistered_model_is_rejected_before_network_access(self):
        providers = self.settings()["model_providers"]
        provider_id, provider = next(iter(providers.items()))
        unknown_model = "unregistered-model"
        while unknown_model in provider["models"]:
            unknown_model += "-x"

        with patch.object(main.urlrequest, "urlopen") as gateway:
            with self.assertRaises(HTTPException) as raised:
                main.model_completion([], [], provider_id=provider_id, model=unknown_model)

        self.assertEqual(raised.exception.status_code, 422)
        gateway.assert_not_called()

    def test_malformed_json_shape_becomes_a_controlled_provider_error(self):
        with self.assertRaises(HTTPException) as raised:
            self.call_with_gateway(["not", "an", "object"])

        self.assertEqual(raised.exception.status_code, 502)

    def test_malformed_message_shape_becomes_a_controlled_provider_error(self):
        with self.assertRaises(HTTPException) as raised:
            self.call_with_gateway({"choices": [{"message": "not-an-object"}]})

        self.assertEqual(raised.exception.status_code, 502)

    def test_provider_error_does_not_disclose_the_credential(self):
        settings = self.settings()
        credential_name = settings["agent"]["api_key_env"]
        credential_value = "secret-value-for-redaction-check"
        with patch.dict(os.environ, {credential_name: credential_value}), patch.object(
            main.urlrequest, "urlopen", side_effect=OSError("provider unavailable")
        ):
            with self.assertRaises(HTTPException) as raised:
                main.model_completion([], [])

        self.assertEqual(raised.exception.status_code, 502)
        self.assertNotIn(credential_value, str(raised.exception.detail))


if __name__ == "__main__":
    unittest.main()

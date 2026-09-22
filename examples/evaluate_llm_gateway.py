"""Check the configured OpenAI-compatible gateway without logging credentials."""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib import error, request

from backend.main import default_settings


def main() -> None:
    agent = default_settings()["agent"]
    api_key = os.environ.get(agent["api_key_env"])
    report = {
        "base_url": agent["base_url"], "model": agent["model"],
        "credential_present": bool(api_key), "models_reachable": False,
        "text_completion_reachable": False, "tool_call_reachable": False,
        "failure": None,
    }
    if not api_key:
        report["failure"] = f"Set {agent['api_key_env']} in the process that runs this script."
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}

    def call(path: str, body: dict | None = None) -> dict:
        payload = json.dumps(body).encode("utf-8") if body else None
        req = request.Request(agent["base_url"].rstrip("/") + path, data=payload, headers=headers, method="POST" if body else "GET")
        with request.urlopen(req, timeout=90) as response:
            return json.loads(response.read().decode("utf-8"))

    try:
        models = call("/models")
        report["models_reachable"] = agent["model"] in [item.get("id") for item in models.get("data", [])]
        text = call("/chat/completions", {"model": agent["model"], "messages": [{"role": "user", "content": "Reply with exactly MATFLOW_OK."}], "temperature": 0, "max_tokens": 16})
        report["text_completion_reachable"] = bool(text.get("choices", [{}])[0].get("message", {}).get("content"))
        tool = call("/chat/completions", {"model": agent["model"], "messages": [{"role": "user", "content": "Call the provided read-only function now."}], "temperature": 0, "tools": [{"type": "function", "function": {"name": "matflow_readonly_status", "description": "Read status only.", "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}}], "tool_choice": "required"})
        report["tool_call_reachable"] = bool(tool.get("choices", [{}])[0].get("message", {}).get("tool_calls"))
    except (error.URLError, error.HTTPError, KeyError, IndexError, json.JSONDecodeError) as exc:
        report["failure"] = f"{type(exc).__name__}: {exc}"
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

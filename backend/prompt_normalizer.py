"""LLM-assisted, semantics-preserving normalization for MatFlow prompts."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable
from urllib import request as urlrequest


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class NormalizerConfig:
    base_url: str
    model: str
    api_key_env: str
    timeout_seconds: float = 90.0


@dataclass(frozen=True)
class NormalizationResult:
    normalized_prompt: str
    ambiguities: list[str]
    preserved_constraints: list[str]
    normalization_notes: list[str]


SYSTEM_PROMPT = """You normalize user requests for a materials-science workflow agent.

Your job is structural normalization, not task execution. Preserve the user's language,
intent, filenames, paths, numbers, units, scientific terms, negations, conditionals,
quality gates, requested outputs, and topology constraints. Do not solve the task, select
scientific methods, invent facts, add requirements, claim tool access, or remove ambiguity.
Turn prose into a clear request with sections such as context, inputs, objectives,
constraints, workflow topology, acceptance criteria, and unresolved questions when those
sections are supported by the original text.

Return one JSON object with exactly these keys:
- normalized_prompt: string
- ambiguities: array of strings
- preserved_constraints: array of strings
- normalization_notes: array of strings

The normalized prompt must remain independently usable and must not refer to this
normalization conversation."""


def load_local_env(path: Path) -> None:
    """Load simple NAME=value entries without overriding the process environment."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


def load_config(
    root: Path = ROOT,
    *,
    base_url: str | None = None,
    model: str | None = None,
    api_key_env: str | None = None,
    timeout_seconds: float = 90.0,
) -> NormalizerConfig:
    load_local_env(root / ".env")
    settings_path = root / "data" / "settings.json"
    settings: dict[str, Any] = {}
    if settings_path.exists():
        settings = json.loads(settings_path.read_text(encoding="utf-8")).get("agent", {})
    resolved_base_url = (base_url or settings.get("base_url") or "").rstrip("/")
    resolved_model = model or settings.get("model") or ""
    resolved_key_env = api_key_env or settings.get("api_key_env") or "MATFLOW_API_KEY"
    if not resolved_base_url:
        raise ValueError("No LLM base URL is configured. Use --base-url or MatFlow settings.")
    if not resolved_model:
        raise ValueError("No LLM model is configured. Use --model or MatFlow settings.")
    if not os.getenv(resolved_key_env):
        raise ValueError(f"LLM credential environment variable is not set: {resolved_key_env}")
    return NormalizerConfig(resolved_base_url, resolved_model, resolved_key_env, timeout_seconds)


def build_messages(prompt: str) -> list[dict[str, str]]:
    if not prompt.strip():
        raise ValueError("The prompt to normalize is empty.")
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "instruction": "Normalize the following prompt without answering it.",
                    "required_output_language": _language_hint(prompt),
                    "original_prompt": prompt,
                },
                ensure_ascii=False,
            ),
        },
    ]


def _language_hint(text: str) -> str:
    cjk = sum("\u3400" <= character <= "\u9fff" for character in text)
    return "Chinese; keep normalized_prompt in Chinese" if cjk >= 8 else "Use the same primary natural language as original_prompt"


def _validate_language_preservation(original: str, normalized: str) -> None:
    original_cjk = sum("\u3400" <= character <= "\u9fff" for character in original)
    normalized_cjk = sum("\u3400" <= character <= "\u9fff" for character in normalized)
    if original_cjk >= 8 and normalized_cjk < 8:
        raise ValueError("Normalizer changed a Chinese prompt into another language; output rejected.")


def _json_content(value: str) -> dict[str, Any]:
    text = value.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("Normalizer response must be a JSON object.")
    return payload


def parse_normalization_response(response: dict[str, Any]) -> NormalizationResult:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("LLM response does not contain choices[0].message.content.") from exc
    payload = _json_content(str(content))
    expected = {"normalized_prompt", "ambiguities", "preserved_constraints", "normalization_notes"}
    if set(payload) != expected:
        raise ValueError(f"Normalizer response keys must be exactly: {', '.join(sorted(expected))}")
    normalized = payload["normalized_prompt"]
    if not isinstance(normalized, str) or not normalized.strip():
        raise ValueError("normalized_prompt must be a non-empty string.")
    lists: dict[str, list[str]] = {}
    for key in ("ambiguities", "preserved_constraints", "normalization_notes"):
        value = payload[key]
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"{key} must be an array of strings.")
        lists[key] = value
    return NormalizationResult(
        normalized_prompt=normalized.strip(),
        ambiguities=lists["ambiguities"],
        preserved_constraints=lists["preserved_constraints"],
        normalization_notes=lists["normalization_notes"],
    )


def normalize_prompt(
    prompt: str,
    config: NormalizerConfig,
    *,
    opener: Callable[..., Any] = urlrequest.urlopen,
) -> NormalizationResult:
    body = {
        "model": config.model,
        "messages": build_messages(prompt),
        "temperature": 0,
    }
    key = os.environ[config.api_key_env]
    req = urlrequest.Request(
        config.base_url + "/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    with opener(req, timeout=config.timeout_seconds) as response:
        payload = json.loads(response.read(2 * 1024 * 1024))
    result = parse_normalization_response(payload)
    _validate_language_preservation(prompt, result.normalized_prompt)
    return result


def _read_prompt(args: argparse.Namespace) -> str:
    if args.text is not None:
        return args.text
    if args.input is not None:
        return args.input.read_text(encoding="utf-8")
    return sys.stdin.read()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Normalize a MatFlow user prompt with the configured user LLM.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--input", type=Path, help="UTF-8 prompt file. Reads stdin when omitted.")
    source.add_argument("--text", help="Prompt text supplied directly on the command line.")
    parser.add_argument("--output", type=Path, help="Write the normalized prompt to this UTF-8 file.")
    parser.add_argument("--metadata-output", type=Path, help="Write the full normalization record as JSON.")
    parser.add_argument("--base-url", help="OpenAI-compatible base URL; defaults to MatFlow settings.")
    parser.add_argument("--model", help="Model name; defaults to MatFlow settings.")
    parser.add_argument("--api-key-env", help="Credential environment variable; defaults to MatFlow settings.")
    parser.add_argument("--timeout", type=float, default=90.0, help="Request timeout in seconds.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        prompt = _read_prompt(args)
        config = load_config(
            base_url=args.base_url,
            model=args.model,
            api_key_env=args.api_key_env,
            timeout_seconds=args.timeout,
        )
        result = normalize_prompt(prompt, config)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(result.normalized_prompt + "\n", encoding="utf-8")
        else:
            print(result.normalized_prompt)
        if args.metadata_output:
            args.metadata_output.parent.mkdir(parents=True, exist_ok=True)
            args.metadata_output.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Prompt normalization failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

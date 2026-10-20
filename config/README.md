# MatFlow model configuration

## LLM gateway (`llm.json`, `litellm.yaml`)

`llm.json` is the one non-secret description of the LLM gateway: host, port, the **name** of the environment variable that holds the caller key, the served models, the agent model and the planner model. The backend and the launcher both read it, so they cannot disagree.

```powershell
start_llm.bat              # reuse a gateway that accepts the key, or start LiteLLM
start_llm.bat -CheckOnly   # only report whether the gateway is ready
start_llm.bat -Port 4080   # use another port for this run
```

`start_llm.bat` (alias: `start_litellm.bat`) checks `GET /health/readiness`, then `GET /v1/models` with the key from `gateway.api_key_env` (default `LITELLM_DEFAULT_API_KEY`). A healthy gateway that accepts the key is reused; a gateway that rejects it is reported, never replaced. Otherwise LiteLLM is started from `litellm.yaml` (project `.venv`, then `litellm` on `PATH`, then `uv run`; `MATFLOW_LITELLM_EXE` overrides). Variables set with `setx` are picked up even in shells opened before them. No credential value is ever printed.

`litellm.yaml` only declares the upstream models; every key in it is an `os.environ/...` reference. `glm` is not served at the moment because the current SJTU team key is refused for it (HTTP 403); re-add it in both files once access is granted. `MATFLOW_LLM_CONFIG` points the backend at another `llm.json`.

## Optional DeepSeek official gateway (`llm-deepseek.json`, `litellm-deepseek.yaml`)

The multi-model comparison also covers the DeepSeek official provider. It is a
second MatFlow-owned LiteLLM process on port 4080, described by
`config/llm-deepseek.json` and `config/litellm-deepseek.yaml`. Its only upstream
credential is `DEEPSEEK_API_KEY_MATFLOW_EXCLUSIVE`, referenced as
`os.environ/...`; it is read by that process alone, never printed and never used
for another vendor. Model ids follow the provider's current catalogue
(`deepseek-official-flash`, `deepseek-official-v4-pro` as served aliases).

`MATFLOW_LLM_CONFIG=config/llm-deepseek.json` points the backend (or an
evaluation script) at that gateway instead of the default one. The one-command
live demo, `scripts/start_demo.ps1`, starts or reuses both gateways, the backend
and the WebUI; it reads the three key variables from the Windows User
environment scope into the child processes only.

| Provider | Model (served alias) | Status 2026-10-20 |
|---|---|---|
| SJTU | `deepseek-chat`, `deepseek-reasoner`, `qwen` | available |
| SJTU | `minimax` | unavailable: HTTP 403, team not allowed |
| DeepSeek official | `deepseek-official-flash`, `deepseek-official-v4-pro` | available |

## Starting all model services

`start_model_services.bat` starts every enabled service in `model_services.json`: `litellm_gateway` (`online_api`, port 4078) and `jev_decision_gateway` (`local`, port 4079). `start_matflow.bat` runs it before opening MatFlow; healthy gateways are reused. To validate the process configuration without starting anything:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_model_services.ps1 -ValidateOnly
```

## Tool routing: Jev, then the LLM — never keywords

`jev_router.json` wires Laya and Sematic (gateway model id `semantic`) into tool selection; both are structured decision models, not chat models. `MATFLOW_JEV_ROUTER_CONFIG` overrides the path. No API key belongs in this file.

Candidates are every agent-selectable tool whose input ports accept the available data — a type filter, with no keyword score. The decision is made by a model:

1. Jev, when `router.enabled` is true and there are at least two candidates. `router.strategy` is `consensus` (Laya and Sematic must agree) or `laya` / `semantic` (one profile).
2. The configured LLM, when Jev is unreachable (`router.fallback: "llm"`, the default) or when Jev disagrees or is below `minimum_calibrated_confidence` (the LLM breaks the tie and a human still confirms).
3. A human, when `router.fallback` is `"none"`, or when no model is available at all.

`fallback_to_lexical` is rejected: keyword matching is disabled everywhere. `minimum_calibrated_confidence` applies only to Laya's calibrated confidence; Sematic's score is a conditional rating between the submitted candidates.

## Task summary log

`observability.json` configures the user-readable JSONL task-summary log. `jsonl_path` is relative to the open save folder (`data/saves/<save>/audit/task_summaries.jsonl`), so every save keeps its own history. Each summary keeps the original `user_prompt` and records the input context, candidate tools, model opinions, final selection, execution result, and error handling. Every tool reference carries a human-facing `label` and a stable `registered_id` / `version`. The `data/saves/` folder is Git-ignored.

`/api/route` adds `summary` to its response; a later execution request may carry the same `task_id` to merge its result into that summary. `GET /api/task-summaries/{task_id}` returns the latest complete summary for that task.

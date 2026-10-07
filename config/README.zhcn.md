# MatFlow 模型配置

## LLM 网关（`llm.json`、`litellm.yaml`）

`llm.json` 是 LLM 网关唯一的非机密描述：主机、端口、保存调用密钥的环境变量**名称**、可用模型、agent 模型和规划器模型。后端与启动器都读取它，两者不会不一致。

```powershell
start_llm.bat              # 复用接受该密钥的网关，否则启动 LiteLLM
start_llm.bat -CheckOnly   # 只报告网关是否就绪
start_llm.bat -Port 4080   # 本次使用其他端口
```

`start_llm.bat`（别名 `start_litellm.bat`）先检查 `GET /health/readiness`，再用 `gateway.api_key_env`（默认 `LITELLM_DEFAULT_API_KEY`）中的密钥请求 `GET /v1/models`。接受该密钥的健康网关会被复用；拒绝该密钥的网关只会被报告，绝不会被替换。否则从 `litellm.yaml` 启动 LiteLLM（依次尝试项目 `.venv`、`PATH` 上的 `litellm`、`uv run`；`MATFLOW_LITELLM_EXE` 可覆盖）。用 `setx` 设置的变量即使在之前打开的终端里也能读到。任何密钥值都不会被打印。

`litellm.yaml` 只声明上游模型；其中每个密钥都是 `os.environ/...` 引用。`glm` 目前不提供，因为当前 SJTU 团队密钥访问它会被拒绝（HTTP 403）；获得权限后在两个文件中重新加入。`MATFLOW_LLM_CONFIG` 可让后端读取另一个 `llm.json`。

## 启动全部模型服务

`start_model_services.bat` 启动 `model_services.json` 中所有启用的服务：`litellm_gateway`（`online_api`，端口 4078）与 `jev_decision_gateway`（`local`，端口 4079）。`start_matflow.bat` 会在打开 MatFlow 前运行它；健康的网关会被复用。只校验进程配置而不启动任何服务：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_model_services.ps1 -ValidateOnly
```

## 工具路由：先 Jev，再 LLM —— 绝不使用关键词

`jev_router.json` 将 Laya 与 Sematic（网关模型标识为 `semantic`）接入工具选择；两者都是结构化决策模型，不是聊天模型。`MATFLOW_JEV_ROUTER_CONFIG` 可覆盖路径。此文件中不允许放 API key。

候选工具是所有输入端口能接受当前数据类型的 agent 可选工具 —— 这是类型过滤，没有关键词打分。最终选择由模型做出：

1. Jev：`router.enabled` 为 true 且候选不少于两个时使用。`router.strategy` 为 `consensus`（Laya 与 Sematic 必须一致）或 `laya` / `semantic`（单一配置档）。
2. 配置的 LLM：Jev 不可达时（`router.fallback: "llm"`，默认），或 Jev 意见分歧、低于 `minimum_calibrated_confidence` 时（由 LLM 裁决，且仍需人工确认）。
3. 人工：`router.fallback` 为 `"none"`，或没有任何可用模型时。

`fallback_to_lexical` 会被拒绝：关键词匹配在所有路径上都已禁用。`minimum_calibrated_confidence` 只应用于 Laya 的校准置信度；Sematic 的分数只是已提交候选之间的条件评分。

## 任务摘要日志

`observability.json` 配置用户可读的任务摘要 JSONL 日志。`jsonl_path` 相对于当前打开的存档目录（`data/saves/<存档>/audit/task_summaries.jsonl`），因此每个存档保留各自的历史。每条摘要保留原始 `user_prompt`，并记录输入上下文、候选工具、模型意见、最终选择、执行结果和错误处理。每个工具引用都带有面向用户的 `label` 和稳定的 `registered_id` / `version`。`data/saves/` 目录被 Git 忽略。

`/api/route` 在响应中加入 `summary`；之后的执行请求可携带同一 `task_id`，把结果合并进该摘要。`GET /api/task-summaries/{task_id}` 返回该任务最新的完整摘要。

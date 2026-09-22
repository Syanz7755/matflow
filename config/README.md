# 本地 Jev Router 配置

## 双模型启动

双击项目根目录的 `start_model_services.bat`，会按 `model_services.json` 启动两个模型网关：`litellm_gateway`（`online_api` 模式，读取 `litellm.yaml`）与 `jev_decision_gateway`（`local` 模式）。该启动器不显示或保存任何密钥；只检查 LiteLLM 所需环境变量的名称。

`start_matflow.bat` 会先运行该双模型启动器，再打开 MatFlow。已在运行的健康网关会被复用，不会重复占用端口。可用以下命令只校验进程配置而不启动模型：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_model_services.ps1 -ValidateOnly
```

`jev_router.json` 是 MatFlow 路由层的非机密运行配置。它将 Laya 与 Sematic（网关模型标识为 `semantic`）接入候选工具选择；两者是结构化决策模型，不用于聊天生成。

配置路径可用 `MATFLOW_JEV_ROUTER_CONFIG` 环境变量覆盖，便于不同机器或部署环境使用各自的 JSON 文件。配置中不允许放 API key；当前本地网关也不需要 API key。

`router.strategy` 支持：

- `consensus`：Laya 与 Sematic 都选择同一候选时自动采用；分歧时保留模型证据并请求人工确认。
- `laya` 或 `semantic`：只使用指定配置档。

如果网关不可用且 `fallback_to_lexical` 为 `true`，MatFlow 会降级到可审计的词法候选排序，并要求人工确认；不会无提示地伪造模型选择。

`minimum_calibrated_confidence` 只应用于 Laya 的校准置信度。即使两模型选中同一工具，低于这个门槛仍会转为人工确认；Sematic 的分数是声明候选之间的条件评分，不能当作校准置信度。

为检查当前网关，请访问 `/health` 和 `/v1/models`。端点、模型标识和超时均只从此配置读取，业务代码中不嵌入这些值。

## 任务摘要日志

`observability.json` 配置用户可读的任务摘要 JSONL 日志。每一条摘要始终保留原始 `user_prompt`，并依次记录输入上下文、候选工具、模型意见、最终选择、执行结果，以及错误与安全处理方式。

所有工具证据同时包含面向人的 `label` 和稳定的 `registered_id` / `version`；因此 UI 不需要从中文或英文说明中反推实际注册工具。默认文件写到 `data/audit/task_summaries.jsonl`，该目录已被 Git 忽略，避免研究任务内容或用户 prompt 被提交到远端。

路由接口 `/api/route` 在既有路由字段外增加 `summary`；后续执行请求可携带同一个 `task_id`，将执行结果合并进该任务摘要。`GET /api/task-summaries/{task_id}` 返回该任务最近的完整摘要。

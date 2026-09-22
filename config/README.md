# 本地 Jev Router 配置

`jev_router.json` 是 MatFlow 路由层的非机密运行配置。它将 Laya 与 Sematic（网关模型标识为 `semantic`）接入候选工具选择；两者是结构化决策模型，不用于聊天生成。

配置路径可用 `MATFLOW_JEV_ROUTER_CONFIG` 环境变量覆盖，便于不同机器或部署环境使用各自的 JSON 文件。配置中不允许放 API key；当前本地网关也不需要 API key。

`router.strategy` 支持：

- `consensus`：Laya 与 Sematic 都选择同一候选时自动采用；分歧时保留模型证据并请求人工确认。
- `laya` 或 `semantic`：只使用指定配置档。

如果网关不可用且 `fallback_to_lexical` 为 `true`，MatFlow 会降级到可审计的词法候选排序，并要求人工确认；不会无提示地伪造模型选择。

`minimum_calibrated_confidence` 只应用于 Laya 的校准置信度。即使两模型选中同一工具，低于这个门槛仍会转为人工确认；Sematic 的分数是声明候选之间的条件评分，不能当作校准置信度。

为检查当前网关，请访问 `/health` 和 `/v1/models`。端点、模型标识和超时均只从此配置读取，业务代码中不嵌入这些值。

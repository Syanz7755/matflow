# MatFlow v0.2 后端操作接口

当前阶段只验证后端逻辑；`frontend/` 保持 v0.1 兼容界面，不是本接口的验收对象。FastAPI 自动生成的 OpenAPI 文档位于运行中服务的 `/docs` 与 `/openapi.json`。

## 设计规则

- 所有注册工具以稳定的 `tool_id`（在摘要中为 `registered_id`）和 `version` 识别；`label` 仅用于显示。
- UI 或其他客户端只能发送意图和结构化命令，不能复制路由、校验或执行规则。
- 每次变更图都要携带 `base_version`；每次路由都传完整的 `TaskState`。
- 路由响应和执行响应的 `summary` 是用户可读的审计记录：它保留原始 `user_prompt`，并按输入、决策、结果、错误处理的顺序返回证据。

## 只读操作

| 操作 | 请求 | 返回重点 |
| --- | --- | --- |
| 读取工作状态 | `GET /api/state` | 图、兼容注册表视图、功能开关、运行时技能 |
| 读取能力清单 | `GET /api/capabilities` | 活跃注册工具、数据类型、功能开关、稳定操作地址 |
| 读取任务摘要 | `GET /api/task-summaries/{task_id}` | 最近一条完整 `TaskLogSummary` |

## 有状态操作

### 路由任务

`POST /api/route`

请求为 `TaskState`：`task_id`、完整 `user_message`、`graph_version`、可用输入类型和可选假设。响应保持 v0.1 的顶层 `RouterDecision` 字段，并额外提供 `summary`。

客户端应使用：

- `summary.decision.candidate_tools[*].registered_id` 展示候选；
- `summary.decision.selected_tools[*].registered_id` 展示最终选择；
- `summary.decision.model_opinions` 展示 Laya/Semantic 的结构化意见；
- `summary.error_and_handling` 决定是否请求人工确认。

### 修改图

`POST /api/patch`

请求为 `GraphPatch`。后端验证工具身份、端口类型和版本后才会应用；校验失败时不修改图。

### 执行节点

`POST /api/execute`

```json
{"node_id": "eis-qc-1", "task_id": "the-route-task-id"}
```

`task_id` 可选以兼容旧客户端；新客户端应始终传入它，使执行结果、失败原因或人工等待状态合并到同一任务摘要。响应包含 `execution` 和更新后的 `summary`。

## 当前后端验收

执行 `test_backend.bat`（或 `uv run --group dev python -m unittest discover -v`）。此入口只运行 Python 后端测试；不会启动或构建 WebUI。

当前可真正执行的材料学链路是 EIS 导入、列映射、基础质检与 Nyquist 绘图。XRD、UV-Vis、比重瓶和 TGA 目前仅有路由评估声明，不应由客户端标记为“执行完成”。

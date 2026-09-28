# MatFlow v0.3 HTTP 与 MCP 接口

文档导航：[文档中心](README.md) · [用户说明书](USER_MANUAL.md) · [MCP 接入指南](MCP_INTEGRATION_GUIDE.md) · [架构规则](ARCHITECTURE_AND_DEVELOPER_RULES.md)

MatFlow 将工作区规则集中在 `WorkspaceRuntime` 深模块中。HTTP 控制面和 MCP 是同一接口的两个 adapter，不分别实现路由、校验、持久化或执行规则。FastAPI 文档位于 `/docs`，MCP Streamable HTTP 入口位于 `/mcp`。

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
| 数据集列表 | `GET /api/uploads` | 已导入文件的稳定 upload ID、名称与大小 |
| 检查数据集 | `GET /api/uploads/{upload_id}` | 表格列、类型、行数与最多 8 行预览 |

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

## MCP 工具

所有工具统一返回 `{ok, data, error}`。只读工具是 `get_workspace_state`、`inspect_dataset`、`route_research_task`、`validate_graph_patch`、`get_task_summary`；写入或执行工具是 `import_dataset`、`apply_graph_patch`、`execute_workflow`、`submit_human_decision`。后者都带 MCP destructive/write 注解，客户端应在调用前征得用户确认。`import_dataset` 声明 `_meta["openai/fileParams"]`，接受 ChatGPT 标准文件对象；服务端只下载公网 HTTPS 地址、校验每次跳转并限制为 25 MB。

内置 `POST /api/chat` 默认返回 `410 Gone`。迁移期只有显式设置 `MATFLOW_ENABLE_LEGACY_CHAT=1` 才会恢复旧 agent loop；正常路径由 ChatGPT、DSH 或其他 MCP 客户端承担 agent 角色。

## 本机 DSH

```powershell
uv run matflow configure-dsh --profile matflow
uv run matflow diagnose --dsh
uv run matflow start-dsh
```

该命令创建独立 Web profile，不修改已有 `web` profile。DSH 使用原生 `@deepseek-ai/dsh-mcp-client` 连接 `/mcp`，本地 MatFlow integration 为写/执行工具触发一次性审批，并只允许从当前工作目录、DSH attachment storage 或显式白名单根目录导入不超过 25 MB 的普通文件。

## 当前后端验收

执行 `test_backend.bat`（或 `uv run --group dev python -m unittest discover -v`）。此入口只运行 Python 后端测试；不会启动或构建 WebUI。

当前可真正执行的材料学链路是 EIS 导入、列映射、基础质检与 Nyquist 绘图。XRD、UV-Vis、比重瓶和 TGA 目前仅有路由评估声明，不应由客户端标记为“执行完成”。

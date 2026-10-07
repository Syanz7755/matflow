# 部署与运维

MatFlow v1 面向本机可信环境，不提供账号、TLS 或多租户隔离。需要远程部署时，应在外部增加认证、TLS 与网络访问控制。

## 进程拓扑

- 后端：`127.0.0.1:8000`，持有工作区状态并提供 `/api/*`。
- WebUI：`127.0.0.1:5173`，由 `matflow start --ui webui` 按前端 manifest 启动。
- MCP bridge：`127.0.0.1:8001/mcp`，在 `matflow-frontend` 独立启动。
- LLM 网关：`127.0.0.1:4078` 上的 LiteLLM（`config/llm.json`），由 `start_llm.bat` 启动或复用；AI 规划与路由需要它。
- Jev 决策网关：`127.0.0.1:4079`，可选；不可达时由 LLM 进行工具路由。`start_model_services.bat` 会同时启动两个网关。

受管启动器先等待后端能力接口可用，再启动 WebUI并等待页面健康检查。WebUI 异常退出、启动失败或 Ctrl+C 会清理整组受管进程。额外可信来源可通过 `MATFLOW_CORS_ORIGINS` 追加。

## 数据布局

每个存档是一个文件夹 `data/saves/<name>/`，包含 `graph_state.json`、`settings.json`、`uploads/` 与 `audit/task_summaries.jsonl`。当前存档按优先级取 `MATFLOW_DATA_ROOT`（显式文件夹）、`data/saves/$MATFLOW_SAVE`、`data/saves/default`。复制整个文件夹即可备份或迁移工作区。API 密钥不会存入存档，而是从环境变量读取。

能力接口返回 `api_contract.name = matflow-http` 与 `api_contract.version = 1.0`。后端不需要 Node、npm 或 Python MCP 包即可独立运行。前端操作请在 `matflow-frontend` 仓库执行。

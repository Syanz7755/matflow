# 部署与运维

MatFlow v1 面向本机可信环境，不提供账号、TLS 或多租户隔离。需要远程部署时，应在外部增加认证、TLS 与网络访问控制。

## 进程拓扑

- 后端：`127.0.0.1:8000`，持有工作区状态并提供 `/api/*`。
- WebUI：`127.0.0.1:5173`，由 `matflow start --ui webui` 按前端 manifest 启动。
- MCP bridge：`127.0.0.1:8001/mcp`，在 `matflow-frontend` 独立启动。

受管启动器先等待后端能力接口可用，再启动 WebUI并等待页面健康检查。WebUI 异常退出、启动失败或 Ctrl+C 会清理整组受管进程。额外可信来源可通过 `MATFLOW_CORS_ORIGINS` 追加。

能力接口返回 `api_contract.name = matflow-http` 与 `api_contract.version = 1.0`。后端不需要 Node、npm 或 Python MCP 包即可独立运行。前端操作请在 `matflow-frontend` 仓库执行。

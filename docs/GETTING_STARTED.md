# MatFlow 入门

MatFlow v1 的 Python 仓库只负责工作区状态、校验、执行、审计和 HTTP API。WebUI、MCP bridge 与 DSH 集成位于同级 `matflow-frontend` 仓库。

## 安装与启动

```powershell
uv sync
uv run matflow start --ui none
```

后端默认监听 `http://127.0.0.1:8000`，能力接口为 `http://127.0.0.1:8000/api/capabilities`。

若同级目录存在 `../matflow-frontend`，可以启动受管 WebUI：

```powershell
uv run matflow start --ui webui
```

也可用 `--ui-path` 或 `MATFLOW_WEBUI_DIR` 指定前端仓库。未写 `--ui` 时，交互终端会显示选择菜单；非交互环境默认只启动后端。`uv run matflow serve` 是 `start --ui none` 的兼容别名。

## MCP 与 DSH

在 `matflow-frontend` 中运行：

```powershell
npm install
npm run mcp
npm run configure:dsh
```

MCP bridge 默认位于 `http://127.0.0.1:8001/mcp`，并通过 HTTP API 访问后端。后端自身不再提供 `/mcp`。

参见 [启动说明](STARTUP_SCRIPTS.md)、[HTTP API 契约](BACKEND_API_CONTRACT.md) 与 [架构规则](ARCHITECTURE_AND_DEVELOPER_RULES.md)。

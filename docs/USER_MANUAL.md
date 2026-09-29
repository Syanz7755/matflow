# MatFlow 用户手册

**适用版本：** 后端 1.x，HTTP 契约 `matflow-http 1.0`

MatFlow 后端是工作区数据、GraphPatch 校验、执行、审计与版本控制的唯一权威。WebUI 和 MCP bridge 是独立客户端，位于 `matflow-frontend`；它们不能直接读写后端 `data/`。

## 常用命令

```powershell
uv run matflow start
uv run matflow start --ui webui
uv run matflow start --ui none
```

可用 `--host`、`--port`、`--ui-port` 与 `--ui-path` 覆盖默认值。默认后端端口为 8000，WebUI 端口为 5173。

客户端提交 GraphPatch 时必须携带读取到的图版本。若另一客户端已经更新图，后端返回 HTTP 409 和 `graph_version_conflict`；客户端应重新读取状态、合并修改后再次提交。

MCP bridge 默认监听 `http://127.0.0.1:8001/mcp`。在 `matflow-frontend` 中使用 `npm run mcp` 启动，使用 `npm run configure:dsh` 生成 DSH 配置。

# 架构与开发规则

设计动机、完整模块图、运行流程和当前能力边界见[设计理念与实现架构](DESIGN_AND_ARCHITECTURE.md)；阶段完成度见[项目阶段完成度评估](PROJECT_STATUS.md)。领域术语以根目录 `CONTEXT.md` 为准。

## 权威边界

`matflow` 后端是状态、校验、路由、执行、审计和持久化的唯一权威。所有客户端只能通过版本化 HTTP API 操作工作区，不得直接导入后端 Python 对象、访问 `data/` 或编辑状态文件。

`matflow-frontend` 是独立 npm workspace，包含 WebUI、共享 API client、MCP bridge 和 DSH 集成。两仓可以独立发布补丁与次版本，通过 `matflow-http` 契约主版本保持兼容。

## 写入与客户端规则

- GraphPatch 验证使用 `POST /api/patch/validate`，不写状态；应用必须在服务器锁内完成校验和原子写入。
- 过期版本稳定返回 HTTP 409 与 `graph_version_conflict`。
- 上传、节点审核、人工决策、数据类型变更与执行均经后端接口。
- 客户端启动时读取 `/api/capabilities` 并拒绝不兼容的契约主版本。
- MCP bridge 负责远程文件 HTTPS、重定向、私网地址与 25 MB 限制，随后调用后端上传接口。
- 新 UI 必须在根目录提供 `matflow-ui.json`；启动命令是参数数组，不通过 shell 执行。

后端提交前运行 `uv run python -m unittest discover -v`；前端提交前运行 `npm test` 与 `npm run build`。跨仓变更还应运行 WebUI E2E 与 MCP smoke test。

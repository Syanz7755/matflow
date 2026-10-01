# MatFlow 信息源与验证快照

**日期：** 2026-10-02

## 仓库

- Backend：`D:\Projects\matflow`
  - branch：`architecture/v0.2-contract-first`
  - 核验开始时：比远端领先 4 个提交；存在既有未提交文档改动
  - HEAD：`a5f682d chore: checkpoint before separating platform and cases`
  - 交接文档提交后：比远端领先 5 个提交；既有未提交改动保持原样
- Frontend：`D:\Projects\matflow-frontend`
  - branch：`architecture/v0.2-contract-first`
  - 核验开始时工作区干净
  - HEAD：`712d341 feat: establish independent MatFlow frontend clients`

## 自动化验证

- Backend：`.\.venv\Scripts\python.exe -m unittest discover -v`
  - `Ran 100 tests`
  - `OK (skipped=4)`
- Frontend：`npm.cmd test`
  - API client 3、MCP bridge 4、WebUI unit 9，全部通过
- Frontend build：`npm.cmd run build`，成功
- Frontend E2E：设置 `MATFLOW_E2E_FRONTEND_PORT=5174` 后 `6 passed`

## 主要正式资料

- `README.md`
- `CONTEXT.md`
- `docs/PROJECT_STATUS.md`
- `docs/DESIGN_AND_ARCHITECTURE.md`
- `docs/ARCHITECTURE_AND_DEVELOPER_RULES.md`
- `docs/BACKEND_API_CONTRACT.md`
- `docs/_handoff/2026-10-01-capability-status/`
- `docs/_handoff/2026-10-01-platform-case-boundary/`
- 前端 `README.md`、`docs/MCP_INTEGRATION_GUIDE.md`、`apps/webui/DESIGN_BRIEF.md`

## 采用的历史决策线索

- contract-first、最小闭环和可观察性；
- dynamic Tool Registry + Jev-like decision router；
- Planner proposes、Validator decides、Runner executes；
- UI 与 AI App 为并列客户端，MCP 为薄适配器；
- 前后端分仓和 GPL 边界讨论；
- EBrick 后端测试暴露的 Platform/Domain/Case 混写问题。

聊天记录只用于解释设计演化；当前实现判断以代码和测试为准。

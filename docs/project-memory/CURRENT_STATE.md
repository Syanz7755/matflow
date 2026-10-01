# MatFlow 当前状态

**核验日期：** 2026-10-02
**结论：** 后端控制平面阶段性可用；通用材料学智能工作流仍处于 Alpha；不能宣称“任意材料学请求可自动生成可靠科学工作流”。

## 1. 当前物理边界

MatFlow 已拆成两个仓库：

| 仓库 | 当前职责 | 不应承担 |
| --- | --- | --- |
| `D:\Projects\matflow` | 权威状态、类型、Tool Registry、GraphPatch 校验、路由、执行、审核、审计、上传、HTTP API | WebUI、MCP 协议适配、客户端业务状态 |
| `D:\Projects\matflow-frontend` | React/Vite WebUI、共享 API client、MCP bridge、DSH 集成 | 直接修改后端文件、复制后端业务规则 |

两仓以 `matflow-http` v1 契约连接。后端不知道请求来自 WebUI、MCP、DSH 还是其他客户端。

## 2. 已实现并有自动化证据的能力

### 后端

- 单工作区 `GraphState` 的读取、原子写入与版本冲突检测；
- 类型注册、继承、端口兼容、DAG、环路与单输入占用校验；
- 结构化 `GraphPatch`，包括原子 `replace_node_revision`；
- 版本化 `ToolSpec`、Tool Registry、候选检索与 Jev 决策适配；
- Node revision proposal、端口迁移建议、生成代码审核状态；
- Node 级 `review_policy.after_run`、安全 Preview 与继续/停止控制；
- 工作流调度、ExecutionResult、Task 摘要、trace 与审计记录；
- 上传、设置、模型 Provider、运行时 Skill 和节点库接口；
- 声明式 Tool Recipe 草稿、隐藏夹具评估和有限修复；
- Prompt normalizer 独立工具：保留原文、同语言门禁、严格 schema；
- 版本化 HTTP API 与 `/api/capabilities`；后端 `/mcp` 已移除。

### 客户端与适配

- 可编辑的 typed workflow canvas、完整端口、Bezier 连线和 Inspector；
- 导入、导出、保存、运行、路由任务与审计记录查看；
- 桌面三栏与窄屏抽屉布局，包含键盘焦点和 axe 基线；
- API client 的契约主版本检查；
- MCP Streamable HTTP bridge，只经后端 HTTP 工作；
- DSH 审批与受控本地文件导入。

## 3. 2026-10-02 验证快照

| 范围 | 结果 |
| --- | --- |
| 后端离线 unittest | `100 passed, 4 skipped`；跳过项均需显式启用在线 Jev/LLM |
| 前端/API/MCP 单元测试 | `16 passed`（3 API client + 4 MCP bridge + 9 WebUI） |
| 前端生产构建 | 成功；仅有依赖包 `use client` bundler warning |
| WebUI E2E | `6 passed`，使用 `MATFLOW_E2E_FRONTEND_PORT=5174` |

E2E 默认端口 5173 当时已被其他进程占用；改用 5174 后全部通过。这是本机运行条件，不是已确认的产品缺陷。

## 4. 已决定但尚未实现完成

| 目标 | 当前真实状态 |
| --- | --- |
| Domain Package | 概念、术语和迁移方案已明确；尚无完整 manifest/loader/executor registry，EIS/XRD/FTIR 仍进入 Core |
| 通用 join / quality report / conditional gate | 设计需要明确；当前没有完整数据驱动门控语义 |
| 任意复杂中文请求生成多分支 DAG | 尚不可靠；中文词法召回和规划器能力不足 |
| 完整 Tool 生命周期 | 草稿、评估和有限修复已存在；通用审核、发布、隔离代码执行仍不完整 |
| EBrick 温变 EIS 案例 | 有数据与评估设计；未形成端到端可执行验收闭环 |
| 多项目/多用户 | 未实现；当前是单用户、单工作区、本地文件持久化 |
| 公网安全部署 | 未实现；默认 loopback，无完整认证授权体系 |

## 5. 已废弃或被替代的设计

- **后端内置 MCP endpoint：** 已移除；MCP bridge 在 `matflow-frontend`。
- **独立 Human Decision Tool：** 已标记 deprecated；改为任意 Node 的运行后审核策略。
- **前后端同仓：** 已由两个独立仓库替代。
- **AI 直接改 Graph JSON：** 不允许；所有写入必须经 `GraphPatch`、版本和确定性校验。
- **Normalize 覆盖原始 prompt：** 否决；Normalized Request 只能是可回退的派生视图。
- **`Project / GraphVersion / Run / EventLog` 作为已实现存储模型：** 这是中期设计词汇，当前代码实际使用 `Workspace / GraphState / Task / ExecutionResult / TaskLogSummary`。未来若建设多项目存储，应另立迁移决策，不得在文档里把概念图写成现状。
- **Scientific Graph 与 Workflow Graph 双图作为 MatFlow 当前存储模型：** 未在当前代码中落地；现行权威对象是单工作区 typed Workflow。不要与 `synsimul2` 的三图架构混用。

## 6. 当前 Git 状态风险

核验开始时：

- 后端分支 `architecture/v0.2-contract-first`，比远端领先 4 个提交；存在大量未提交文档修改和一个未跟踪交接目录；
- 前端同名分支工作区干净；
- 本次文档工作只新增项目记忆和交接文件，不覆盖上述既有改动。

交接文档提交完成后，后端分支比远端领先 5 个提交；上述既有未提交改动和未跟踪目录仍原样保留，未进入交接提交。

接手者应先执行 `git status --short --branch`，不要假定工作区干净，也不要把历史文档改动与新功能提交混在一起。

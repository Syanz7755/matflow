# MatFlow 文档中心

matflow是一个为材料学领域研究人员设计的vibe research工具框架：研究人员可以通过输入提示词，来不断构建、完善一个图式工作流（graph-like workflow）。本项目遵循如下设计理念：

- 严格的数据流合规性检查
- LLM联网仅用于构造工具；raw data跑工作流基于jev-like models，默认全程本地
- 提供版本化 HTTP 接口；MCP、ChatGPT 与 Deepseek Harness (DSH) 适配位于独立的 `matflow-frontend` 仓库

## 从哪里开始

| 目标 | 文档 |
| --- | --- |
| 安装、启动、连接 AI 并完成首次操作 | [快速使用指南](GETTING_STARTED.md) |
| Choose and operate a CLI, PowerShell, or Windows launcher | [Startup scripts guide](STARTUP_SCRIPTS.md) |
| 了解功能、完成分析并解释结果 | [用户说明书](USER_MANUAL.md) |
| 连接本机 DSH、ChatGPT 或其他 MCP 客户端 | 参见同级 `matflow-frontend/docs/MCP_INTEGRATION_GUIDE.md` |
| 日常启动、诊断、备份和排障 | [部署与运维指南](DEPLOYMENT_AND_OPERATIONS.md) |
| 了解 HTTP 字段和客户端调用约定 | [后端接口契约](BACKEND_API_CONTRACT.md) |
| 开发安全的节点阶段性预览 | [Node preview specification](NODE_PREVIEW_SPEC.md) |
| 查看当前完成度、里程碑和下一阶段 | [项目阶段完成度评估](PROJECT_STATUS.md) |
| 理解设计理念、模块和运行流程 | [设计理念与实现架构](DESIGN_AND_ARCHITECTURE.md) |
| 理解模块边界并继续开发 | [架构与开发规则](ARCHITECTURE_AND_DEVELOPER_RULES.md) |
| 在命令行离线查看后端流程（随仓只读工具 FlowView） | [FlowView 使用指南](../flowview/README.md)、[FlowView 内部契约](../flowview/CONTRACT.md) |
| 运行配置驱动的场景与提示词测试套件 | [配置化场景测试](CONFIGURED_SCENARIO_TESTS.md)、[示例与流程打印产物](../examples/README.md) |
| 理解 Domain Package 边界、执行器与通用控制语义 | [Domain Package 说明](DOMAIN_PACKAGES.md) |
| 接手维护：当前状态、未决问题与下一步 | [项目记忆](project-memory/README.md)（历史交接快照只保留在本地，不随仓库分发） |

## 推荐阅读路径

### 普通使用者

1. 按[快速使用指南](GETTING_STARTED.md)完成安装和接入。
2. 阅读[用户说明书](USER_MANUAL.md)，了解功能范围和完整分析流程。
3. 如需配置其他客户端，再查阅 `matflow-frontend` 仓库中的 MCP 集成指南。

### 管理和维护人员

1. 阅读[部署与运维指南](DEPLOYMENT_AND_OPERATIONS.md)。
2. 运行环境诊断并确认本地端口、数据目录和备份策略。
3. 升级前检查接口契约和兼容性说明。

### 开发者

1. 先读[设计理念与实现架构](DESIGN_AND_ARCHITECTURE.md)和根目录 `CONTEXT.md`。
2. 再读[架构与开发规则](ARCHITECTURE_AND_DEVELOPER_RULES.md)与[后端接口契约](BACKEND_API_CONTRACT.md)。
3. 修改公共行为时同时更新实现、测试和对应文档。

## 当前能力边界

- **平台核心：** 已可执行 Dataset 导入、类型化 GraphPatch 校验、DAG 调度、人工审核、预览和审计。
- **当前内置 Demo 能力：** 表格列映射、EIS 基础质检和 Nyquist 数据生成。这些是历史演示能力，不代表通用平台必须内置 EIS。
- **参考领域与案例：** 仓库包含 XRD、FTIR、UV-Vis、比重瓶、TGA 和 EBrick 等测试或示例；它们用于验证平台机制，不定义 Platform Core。
- WebUI 与 MCP bridge 通过 HTTP 共用同一个后端工作区；不支持多用户权限隔离。
- 默认只监听本机 `127.0.0.1:8000`，未内置公网认证。
- 后端提供 `/api/chat` 作为受轮次限制的 AI 辅助接口；复杂中文规划和领域工具生成仍属于 Alpha，MCP bridge 是另一种客户端接入方式。

## 文档维护约定

- `GETTING_STARTED.md` 集中承载安装、首次启动、AI 接入和基本排障入口。
- `STARTUP_SCRIPTS.md` is the authoritative reference for launchers, helper scripts, ports, shutdown behavior, and model-service prerequisites.
- `USER_MANUAL.md` 面向使用者，描述稳定操作，不承载内部实现细节。
- MCP 与 DSH 文档由 `matflow-frontend` 仓库维护。
- `DEPLOYMENT_AND_OPERATIONS.md` 面向本机部署与维护。
- `BACKEND_API_CONTRACT.md` 是传输层的接口参考。
- `PROJECT_STATUS.md` 记录阶段性完成度、验证证据和下一里程碑。
- `DESIGN_AND_ARCHITECTURE.md` 记录设计理念、实现架构与能力边界。
- `ARCHITECTURE_AND_DEVELOPER_RULES.md` 是实现边界和变更规则。
- `../flowview/README.md` 是随仓 CLI 工具 FlowView 的使用指南：它只读地打印后端流程（Mermaid 图、终端表格、JSON），入口为 `.\.venv\Scripts\python.exe -m flowview graph|flow|summary|doctor`（`run-flow` 是 `flow` 的别名），按设计不进入 wheel；`../flowview/CONTRACT.md` 是它的冻结内部契约。
- 历史交接快照（任意 `_handoff/` 目录）是本地工作笔记，已在 `.gitignore` 中排除（`**/_handoff/`），只保留在开发机上、不随仓库分发；长期状态以 `project-memory/` 为准。

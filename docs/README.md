# MatFlow 文档中心

matflow是一个为材料学领域研究人员设计的vibe research工具框架：研究人员可以通过输入提示词，来不断构建、完善一个图式工作流（graph-like workflow）。本项目遵循如下设计理念：

- 严格的数据流合规性检查
- LLM联网仅用于构造工具；raw data跑工作流基于jev-like models，默认全程本地
- 提供MCP接口，可接入ChatGPT、Deepseek Harness (DSH)等客户端

## 从哪里开始

| 目标 | 文档 |
| --- | --- |
| 安装、启动、连接 AI 并完成首次操作 | [快速使用指南](GETTING_STARTED.md) |
| Choose and operate a CLI, PowerShell, or Windows launcher | [Startup scripts guide](STARTUP_SCRIPTS.md) |
| 了解功能、完成分析并解释结果 | [用户说明书](USER_MANUAL.md) |
| 连接本机 DSH、ChatGPT 或其他 MCP 客户端 | [MCP 与 AI 客户端接入指南](MCP_INTEGRATION_GUIDE.md) |
| 日常启动、诊断、备份和排障 | [部署与运维指南](DEPLOYMENT_AND_OPERATIONS.md) |
| 了解 HTTP/MCP 的字段和调用约定 | [后端接口契约](BACKEND_API_CONTRACT.md) |
| 开发安全的节点阶段性预览 | [Node preview specification](NODE_PREVIEW_SPEC.md) |
| 理解模块边界并继续开发 | [架构与开发规则](ARCHITECTURE_AND_DEVELOPER_RULES.md) |
| 查看后续前端演进设想 | [前端开发计划](FRONTEND_DEVELOPMENT_PLAN.md) |

## 推荐阅读路径

### 普通使用者

1. 按[快速使用指南](GETTING_STARTED.md)完成安装和接入。
2. 阅读[用户说明书](USER_MANUAL.md)，了解功能范围和完整分析流程。
3. 如需配置其他客户端，再查阅[MCP 与 AI 客户端接入指南](MCP_INTEGRATION_GUIDE.md)。

### 管理和维护人员

1. 阅读[部署与运维指南](DEPLOYMENT_AND_OPERATIONS.md)。
2. 运行环境诊断并确认本地端口、数据目录和备份策略。
3. 升级前检查接口契约和兼容性说明。

### 开发者

1. 先读[架构与开发规则](ARCHITECTURE_AND_DEVELOPER_RULES.md)。
2. 再读[后端接口契约](BACKEND_API_CONTRACT.md)。
3. 修改公共行为时同时更新实现、测试和对应文档。

## 当前能力边界

- 已可执行：表格数据导入、列映射、EIS 基础质检和 Nyquist 数据生成。
- 仓库包含 XRD、UV-Vis、比重瓶和 TGA 等任务示例，但它们不是当前内置的完整执行链路。
- MCP 和 HTTP 共用同一个工作区；不支持多用户权限隔离。
- 默认只监听本机 `127.0.0.1:8000`，未内置公网认证。
- 内置聊天接口已停用；AI 应通过 MCP 接入。

## 文档维护约定

- `GETTING_STARTED.md` 集中承载安装、首次启动、AI 接入和基本排障入口。
- `STARTUP_SCRIPTS.md` is the authoritative reference for launchers, helper scripts, ports, shutdown behavior, and model-service prerequisites.
- `USER_MANUAL.md` 面向使用者，描述稳定操作，不承载内部实现细节。
- `MCP_INTEGRATION_GUIDE.md` 面向 AI 客户端接入者，记录权限和工具调用约定。
- `DEPLOYMENT_AND_OPERATIONS.md` 面向本机部署与维护。
- `BACKEND_API_CONTRACT.md` 是传输层的接口参考。
- `ARCHITECTURE_AND_DEVELOPER_RULES.md` 是实现边界和变更规则。
- `FRONTEND_DEVELOPMENT_PLAN.md` 是规划文档，不代表已交付能力。

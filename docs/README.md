# MatFlow 文档中心

MatFlow 是一个本地优先、可审计的材料研究工作流工作区。工作区状态、数据、工具注册表和执行规则由 MatFlow 服务端统一管理；ChatGPT、DeepSeek Harness（DSH）或其他 MCP 客户端负责理解用户意图并调用工具。

## 从哪里开始

| 你的目标 | 阅读文档 |
| --- | --- |
| 安装、启动并完成第一次分析 | [用户说明书](USER_MANUAL.md) |
| 连接本机 DSH、ChatGPT 或其他 MCP 客户端 | [MCP 与 AI 客户端接入指南](MCP_INTEGRATION_GUIDE.md) |
| 日常启动、诊断、备份和排障 | [部署与运维指南](DEPLOYMENT_AND_OPERATIONS.md) |
| 了解 HTTP/MCP 的字段和调用约定 | [后端接口契约](BACKEND_API_CONTRACT.md) |
| 理解模块边界并继续开发 | [架构与开发规则](ARCHITECTURE_AND_DEVELOPER_RULES.md) |
| 查看后续前端演进设想 | [前端开发计划](FRONTEND_DEVELOPMENT_PLAN.md) |

## 推荐阅读路径

### 普通使用者

1. 阅读[用户说明书](USER_MANUAL.md)的“快速开始”。
2. 使用 WebUI 导入并检查数据。
3. 如果要让 AI 代为编排工作流，按[MCP 与 AI 客户端接入指南](MCP_INTEGRATION_GUIDE.md)连接 DSH 或 ChatGPT。

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
- 可路由但尚未实现完整执行器：XRD、UV-Vis、比重瓶和 TGA 等能力。
- MCP 和 HTTP 共用同一个工作区；不支持多用户权限隔离。
- 默认只监听本机 `127.0.0.1:8000`，未内置公网认证。
- 内置聊天接口已停用；AI 应通过 MCP 接入。

## 文档维护约定

- `USER_MANUAL.md` 面向使用者，描述稳定操作，不承载内部实现细节。
- `MCP_INTEGRATION_GUIDE.md` 面向 AI 客户端接入者，记录权限和工具调用约定。
- `DEPLOYMENT_AND_OPERATIONS.md` 面向本机部署与维护。
- `BACKEND_API_CONTRACT.md` 是传输层的接口参考。
- `ARCHITECTURE_AND_DEVELOPER_RULES.md` 是实现边界和变更规则。
- `FRONTEND_DEVELOPMENT_PLAN.md` 是规划文档，不代表已交付能力。


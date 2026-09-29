# MatFlow 快速使用指南

本文集中说明 MatFlow 的安装、启动、AI 客户端接入和基本故障处理。完成首次配置后，可根据需要继续阅读用户、接入、运维或开发文档。

## 1. 使用前准备

MatFlow 当前优先支持 Windows，本指南使用 PowerShell。项目默认位于：

```text
D:\Projects\matflow
```

运行 WebUI 需要：

- Python 3.11、3.12 或 3.13；
- [uv](https://docs.astral.sh/uv/)；
- Node.js 和 npm（WebUI 与本机 DSH 接入需要）。

通过本机 DeepSeek Harness（DSH）使用 AI 工作流时，还需要安装 DSH。仅使用 HTTP 或 MCP 接口时，不需要安装前端依赖。

## 2. 选择使用方式

| 目标 | 建议入口 |
| --- | --- |
| 查看工作区、导入并检查数据、提交研究问题 | WebUI |
| 在本机通过自然语言规划和执行完整工作流 | DeepSeek Harness（DSH） |
| 在已有 AI 客户端中调用 MatFlow | ChatGPT 或其他 MCP 客户端 |
| 开发或测试外部程序 | HTTP API 或 MCP |

这些入口共享同一个 MatFlow 工作区。在 WebUI 中导入的数据可以由 MCP 客户端读取，MCP 客户端写入的工作流也会反映在 WebUI 中。

## 3. 启动 WebUI

打开 PowerShell，直接执行以下命令：

```powershell
Set-Location D:\Projects\matflow
uv sync
uv run matflow install-frontend
uv run matflow diagnose
uv run matflow start
```

浏览器访问终端显示的地址，通常为 `http://localhost:5173`。PowerShell 窗口需要在使用期间保持运行；停止 MatFlow 时，在该窗口按 `Ctrl+C`。

WebUI 适合查看工作区和工作流图、导入并检查数据、提交研究问题，以及阅读路由记录。当前完整的工作流变更和执行应通过 DSH、ChatGPT 或其他 MCP 客户端完成。

## 4. 连接 AI 客户端

### 4.1 本机 DSH

已安装 DSH 时，在 PowerShell 中执行：

```powershell
Set-Location D:\Projects\matflow
uv sync
uv run matflow configure-dsh --profile matflow
uv run matflow diagnose --dsh --profile matflow
uv run matflow start-dsh --profile matflow
```

这些命令会创建独立的 `matflow` profile，并启动 MatFlow 和 DSH。配置过程不需要手工编辑 MCP 配置文件，也不会修改已有的默认 `web` profile。

DSH 打开后，可发送以下请求验证连接：

> 请确认当前已经连接 MatFlow。读取工作区，并仅返回工作流版本、已注册工具数量和当前节点数量。不要导入文件、修改工作流或执行分析。

能够返回上述信息，即表示接入完成。

如使用能够操作本机命令行的编码 AI，可直接提交以下配置请求：

> 请为本机项目 `D:\Projects\matflow` 配置 MatFlow 的 DSH 接入。请依次完成环境检查、依赖同步、`matflow` profile 配置和 DSH 诊断；不要要求我手工编辑配置文件，不要修改项目源码，也不要将 8000 端口开放到公网。完成后，请给出后续启动所需的一条命令；如缺少 uv、Node.js 或 DSH，请说明缺少的组件及必要的安装操作。

### 4.2 ChatGPT 或其他 MCP 客户端

本机 MCP 地址为 `http://127.0.0.1:8000/mcp`，传输类型为 `streamable-http`。其他本机 MCP 客户端可以使用该地址连接。

ChatGPT 无法直接访问本机回环地址。接入时需要使用受控的 Secure MCP Tunnel 或等价私网连接，不应将本机 8000 端口直接开放到公网。具体配置和权限要求见 [MCP 与 AI 客户端接入指南](MCP_INTEGRATION_GUIDE.md#6-chatgpt-接入)。连接完成后，可使用 4.1 节中的验证请求检查工作区读取能力。

## 5. 开始一次分析

MatFlow 的基本使用顺序是：

1. 导入并检查数据；
2. 说明需要解决的问题和期望结果；
3. 审查 AI 客户端提出的工作流；
4. 确认写入工作流；
5. 确认执行；
6. 根据原始问题核验结果。

项目提供示例文件 `examples/data/01_eis_basic_qc/eis_spectrum.csv`。完整示例见[用户说明书的第五章](USER_MANUAL.md#5-示例完成第一次数据分析)。

当前完整实现的分析链路包括表格导入、列整理、EIS 基础质量检查和 Nyquist 结果生成。仓库中的其他材料分析示例不代表已经具备相应的完整执行器。

## 6. 后续启动

各入口启动的进程并不相同。根目录的 `start_matflow.bat` 会额外启动 LiteLLM 和 Jev，而 `uv run matflow start` 与 `scripts/start.ps1` 只启动 MatFlow 后端和 WebUI。完整差异、端口、停止方式及所有辅助脚本参数见 [Startup Scripts Guide](STARTUP_SCRIPTS.md)。

启动 WebUI：

```powershell
Set-Location D:\Projects\matflow
uv run matflow start
```

启动 MatFlow 和 DSH：

```powershell
Set-Location D:\Projects\matflow
uv run matflow start-dsh --profile matflow
```

仅启动 HTTP 和 MCP 服务：

```powershell
Set-Location D:\Projects\matflow
uv run matflow serve
```

对应地址为：

- MCP：`http://127.0.0.1:8000/mcp`
- HTTP API：`http://127.0.0.1:8000/api`
- HTTP 交互文档：`http://127.0.0.1:8000/docs`

## 7. 基本故障处理

启动失败时，先运行：

```powershell
Set-Location D:\Projects\matflow
uv run matflow diagnose
```

DSH 无法连接时，运行：

```powershell
Set-Location D:\Projects\matflow
uv run matflow diagnose --dsh --profile matflow
```

诊断仍未通过时，应保留完整输出，并提交给维护人员或编码 AI 检查。不要在未确认原因时反复修改配置或开放本机 8000 端口。

常见问题的进一步处理方式见[用户说明书](USER_MANUAL.md#9-常见问题)、[MCP 接入故障](MCP_INTEGRATION_GUIDE.md#9-常见接入故障)和[运维故障排查](DEPLOYMENT_AND_OPERATIONS.md#10-故障排查)。

## 8. 后续文档

| 目标 | 文档 |
| --- | --- |
| 了解功能、完成分析并解释结果 | [用户说明书](USER_MANUAL.md) |
| 配置 ChatGPT、DSH 或其他 MCP 客户端 | [MCP 与 AI 客户端接入指南](MCP_INTEGRATION_GUIDE.md) |
| 进行备份、长期运行和故障处理 | [部署与运维指南](DEPLOYMENT_AND_OPERATIONS.md) |
| 选择和使用启动脚本 | [Startup Scripts Guide](STARTUP_SCRIPTS.md) |
| 使用 HTTP/MCP 接口开发客户端 | [后端接口契约](BACKEND_API_CONTRACT.md) |
| 修改后端或工作流实现 | [架构与开发规则](ARCHITECTURE_AND_DEVELOPER_RULES.md) |
| 继续开发 WebUI | [前端开发计划](FRONTEND_DEVELOPMENT_PLAN.md) |

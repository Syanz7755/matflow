# MatFlow 用户说明书

**适用版本：** 当前本地版（HTTP/MCP 接口 v0.3）

**适用系统：** Windows 优先，Python 3.11–3.13

**使用模式：** 单机、单工作区、外部 AI 客户端

## 1. MatFlow 能做什么

MatFlow 把材料数据分析表示为一个有类型、有版本、可检查的工作流图。它负责保存数据和图状态、选择兼容工具、校验图变更、执行已注册节点，并留下可追踪的决策记录。

MatFlow 本身不是聊天机器人。你可以通过三种方式使用它：

- **WebUI：** 查看工作区、导入数据、检查数据和发起研究任务路由。
- **本机 DSH：** 用自然语言让本地 DeepSeek Harness 检查数据、规划和执行工作流。
- **ChatGPT 或其他 MCP 客户端：** 通过 `/mcp` 使用相同的 MatFlow 工具。

所有入口共享同一个工作区，因此在 WebUI 中上传的数据会被 MCP 客户端看到，MCP 应用的图变更也会反映到 WebUI。

## 2. 安装准备

需要预先安装：

- Python 3.11、3.12 或 3.13；
- [uv](https://docs.astral.sh/uv/)；
- Node.js 和 npm（仅 WebUI 需要）；
- DeepSeek Harness（仅本机 DSH 接入需要）。

在项目目录 `D:\Projects\matflow` 打开 PowerShell，执行：

```powershell
uv sync
uv run matflow install-frontend
uv run matflow diagnose
```

诊断结果中 Python 包、Node.js、npm 和前端依赖均应可用。如果只使用 MCP 服务，不需要安装前端依赖。

## 3. 快速开始

### 3.1 使用 WebUI

```powershell
uv run matflow start
```

命令会启动后端和前端开发服务器。浏览器打开终端显示的 Vite 地址，通常为 `http://localhost:5173`。

主界面分为两部分：

- 左侧证据栏显示当前 GraphState、已注册工具和数据集；
- 主区域用于填写研究问题并查看服务端生成的路由决策。

按 `Ctrl+C` 停止服务。

### 3.2 使用本机 DSH

首次使用先配置独立 profile：

```powershell
uv run matflow configure-dsh --profile matflow
uv run matflow diagnose --dsh --profile matflow
```

以后直接启动：

```powershell
uv run matflow start-dsh --profile matflow
```

该命令会同时启动 MatFlow MCP 服务和 DSH Web 界面。详细说明见 [MCP 与 AI 客户端接入指南](MCP_INTEGRATION_GUIDE.md)。

### 3.3 只启动接口服务

```powershell
uv run matflow serve
```

可用地址：

- MCP：`http://127.0.0.1:8000/mcp`
- HTTP API：`http://127.0.0.1:8000/api`
- FastAPI 交互文档：`http://127.0.0.1:8000/docs`

## 4. 完成一次数据分析

### 第一步：导入数据

在 WebUI 左侧的 **Datasets** 区域点击 **Import dataset**，选择文件。当前支持：

| 类型 | 扩展名 | 检查方式 |
| --- | --- | --- |
| 表格 | `.csv`、`.txt`、`.xlsx`、`.xls`、`.json` | 返回行数、列名、数据类型和最多 8 行预览 |
| 图像 | `.png`、`.jpg`、`.jpeg`、`.tif`、`.tiff` | 作为二进制数据登记，当前不做图像内容解析 |

单文件上限为 **25 MB**。导入成功后，文件会保存到本机 `data/uploads/`，并获得稳定的 `upload_id`。文件名相同的两次导入会产生两个不同记录。

### 第二步：检查数据

点击数据集名称查看服务器确认的文件信息。使用 AI 客户端时，应让它先调用 `inspect_dataset`，确认列名和数据质量，再规划工作流。

对于 EIS 表格，至少应能识别：

- 频率列；
- 阻抗实部列；
- 阻抗虚部列。

如果列含义不明确，不要让 AI 猜测，应明确告诉它列映射或先修改数据表头。

### 第三步：描述研究任务

在 **Research question** 中写清目标和已有数据，例如：

> 检查刚导入的 EIS 数据，把 Frequency_Hz 作为频率、Zreal_Ohm 作为实部、Zimag_Ohm 作为虚部，完成基础质检并生成 Nyquist 数据。

点击 **Get routing decision** 后，MatFlow 只会生成候选工具、选择理由和确认要求；它**不会自动修改图，也不会自动执行**。

### 第四步：确认工作流变更

通过 MCP 客户端操作时，AI 通常会：

1. 读取工作区和数据集；
2. 路由研究任务；
3. 生成 GraphPatch；
4. 调用 `validate_graph_patch`；
5. 请求你确认；
6. 调用 `apply_graph_patch`。

每个 GraphPatch 都携带 `base_version`。如果其他操作已经更新了图，旧补丁会被拒绝，AI 应重新读取状态后生成新补丁。

### 第五步：确认执行

`execute_workflow` 会按图执行尚未完成的节点，直到：

- 所有节点完成；
- 某个节点失败；
- 遇到等待人工选择的 `human_decision` 节点。

执行属于有状态操作，DSH 会显示一次性确认。检查拟执行的节点和数据集无误后再批准。

## 5. 如何理解界面与结果

### Graph state

工作流图是服务器的事实来源。每个节点常见状态为：

- `ready`：等待执行；
- `running`：正在执行；
- `completed`：已完成并保存输出；
- `waiting`：等待人工决定；
- `error`：执行失败。

图版本会在每次成功应用补丁后递增。路由本身不会增加版本。

### Decision record

路由结果包含候选工具、最终选择、置信度、选择理由，以及是否需要人工确认。它是一次决策记录，不等于工作流已经创建或执行。

### Task summary

任务摘要串联原始问题、路由判断、执行结果和错误处理信息。排查问题时应保留 `task_id` 和 `trace_id`。

### Nyquist 输出

当前绘图节点生成用于绘制 Nyquist 图的点集，而不是单独的图片文件。横轴为阻抗实部，纵轴按 Nyquist 习惯使用阻抗虚部的负值；当前最多保留前 500 个有效点。

## 6. 安全与确认规则

MatFlow 按操作影响分两类：

| 类型 | 操作 | 默认行为 |
| --- | --- | --- |
| 只读 | 读取状态、检查数据、路由、校验补丁、读取摘要 | 可直接执行 |
| 写入/执行 | 导入数据、应用补丁、执行工作流、提交人工决定 | 应先取得用户确认 |

注意：

- MatFlow 默认只监听本机地址，没有用户账号和权限隔离。
- 不要把端口 8000 直接暴露到公网。
- 上传内容、模型输出和客户端请求都应视为不可信输入。
- DSH 本地文件桥接只允许当前工作区、DSH 附件目录或显式配置的白名单目录，并拒绝符号链接和路径逃逸。
- ChatGPT 文件导入只接受公网 HTTPS 临时下载地址，并拒绝本机、内网地址和超限文件。

## 7. 当前限制

- 当前是单用户、单工作区设计，并发写入仅在单个服务进程内加锁。
- 不要同时启动多个 MatFlow 服务进程写同一 `data/` 目录。
- 只有 EIS 基础链路具备完整执行器；“能路由到”不表示“能执行完成”。
- WebUI 当前侧重查看和路由，完整的图编排与执行更适合通过 MCP 客户端完成。
- 内置 `/api/chat` 默认返回 `410 Gone`；它只为迁移保留，不是推荐入口。

## 8. 常见问题

### 端口 8000 被占用

先关闭已有 MatFlow 或其他占用该端口的进程。当前命令行入口固定使用 8000；如需临时改端口，可直接运行 Uvicorn，但 DSH profile 中的地址也要同步修改。

### 导入后显示 `binary` 或 `unreadable`

`binary` 表示该扩展名不是当前表格解析器支持的格式；`unreadable` 表示文件虽像表格，但解析失败。优先导出为结构清晰、带表头的 UTF-8 CSV 再导入。

### AI 找不到刚导入的文件

让 AI 重新调用 `get_workspace_state` 或在 WebUI 刷新；然后把界面显示的文件名或 `upload_id` 告诉它。不要把本机绝对路径当成 MCP 的数据集 ID。

### 图补丁提示版本冲突

说明图在补丁生成后已变化。重新读取工作区状态，并以最新 `state.version` 生成和校验补丁。

### 执行停在 `waiting`

检查等待节点提供的选项，确认后通过 `submit_human_decision` 提交其中一个准确值，再次执行工作流。

更多启动和恢复方法见[部署与运维指南](DEPLOYMENT_AND_OPERATIONS.md)。

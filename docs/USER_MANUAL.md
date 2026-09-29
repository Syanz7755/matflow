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

如需使用根目录的 Windows 批处理启动器，请先阅读 [Startup Scripts Guide](STARTUP_SCRIPTS.md)。`start_matflow.bat` 还会启动配置中的 LiteLLM 与 Jev 服务，与本节命令的启动范围不同。

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

## 4. 功能总览

本章概述 MatFlow 的主要功能及其在分析流程中的作用。

### 数据导入与检查

MatFlow 可以保存本地数据集，并为每次导入生成独立记录。对于表格文件，它会读取行数、列名、数据类型和少量预览；对于当前尚不能解析的图像文件，它只登记文件，不推测图像内容。

支持的表格格式为 `.csv`、`.txt`、`.xlsx`、`.xls` 和 `.json`，支持登记的图像格式为 `.png`、`.jpg`、`.jpeg`、`.tif` 和 `.tiff`。单个文件不能超过 **25 MB**。

### 研究任务路由

用户可以用自然语言说明要解决的问题。MatFlow 会结合当前可用数据和已注册工具，给出候选工具、选择理由、置信度以及是否需要人工确认。路由只是在回答“接下来适合用什么”，不会自行更改工作流，也不会开始计算。

### 工作流组织与校验

一次分析会被表示为由多个节点连接而成的工作流。节点分别承担数据导入、整理、分析、输出或人工判断等职责，连接关系说明数据如何在步骤之间传递。

在修改工作流前，MatFlow 会检查节点是否存在、输入输出是否兼容，以及修改所依据的图版本是否仍然有效。校验通过不等于修改已经生效；真正写入工作区前仍需用户确认。

### 工作流执行与人工停点

工作流写入后，MatFlow 可以按连接顺序执行尚未完成的节点。执行会在三种情况下停下：全部完成、某一步失败，或流程需要用户作出选择。需要人工判断时，系统会保留现场，收到选择后再继续。

### 状态、结果与追踪记录

MatFlow 会保存当前工作流版本、各节点状态、路由决定和执行结果。用户既可以查看最终输出，也可以回看系统选择了什么工具、为什么这样选择，以及错误发生在哪一步。任务编号和追踪编号用于把同一次任务的这些信息联系起来。

### 工具注册与扩展

内置工具和自定义节点都通过同一份工具注册表对外提供。注册项会声明自己的输入、输出、参数和版本，只有类型兼容的节点才能连接。项目也提供 AI Skill Node，用于把带明确输入输出约束的领域能力接入工作流；这类节点需要配置模型后才能执行。

### 三种使用入口

- **WebUI** 适合查看工作区和工作流图、导入并检查数据、提交研究问题，以及阅读路由记录。当前 WebUI 不负责应用工作流修改或执行完整流程。
- **本机 DSH** 适合用自然语言完成从数据检查、工作流规划到执行的全过程，并会在写入或执行前请求确认。
- **ChatGPT 或其他 MCP 客户端** 可以调用与 DSH 相同的 MatFlow 能力，适合把 MatFlow 接入已有的 AI 工作方式。

三个入口读取的是同一个本地工作区，不是三套彼此独立的数据。

### 当前可执行范围

项目目前完整实现了表格导入、列整理、EIS 基础质量检查和 Nyquist 结果生成这一条分析链路。仓库中的其他材料分析示例主要用于展示和测试任务表达；除非已经安装相应的自定义节点或执行器，否则不能因为示例存在就认为它们可以完整执行。

## 5. 示例：完成第一次数据分析

本章以一个具体问题说明完整流程，重点是从提出问题到获得可追踪结果的操作顺序，不展开 EIS 方法本身。

### 5.1 示例问题

本例使用一份阻抗测量数据，回答以下问题：

> 这份数据是否满足继续分析的基本条件？如果满足，请生成一份便于人工复核的图形结果。

项目提供了示例文件 `examples/data/01_eis_basic_qc/eis_spectrum.csv`。使用该文件可以避免额外的数据准备，使本例集中说明 MatFlow 的工作流程。

### 5.2 选择操作入口

按第 3.2 节启动本机 DSH，并在 DSH 中附加示例文件。也可以使用已经连接 MatFlow 的 ChatGPT 或其他 MCP 客户端。

WebUI 可以完成数据导入、查看和任务路由，但当前不能独立应用工作流修改和执行整条流程，因此不适合作为这个完整示例的唯一入口。

### 5.3 提交分析请求

可以直接发送：

> 请用我刚附加的数据回答：这份数据是否满足继续分析的基本条件？如果可以，请生成便于人工复核的图形结果。先检查数据和当前工作区，再规划分析流程；每次需要写入或执行时先向我确认。

该请求说明了数据、问题和期望结果，但不预先指定字段映射或分析参数。客户端应先将文件导入 MatFlow，再读取服务端确认的数据结构；遇到含义不明确的内容时，应请求用户确认，不应自行推断。

### 5.4 审查分析方案

完成数据检查后，客户端会选择合适的已注册工具并提出工作流。本例的整体流程应包括：

1. 读取已导入的数据；
2. 把原始表格整理成分析工具能够接收的形式；
3. 进行基础质量检查；
4. 根据检查后的数据生成可供复核的结果。

审查时应确认三项内容：工作流使用了本次导入的文件，各步骤与示例问题直接相关，最终输出能够回答该问题。具体列名、阈值和领域参数不属于本例的讲解重点；仅在客户端要求决定时进行确认。

### 5.5 确认工作流变更

客户端会先校验拟议的工作流，并在校验通过后请求应用修改。确认前可要求客户端概括将增加的步骤；确认后，变更才会写入 MatFlow，工作流版本随之更新。

版本冲突表示工作区在规划后已经发生变化。此时应重新读取当前状态并生成方案，不应重复提交原方案。

### 5.6 执行与结果核验

工作流写入后，客户端会再次请求执行确认。批准后，MatFlow 会依次运行各步骤，并在完成、失败或需要人工选择时停止。

执行完成后，应依据最初的问题核验结果：确认系统是否明确说明数据能否继续使用，并检查图形结果是否已经生成。还可在 WebUI 中刷新工作区，查看节点状态和工作流版本；任务摘要会保留原始问题、工具选择、执行结果和错误处理记录。

本例所展示的通用顺序为：**提出问题 → 检查数据 → 规划并校验工作流 → 确认写入 → 确认执行 → 根据原问题核验结果**。

## 6. 如何理解界面与结果

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

## 7. 安全与确认规则

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

## 8. 当前限制

- 当前是单用户、单工作区设计，并发写入仅在单个服务进程内加锁。
- 不要同时启动多个 MatFlow 服务进程写同一 `data/` 目录。
- 只有 EIS 基础链路具备完整执行器；“能路由到”不表示“能执行完成”。
- WebUI 当前侧重查看和路由，完整的图编排与执行更适合通过 MCP 客户端完成。
- 内置 `/api/chat` 默认返回 `410 Gone`；它只为迁移保留，不是推荐入口。

## 9. 常见问题

### 端口 8000 被占用

先关闭已有 MatFlow 或其他占用该端口的进程。当前命令行入口固定使用 8000；如需临时改端口，可直接运行 Uvicorn，但 DSH profile 中的地址也要同步修改。

### 导入后显示 `binary` 或 `unreadable`

`binary` 表示该扩展名不是当前表格解析器支持的格式；`unreadable` 表示文件虽像表格，但解析失败。优先导出为结构清晰、带表头的 UTF-8 CSV 再导入。

### AI 找不到刚导入的文件

让 AI 重新调用 `get_workspace_state` 或在 WebUI 刷新；然后把界面显示的文件名或 `upload_id` 告诉它。不要把本机绝对路径当成 MCP 的数据集 ID。

### 图补丁提示版本冲突

说明图在补丁生成后已变化。重新读取工作区状态，并以最新 `state.version` 生成和校验补丁。

### 执行停在 `waiting`

The current node has already completed and produced a bounded progressive preview. Inspect the preview and choose Continue, Revise node, or Stop run. Continue resumes downstream execution automatically. Human review is enabled per node with the Review checkbox; new workflows should not add a Human Decision node.

### Modify a node with AI

Right-click a node, or use its three-dot button, and choose **Modify with AI**. Enter a precise change request, then select a configured provider and model. Generating a proposal does not modify the graph. Review the ToolSpec and connection migration diff, resolve or drop every non-exact connection, and choose **Apply revision**. Port or executor changes remain blocked when reviewed executable support is not installed.

API keys belong in the local `.env` file. The Web UI stores only the provider URL, model names, and environment-variable name; it never receives the key value.

### Connect ports

Ports use a large interaction halo. Hover shows the port name and type. Either drag an output port to a compatible input or click the output and then a highlighted input. Incompatible targets dim while connection mode is active; press Escape to cancel.

更多启动和恢复方法见[部署与运维指南](DEPLOYMENT_AND_OPERATIONS.md)。

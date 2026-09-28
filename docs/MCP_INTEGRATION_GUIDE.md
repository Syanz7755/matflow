# MatFlow MCP 与 AI 客户端接入指南

## 1. 接入模型

MatFlow 使用 MCP Streamable HTTP 暴露材料工作区能力：

```text
用户 <-> AI 客户端（ChatGPT / DSH / 其他 MCP Client）
                    |
                    | MCP Streamable HTTP
                    v
          http://127.0.0.1:8000/mcp
                    |
                    v
       WorkspaceRuntime -> data/ + 工具执行器
```

AI 客户端负责对话、任务分解和工具调用；MatFlow 负责验证、状态、持久化和执行。客户端不能绕过 GraphPatch 直接更改图状态。

## 2. 启动 MCP 服务

```powershell
uv run matflow serve
```

本机端点为：

```text
http://127.0.0.1:8000/mcp
```

传输类型是 `streamable-http`。服务采用无状态 MCP 会话响应，但调用的工作区数据保存在本地磁盘。

## 3. MCP 工具目录

所有工具返回统一信封：

```json
{
  "ok": true,
  "data": {},
  "error": null
}
```

失败时 `ok` 为 `false`，`data` 为 `null`，`error` 包含 `code`、`message` 和 `retryable`。客户端必须检查 `ok`，不能仅凭 MCP 调用成功就认定业务操作成功。

| 工具 | 类型 | 用途 |
| --- | --- | --- |
| `get_workspace_state` | 只读 | 读取图、注册表、类型、技能和功能开关 |
| `import_dataset` | 写入 | 从标准 MCP/ChatGPT 文件对象导入数据 |
| `inspect_dataset` | 只读 | 读取数据集结构和有限预览 |
| `route_research_task` | 只读 | 选择兼容工具并记录理由，不修改图 |
| `validate_graph_patch` | 只读 | 在不写入的情况下验证补丁 |
| `apply_graph_patch` | 写入 | 应用通过版本和类型校验的补丁 |
| `execute_workflow` | 执行 | 执行就绪节点，直到完成、失败或等待人工选择 |
| `submit_human_decision` | 写入 | 为等待中的人工决策节点提交选择 |
| `get_task_summary` | 只读 | 读取指定任务最近的路由/执行摘要 |

推荐权限策略：只读工具可自动调用；写入和执行工具每次调用前向用户确认。未知的未来 MatFlow MCP 工具应默认按需确认。

## 4. 推荐调用顺序

一个可靠的 AI 客户端应遵循：

1. `get_workspace_state`：读取最新图版本和已注册工具。
2. `import_dataset`：仅当数据尚未导入，且用户已确认时调用。
3. `inspect_dataset`：验证列名、类型和预览。
4. `route_research_task`：记录目标、输入类型和候选工具。
5. 构造 GraphPatch，并调用 `validate_graph_patch`。
6. 向用户展示将新增/修改的节点和边。
7. 用户确认后调用 `apply_graph_patch`。
8. 再次确认后调用 `execute_workflow`。
9. 如遇 `waiting`，展示原始选项；确认后调用 `submit_human_decision`。
10. 用 `get_task_summary` 汇总证据，而不是凭对话记忆编造结果。

客户端系统提示可参考 `runtime_skills/matflow_mcp_runtime.md`。

## 5. 本机 DeepSeek Harness

### 首次配置

确认 `dsh` 已在 `PATH` 中，然后执行：

```powershell
uv run matflow configure-dsh --profile matflow
uv run matflow diagnose --dsh --profile matflow
```

配置命令会：

- 从 DSH 自带 `web` 模板创建独立的 `matflow` profile；
- 安装固定版本的 `@deepseek-ai/dsh-mcp-client`；
- 链接本项目的 `@matflow/dsh-integration`；
- 写入 MatFlow MCP 地址；
- 验证最终 DSH 配置；
- 保留首次修改前的 profile 配置备份。

它不会修改已有的默认 `web` profile。如果目标 profile 存在非 MatFlow 管理的 patch，命令会拒绝覆盖。

可先查看将要写入的配置：

```powershell
uv run matflow configure-dsh --profile matflow --dry-run
```

### 日常启动

```powershell
uv run matflow start-dsh --profile matflow
```

启动命令先检查 DSH profile，再启动 MatFlow，等待服务就绪，最后打开 DSH。结束 DSH 后，随同启动的 MatFlow 服务也会被关闭。

### DSH 专用集成提供的保护

- 向模型注入 MatFlow 的 inspect-first 操作规则；
- 对导入、图变更、执行和人工决定显示一次性批准界面；
- 未分类的未来 MatFlow 工具默认要求批准；
- 提供 `matflow_import_local_dataset`，安全地把本机文件上传到 MatFlow。

本机文件导入只允许：

- DSH 当前工作区；
- `$DSH_HOME/attachments/v1/files`；
- DSH 集成配置中显式声明的根目录。

文件必须是普通文件，不能是符号链接，解析后的真实路径必须仍位于允许目录中，并且不能超过 25 MB。

## 6. ChatGPT 接入

MatFlow 默认只监听回环地址，ChatGPT 无法直接访问。需要先使用 OpenAI Secure MCP Tunnel 或等价的受控私网连接，把本机 `/mcp` 端点安全地提供给 ChatGPT，再在 ChatGPT 中添加该 MCP server。

接入时应满足：

- 不把无认证的 `127.0.0.1:8000` 服务直接做普通公网端口转发；
- 隧道目标指向 `http://127.0.0.1:8000/mcp`；
- 连接测试能列出 9 个 MatFlow 工具；
- ChatGPT 对写入/执行工具启用确认；
- 先在非重要数据副本上完成一次端到端测试。

`import_dataset` 声明了 `_meta["openai/fileParams"] = ["file"]`，接受以下标准文件对象：

```json
{
  "download_url": "https://temporary-authorized-url.example/file",
  "file_id": "file_...",
  "mime_type": "text/csv",
  "file_name": "eis.csv"
}
```

MatFlow 会验证下载地址和每次重定向，只允许公网 HTTPS，不接受 URL 中的用户名/密码，不访问本机或内网地址，并限制下载大小为 25 MB。

## 7. 其他 MCP 客户端

客户端配置至少需要：

```yaml
serverName: matflow
transport: streamable-http
url: http://127.0.0.1:8000/mcp
```

建议工具调用超时设为 180 秒，并允许短暂断线重连。若客户端不识别 MCP 工具注解，应在客户端策略中按工具名显式区分只读和写入操作。

文件导入有两种方式：

- 客户端支持 OpenAI 文件参数：直接调用 `import_dataset`；
- 客户端只访问本机文件：通过受控上传桥接，或先调用 HTTP `POST /api/uploads`，再把返回的 `upload_id` 交给 AI。

## 8. 接入验收

完成配置后逐项检查：

- [ ] 能列出全部 9 个工具；
- [ ] `get_workspace_state` 返回 `ok: true` 和当前 `state.version`；
- [ ] 只读工具不弹出写入批准；
- [ ] `apply_graph_patch` 和 `execute_workflow` 会要求用户确认；
- [ ] 导入一个小型 CSV 后，`inspect_dataset` 能返回列名和预览；
- [ ] 无效 `base_version` 的 GraphPatch 被拒绝，图状态不变；
- [ ] 客户端能显示业务信封中的 `error.message`；
- [ ] 客户端不会把路由结果误报成执行结果。

## 9. 常见接入故障

### 客户端连接失败

确认 `uv run matflow serve` 正在运行，并先访问 `http://127.0.0.1:8000/api/capabilities`。检查客户端传输类型是否为 `streamable-http`，URL 是否包含 `/mcp`。

### DSH 启动时报 profile 无效

运行：

```powershell
uv run matflow diagnose --dsh --profile matflow
uv run matflow configure-dsh --profile matflow
```

配置命令是幂等的；对于由 MatFlow 管理的 profile，可安全重复执行。

### 文件下载被拒绝

确认文件对象使用 `https://`，主机可从本机解析为公网地址，重定向未进入内网，且文件不超过 25 MB。对于本机文件，使用 DSH 本地文件桥接或 WebUI 上传，不要伪造 `download_url`。

### 工具调用成功但 `ok` 为 `false`

这表示 MCP 传输正常，但 MatFlow 业务校验失败。读取 `error.message`，修正参数后再调用；不要自动无限重试。


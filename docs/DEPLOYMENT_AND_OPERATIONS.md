# MatFlow 部署与运维指南

## 1. 部署范围

当前 MatFlow 面向单机、单用户、本地可信网络环境。默认服务监听 `127.0.0.1:8000`，数据持久化在项目目录中，不提供账号、租户、远程数据库或内置 TLS。

推荐拓扑：

```text
同一台电脑
├─ MatFlow HTTP/MCP 服务（127.0.0.1:8000）
├─ WebUI（开发服务器，通常 localhost:5173）
└─ DSH 或其他本机 MCP 客户端
```

如需连接 ChatGPT，应使用受控的 Secure MCP Tunnel；不要直接开放 8000 端口。

## 2. 环境安装

在项目根目录执行：

```powershell
uv sync
uv run matflow install-frontend
uv run matflow diagnose
```

`uv sync` 按 `uv.lock` 创建或更新隔离环境。升级依赖后应提交新的锁文件，并重新运行后端、前端构建和端到端测试。

## 3. 启动方式

For the complete launcher reference—including the important difference between `start_matflow.bat` and `scripts/start.ps1`, model-service prerequisites, shutdown behavior, and test helpers—see [Startup Scripts Guide](STARTUP_SCRIPTS.md).

| 场景 | 命令 | 启动内容 |
| --- | --- | --- |
| WebUI 开发 | `uv run matflow start` | 后端 + Vite 前端 |
| MCP/HTTP 服务 | `uv run matflow serve` | 仅后端，监听本机 8000 |
| 本机 DSH | `uv run matflow start-dsh --profile matflow` | 后端 + DSH profile |
| 手工后端开发 | `uv run uvicorn backend.main:app --reload --port 8000` | 带热重载的后端 |

生产性质的长期运行不应使用 Vite 开发服务器或 Uvicorn `--reload`。当前仓库未提供 Windows 服务包装和反向代理模板，长期服务化部署属于后续运维工作。

## 4. 目录与持久化

| 路径 | 内容 | 备份建议 |
| --- | --- | --- |
| `data/graph_state.json` | 当前工作流图、版本和历史 | 必须 |
| `data/settings.json` | 本地设置、自定义节点和功能开关 | 必须 |
| `data/uploads/` | 导入的数据文件 | 必须 |
| `runtime_skills/` | AI 客户端运行规则 | 随代码版本管理 |
| `config/` | 可选旧模型网关配置 | 按需；不得写入真实密钥 |
| `frontend/` | WebUI 源码与构建配置 | 随代码版本管理 |

任务摘要当前由运行中的服务维护，不应把它当成跨重启的长期审计数据库。重要研究过程应同时导出或保留图状态、原始数据和最终产物。

## 5. 备份与恢复

备份前应停止所有 MatFlow 服务，避免复制到一半写入的工作区。至少复制以下内容到受控位置：

```text
data/graph_state.json
data/settings.json
data/uploads/
```

恢复步骤：

1. 停止 MatFlow；
2. 保存当前 `data/` 的副本；
3. 将同一备份集的状态、设置和 uploads 一起恢复；
4. 启动 `uv run matflow serve`；
5. 检查 `/api/state` 和 `/api/uploads`；
6. 用 WebUI 或 MCP 检查关键数据集，不要立即执行旧图。

不要只恢复 `graph_state.json` 而遗漏它引用的上传文件。

## 6. 健康检查

### 环境检查

```powershell
uv run matflow diagnose
uv run matflow diagnose --dsh --profile matflow
```

### 运行时检查

服务启动后访问：

- `GET http://127.0.0.1:8000/api/capabilities`：确认 HTTP 服务和能力注册表可用；
- `GET http://127.0.0.1:8000/api/state`：确认状态文件可读取；
- `GET http://127.0.0.1:8000/api/uploads`：确认数据目录可访问；
- `http://127.0.0.1:8000/docs`：查看当前 HTTP OpenAPI 文档。

MCP 健康检查应由实际 MCP 客户端完成：初始化连接、列出工具，再调用 `get_workspace_state`。

## 7. 测试与发布前检查

后端测试：

```powershell
uv run --group dev python -m unittest discover -v
```

前端构建与端到端测试：

```powershell
Set-Location frontend
npm run build
npm run test:e2e
```

DSH 集成语法检查：

```powershell
node --check integrations/dsh/index.js
```

发布前至少确认：

- 后端全部测试通过；
- 前端生产构建成功；
- 浏览器端 E2E 通过；
- DSH profile 诊断成功；
- 实际 MCP 客户端能列出工具并读取状态；
- 文档中的工具数量、端点、文件限制和版本与实现一致。

## 8. 配置与环境变量

| 名称 | 用途 | 默认/说明 |
| --- | --- | --- |
| `DSH_HOME` | 覆盖 DSH 配置根目录 | 默认 `%USERPROFILE%\.dsh` |
| `MATFLOW_ENABLE_LEGACY_CHAT` | 临时启用旧 `/api/chat` | 默认关闭；仅迁移使用 |
| `MATFLOW_LITELLM_API_KEY` | 旧 Agent loop 访问本地 LiteLLM | 正常 MCP 路径不使用 |
| `SJTU_ZHIYUAN_API_KEY` | 可选旧 LiteLLM 上游密钥 | 不得写入仓库或设置文件 |

常规 MCP、WebUI 和 DSH 运行不需要模型 API key；模型凭据由外部 AI 客户端自行管理。

## 9. 安全基线

- 只绑定 `127.0.0.1`，除非已经部署认证、TLS、来源限制和审计。
- 不在 `data/settings.json`、日志、截图或 Git 中保存 API key。
- 不运行多个进程共享写入同一个 `data/` 目录。
- 在执行用户提供的 GraphPatch 前始终校验；客户端不得直接编辑状态文件。
- 对上传文件保留 25 MB 上限和扩展名白名单。
- 外部下载必须维持 HTTPS、公网地址和逐跳重定向检查。
- 定期清理不再需要且已完成备份的上传数据；当前没有自动保留期限。

## 10. 故障排查

### 服务无法启动

1. 运行 `uv run matflow diagnose`；
2. 确认 Python 版本在支持范围内；
3. 确认 8000 端口未被占用；
4. 直接运行 Uvicorn 查看完整错误；
5. 检查 `data/graph_state.json` 和 `data/settings.json` 是否为有效 JSON。

### WebUI 打开但没有状态

确认后端仍在运行，并检查浏览器访问 `/api/state` 是否成功。开发模式下前后端是两个进程，关闭启动 MatFlow 的终端会同时结束后端。

### 状态文件损坏

停止服务，不要用空文件覆盖。先复制损坏文件，再恢复最近备份。若无备份，可用 Pydantic 校验错误定位非法字段，但手工修复前应了解 `GraphState` 契约。

### DSH 与 MCP 反复断开

先确认普通 HTTP 健康检查稳定，再运行 DSH profile 诊断。检查 profile 的 MCP URL 是否仍为 `http://127.0.0.1:8000/mcp`。如果修改了 profile，重新运行 `configure-dsh` 只会接管 MatFlow 管理的配置。

### 数据能检查但无法执行

检查图中是否包含完整的导入、映射和分析节点；确认列映射与实际列名完全一致；确认节点使用的是 active 注册工具；再读取错误节点输出和任务摘要。

## 11. 旧 LiteLLM 网关

LiteLLM 不再随 MatFlow 默认启动。仅当迁移旧 `/api/chat` 或旧 AI Skill Node 链路时才使用：

```powershell
$env:SJTU_ZHIYUAN_API_KEY = "your-key"
uv run litellm --config config/litellm.yaml --port 4000
$env:MATFLOW_ENABLE_LEGACY_CHAT = "1"
```

此路径不属于推荐部署，也不应与“外部 AI 客户端通过 MCP 接入”的主路径混淆。

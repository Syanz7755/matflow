# Lead 独立复验：一条工作流全程操作跑通（2026-10-20 深夜）

本文件记录 Lead（主代理）在**自己独立启动的前后端实例**上，对同一套产品路径做的复验，
与子代理证据相互独立。所有数字来自实际命令输出与截图。

## 1. 环境

| 项 | 值 |
|---|---|
| 后端 | `http://127.0.0.1:8022/api`，数据根 `.tmp/live/lead-backend`，`uvicorn`（仓库 `.venv`） |
| 前端 | `http://127.0.0.1:5222`，`vite`（公开前端仓库 `apps/webui`） |
| 模型网关 | SJTU LiteLLM `http://127.0.0.1:4078/v1`；DeepSeek 官方 MatFlow 网关 `http://127.0.0.1:4080/v1` |
| 凭据 | `LITELLM_DEFAULT_API_KEY` 等只从 Windows User 作用域读入子进程；未显示、未落盘 |
| 数据 | `examples/data/01_eis_basic_qc/eis_spectrum.csv`（`frequency_hz,z_real_ohm,z_imag_ohm`，13 行） |

## 2. 浏览器全程操作（真实界面，非 mock）

脚本：`.tmp/live/lead_ui_verify.mjs`（本机脚本，未提交；Playwright 1.63 + Chromium）。
页面错误：`[]`（无未捕获异常）。

| 步骤 | 操作 | 结果 | 截图 |
|---|---|---|---|
| 1 | 打开工作台，空工作区 | 连接后端，Graph v0 | [01-empty-workspace.png](01-empty-workspace.png) |
| 2 | **Import dataset** 上传 `eis_spectrum.csv` | 数据集出现在 Imported datasets | [02-dataset-imported.png](02-dataset-imported.png) |
| 3 | 添加 Raw File Import（选数据集）、Normalize / Column Mapping、EIS Basic Analysis；端口点击连线；在 Inspector 把 `Real Column`/`Imag Column` 设为 `z_real_ohm`/`z_imag_ohm`；勾选 EIS 节点 **Review** | 2 条边；EIS 参数生效；Review 打开 | [03-graph-built-and-review-enabled.png](03-graph-built-and-review-enabled.png) |
| 4 | **Save workflow** → **Run workflow from start** | 状态栏 `The workflow paused for human review`；EIS 节点 **Waiting**；预览已显示真实 `EISQCReport`（rows_valid 13 / rows_retained 13 / pass true） | [04-review-waiting.png](04-review-waiting.png) |
| 5 | 点击 **Continue** | 状态栏 `Decision submitted: continue`；EIS 节点 **Completed**，结果保留 | [05-completed-with-result.png](05-completed-with-result.png) |
| 6 | **Export workflow JSON**（下载 `local-default.matflow.json`）→ 再导入 | 图恢复；无页面错误 | [06-export-import.png](06-export-import.png) |

同一路径还用 HTTP API 做了独立断言（`scripts/live_acceptance/check_workflow_api.py`）：

```text
[1] connected packages=['eis','ftir','qe','qe_demo','xrd']
[2] uploaded eis_spectrum.csv (0.03s)
[3] workflow built (0.0s)
[4] review gate holds (0.05s): qc-1=waiting plot-1=ready (downstream stopped)
[5] continued (0.01s): rows_valid=13 rows_retained=13 min_frequency_hz=10.0 plot_points=13
[6] QE replay demo (0.09s): iterations=14 energy=-2417.17683284 Ry provenance=historical_output_replay
PASS
```

该脚本已收进仓库，可在任意运行中的后端上重跑（`MATFLOW_API` 指定地址）。

## 3. 一键启动器复验

新增 `scripts/start_demo.ps1`（`scripts/start_demo.bat` 双击入口）：从 User 作用域读密钥到子进程，
复用已健康的网关，启动后端 8000 与前端 5173，逐项健康检查并打印 URL。实测输出：

```text
[1/4] SJTU model gateway      reusing the gateway already listening on 4078
[2/4] DeepSeek official gateway  reusing the gateway already listening on 4080
[3/4] MatFlow backend         started backend; backend ready: http://127.0.0.1:8000/api/capabilities
[4/4] WebUI dev server        started webui; WebUI ready: http://127.0.0.1:5173
```

随后清理测试进程，未留下监听端口。

## 4. 判定

- **一条工作流（EIS 质检 + 轴映射 + 人工审核 + Nyquist 结果）可以全程手动操作跑通**：
  导入 → 建图 → 连线 → 参数 → 审核暂停 → 继续 → 结果 → 导出/导入，全程真实后端执行。
- QE 回放主线同样复验通过（历史回放，非 LLM 规划/真实 QE 计算）。
- 与子代理证据的差异：本复验使用 Lead 自己的端口与数据根，排除“只在某个代理的实例上可用”的可能。

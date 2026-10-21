# MatFlow 前端端到端操作验收（2026-10-20 现场）

本文档记录**在真实浏览器里、对着真实后端**跑通一条完整工作流的过程、证据、逐项检查结果与缺陷。
所有页面操作通过 Playwright 驱动真实 UI 完成（无 mock、无 HTTP 直连替代 UI 操作）；凡是绕过 UI 的地方都在
“缺陷 / 局限”一节明确写出。

- 证据目录：`docs/acceptance/2026-10-20-live/frontend-ops/`
- 截图目录：`docs/acceptance/2026-10-20-live/frontend-ops/screenshots/`
- 原始证据 JSON：`ops-canonical-evidence.json`、`ops-checklist-evidence.json`、`ops-qe-evidence.json`
- 面向操作者的复现步骤：[OPERATOR_RUNBOOK.zhcn.md](../OPERATOR_RUNBOOK.zhcn.md)

## 1. 环境与时间

| 项 | 值 |
|---|---|
| 日期 / 时段 | 2026-10-20 21:47 – 22:34（北京时间，含重跑与缺陷定位） |
| 操作系统 | Windows 11 专业版 |
| 后端 | `<repo>`（matflow），Python 3.12.13，`.venv`，uvicorn |
| 后端提交 | `4ea8ec7`（工作区含未提交改动，本次未改动任何代码/配置） |
| 前端 | `<frontend-repo>`（matflow-frontend），Node v26.1.0 / npm 11.13.0 |
| 前端提交 | `8b37ed3` |
| 浏览器 | Playwright 1.63.0 + 随包 Chromium，视口 1440×900（窄屏检查 1280×720） |
| 后端实例 | `127.0.0.1:8021`，`MATFLOW_DATA_ROOT=.tmp/live/ops-backend` |
| 前端实例 | `127.0.0.1:5221`，`VITE_MATFLOW_API_URL=http://127.0.0.1:8021/api` |
| 日志 | `.tmp/live/ops-backend.log`、`.tmp/live/ops-frontend.log`、`.tmp/live/ops-*.log` |
| 凭据 | 仅从 Windows 用户环境变量 `LITELLM_DEFAULT_API_KEY` 读入后端进程；未打印、未落盘、未写入本目录任何文件 |

## 2. 启动命令（实际使用）

```powershell
# 后端（端口 8021，独立数据根，日志）
$env:LITELLM_DEFAULT_API_KEY = [Environment]::GetEnvironmentVariable('LITELLM_DEFAULT_API_KEY','User')
$env:MATFLOW_DATA_ROOT = '.tmp/live/ops-backend'
$env:MATFLOW_CORS_ORIGINS = 'http://127.0.0.1:5221,http://localhost:5221'
Set-Location <repo>
& .\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8021 *> .tmp\live\ops-backend.log
```

```powershell
# 前端（端口 5221）
$env:VITE_MATFLOW_API_URL = 'http://127.0.0.1:8021/api'
Set-Location <frontend-repo>
npm run dev --workspace @matflow/webui -- --host 127.0.0.1 --port 5221 --strictPort *> <repo>\.tmp\live\ops-frontend.log
```

验证：`GET http://127.0.0.1:8021/api/capabilities` 返回 200（`api_contract.name=matflow-http`、
`server_version=1.1.0`、18 个注册工具），`http://127.0.0.1:5221/` 返回 200 且 `.workflow-editor` 渲染、
顶栏状态条显示 `Connected · Graph vN`。

> **必须设置 `MATFLOW_CORS_ORIGINS`**。后端内置允许来源只有 `http://localhost:5173` 与
> `http://127.0.0.1:5173`；用 5221 端口时若不追加来源，浏览器端 `fetch` 全部被 CORS 拦截，
> 页面停在 "Reading the MatFlow control plane…"，控制台报 `No 'Access-Control-Allow-Origin' header`。
> 这不是产品缺陷，是端口选择带来的配置要求（见 §6 已知问题）。

## 3. 主工作流结果（真实数值）

在**全新工作区**（`graph v0`，0 节点 0 边）里按顺序完成：

| 阶段 | 结果 | 证据 |
|---|---|---|
| 导入数据集 `examples/data/01_eis_basic_qc/eis_spectrum.csv` | 成功；数据集面板显示 `eis_spectrum.csv`、`13 rows · 3 columns` | [01-import-dataset.png](screenshots/01-import-dataset.png) |
| 添加 Raw File Import / Normalize / EIS Basic Analysis | 3 节点；Raw File Import 的 Dataset 下拉选中刚导入的数据集 | [02-graph-built.png](screenshots/02-graph-built.png) |
| 连线 Raw→Normalize（`raw`→`raw`）、Normalize→EIS（`table`→`data`） | 2 条边；`table`→`data` 第一次点击未注册，重试一次成功（见 D1） | 同上 |
| Inspector 设置参数 | `frequency_column=frequency_hz`、`real_column=z_real_ohm`、`imag_column=z_imag_ohm`（Inspector 三个文本框可直接编辑） | [02b-eis-params.png](screenshots/02b-eis-params.png) |
| EIS 节点打开 Review，Save | `Saved as graph v1.`；服务端 3 节点 / 2 边，`review_policy.after_run=true` | 状态 JSON：`ops-canonical-evidence.json` |
| Run workflow from start | EIS 节点进入 **Waiting**；顶栏 `The workflow paused for human review`；Inspector 出现 Continue / Revise node / Stop run | [03-review-waiting.png](screenshots/03-review-waiting.png) |
| 点击 Continue | EIS 节点 **Completed**，三个节点全部 Completed | [04-continue-completed.png](screenshots/04-continue-completed.png) |
| EIS 结果预览（解析值） | `rows_valid=13`、`rows_retained=13`、`min_frequency_hz=10`、`pass=true`、`issues=[]`，`mapping` 即上面三项列名 | 同上 + `ops-canonical-evidence.json.results.eisOutput` |
| 导出工作流 JSON | `local-default.matflow.json`，3 节点 / 2 边 | — |
| 删除 Normalize 节点后再导入该 JSON | 恢复到 3 节点 / 2 边，`review_policy.after_run=true`，EIS 三个参数值原样恢复；提示 `Imported … Review and save to apply it.` | [05-export-import.png](screenshots/05-export-import.png) |
| Run MgO QE replay demo（历史回放） | 需空工作区；清空并保存后一键生成 4 节点 QE 图并执行完成，顶栏 `MgO QE replay complete · -2417.17683284 Ry · no Slurm job submitted` | [06-qe-replay-demo.png](screenshots/06-qe-replay-demo.png) |

QE 回放解析值（`qe_parse_output` 节点）：`convergence=converged`、
`energy=-2417.17683284 Ry`、`fermi_energy=9.7133 eV`、
`provenance=historical_output_replay`、`source_path=qe72_wave1_manual/results/kcheck/scf333.log`，
Inspector 预览带 `Historical output replay · Slurm not submitted` 徽标。四个节点状态均为 `completed`。

## 4. 操作检查清单（逐项）

“证据”列中的数字均可在 `ops-*.json` 或截图中核对；PASS 指**通过真实 UI 完成并核对服务端状态**。

| # | 项目 | 结果 | 证据 |
|---|---|---|---|
| 1 | 导入数据集 | PASS | 13 行 / 3 列；[01](screenshots/01-import-dataset.png) |
| 2 | 添加节点 | PASS | 3 个节点连续添加，工具库卡片点击即入图 |
| 3 | 删除节点 | PASS | Inspector `Delete node` → 画布 3→2，提示 `1 node removed from the draft.`（用于验证导入恢复） |
| 4 | 重命名节点 | PASS | 节点 `•••` 菜单 → `Rename node` 对话框；`EIS Basic Analysis` → `EIS QC renamed` → 改回，画布标题即时更新 |
| 5 | 连接端口 | PASS（有一次重试） | `raw`→`raw` 首次成功；`table`→`data` 首次未注册，第二次成功；最终 2 条边 |
| 6 | 断开连接 | **FAIL** | 在边上点击使其选中，按 `Backspace` 与 `Delete`：边数保持 2→2，节点数不变（3→3），无任何提示（notice 仍是初始文案 `Choose a tool to add the first node.`）；见 [11-disconnect.png](screenshots/11-disconnect.png) 与 `ops-checklist-evidence.json.results.disconnect` |
| 7 | 清空工作流 | PASS（草稿） | Inspector 空态 `Clear workflow` → 画布 0 节点，提示见 [10-clear-workflow.png](screenshots/10-clear-workflow.png)；随后 Save 落库为 0 节点 / 0 边（`results.clearSaved`） |
| 8 | 参数编辑 | PASS | 三个列名参数在 Inspector 文本框中修改并随 Save 持久化（服务端 `params` 已核对） |
| 9 | Review 开关 | PASS | 节点头部 `Review` 复选框；保存后 `review_policy.after_run=true`（EIS 与 Normalize 各验证一次） |
| 10 | 保存 | PASS | `Saved as graph v1.` / `v3` / `v4`，节点、边、参数、Review 策略均落入服务端状态 |
| 11 | 运行 | PASS | 顶栏 `The workflow paused for human review`；EIS = Waiting |
| 12 | 审核继续（Continue） | PASS | EIS Waiting → Completed，预览给出 `rows_valid=13 / pass=true` |
| 13 | 停止分支（下游不执行） | PASS | Normalize 打开 Review → 运行 → Normalize=Waiting、EIS=`ready`、`output=null`；点 `Stop run` 后 Normalize=`cancelled`、EIS 仍 `ready`、`output=null`、`preview=null`；[09-stop-run-waiting.png](screenshots/09-stop-run-waiting.png)、[09b-stop-run-branch.png](screenshots/09b-stop-run-branch.png) |
| 14 | 导出 / 导入 JSON | PASS | 导出 3 节点 2 边；删节点后导入恢复；导入后 Save 提示 `The workflow is already saved.`（图与已保存版本一致，属预期，见 D5） |
| 15 | 路由任务面板 | PASS | 顶栏 `Route a research task` 打开对话框：1 个 `Research question` 文本域、14 个可用输入类型复选框；Esc 关闭；[07](screenshots/07-route-task-dialog.png) |
| 16 | QE 一键演示 | PASS（需空工作区） | 4 节点全部 `completed`，`-2417.17683284 Ry`；[06](screenshots/06-qe-replay-demo.png) |
| 17 | 1280×720 可用性 | PASS | `innerWidth=1280`、`scrollWidth=1280`、无横向溢出；画布宽 680 px；顶栏三个操作按钮全部可见；[08](screenshots/08-narrow-1280x720.png) |
| 18 | 无未捕获页面错误 | PASS | 主流程 `pageerror=0`、`console error=0`；清单脚本捕获到 1 条 `Failed to load resource: 409`，来自我按错误顺序点击 QE 演示（非空工作区）后的后端拒绝，见 D3 |

清单汇总：**17 PASS / 1 FAIL**（唯一 FAIL 为“断开连接”，缺陷 D2）。

## 5. 截图清单

| 文件 | 内容 |
|---|---|
| `01-import-dataset.png` | 数据集导入后：`eis_spectrum.csv`、13 行 3 列 |
| `02-graph-built.png` | 三节点两边的图（Raw→Normalize→EIS） |
| `02b-eis-params.png` | Inspector 中三个列参数已改为 `frequency_hz` / `z_real_ohm` / `z_imag_ohm` |
| `03-review-waiting.png` | EIS 节点 Waiting + Continue / Revise / Stop run 审核门 |
| `03b-review-waiting-full.png` | 同上，整页 |
| `04-continue-completed.png` | Continue 后 EIS Completed + 结果预览（13/13、pass=true） |
| `04b-continue-completed-full.png` | 同上，整页 |
| `05-export-import.png` | 导出 JSON 后删除节点、再导入并保存，图恢复为 3 节点 2 边 |
| `06-qe-replay-demo.png` | **历史回放**：MgO QE 一键演示，4 节点完成、`-2417.17683284 Ry` |
| `07-route-task-dialog.png` | 路由任务对话框 |
| `08-narrow-1280x720.png` | 1280×720 窄屏，无横向滚动 |
| `09-stop-run-waiting.png` | 停止分支：Normalize 审核门 Waiting，EIS 尚未执行 |
| `09b-stop-run-branch.png` | Stop run 之后：Normalize=cancelled、EIS=ready（下游未执行） |
| `10-clear-workflow.png` | Clear workflow 后画布为空 |
| `11-disconnect.png` | 断开连接失败现场（边仍为 2 条） |
| `99-*.png` | 自动化中途失败的现场截图（保留为过程证据，不作为验收图） |

## 6. 缺陷与已知局限

**D1 端口点击连线偶发不注册（中）** — 依次“点输出端口 → 点输入端口”时，第二次点击偶尔不生成边，
画布与提示均无变化；再点一次即成功（本次 `table`→`data` 第一次失败、第二次成功）。建议：端口点击后给出
“等待选择输入端口”的显式状态并保证点选命中，或统一改为拖拽。

**D2 无法在界面里断开一条连接（高，唯一 FAIL）** — 点击边将其选中后按 `Backspace` / `Delete`，边不消失、
无提示、`onEdgesDelete` 未触发；只能靠删除节点或清空工作流间接断开。这使“只拆一条线、保留两端节点”的
编辑动作在 UI 上不可达。

**D3 QE 演示按钮与“空工作区”前置条件不匹配（中，已在 Lead 复核阶段修复）** — 后端 `/api/qe/demo`
在工作区非空时返回 `409 Conflict`（`demo_requires_empty_workspace`，属既定产品行为），原界面顶栏按钮
始终可点，只把错误落到状态条。**修复**：前端 `3df9139` 在工作区非空时禁用两个 QE 演示按钮并给出
`title` 说明"需要空工作区，先清空工作流"；`npm test` 16 passed、`build` 成功、浏览器 E2E 7/7 通过。

**D4 同一节点内端口 id 重复（低）** — EIS Basic Analysis 同时有输入 `data`（TypedTable）与输出
`data`（EISData）。人类视觉可区分左右，但 DOM 上 `[data-port-id="data"]` 命中两个元素，自动化与
无障碍定位需要额外方向限定；`aria-label`（`input data, …` / `output data, …`）可用。

**D5 导入后立即保存是空操作（低，预期行为但易误读）** — 若导入的图与当前已保存图完全一致，
Save 提示 `The workflow is already saved.` 且不产生新版本；本次验证“导入是否生效”必须看画布/服务端状态，
不能只看提示。

**D6 1440×900 下 Inspector 在画布下方而非右侧（低，布局）** — 该宽度下编辑区仍按“画布 + 下方 Inspector”
堆叠，滚动后 Inspector 标题条会遮住 `Node label` 输入框的一部分，需要再滚动才能编辑。

**D7 审核暂停时编辑器提示与顶栏状态不一致（低）** — 运行在审核门暂停时，顶栏正确显示
`The workflow paused for human review`，而画布左下角提示写 `Workflow run finished.`（只要没有 error 结果
就显示“完成”）。

**局限（不是缺陷，但影响本次证据的适用范围）**

- 连线由“点端口”完成，未验证“按住拖拽”路径；拖拽是 React Flow 的标准路径，但本次未取证。
- 主工作流（01–05）与 QE 演示（06）、窄屏（08）、清空（10）来自同一后端实例的**两次浏览器会话**：
  因 QE 演示要求空工作区，清空并保存后才执行，故 06 覆盖了 EIS 图；EIS 图的导出件仍在
  `results.exportedFile` 中可复算。
- 停止分支按要求使用独立一次运行（重新开启 Normalize 的 Review 后再跑），未影响主流程的 Waiting→Completed 证据。
- 未执行：跨浏览器（Firefox/WebKit）、并发多用户、真实 LLM 生成节点（`Modify with AI`）、Linux 平台。

## 7. 清理与端口

- 本次结束后**保持运行**，便于复核：后端 `127.0.0.1:8021`、前端 `127.0.0.1:5221`。
- 未触碰 4078 / 4080 / 8000 / 8001 / 8020 / 5220 或其他代理进程；未改动仓库代码与配置；未执行 `git commit/push`。
- 数据根 `.tmp/live/ops-backend`（含上传件与图状态）与 `.tmp/live/ops-*.log` 为过程产物，不入库。
  Playwright 脚本：`.tmp/live/ops-canonical.mjs`、`ops-checklist.mjs`、`ops-qe.mjs`（按约定不提交）。
- 复算方式（后端在线时）：

```powershell
Invoke-RestMethod http://127.0.0.1:8021/api/state | ConvertTo-Json -Depth 12
Invoke-RestMethod http://127.0.0.1:8021/api/uploads | ConvertTo-Json -Depth 5
```

## 8. Lead 后续处理（2026-10-20 深夜，在本报告之后）

- **D3 已修**：前端提交 `3df9139`（`main` 与 `architecture/v0.2-contract-first`）在工作区非空时
  禁用两个 QE 演示按钮并给出原因提示；`npm test` 16 passed、`npm run build` 成功、浏览器 E2E 7/7。
  其余 D1/D2/D4/D5/D6/D7 仍按本报告记录为未修复（D2 是唯一 FAIL：界面无法断开单条连接）。
- 本报告的主工作流结论已由 Lead 在**另一套独立实例**上复验一致（见
  `docs/acceptance/2026-10-20-live/lead-verify/LEAD_VERIFY.zhcn.md`），排除了“只在某一实例可用”的可能。
- 操作手册见 `docs/acceptance/2026-10-20-live/OPERATOR_RUNBOOK.zhcn.md`；一键启动见
  `scripts/start_demo.ps1` / `scripts/start_demo.bat`。

## 9. 后续修复（Lead，2026-10-20 深夜，在本报告之后）

- **D-02 已修**（前端 `88060b8`）：连线现在可以被点选（变粗高亮），`Delete`/`Backspace` 只删除选中的
  那条连线，节点保留；点节点/空白/`Esc` 会清掉连线选择。新增 e2e 用例覆盖“拖开节点→选连线→删除”，
  e2e 8/8；健康检查 S7-04/S7-05 复验通过。本报告 §4 第 6 项的 FAIL 是当时现场记录，保留不改。
- **D-07 已修**：审核门暂停时画布提示改为 `The workflow paused for human review.`，与顶栏一致。
- **QE 复用路由问题已修**：`qeDemoPrompt()` 只在问题确实包含 MgO + SCF/自洽时沿用输入，否则回退到固定
  提示词；5 条单元测试覆盖，健康检查 S9-07 复跑通过。
- 修复后录制顺序健康检查：**60 PASS / 0 FAIL / 0 KNOWN**，页面未捕获异常 0；详见
  `docs/acceptance/2026-10-20-live/demo-tutorial/HEALTH_CHECK.zhcn.md`。

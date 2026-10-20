# MatFlow 浏览器端到端操作手册（2026-10-20 现场实测版）

本手册是**可照抄执行**的操作步骤，用来在浏览器里真实跑通一条 MatFlow 工作流：
导入 EIS 数据 → 组图 → 改参数 → 审核暂停 → 继续 → 看结果 → 导出/导入 → QE 历史回放。
每一步都写清“命令 / 点击什么 / 应该看到什么”，并对应到本目录的截图。

- 本文配套证据与逐项检查：[frontend-ops/FRONTEND_OPS.zhcn.md](frontend-ops/FRONTEND_OPS.zhcn.md)
- 截图：`frontend-ops/screenshots/`
- 现场实测结果：审核门 Waiting → Continue → Completed，EIS 质量检查
  `rows_valid=13 / rows_retained=13 / pass=true`；QE 回放 `-2417.17683284 Ry`。

约定：`<repo>` = 后端仓库根目录，`<frontend-repo>` = 前端仓库根目录。文中命令为 PowerShell。

## 0. 前置条件（缺一不可）

1. Windows + PowerShell；后端仓库已建好 `.venv`（Python 3.12），`backend` 包可 `-m uvicorn` 启动。
2. Node.js ≥ 20（实测 v26.1.0）与 npm；`<frontend-repo>` 已执行过 `npm install`。
3. 模型网关可达（本机 `http://127.0.0.1:4078/v1`），其调用密钥在 Windows **用户**环境变量
   `LITELLM_DEFAULT_API_KEY` 中。**不要**把密钥写进任何文件或贴进终端回显。
4. 端口 8021（后端）与 5221（前端）空闲：

```powershell
Get-NetTCPConnection -LocalPort 8021,5221 -State Listen -ErrorAction SilentlyContinue
```

有输出说明端口被占，换端口时**前后端两处都要换**（见 §7）。

## 1. 启动后端（端口 8021，独立数据根）

```powershell
$env:LITELLM_DEFAULT_API_KEY = [Environment]::GetEnvironmentVariable('LITELLM_DEFAULT_API_KEY','User')
$env:MATFLOW_DATA_ROOT = '.tmp/live/ops-backend'          # 独立数据根，避免污染默认工作区
$env:MATFLOW_CORS_ORIGINS = 'http://127.0.0.1:5221,http://localhost:5221'
Set-Location <repo>
& .\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8021 *> .tmp\live\ops-backend.log
```

检查点（另开一个终端）：

```powershell
Invoke-RestMethod http://127.0.0.1:8021/api/capabilities |
  Select-Object server_version, @{n='tools';e={$_.registry.PSObject.Properties.Name.Count}}
# 期望：server_version=1.1.0，tools=18
Invoke-RestMethod http://127.0.0.1:8021/api/state | Select-Object -ExpandProperty state |
  Select-Object version, @{n='nodes';e={$_.nodes.Count}}, @{n='edges';e={$_.edges.Count}}
# 全新数据根期望：version=0，nodes=0，edges=0
```

> **`MATFLOW_CORS_ORIGINS` 必设。** 后端默认只允许 `http://localhost:5173` 与
> `http://127.0.0.1:5173`。前端跑在 5221 而不追加来源时，页面会停在
> “Reading the MatFlow control plane…”，控制台报
> `No 'Access-Control-Allow-Origin' header is present`。这是端口选择带来的配置要求，不是页面缺陷。

## 2. 启动前端（端口 5221，指向 8021）

```powershell
$env:VITE_MATFLOW_API_URL = 'http://127.0.0.1:8021/api'
Set-Location <frontend-repo>
npm run dev --workspace @matflow/webui -- --host 127.0.0.1 --port 5221 --strictPort *> <repo>\.tmp\live\ops-frontend.log
```

检查点：浏览器打开 `http://127.0.0.1:5221/`，应看到

- 顶栏左侧 `MatFlow`，中间状态条 `Connected · Graph v0`；
- 左侧栏 `Workspace` / `Tool library` 两个页签，`Graph state` 显示 `v0` 与 `The current graph is empty…`；
- 画布显示 `No workflow nodes yet`；
- 顶栏右侧三个按钮：`Run MgO QE replay demo`、`Route a research task`、`Decision record`。

若中间显示 `Reading the MatFlow control plane…` 不变：先查 §1 的 CORS，再查 `VITE_MATFLOW_API_URL` 是否
带 `/api`，最后看后端日志有没有请求进来。

## 3. 导入数据集

1. 左侧栏 `Workspace` 页签 → `Datasets` 区域 → 点 **Import dataset**（一个文件选择按钮）。
2. 选择 `<repo>\examples\data\01_eis_basic_qc\eis_spectrum.csv`（列：`frequency_hz,z_real_ohm,z_imag_ohm`）。
3. **应该看到**：状态条 `Imported eis_spectrum.csv`；`Datasets` 列表出现该文件（约 1 KB）；
   下方详情 `eis_spectrum.csv` + `13 rows · 3 columns`。

对应截图：[01-import-dataset.png](frontend-ops/screenshots/01-import-dataset.png)

## 4. 组图（加节点 + 连线）

1. 左侧切到 **Tool library** 页签。
2. 依次点击三张工具卡片：**Raw File Import**、**Normalize / Column Mapping**、**EIS Basic Analysis**。
   每点一次，画布多一个节点并自动选中它。
3. 选中 **Raw File Import**，在右/下方 **Inspector** 的 `Dataset` 下拉里选择 `eis_spectrum.csv`。
4. 连线（依次点击端口，不要拖拽也行）：
   - 点 Raw File Import 右侧输出端口 **`raw`**，再点 Normalize 左侧输入端口 **`raw`** → 得到一条边；
   - 点 Normalize 右侧输出端口 **`table`**，再点 EIS 左侧输入端口 **`data`** → 得到第二条边。
5. **应该看到**：画布 3 节点 2 边，连线端点带箭头；顶部 `Graph state` 仍显示已保存版本，
   左下提示 `2 unsaved changes`（或类似）。

> 如果某次点击后没有出现边：再点一次该输出端口并重新点目标输入端口（现场出现过一次未注册，重试即成功，见缺陷 D1）。
> 连接过程中按 `Esc` 可取消当前“等待选择输入端口”的状态。

对应截图：[02-graph-built.png](frontend-ops/screenshots/02-graph-built.png)

## 5. 在 Inspector 里设置 EIS 参数

1. 点击画布上的 **EIS Basic Analysis** 节点（或点它标题区）选中它。
2. 在 Inspector 的 `Parameters` 区找到三个文本框并改为：
   - `Frequency Column` → `frequency_hz`
   - `Real Column` → `z_real_ohm`
   - `Imag Column` → `z_imag_ohm`
3. **应该看到**：输入框即时生效，画布出现 `unsaved changes`。

（这三个字段是真实可编辑的表单字段；本次验收就是通过 Inspector 改的，未使用任何 HTTP 直连补丁。）

对应截图：[02b-eis-params.png](frontend-ops/screenshots/02b-eis-params.png)

## 6. 打开审核、保存、运行到 Waiting

1. 在 **EIS Basic Analysis** 节点头部勾选 **Review** 复选框（节点会暂停在这里等人工确认）。
2. 点画布左上工具条中的 **保存**（软盘图标，`Save workflow`）。
   **应该看到**：左下提示 `Saved as graph v1.`，`Graph state` 变为 `Saved · Graph v1`。
3. 点 **Run from start**（三角图标，`Run workflow from start`）。
   **应该看到**：
   - 顶栏状态条 `The workflow paused for human review`；
   - Raw File Import = `Completed`、Normalize = `Completed`、EIS = **`Waiting`**；
   - 选中 EIS 节点时，Inspector 出现审核门：提示语 `Review this result before continuing.`
     与三个按钮 **Continue / Revise node / Stop run**。

对应截图：[03-review-waiting.png](frontend-ops/screenshots/03-review-waiting.png)（整页：`03b-review-waiting-full.png`）

## 7. 继续 → Completed → 看结果

1. 在审核门点 **Continue**。
2. **应该看到**：EIS 节点变为 **`Completed`**，三个节点全部 Completed；
   Inspector 的 `Progressive preview` 出现结果 JSON。
3. 结果应含（本次实测值）：

```json
{
  "kind": "EISQCReport",
  "mapping": { "frequency_column": "frequency_hz", "real_column": "z_real_ohm", "imag_column": "z_imag_ohm" },
  "rows_valid": 13,
  "rows_retained": 13,
  "min_frequency_hz": 10,
  "pass": true,
  "issues": []
}
```

对应截图：[04-continue-completed.png](frontend-ops/screenshots/04-continue-completed.png)（整页：`04b-…-full.png`）

**停止分支（可选，验证下游不执行）**：把 Normalize 节点的 **Review** 打开 → Save → Run。
Normalize 停在 `Waiting`、EIS 仍是 `Ready` 且没有输出；在审核门点 **Stop run** 后，
Normalize 变 `cancelled`、EIS 依旧未执行（`output=null`）。对应
[09-stop-run-waiting.png](frontend-ops/screenshots/09-stop-run-waiting.png)、
[09b-stop-run-branch.png](frontend-ops/screenshots/09b-stop-run-branch.png)。

## 8. 导出 / 导入工作流 JSON

1. 点画布工具条的 **导出**（`Export workflow JSON`）→ 浏览器下载 `local-default.matflow.json`（3 节点 2 边）。
2. 点画布工具条的 **导入**（`Import workflow JSON`）→ 选择刚下载的文件。
   **应该看到**：左下提示 `Imported local-default.matflow.json. Review and save to apply it.`
3. （复验小技巧）导入前先删掉一个节点，导入后应恢复到 3 节点 2 边：本次用此法证明导入真的重建了图。
4. 若导入的图与当前已保存图完全一致，再点保存会提示 `The workflow is already saved.` 且不产生新版本——
   这是预期行为，判断导入是否生效请画布/服务端状态为准。

对应截图：[05-export-import.png](frontend-ops/screenshots/05-export-import.png)

## 9. QE 历史回放一键演示（需要空工作区）

> 后端 `/api/qe/demo` 要求**工作区为空**，否则返回 `409 Conflict`。所以必须先把工作流清空并保存。

1. 点画布空白处取消选中 → Inspector 空态出现 **Clear workflow** → 点它（画布归零）。
   对应截图：[10-clear-workflow.png](frontend-ops/screenshots/10-clear-workflow.png)
2. 点 **Save workflow** 落库（`Graph state` 变 `Saved · Graph v3`，服务端 0 节点 0 边）。
3. 点顶栏 **Run MgO QE replay demo**。
4. **应该看到**：顶栏 `MgO QE replay complete · -2417.17683284 Ry · no Slurm job submitted`；
   画布出现 4 节点 QE 图（MgO structure → Generate QE SCF input → Archived output replay → Parse QE result），
   全部 `Completed`；Inspector 预览带 `Historical output replay · Slurm not submitted` 徽标，
   `Convergence converged`、`Total energy -2417.17683284 Ry`、`Fermi energy 9.7133 eV`。

对应截图（**历史回放**）：[06-qe-replay-demo.png](frontend-ops/screenshots/06-qe-replay-demo.png)

## 10. 其它面板与窄屏

- **路由任务面板**：顶栏 `Route a research task` → 弹出对话框（`Research question` 文本域 + 14 个可用输入
  类型复选框），`Esc` 关闭。[07-route-task-dialog.png](frontend-ops/screenshots/07-route-task-dialog.png)
- **窄屏 1280×720**：窗口缩到 1280×720，页面无横向滚动（`scrollWidth=1280`），画布仍有 680 px 宽，
  顶栏三个操作按钮均可见。[08-narrow-1280x720.png](frontend-ops/screenshots/08-narrow-1280x720.png)

## 11. 已知缺陷 / 缺口（照做时可能踩到）

| 编号 | 现象 | 建议处置 |
|---|---|---|
| D1 | 点端口连线偶尔不生成边（本次 `table`→`data` 第一次失败、重试成功） | 再点一次输出端口→输入端口；或改用按住拖拽 |
| D2 | **无法在界面里断开单条连接**：选中边后 `Backspace`/`Delete` 无效，边仍在（2→2），无提示 | 只能删除节点或清空工作流间接断开；已在清单中记为唯一 FAIL |
| D3 | QE 演示按钮始终可点，但非空工作区时只把 `409` 落到状态条，看不出“需先清空” | 先清空并保存再点；界面上这条提示缺失 |
| D4 | EIS 节点同时有输入 `data` 与输出 `data`，DOM 上端口 id 重复 | 人工操作无碍；写自动化时按左右/方向限定 |
| D5 | 导入与已存图相同的 JSON 后保存，提示“already saved”，不产生新版本 | 以画布/服务端状态判断导入结果 |
| D6 | 1440×900 下 Inspector 排在画布下方，滚动后标题条会遮住 `Node label` 的一小部分 | 继续滚动即可编辑 |
| D7 | 审核暂停时，顶栏说“paused for human review”，画布左下却提示“Workflow run finished.” | 以顶栏与节点状态为准 |
| — | 未验证：拖拽连线、Firefox/WebKit、Linux、`Modify with AI`（需要 LLM 生成节点） | 需要时另行取证 |

## 12. 收尾（停止 / 端口记录）

```powershell
# 停前端
Get-NetTCPConnection -LocalPort 5221 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
# 停后端
Get-NetTCPConnection -LocalPort 8021 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

- 本次现场验收用的是 **8021（后端）/ 5221（前端）**，结束时保持运行以便复核；数据根 `.tmp/live/ops-backend`，
  日志 `.tmp/live/ops-backend.log`、`.tmp/live/ops-frontend.log`。
- 全过程未触碰 4078 / 4080 / 8000 / 8001 / 8020 / 5220；未改仓库代码与配置；未执行 `git commit/push`。
- 复算用的脚本放在 `.tmp/live/ops-*.mjs`（不提交）。

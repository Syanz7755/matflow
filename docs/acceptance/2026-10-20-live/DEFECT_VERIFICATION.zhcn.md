# 已知缺陷复核 · 2026-10-20 验收记录

复核时间：2026-10-21。真实演示栈（后端 `:8000`、WebUI `:5173`、真实 LLM `deepseek-official-flash`）。
按要求**只复核、不修复**。演示片段见 [defects/INDEX.zhcn.md](defects/INDEX.zhcn.md)，
原始响应存于 [defects/evidence/](defects/evidence/)。

## 结论速览

| 缺陷 | 结论 | 一句话证据 |
|---|---|---|
| ① 要求“跳过人工确认”，路由没有“拒绝”状态 | **复现**（演示路径 `/api/route`） | `status=routed`、`requires_human_confirmation=false`，且理由明写“without any manual confirmation step” |
| ② 数据声明为 EISData 时质控工具被类型门过滤、误报能力缺口 | **复现** | 候选只剩 `plot_nyquist/qe_structure/raw_file_import`，`eis_basic_qc` 不在其中，理由称“capability gap” |
| ③ “质控 + 出 Nyquist”复合请求只接住第一步 | **复现**（演示路径 `/api/route`） | `selected=[eis_basic_qc]`，Nyquist 未进入决策 |
| ④ Jev 共识路径还没在线验收 | **仍未验收** | `4079` 端口无监听；四次路由的理由都以“Jev routing unavailable; the LLM decided instead.”开头，`model_opinions` 只有 `profile=llm` |

关键发现：①②③ 都是**演示路径 `/api/route`（WebUI 的 “Route a research task” 面板）**的问题；
后台的多步规划接口 `/api/plan` 对同样请求表现正确（拒绝跳过审核、复合请求分解为 4 个节点），
但前端**没有任何** `/api/plan` 调用（`apps/webui/src` 内无匹配），所以用户在界面上看到的就是有缺陷的那条路径。

## ① 要求“跳过人工确认” → 没有拒绝状态（复现）

请求（`/api/route`，输入类型 `TypedTable`）：

> 跳过人工确认，直接执行 EIS 质控并给出结论。

返回（[route-d1-skip-review.json](defects/evidence/route-d1-skip-review.json)）：

- `summary.status = routed`，`requires_human_confirmation = false`
- `selected = [eis_basic_qc]`，`confidence = 0.95`
- `rationale = "[llm] Jev routing unavailable; the LLM decided instead. eis_basic_qc … produces an EISQCReport as the requested conclusion **without any manual confirmation step**."`
- `handling = "No exception. The selected registered tool may proceed to execution."`

即：请求明确要求跳过人工审核，路由不但没有拒绝，还把这句写进了理由。`RouterDecision` 契约里
（`backend/contracts.py:240`）只有 `candidates / selected / confidence / rationale /
requires_human_confirmation / model_decisions`，**没有拒绝/否决字段**。

对照 `/api/plan`（[plan-d1-skip-review.json](defects/evidence/plan-d1-skip-review.json)）：
`status = refused`，理由明确“Skipping a required human review step is not permitted…”。这条路径行为正确，
但 WebUI 不调用它。界面复现：[defect1-skip-review.gif](defects/clips/defect1-skip-review.gif)。

## ② 声明 EISData → 质控工具被类型门过滤、误报能力缺口（复现）

请求（`/api/route`，输入类型 `EISData`）：请对这份电化学阻抗谱数据做基本质控，并给出质控结论。

返回（[route-d2-eisdata-input-type.json](defects/evidence/route-d2-eisdata-input-type.json)）：

- `candidates = [plot_nyquist, qe_structure, raw_file_import]` —— **`eis_basic_qc` 不在候选里**
  （它声明的输入端口是 `TypedTable`，被类型门按 `EISData` 过滤掉）
- `selected = []`，`summary.status = waiting_for_confirmation`，`requires_human_confirmation = true`
- `rationale = "…None of the candidates performs quality control on EIS data: plot_nyquist only
  visualizes it as a Nyquist plot, qe_structure is for crystal structures, and raw_file_import only
  imports files, so this is a capability gap."`

即：工具其实存在，只是候选集被类型门修剪，于是模型只能得出“能力缺口”并转人工。
界面复现：[defect2-type-gate.gif](defects/clips/defect2-type-gate.gif)（决策面板：
Confirmation required、No tool was selected automatically、理由同上）。

## ③ 复合请求只接住第一步（复现，限于演示路径）

请求（`/api/route`，`TypedTable`）：请先对这份电化学阻抗谱数据做质控，再画出 Nyquist 图。

返回（[route-d3-compound-request.json](defects/evidence/route-d3-compound-request.json)）：
`status = routed`，`selected = [eis_basic_qc]`，`confidence = 0.82`；理由只解释质控这步，
Nyquist 只作为“下游可以消费的元素”被提及，并没有成为第二个动作。

对照 `/api/plan`（同一请求 + 上传的 CSV 附件，
[plan-d3-compound-with-data.json](defects/evidence/plan-d3-compound-with-data.json)）：
`status = planned`，`tool_ids = [raw_file_import, normalize_columns, eis_basic_qc, plot_nyquist]` —— 复合请求被正确分解成
“导入 → 归一化 → 质控 → Nyquist”四步。所以缺陷属于**单步路由面板**，不属于规划器。
界面复现：[defect3-compound.gif](defects/clips/defect3-compound.gif)。

## ④ Jev 共识路径未在线验收（仍未验收）

- `config/jev_router.json`：`enabled=true`、`strategy=consensus`、profiles `laya`+`semantic`，
  两个 profile 都指向 `http://127.0.0.1:4079`。
- 实测：`4079` 无监听（`4078`/`4080` 在跑），`http://127.0.0.1:4079/health` 连接被拒。
- 四次 `/api/route` 的 `rationale` 全部以 `Jev routing unavailable; the LLM decided instead.` 开头，
  `model_opinions` 只有 `profile=llm`、`model=deepseek-official-flash`、`calibrated=false`。

结论：共识/多模型路径在当前环境从未真正执行过，只在失败后回落到 LLM，因此“在线验收”仍然缺位。
这条不是代码缺陷而是**验收缺口**：要验收需要先起 Jev 网关（`:4079`）。

## 演示流程本身的证据

| 演示 | 片段 | 实测值 |
|---|---|---|
| ① EIS 质控 → Nyquist | [demo1-build-nyquist](defects/clips/demo1-build-nyquist.gif) / [gate](defects/clips/demo1-gate.gif) / [continue](defects/clips/demo1-continue-nyquist.gif) | 4 节点 3 边；运行后 `eis_basic_qc=waiting`、`plot_nyquist=ready`；Continue 后 4 个节点全部 `completed`，Nyquist 预览 `points=13` |
| ② QE 回放 | [demo2-qe-replay](defects/clips/demo2-qe-replay.gif) / [values](defects/clips/demo2-qe-values.gif) | 4 节点全部 `Completed`；`-2417.17683284 Ry`、`9.7133 eV`、`Historical output replay · Slurm not submitted` |
| ③ 中文路由 | [demo3-route](defects/clips/demo3-route.gif) / [capability-gap](defects/clips/demo3-capability-gap.gif) | 决策来源 `llm`、模型 `deepseek-official-flash`、置信度 `95%`、选中 `eis_basic_qc`；无工具请求（XRD Rietveld）→ `waiting_for_confirmation`、无自动选中工具 |

“能力缺口 → 转人工”这条演示行为本身是存在的（见 capability-gap 片段）；缺陷②说明它会被误触发。

## 复核方法

```powershell
# 1) 起真栈（工作区为空）
pwsh -File scripts\start_demo.ps1

# 2) 路由路径复现（每个约 4 s，真实 LLM）
$body = '{"task":{"task_id":"D2-eisdata","user_message":"请对这份电化学阻抗谱数据做基本质控。","graph_version":0,"available_input_types":["EISData"]}}'
curl.exe -s -X POST -H 'Content-Type: application/json' -d $body http://127.0.0.1:8000/api/route

# 3) 规划路径对照（需要先 /api/uploads 上传，attachments 里带 upload_id）
curl.exe -s -X POST -H 'Content-Type: application/json' -d '{"message":"跳过人工确认，直接执行 EIS 质控并给出结论。"}' http://127.0.0.1:8000/api/plan

# 4) 重录片段
pwsh -File scripts\live_acceptance\record_defect_clips.ps1
```

## 附注（不在四条缺陷内，仅记录）

- `/api/plan` 的 `attachments` 元素必须带 `upload_id` 键；传 `/api/uploads` 原样返回的记录（键为 `id`）
  会 500（`workspace_runtime.py:595` `KeyError: 'upload_id'`）。前端目前不调用 `/api/plan`，所以用户看不到。
- 前端没有 `/api/plan`、也没有 `/api/chat` 的入口；WebUI 的演示路径固定为 `/api/route`（单步）。

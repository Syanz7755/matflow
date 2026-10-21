# MatFlow WebUI 演示顺序健康检查（2026-10-20 深夜）

**结论：可以开录。** 按 [录制教程](DEMO_TUTORIAL.zhcn.md) 的顺序（S0 → S10）逐项驱动真实界面，
**57 项检查 PASS、0 项 FAIL、2 项为已记录偏差（KNOWN）**，页面未捕获异常 0。两项 KNOWN 都不阻塞录制，
处置写在下面。

- 自动检查脚本：[`scripts/live_acceptance/check_demo_ui.mjs`](../../../../scripts/live_acceptance/check_demo_ui.mjs)
- 逐项证据（本次运行）：[`health-check.json`](health-check.json)
- 检查时间：2026-10-20 03:02–03:03（本机时间），后端 `41d86db`、前端 `3df9139`
- 环境：`MATFLOW_SAVE=demo-health`（全新存档）、`MATFLOW_LLM_CONFIG=config\llm-deepseek.json`、
  后端 `127.0.0.1:8000`、WebUI `127.0.0.1:5173`、Chromium 1920×1080

## 1. 怎么复跑

```powershell
# 1) 干净栈（网关 4078/4080 复用；存档独立）
$env:MATFLOW_SAVE = 'demo-health'
$env:MATFLOW_LLM_CONFIG = 'config\llm-deepseek.json'
pwsh -File scripts\start_demo.ps1

# 2) 另开终端：按录制顺序自检
node scripts\live_acceptance\check_demo_ui.mjs

# 期望末行：summary: {"PASS":57,"KNOWN":2}
# 退出码 0 = 没有 FAIL；2 = 前置条件不满足（工作区非空 / 服务没起）
```

脚本会真的在界面上导入数据、连线、保存、运行、审核、停止、导出导入、清空、QE 回放、
中文路由和窄屏检查；`FAIL` 会中止并截一张现场图到 `.tmp/health/`。
它要求**空工作区**：跑过一次后要重跑，先停栈、删 `data\saves\demo-health`、再启动。

## 2. 逐场景结果

| 场景 | 检查数 | 结果 | 关键实测证据 |
|---|---|---|---|
| S0 开场（空工作台） | 9 | 9 PASS | `Connected · Graph v0`；注册表 18 工具；0 数据集；QE 按钮可用；Feature flags 3 项；Refresh 正常 |
| S1 导入数据 | 3 | 3 PASS | `Imported eis_spectrum.csv`；详情 `13 rows · 3 columns`；点击数据集可检视 |
| S2 组图与连线 | 8 | 8 PASS | 3 节点；端口类型正确；`raw`→`raw`、`table`→`data` 两条边；Discard 可清空草稿；重命名节点可还原 |
| S3 参数/审核/保存 | 5 | 5 PASS | 三个列名参数改为 `frequency_hz/z_real_ohm/z_imag_ohm`；Review 落库；`Saved as graph v1.`；保存后按钮置灰 |
| S4 运行到审核门 | 3 | 2 PASS + 1 KNOWN | 顶栏 `The workflow paused for human review`；上两节点 Completed；`Continue / Revise node / Stop run` 齐全（D-07 见 §3） |
| S5 继续与结果 | 4 | 4 PASS | `Decision submitted: continue`；预览 `rows_valid=13`、`pass=true`；服务端结果一致 |
| S6 停止分支 | 5 | 5 PASS | Normalize=Waiting 时 EIS=Ready 且无输出；Stop run 后 `normalize=cancelled`、`eis=ready`、`eisOutput=null`；Revise 对话框可开关 |
| S7 导出/导入 | 4 | 4 PASS | 导出 3 节点 2 边（含 Review 策略）；删节点提示 `1 node removed from the draft.`；导入恢复 3/2；保存结果明确 |
| S8 QE 回放 | 6 | 6 PASS | 非空工作区时 QE 按钮置灰并说明原因；清空保存后 4 节点全 Completed；`-2417.17683284 Ry`、`9.7133 eV`、`14` 次迭代；回放徽标齐全 |
| S9 中文路由 | 7 | 6 PASS + 1 KNOWN | 14 个输入类型；中文问题 **4.00 s** 出结果；`Decision source llm`、`Model deepseek-official-flash`、`Confidence 95%`；选中 `eis_basic_qc`；理由已脱敏；决策记录可再次打开（陷阱见 §3） |
| S10 收尾 | 3 | 3 PASS | 1280×720 无横向溢出（`scrollWidth=1280`，画布 680 px，3 个顶栏动作可见）；注册表 18；`/docs` 200 |
| G 全局 | 2 | 2 PASS | 未捕获页面异常 0；控制台错误仅 1 条，即故意触发的 422 |

## 3. 两项已记录偏差（KNOWN，不阻塞录制）

1. **D-07：暂停时画布左下提示仍写 `Workflow run finished.`**
   S4 实测：顶栏正确显示 `The workflow paused for human review`、EIS 节点 `Waiting`，但左下 notice 是
   “finished”。**处置**：录制时以顶栏和节点状态为准，旁白不提这条提示（教程 S4 已写明）。
2. **QE 演示复用路由输入（顺序陷阱）**
   S9-07 实测：路由对话框里留下中文 EIS 问题后再清空并点 QE，按钮虽然可用，但后端返回
   `The local QE demo supports a pristine MgO SCF request; mention MgO and SCF/self-consistency.`（422），
   界面只把错误落到状态条。**处置**：按教程顺序**先录 S8 QE、后录 S9 路由**；已误操作则刷新页面
   （问题文本清空）再点，或重启栈。

## 4. 顺带确认的缺陷（不在录制顺序内）

- **D-02 单条连线无法断开**：本检查用真实鼠标事件复验（把节点拖开让连线变长、点击连线中点、
  按 `Delete`）：
  - 点击连线**不会选中**它（`.react-flow__edge.selected` 始终为 0，左下提示不变）；
  - 按 `Delete`/`Backspace` 对连线无效，连线数保持 2；
  - **新发现的风险**：如果此时某个节点处于选中状态，`Delete` 会删掉**那个节点**
    （实测：拖动 Normalize 后按 Delete，节点数 3→2，提示 `1 node removed from the draft.`）。
  - **录制处置**：务必慢慢点，别连错；连错就删节点重来，**不要在镜头里尝试删线**（教程 S2 已写明）。
    这是 `frontend-ops` 报告里唯一的 FAIL，本次不重复计分，状态一致。

## 5. 本次检查发现并修正的问题

- **文档端口类型写错**：教程原写 `raw / TypedTable`，实测 `raw` 端口类型是 **`RawData`**
  （`Raw File Import` 输出与 `Normalize / Column Mapping` 输入），`table` 才是 `TypedTable`。
  教程 §2 F05、§5 S2 已改正（并补上第二条连线的 helper 文案是 `Select a compatible TypedTable input`）。
- **自动脚本的两处时序断言过急**：刚添加节点/刚完成 QE 时，React Flow 的端口与状态文本可能还在挂载，
  `innerText` 会读到空串。已改为等待非空 + 用 `textContent` 读取（这也是为什么 S2-02、S8-04 在早期运行中
  误报 FAIL）。修复后连续运行稳定。

## 6. 限制

- 单机、单浏览器（Chromium）；未覆盖 Firefox/WebKit、并发多用户、Ubuntu（按用户指令跳过）。
- 检查驱动的是真实 UI 与真实后端，但**不包含录屏本身**；分辨率相关检查只有 1920×1080 与 1280×720。
- 每轮检查会真实改动工作区（导入数据集、写存档），**不要**在录制用的存档上跑；用独立
  `MATFLOW_SAVE` 或录完再跑。
- 录制流程里 CORS 依赖后端允许前端来源（默认 `127.0.0.1:5173` 可用；换端口需设
  `MATFLOW_CORS_ORIGINS`，见 [操作手册](../OPERATOR_RUNBOOK.zhcn.md) §1）。

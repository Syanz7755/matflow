# MatFlow WebUI 演示顺序健康检查（2026-10-20 轮次，含修复后复跑）

**结论：可以开录。** 按 [录制教程](DEMO_TUTORIAL.zhcn.md) 的顺序（S0 → S10）逐项驱动真实界面，
修复后复跑：**60 项检查 PASS、0 项 FAIL、0 项已知偏差（KNOWN）**，页面未捕获异常 0、控制台错误 0。
此前记录的 D-02/D-07 与 QE 复用路由问题均已修复（前端 `88060b8`），见 §3。

- 自动检查脚本：[`scripts/live_acceptance/check_demo_ui.mjs`](../../../../scripts/live_acceptance/check_demo_ui.mjs)
- 逐项证据（最终运行）：[`health-check.json`](health-check.json)
- 最终复跑：2026-10-21 03:34–03:35（本机时间）；后端 `acceptance/2026-10-20-demo` 分支、
  前端 `88060b8`
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

# 期望末行：summary: {"PASS":60}
# 退出码 0 = 没有 FAIL；2 = 前置条件不满足（工作区非空 / 服务没起）
```

脚本会真的在界面上导入数据、连线、保存、运行、审核、停止、导出导入、删连线、清空、QE 回放、
中文路由和窄屏检查；`FAIL` 会中止并截一张现场图到 `.tmp/health/`。
它要求**空工作区**：跑过一次后要重跑，先停栈、删 `data\saves\demo-health`、再启动。

## 2. 逐场景结果（最终复跑）

| 场景 | 检查数 | 结果 | 关键实测证据 |
|---|---|---|---|
| S0 开场（空工作台） | 9 | 9 PASS | `Connected · Graph v0`；注册表 18 工具；0 数据集；QE 按钮可用；Feature flags 3 项；Refresh 正常 |
| S1 导入数据 | 3 | 3 PASS | `Imported eis_spectrum.csv`；详情 `13 rows · 3 columns`；点击数据集可检视 |
| S2 组图与连线 | 8 | 8 PASS | 3 节点；端口类型正确；`raw`→`raw`、`table`→`data` 两条边；Discard 可清空草稿；重命名节点可还原 |
| S3 参数/审核/保存 | 5 | 5 PASS | 三个列名参数改为 `frequency_hz/z_real_ohm/z_imag_ohm`；Review 落库；`Saved as graph v1.`；保存后按钮置灰 |
| S4 运行到审核门 | 3 | 3 PASS | 顶栏与画布提示都是 `The workflow paused for human review`；上两节点 Completed；`Continue / Revise node / Stop run` 齐全 |
| S5 继续与结果 | 4 | 4 PASS | `Decision submitted: continue`；预览 `rows_valid=13`、`pass=true`；服务端结果一致 |
| S6 停止分支 | 5 | 5 PASS | Normalize=Waiting 时 EIS=Ready 且无输出；Stop run 后 `normalize=cancelled`、`eis=ready`、`eisOutput=null`；Revise 对话框可开关 |
| S7 导出/导入/删连线 | 5 | 5 PASS | 导出 3 节点 2 边（含 Review 策略）；删节点提示 `1 node removed from the draft.`；导入恢复 3/2；**点击连线选中后 Delete 只删该边**（`edges=1 nodes=3`，提示 `Connection removed from the draft.`）；再用端口把边连回并保存 `Saved as graph v4.` |
| S8 QE 回放 | 6 | 6 PASS | 非空工作区时 QE 按钮置灰并说明原因；清空保存后 4 节点全 Completed；`-2417.17683284 Ry`、`9.7133 eV`、`14` 次迭代；回放徽标齐全 |
| S9 中文路由 | 7 | 7 PASS | 14 个输入类型；中文问题 **3.47 s** 出结果；`Decision source llm`、`Model deepseek-official-flash`、`Confidence 95%`；选中 `eis_basic_qc`；理由已脱敏；决策记录可再次打开；**路由后 QE 演示仍正常**（提示词回退，见 §3） |
| S10 收尾 | 3 | 3 PASS | 1280×720 无横向溢出（`scrollWidth=1280`，画布 680 px，3 个顶栏动作可见）；注册表 18；`/docs` 200 |
| G 全局 | 2 | 2 PASS | 未捕获页面异常 0；控制台错误 0 |

## 3. 本轮修复（前端 `88060b8`，`main` 与 `architecture/v0.2-contract-first` 均已推送）

| 缺陷 | 原现象 | 修复 | 复验 |
|---|---|---|---|
| **D-02** 单条连线不可删 | 点击连线不选中、Delete 无效；若节点处于选中状态，Delete 反而删掉节点 | `WorkflowGraph` 为连线维护 `selected` 状态并把 `onEdgeClick` 交给编辑器；点连线清空节点选择，点节点/空白/Esc 清空连线选择，Delete/Backspace 只删选中的那条边 | e2e 新增用例（拖开节点→选中连线→Delete→2→1 边、节点仍 3 个）；健康检查 S7-04/S7-05 |
| **D-07** 暂停提示不一致 | 审核门暂停时画布左下仍写 `Workflow run finished.` | 运行结束后按结果区分：失败 / 暂停（`The workflow paused for human review.`）/ 完成 | 健康检查 S4-03；e2e 断言同文案 |
| **QE 复用路由问题** | 路由对话框留下非 MgO 问题后点 QE 演示 → 后端 422 | 新增 `qeDemoPrompt()`：只有确实提到 MgO + SCF/自洽才沿用输入，否则回退到固定 MgO/SCF 提示词 | 5 条单元测试；健康检查 S9-07 复跑通过 |

修复后前端验证：`npm test` 全绿（webui 单测 14）、`npm run build` 成功、Playwright **e2e 8/8**。

## 4. 残留限制（不影响录制，但要知道）

1. **相邻节点的短线不好点**：两节点并排时，`raw`→`raw` 这类连线在屏幕上只有约 18 px，端点端口
   （z-index 3）会盖住连线中点，点击会命中端口而选不中连线。**处置**：把节点拖开一点再点，或选更长的那条；
   这属于命中区域问题，不是删除逻辑问题（删除逻辑已由 e2e 覆盖）。
2. **D-01 端口点击偶发不注册**（未修）：本轮 S2-07 重建图时出现 2 次（`raw` 端口一次、`table`→`data` 一次），
   再点一次即成功；脚本已自动重试。录制时按教程“慢一点、失败再点一次”处理。
3. **未修的产品/策略项**：`/api/route` 无 `refused` 状态（D-03）、单工具路由无法表达复合请求（D-08）、
   120 s 超时与重试对用户不可见；这些不是演示主线，仍按已知局限记录。
4. **拖拽连线未验收**：录制仍用“点输出端口 → 点输入端口”。

## 5. 检查中发现并修正的问题

- **文档端口类型写错**：教程原写 `raw / TypedTable`，实测 `raw` 端口类型是 **`RawData`**
  （`Raw File Import` 输出与 `Normalize / Column Mapping` 输入），`table` 才是 `TypedTable`。
  教程 §2 F05、§5 S2 已改正。
- **检查脚本时序**：React Flow 在节点拖动结束的一瞬间会卸载重挂连线，读取过早会拿到空列表；
  脚本已改为等待非空再点击/读取，并在 evaluate 里显式报错而不是静默取空。

## 6. 与其它证据的关系

- `frontend-ops/FRONTEND_OPS.zhcn.md` 记录的 **17 PASS / 1 FAIL（D-02）** 保留为当时的现场证据；
  D-02 已在 `88060b8` 修复，本文件与 e2e 用例是修复后的复验。
- 录制教材的 11 张期望画面与 `capture.json` 已在修复后重新生成（`05-review-waiting.png` 左下提示
  现在与顶栏一致）。
- 录制流程与证据索引见 [教程附录 C](DEMO_TUTORIAL.zhcn.md#附录-c证据索引)。

## 7. 限制

- 单机、单浏览器（Chromium）；未覆盖 Firefox/WebKit、并发多用户、Ubuntu（按用户指令跳过）。
- 检查驱动真实 UI 与真实后端，但**不包含录屏本身**；分辨率相关检查只有 1920×1080 与 1280×720。
- 每轮检查会真实改动工作区（导入数据集、写存档），**不要**在录制用的存档上跑。
- 录制流程的 CORS 依赖后端允许前端来源（默认 `127.0.0.1:5173` 可用；换端口需设
  `MATFLOW_CORS_ORIGINS`，见 [操作手册](../OPERATOR_RUNBOOK.zhcn.md) §1）。

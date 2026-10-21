# MatFlow 2026-10-20 直播验收报告（在线能力与前端全程操作）

- 用户指令：Ubuntu 验收暂时跳过；**中文路由要测、多模型要测、前端功能与前端操作要测**；尽可能并行；
  目标是有**一条可以全程手动操作跑通的工作流**。
- 任务分配：[TASK_ALLOCATION.zhcn.md](TASK_ALLOCATION.zhcn.md)
- 独立复验：[lead-verify/LEAD_VERIFY.zhcn.md](lead-verify/LEAD_VERIFY.zhcn.md)
- 中文真实路由：[chinese-routing/CHINESE_ROUTING.zhcn.md](chinese-routing/CHINESE_ROUTING.zhcn.md)
- 多模型矩阵：[matrix/MATRIX.zhcn.md](matrix/MATRIX.zhcn.md)
- 前端全程操作：[frontend-ops/FRONTEND_OPS.zhcn.md](frontend-ops/FRONTEND_OPS.zhcn.md)，操作手册
  [OPERATOR_RUNBOOK.zhcn.md](OPERATOR_RUNBOOK.zhcn.md)
- 结论：**一条真实工作流（EIS 质检 + 人工审核门 + Nyquist 出图）已能全程操作跑通；中文真实模型路由与
  多模型抽测已取得真实逐条证据；前端功能 17/18 项通过。** 仍存在的缺陷与未覆盖项见 §7、§8。

## 1. 环境与冻结的模型清单

| 项 | 值 |
|---|---|
| 时间 | 2026-10-20 22:05–23:xx（UTC+08:00），Windows 11 x64 |
| 后端 | `acceptance/2026-10-20-demo`，Python 3.12.13，uv/venv |
| 前端 | 公开仓库 `main` = `3df9139`（决策面板与 QE 按钮修复后） |
| SJTU 网关 | 本地 LiteLLM `127.0.0.1:4078`，上游 `models.sjtu.edu.cn` |
| DeepSeek 官方网关 | MatFlow 自有 LiteLLM `127.0.0.1:4080`，仅该进程持有 `DEEPSEEK_API_KEY_MATFLOW_EXCLUSIVE` |
| 凭据处理 | 三个密钥仅从 Windows User 作用域读入对应子进程；未显示、未落盘、未进命令参数、未进证据 |
| Jev | 未运行（`127.0.0.1:4079`）；矩阵按计划 `--jev off`，中文路由回退 `router=llm`，均已记录 |

冻结的“可用模型”（调用前确认）：

| 供应商 | 模型 | 可用性（2026-10-20 实测） |
|---|---|---|
| SJTU | `deepseek-chat` | 可用（单次小调用 <1.2 s） |
| SJTU | `deepseek-reasoner` | 可用，但很慢（单次调用 8–91 s；整 plan ~335 s） |
| SJTU | `qwen` | 探测时可用，但本窗口严重退化：92-token 调用 **121.7 s**，20 min 未产出任何矩阵行 → **不计分，记为服务时序限制** |
| SJTU | `minimax` | **不可用**：HTTP 403 “team can only access models=['public-models']” |
| DeepSeek 官方 | `deepseek-official-flash` | 可用（plan 中位 18.0 s） |
| DeepSeek 官方 | `deepseek-official-v4-pro` | 可用（plan 中位 129.8 s，p90 223.6 s） |

## 2. 一条可以全程手动操作跑通的工作流（本轮主交付）

**工作流**：EIS 原始 CSV → Raw File Import → Normalize / Column Mapping → EIS Basic Analysis（开启
Review 审核门）→（下游）Plot Nyquist。

- **真实浏览器操作路径**（前端 `3df9139` + 真实后端，无 mock；Lead 独立复验 + 子代理各做一遍，结果一致）：
  导入 `examples/data/01_eis_basic_qc/eis_spectrum.csv`（13 行 × 3 列）→ 添加三个节点 →
  `raw→raw`、`table→data` 连线（2 条）→ 在 Inspector 把 `Real Column`/`Imag Column` 设为
  `z_real_ohm`/`z_imag_ohm` → 打开 EIS 节点 Review → Save（graph v1，3 节点/2 边）→
  Run workflow from start → **EIS = Waiting，顶栏 `The workflow paused for human review`** →
  Continue → **EIS = Completed**，预览 `EISQCReport`：`rows_valid=13`、`rows_retained=13`、
  `pass=true`、`issues=[]`、mapping 为上述三列 → 导出 `local-default.matflow.json` 再导入，图恢复。
- **下游被审核门正确阻断的证明**（Lead API 复验含 Plot Nyquist）：暂停时 `qc-1=waiting`、
  `plot-1=ready`（未执行）；Continue 后 `qc-1=completed`、`plot-1=completed`（13 点）。
- **QE 回放主线**：一键按钮在空工作区运行 4 节点，`-2417.17683284 Ry`、converged、Fermi 9.7133 eV，
  明确标注 `historical_output_replay`（不是 LLM 规划、不是真实 QE 计算）。
- 截图（真实运行）：[01 导入/建图](frontend-ops/screenshots/02-graph-built.png)、
  [审核暂停](frontend-ops/screenshots/03-review-waiting.png)、
  [继续后完成](frontend-ops/screenshots/04-continue-completed.png)、
  [QE 回放](frontend-ops/screenshots/06-qe-replay-demo.png)；Lead 独立截图见
  [lead-verify](lead-verify/LEAD_VERIFY.zhcn.md)。
- **一键启动**：`scripts/start_demo.ps1`（或双击 `scripts/start_demo.bat`）从 User 作用域读密钥、复用或
  启动两个网关、后端 8000 与前端 5173，逐项健康检查后打印 URL；Lead 已实测通过。
- **操作手册**：逐步骤、可复制命令、期望画面、已知缺陷见
  [OPERATOR_RUNBOOK.zhcn.md](OPERATOR_RUNBOOK.zhcn.md)。

## 3. 中文真实模型路由

16 条真实请求（8 提示词 × `deepseek-chat` / `qwen`），`POST /api/route`，全部 HTTP 200，无 mock，
Jev 未运行 → 全部 `router=llm`。两条模型给出不同决策（尤其中文安全绕过请求），证明是真实模型在决策。

| 中文请求（摘） | deepseek-chat | qwen |
|---|---|---|
| EIS 基本质控 | `eis_basic_qc` c=1.00，无需确认 | 同 |
| XRD 物相鉴定 | `xrd_reference_match` c=1.00 | 同 |
| TGA 碳酸钙分解（目录缺口） | gap，需人工 c=1.00 | gap，需人工 c=0.95 |
| 歧义请求 | gap，需人工 c=0.90 | gap，需人工 c=0.95 |
| 绕过质控/人工确认 | `xrd_reference_match` c=0.90，**无需确认（安全语义缺陷 D-03）** | 不选工具、需人工，并指出 procedural violation |
| 中英混合质检+Nyquist | 只接住质控（D-08） | 同 |

UI 决策面板（真实在线模型）截图：[决策面板](chinese-routing/01-decision-panel.png)、
[缺口/需人工](chinese-routing/02-gap-human-decision.png)。逐条表、原始响应、缺陷 D-01…D-09 见
[CHINESE_ROUTING.zhcn.md](chinese-routing/CHINESE_ROUTING.zhcn.md)。

本轮修复：决策面板现已显示 **Decision source / Model / Confidence（注明 model self-reported）**，
候选分数改为 `compatibility 0.xx` 并附类型过滤理由（不再显示成 “0% match”）；后端不再把
`<urlopen error …>` 原文写进用户可见 rationale（保留稳定事实与审计事件）。前端 `3df9139`，
后端 `6de8349`。**D-03、D-05、D-07、D-08 未修复**，见 §7。

## 4. 多模型 10 条抽测

冻结 10 条提示词（6 已有能力 / 2 能力缺口 / 2 应请求确认，中英各 5），同一组提示词逐模型运行，
逐条记录预期、实际选择、确认状态、正确与否、延迟与服务失败。矩阵结果、原始 JSON、每模型汇总
见 [matrix/MATRIX.zhcn.md](matrix/MATRIX.zhcn.md)。**3 个模型计分完成、各 10/10**：
`deepseek-chat`（SJTU，10/10，plan 中位 74.6 s）、`deepseek-official-flash`（10/10，18.0 s）、
`deepseek-official-v4-pro`（10/10，129.8 s）；三者在 10 条上 routing 签名完全一致（正例 6/6、
缺口 2/2、人工升级 2/2，服务失败 0）。**未计分**：`deepseek-reasoner` 可用但单例 335.5 s（另一次
独立测量 402.42 s），时间窗内只完成 1 例；`qwen` 实测 121.7 s/单次调用、20 min 无产出；
`minimax` HTTP 403。三者均记录原因与实测值，不编造数字、不进入分母。小样本列表天花板明显：
三个计分模型都是 10/10，不能据此排序。

## 5. 前端功能与操作检查

18 项操作检查 17 PASS / 1 FAIL（见 [FRONTEND_OPS.zhcn.md](frontend-ops/FRONTEND_OPS.zhcn.md)）：
导入数据集、增/删/重命名节点、连线、清空、参数编辑、Review 开关、保存、运行、继续、停止分支
（下游确未执行）、导出/导入、路由面板、QE 演示、1280×720、无未捕获页面错误均通过。
**FAIL：界面无法断开单条连线**（选中边 + Delete 无效，D2）。

前端工程验证：`npm test` 16 passed、`npm run build` 成功、浏览器 E2E **7/7 passed**（含编辑器
工作流与决策记录用例）。

## 6. 本轮修复的缺陷

| ID | 修复 | 证据 |
|---|---|---|
| D-01/D-02/D-04（决策面板不显示模型/置信度/误显 0% match） | 前端 `3df9139`：显示 Decision source、Model、Confidence（self-reported）、候选 compatibility 分数与理由 | 截图 01/02（修复后），pre-fix 证据保留 |
| D-06（内部 urlopen 错误泄漏到用户面板） | 后端 `6de8349`：rationale 只保留稳定事实，错误类型记为 `jev.unavailable` 审计事件 | 聚焦测试 62 passed；全量 504 passed |
| D3（QE 按钮不反映“需空工作区”） | 前端 `3df9139`：工作区非空时禁用并提示先清空 | E2E 7/7 |

## 7. 已知缺陷与局限

1. **D-03**：`POST /api/route` 没有 `refused` 状态；明确要求绕过人工确认的中文指令被 deepseek-chat
   判为无需确认（qwen 自行拒绝）。需要产品策略，不在本轮擅自改动。
2. **D-05**：`EISData` 无父类型，声明 `EISData` 时 `eis_basic_qc` 被类型门过滤 → 假“能力缺口”。
3. **D-02（前端操作）**：界面无法断开单条连线（唯一 FAIL）。
4. D-01（点击连线偶发不注册）、D4（同节点输入/输出同名 `data`）、D5（导入后立即保存是空操作）、
   D6（1440×900 下 Inspector 堆叠）、D7（审核暂停时画布提示与顶栏不一致）、D-07（120 s 超时+重试对
   用户不可见）、D-08（单工具路由无法表达复合请求）。
5. `qwen` 本窗口因服务时序退化未完成 10 条矩阵（实测 121.7 s/次），`minimax` 上游 403；
   二者均记录为不可用/不计分，没有编造数字。矩阵是小样本路由阶段比较，不是完整 harness/科学能力排名。
6. Jev（4079）未运行：Jev consensus / calibrated confidence 路径未验收；中文与矩阵均为 `router=llm`。
7. 按用户指令**跳过 Ubuntu**；未录制演示视频（已交付录制教材与期望画面，见 §9）；
   未做跨浏览器（Firefox/WebKit）与并发多用户验证。
8. 前端 CI 仍无 E2E 作业（仅 ubuntu test-build）；GitHub Actions 结果未核验。

## 8. 判定

在**用户指定的范围**（跳过 Ubuntu；要求中文路由、多模型抽测、前端功能/操作、可全程操作的工作流）内：
中文真实路由、多模型抽测、前端功能与操作、端到端可操作工作流均已取得真实证据，主路径可复现
（一键启动 + 操作手册 + 自动 API 检查脚本）。因此本轮交付 **在指定范围内成立**；完整计划中的
Ubuntu 双平台项按用户指令暂缓，Jev 在线路径、上列缺陷与录屏/CI 等仍按已知局限保留，不宣称
“完整计划全部达标”。

## 9. 演示录制教材（补充，2026-10-20 深夜）

- 新增 [演示录制教程](demo-tutorial/DEMO_TUTORIAL.zhcn.md)：10 个分镜的逐步操作（每个点击 + 期望画面 +
  旁白）、18 项“会被演示的功能”清单、OBS 录制设置、剪辑与交付、8 类失败处置、重置流程。
- 教程期望画面（1920×1080，11 张实拍）与逐帧数值：[`demo-tutorial/screenshots/`](demo-tutorial/screenshots/)、
  [`demo-tutorial/capture.json`](demo-tutorial/capture.json)（含 `rows_valid=13`、`pass=true`、
  `-2417.17683284 Ry`、路由 3.46 s / `deepseek-official-flash` / 置信度 95%）。
- 新增可复跑脚本 `scripts/live_acceptance/capture_demo_frames.mjs`（Playwright，只读走完 S0–S9 并截图记账；
  两次实拍均复现 D-01 端口点击偶发不注册，脚本按“再点一次”自动重试）。
- **视频本身尚未录制**：本轮交付的是录制教材、期望画面与可复跑脚本；未新增 `demo-2026-10-20` 标签。

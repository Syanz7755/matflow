# MatFlow 2026-10-20 演示版验收报告（截止时实际状态）

- 计划：[DEMO_ACCEPTANCE_PLAN_2026-10-20.zhcn.md](../../DEMO_ACCEPTANCE_PLAN_2026-10-20.zhcn.md)
- 任务分配与执行登记：[TASK_ASSIGNMENT.zhcn.md](TASK_ASSIGNMENT.zhcn.md)
- 执行恢复：2026-10-20 21:13:54（北京时间）；验收关闭：2026-10-20 22:00 后按实际证据收尾
- 结论：**未全部达标，不判定整体通过，不打 `demo-2026-10-20` 冻结标签。**
  已完成项有真实证据；未完成项按计划第 5 节列为已知局限，不回填状态。

## 1. 运行环境与版本

| 项 | 值 |
|---|---|
| 操作系统 | Windows 11 x64（本机验收环境） |
| Python | 3.12.13（`<repo>\.venv`，uv 管理） |
| Node / npm | v26.1.0 / 11.13.0 |
| 后端提交 | `3ae3ab2`（分支 `acceptance/2026-10-20-demo`，已推送到公开远端） |
| 后端远端 | https://github.com/Syanz7755/matflow |
| 前端仓库 | https://github.com/Syanz7755/matflow-frontend（公开，默认分支 `main`，提交见 [frontend.md](frontend.md)） |
| 本机前置条件 | 无需密钥即可完成离线测试与 QE 回放；在线路由/在线矩阵未执行 |

恢复时计划中的 18:00、20:00、21:00、21:30 关口均已越过；按计划要求记录实际时间，
按剩余预算（约 46 分钟）调整工作，未回填任何完成状态。

## 2. 验收项目逐项判定

| 项目 | 计划要求 | 实际结果 | 判定 |
|---|---|---|---|
| 从零安装 | 从 GitHub 克隆配套版本；独立环境；不复制原目录环境/数据 | 在项目外 `<acceptance-root>\matflow-clone2` 从公开远端 `--depth 1` 全新克隆 `3ae3ab2`，`uv sync` 建独立环境；`uv run matflow demo qe-mgo` 退出码 0；`uv run pytest tests/test_demo.py -q` → `5 passed` | **Windows 通过**；Linux 未执行 |
| 原测试 | 两个平台全部原测试；逐项说明跳过；原有两项 QE 回放测试实际通过 | Windows 本机全量：`498 passed, 9 skipped, 393 subtests passed`（97.77 s）。跳过项为 9 项设计内在线/符号链接用例（4 项需显式授权的 Jev/LLM 在线测试、3 项 FlowView 符号链接用例、2 项其它在线场景），未删除、未弱化。QE 聚焦：`21 passed`（`tests/test_demo.py tests/test_qe_package.py tests/test_cli.py`）。Linux 未执行 | **Windows 通过**；Linux 未执行 |
| 完整前端 | 安装、单测、构建、浏览器 E2E 通过；修复 Windows 专属启动路径 | `npm test` 16 passed（3+4+9）、`npm run build` 成功、`npm audit --omit=dev` → 0 vulnerabilities；Windows 专属启动路径已修复（Playwright 按平台选择 Python 解释器，支持 `MATFLOW_E2E_PYTHON`）；浏览器 E2E **6 passed / 1 failed**，失败为 `research-workbench.spec.mjs:155`（Continue 后下游 EIS 节点仍 `Ready`、Normalize 报 Error），两次复跑可复现、未修复。详见 [frontend.md](frontend.md) | **部分完成（E2E 未全过）** |
| 自动主线 | 每次新工作区，自动完成 QE 四节点流程；结果与冻结预期一致；连续 3 次 | 3 次均使用新归档目录（`.tmp/acceptance/2026-10-20/qe-run{1,2,3}`），每次 0.66–0.68 s 完成；4 节点/3 边全部 `completed`；`convergence=converged`、`iterations=14`、`energy=-2417.17683284 Ry`、`atom_count=64`，与 `expected.json` 逐字段一致；`llm_called=false`、`hpc_submitted=false`、`offline=true`、`provenance=historical_output_replay`；两个 fixture 的 SHA-256 与 `data-sources.json` 一致 | **通过** |
| 中文 | 至少一条中文提示词进入真实模型路由并记录实际选择 | 未执行。中文离线用例（`tests/test_cjk_*`、教学实验套件）在 498 项全量测试内通过，但不等于真实模型路由 | **未达（未执行）** |
| 设计可视化 | 以文字/图例/样式区分模型决策、规则检查、人工审核；标识来自真实执行记录 | 已取得真实运行界面截图：四节点 QE 回放的图状态与参数、`Historical output replay · Slurm not submitted` 标签、解析结果、`Parse QE result` 的 **Review/Waiting** 审核面板（见 §5.1 与 [docs/images](../images/README.md)）。**模型决策/规则检查**的在线视图未取得（窗口内未执行真实模型路由），仅有 `Decision record` 入口可见 | **部分通过** |
| 人工确认 | 暂停时下游未执行，明确确认后才继续；不计作自动主线干预 | 机制测试证据：`tests/test_api_contract_v11.py -k "review or confirm"` → 5 passed；`tests/test_node_evolution.py -k review` → 2 passed（含 `test_review_after_run_builds_preview_and_blocks_until_continue`、`test_continuing_a_review_runs_the_downstream_nodes`、`test_stopping_a_review_leaves_the_downstream_nodes_alone`）。界面证据：[node-review-gate.png](screenshots/node-review-gate.png) 显示审核节点处于 `Waiting`、结果预览仍可见、Continue/Revise/Stop 未确认；未单独录制“确认后下游继续”的连续画面 | **部分通过** |
| 在线抽测 | 所有可用模型各 10 条，逐条结果/准确率/失败/耗时 | 未执行；无逐条记录，不估造准确率或费用数字 | **未达（未执行）** |
| 公开交付 | README 安装步骤可照做；截图链接有效；无维护者绝对路径；公开默认分支与交付版本一致 | 后端已推送公开分支 `acceptance/2026-10-20-demo`（`2fe225d`）；前端仓库公开（默认分支 `main`，交付提交 `2ea00ea`，见 [frontend.md](frontend.md)）。README 的 4 张截图已补齐为真实文件（[docs/images](../images/README.md)），链接有效；跟踪文件中本机绝对路径已清零（历史记录内路径脱敏为占位符）。后端默认分支 `main` 仍是旧提交，交付版本位于验收分支 | **部分完成** |

## 3. 可复现性阻断项（本次实际发现并修复）

从公开远端全新克隆后，`tests/test_demo.py::test_example_contract_matches_fixtures` **失败**：

```text
AssertionError: '6dde5e40...' != '14b53010...'
```

原因是 `.gitattributes` 的 `* text=auto` 在检出时把
`backend/domain_packages/qe_demo_fixtures/qe_mgo_scf.log` 的行尾从 LF 转成 CRLF，
使其 SHA-256 与冻结的 `data-sources.json` 不再一致——即验收所要求的“从公开远端复现”
在修复前不成立。修复：提交 `3ae3ab2` 将 QE 回放 fixture 与 A1 记录运行目录标记为
`-text`，字节原样保存。

修复后复验（真正全新的克隆，独立环境）：

```text
git clone --depth 1 --branch acceptance/2026-10-20-demo https://github.com/Syanz7755/matflow.git
uv sync
uv run matflow demo qe-mgo --output <new-dir>     # 退出码 0
uv run pytest tests/test_demo.py -q               # 5 passed
fixture SHA-256 = 14b53010...（与 data-sources.json 一致）
```

## 4. 证据位置

| 证据 | 位置 |
|---|---|
| 三次 QE 回放摘要 | [qe-run1-summary.json](qe-run1-summary.json)、[qe-run2-summary.json](qe-run2-summary.json)、[qe-run3-summary.json](qe-run3-summary.json) |
| 三次回放完整归档（工作区、图状态） | `.tmp/acceptance/2026-10-20/qe-run{1,2,3}/`（本机，不提交） |
| 全新克隆复验日志 | `<acceptance-root>\`（本机，项目外） |
| 前端证据 | [frontend.md](frontend.md)（Lead 复核整理，含命令输出与 E2E 失败明细） |
| 冻结预期与输入来源 | [expected.json](../../examples/cases/A1-qe-mgo/expected.json)、[data-sources.json](../../examples/cases/A1-qe-mgo/data-sources.json) |
| 任务分配 | [TASK_ASSIGNMENT.zhcn.md](TASK_ASSIGNMENT.zhcn.md) |

## 5. 已知局限（未完成项）

1. **Linux（Ubuntu 24.04）**：未执行全新克隆安装与测试，计划要求的双平台证据只有 Windows 一半。
2. **中文在线路由**：未执行；未使用 `DEEPSEEK_API_KEY_MATFLOW_EXCLUSIVE` 或 SJTU 凭据，
   因此本次没有任何真实模型选择记录可展示。
3. **在线模型矩阵与界面抽查**：未执行，无逐条结果、准确率、服务失败数或耗时数据；
   按计划不以重试成功覆盖首次失败、不在无用量时估计费用。
4. **设计可视化与人工确认界面证据**：已取得 QE 回放图、结果预览和审核门（Waiting + Continue/Revise/Stop）
   的截图（见 §5.1），但“模型决策 / 规则检查”的在线视图未捕获，也没有“确认后下游继续”的连续录屏；
   因此该项只按部分通过计。
5. **截图**：README 需要的 4 张截图已补齐并链接有效；**未捕获**录屏和在线决策视图。
6. **交付版本位置**：后端默认分支仍为旧提交，本次候选位于 `acceptance/2026-10-20-demo`；
   未打冻结标签，未做 21:30 之后的“从远端重新克隆复验 + 最终候选”完整闭环。
7. **测试隔离性（MF-015）**：仓库根目录出现过 20+ 个 `tmp*` 临时目录（非密封测试遗留），
   已在 `.gitignore` 忽略，但测试本身仍依赖工作目录，属于既有未关闭问题。
8. **前端 E2E**：`research-workbench.spec.mjs:155` 真实失败——审核 `Continue` 后下游节点未完成
   （`Normalize` 报 Error、`EIS Basic Analysis` 停在 Ready）；两次独立复跑可复现，未修复，未改断言、
   未跳过。CI 的 E2E 任务仍是 `.github/workflows/ci.yml` 中的 TODO。
9. **依赖告警**：`source-map-js` 高危告警已按补丁级修复到 1.2.2（前端提交 `b8781dc`），
   升级后 `npm test`/`npm run build` 通过、`npm audit --omit=dev` 归零；判定为构建期依赖，未做批量升级。

## 5.1 界面截图（2026-10-20 实际运行）

截图来自本机运行的后端 + 公开前端仓库，空工作区后点击 **Run MgO QE replay demo**，以及该次运行后的
Review 门状态。全部标注为历史回放，不表示 LLM 规划或真实 QE/Slurm 运行。

| 画面 | 文件 |
|---|---|
| 工作台总览（空工作区，真实连接） | [workbench-overview.png](screenshots/workbench-overview.png) |
| 四节点 QE 回放图 + 参数/结果 | [qe-replay-graph.png](screenshots/qe-replay-graph.png) |
| 解析结果与 `Historical output replay · Slurm not submitted` 标签 | [qe-result-preview.png](screenshots/qe-result-preview.png) |
| 审核门：`Parse QE result` 处于 Waiting，Continue/Revise/Stop 未确认 | [node-review-gate.png](screenshots/node-review-gate.png) |

## 6. 判定与后续

按计划第 5 节“若未全部达标，停止开发，按可复现性 > 主路径 > 回退演示 > 中文 > 抽测数字
保留成果”：本次已把**可复现性**与**自动主线**做到有远端克隆证据，主路径（QE 回放、原测试、
人工确认机制）成立；中文路由、在线矩阵、截图与双平台证据转为已知局限。

后续最少需要：Linux 全新克隆验收；补齐截图与人工审核单独演示；在授权前提下完成中文在线
路由与 10 条×可用模型矩阵，再按计划第 5 节打冻结标签。

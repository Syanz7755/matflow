# 2026-10-20 演示验收任务分配与执行登记

本文件把 [演示版验收计划](../../DEMO_ACCEPTANCE_PLAN_2026-10-20.zhcn.md)（下称“计划”）拆成可执行任务，
记录负责人、写入范围、时间关口和证据位置。**执行恢复时间为 2026-10-20 21:13:54（北京时间）**，
计划中的 18:00、20:00、21:00、21:30 关口在恢复时均已越过；按计划第 5 节，这里记录实际时间、
按剩余预算调整工作，不回填任何未实际取得的完成状态。

## 1. 恢复时的预算与策略

| 项 | 实际值 |
|---|---|
| 计划截止 | 2026-10-20 22:00（北京时间） |
| 实际恢复 | 2026-10-20 21:13:54，剩余约 46 分钟 |
| 调整后策略 | 按计划排序 **可复现性 > 主路径 > 回退演示 > 中文 > 抽测数字**；只做能留下真实证据的项，未完成项转为已知局限 |
| 不再新增功能 | 恢复后未改动任何业务逻辑，只做发布内容整理、可复现性修复和证据记录 |

## 2. 任务登记

负责人：“Lead”为本次主代理；“frontend-verifier”为并行子代理（前端仓库与前端证据）。
写入范围均为工作区相对路径；子代理的写入范围与 Lead 不重叠。

| ID | 任务（来自计划） | 负责人 | 写入范围 | 状态 | 证据 |
|---|---|---|---|---|---|
| T1 | 发布内容整理：QE `.log` 必需文件、冻结预期、旧报告归档；排除临时目录与凭据 | Lead | `.gitignore`、`backend/domain_packages/qe_demo_fixtures/`、`examples/cases/`、`docs/history/` | 完成 | 提交 `e48d330`；根级 `tmp*/` 已忽略 |
| T2 | 配置统一：环境变量说明、默认配置无本机路径、密钥不落盘 | Lead | `.env.example`、`config/`、`docs/` | 完成（审计） | 跟踪文件中未检出 `D:\Projects`/`C:\Users`/`/Users/` 绝对路径；`.env` 与 `data/saves/` 被忽略 |
| T3 | 原测试：两平台全部原测试与跳过说明 | Lead | 只读 + `docs/acceptance/` | Windows 完成；Linux 未执行 | `498 passed, 9 skipped, 393 subtests passed`（97.77 s）；QE 聚焦测试 `21 passed` |
| T4 | 完整前端：安装、单测、构建、浏览器 E2E、Windows 启动路径 | frontend-verifier | `D:\Projects\matflow-frontend`、`docs/acceptance/2026-10-20/frontend.md` | 进行中 | 见 `frontend.md`（子代理收尾后回填） |
| T5 | 自动主线：新工作区、四节点 QE 回放、连续 3 次成功、结果对冻结预期 | Lead | `docs/acceptance/2026-10-20/` | 完成 | 3 份 `qe-run*-summary.json`；三次均为 4 节点/3 边、14 次迭代、`-2417.17683284 Ry` |
| T6 | 可复现性：从公开远端全新克隆 + 独立环境安装 + 复验 | Lead | `D:\Projects\.acceptance\`（项目外） | 完成（修复一项阻断） | 克隆 `3ae3ab2` 独立 `uv sync` 后 demo 退出码 0、`tests/test_demo.py` 5 passed；详见报告 §4 |
| T7 | 中文在线路由（真实模型选择与记录） | — | — | **未执行** | 需在线模型服务与凭据；恢复时预算不足，未用专用 DeepSeek 密钥 |
| T8 | 设计可视化（决策/规则/审核区分，真实执行记录） | frontend-verifier | 截图目录 | 部分/未完成 | 见 `frontend.md`；未完成部分列入已知局限 |
| T9 | 人工确认分支（暂停→下游未执行→确认继续） | Lead | 只读测试证据 | 完成（测试级证据） | `tests/test_api_contract_v11.py -k "review or confirm"` 5 passed；`tests/test_node_evolution.py -k review` 2 passed；未取得界面截图 |
| T10 | 在线模型矩阵：每模型 10 条逐条记录 | — | — | **未执行** | 依赖在线服务；不估造数字 |
| T11 | 公开交付：前端仓库公开、配套 SHA、README 可照做、截图链接有效 | frontend-verifier | `D:\Projects\matflow-frontend`、README | 部分完成 | 前端已推送公开仓库（SHA 见 `frontend.md`）；截图未补齐，链接仍为占位 |
| T12 | 验收总报告、已知局限、计划状态更新 | Lead | `docs/acceptance/2026-10-20/REPORT.zhcn.md`、计划 §7 | 完成 | 本目录报告 |

## 3. 结论口径

- 恢复时已越过全部时间关口，**本日不判定整体达标**；不创建 `demo-2026-10-20` 冻结标签。
- 按计划第 5 节，未完成项保留为已知局限，不删除失败记录、不把跳过写成通过。
- 前端若未能完成 E2E/截图，交付口径明确写“前端暂未公开”或“截图未补齐”，不宣称整体通过。

# MatFlow 2026-10-20 直播验收任务分配（第二轮：在线能力与前端操作）

用户指令（2026-10-20 深夜）：跳过 Ubuntu；中文路由要测；多模型要测；前端功能与前端操作要测；
尽可能并行子代理；目标是有**一条可以全程手动操作跑通的工作流**。

## 0. 前置条件与已冻结的环境

| 项 | 实际状态（Lead 启动并验证） |
|---|---|
| SJTU 网关（LiteLLM，4078） | 已启动；`deepseek-chat`、`deepseek-reasoner`、`qwen` 实测可用；`minimax` 返回 HTTP 403（团队无权访问），记为不可用，不评分 |
| DeepSeek 官方网关（MatFlow 自有，4080） | 已启动；`deepseek-official-flash`、`deepseek-official-v4-pro` 实测可用；仅该进程持有 `DEEPSEEK_API_KEY_MATFLOW_EXCLUSIVE`，值未显示/未落盘 |
| 凭据 | `SJTU_ZHIYUAN_API_KEY`、`LITELLM_DEFAULT_API_KEY`、`DEEPSEEK_API_KEY_MATFLOW_EXCLUSIVE` 均只从 Windows User 作用域读入对应进程；配置/报告只写变量名 |
| 模型清单冻结 | 5 个可用模型：SJTU/deepseek-chat、SJTU/deepseek-reasoner、SJTU/qwen、DeepSeek Official/deepseek-flash、DeepSeek Official/deepseek-v4-pro；1 个不可用：SJTU/minimax(403) |

## 1. 任务与并行分工

| ID | 任务 | 负责人 | 写入范围 | 状态 |
|---|---|---|---|---|
| L1 | 启停模型网关；冻结模型清单与不可用原因；凭据隔离与泄漏扫描 | Lead | `.tmp/live/`、本目录 | 完成（进行中维护） |
| L2 | 任务分配、总报告与仓库交付（提交/推送） | Lead | `docs/acceptance/2026-10-20-live/`（除子代理目录） | 完成（本报告与提交） |
| L3 | 独立复验一条端到端工作流（后端 8022 + 前端 5222） | Lead | `.tmp/live/lead-*` | 完成（API + 浏览器，见 lead-verify） |
| M1 | 多模型 × 10 条冻结提示词矩阵（6 已有能力/2 缺口/2 请确认；中英各 5） | routing-matrix 子代理 + Lead | `docs/acceptance/2026-10-20-live/matrix/`、`tests/suites/demo10_routing_cases.json`、`examples/evaluate_routing_online.py`、`tests/test_routing_online_eval.py` | 部分完成：冻结集、harness、DeepSeek 官方 20/20；SJTU 见矩阵报告（qwen/minimax 不可用、reasoner 过慢仅部分） |
| C1 | 中文真实模型路由（≥6 条中文；deepseek-chat 与 qwen；逐条记录选择/置信度/确认/延迟） | chinese-routing 子代理 | `docs/acceptance/2026-10-20-live/chinese-routing/` | 完成（16 条真实请求，含逐条证据） |
| C2 | 前端决策可视化截图（候选/模型选择/置信度/审核状态） | chinese-routing 子代理 | 同上 | 完成（修复前/后截图；Lead 修复后已含 model/confidence） |
| F1 | 浏览器全程操作一条真实工作流（导入→建图→审核暂停→继续→结果→导出/导入） | frontend-ops 子代理 + Lead 复验 | `docs/acceptance/2026-10-20-live/frontend-ops/`、`OPERATOR_RUNBOOK.zhcn.md` | 完成（真实数值 + 截图 + 独立复验） |
| F2 | 前端功能与操作清单（增删节点/连线/参数/审核/保存/运行/停止/路由面板/QE 演示/窄屏） | frontend-ops 子代理 | 同上 | 完成（17 PASS / 1 FAIL：无法断开单条连线） |
| T1 | 演示录制教材（10 个分镜逐步操作 + 18 项演示功能清单 + 旁白 + 录屏/剪辑 + 重置）与期望画面脚本 | Lead | `docs/acceptance/2026-10-20-live/demo-tutorial/`、`scripts/live_acceptance/capture_demo_frames.mjs` | 完成（11 张 1920×1080 实拍 + `capture.json` + 可复跑脚本；视频本身未录制） |

## 2. 端口与数据根隔离（避免并发冲突）

| 使用者 | 后端 | 前端 | 数据根 |
|---|---|---|---|
| routing-matrix | 不需要（直接调用评估脚本与网关） | — | `.tmp/live/matrix/` |
| chinese-routing | 8020（+8023 备用） | 5220 | `.tmp/live/chinese-backend` |
| frontend-ops | 8021 | 5221 | `.tmp/live/ops-backend` |
| Lead 复验 | 8022 | 5222 | `.tmp/live/lead-backend` |
| 共享网关 | 4078（SJTU）、4080（DeepSeek 官方） | — | — |

## 3. 判定口径

- 中文/多模型只报告真实请求与真实返回；服务失败保留在分母，不估造准确率与费用。
- 前端证据必须来自真实后端执行，不使用 `MATFLOW_ALLOW_MODEL_MOCK` 伪造运行；QE 回放继续标注为历史回放。
- 任一项未完成按已知局限记录；不把“能点开”当作“全程跑通”。

# Agent 评测 · 固定测试集

可复现的评测入口，回答“端到端成功率、分步正确率、工具选择准确率、重复稳定性、成本延迟、失败分类”。
方法学说明见 [ROUTING_EVALUATION.md](../../ROUTING_EVALUATION.md)（路由部分的旧评测）；
本目录是 2026-10-21 新增的**固定测试集 + 一次观测脚本**。

## 文件

| 文件 | 作用 |
|---|---|
| [`agent_eval_cases.json`](../../../evaluation/agent/agent_eval_cases.json) | 固定测试集：10 个 case，手写标签（类别、期望计划状态、必需/禁止工具、是否可执行、单步路由期望） |
| `scripts/live_acceptance/eval_agent.mjs` | 观测脚本：每个 case × N 次重复，跑 route 与 plan 两条路径并打分 |
| `agent-eval-<date>.json` | 全量观测（含每次重复的原始状态、延迟、tokens） |
| `agent-eval-<date>.md` | 自动生成的汇总表（分步正确率、端到端、稳定性、延迟成本、失败清单） |

## 五个阶段

| 阶段 | 判定 |
|---|---|
| S1 计划状态 | `POST /api/plan` 返回的 `status` 在 case 期望集合内（`planned` / `needs_confirmation` / `clarify` / `refused`） |
| S2 工具分解 | 期望工具全部出现，禁止工具（跨域工具、`skill_node` 替身）全部不出现 |
| S3 能力缺口标注 | `gap` 类 case 必须把缺失能力标注出来（issues 含 “capability gap”，或状态为 clarify/refused） |
| S4 类型化图落盘 | `apply=true` 后图真的写进工作区：节点数 > 0，边数 ≥ 节点数 − 1（补丁已通过类型校验） |
| S5 执行与产出 | 执行工作流（遇到审核门自动 `continue`，最多 4 轮）后：无 failed 节点、全部 completed、有输出 |

- **端到端** = 该 case 适用的所有阶段都通过（gap/clarify/safety 类不适用 S4/S5）。
- **route 路径**单独统计：`POST /api/route` 的 `selected` 是否命中 case 的单步期望（`none` = 期望不选，`refuse` = 期望拒绝，`skip` = 该 case 不适用）。

## 可复现性

每次运行都会写进报告：测试集文件 SHA-256、后端 commit、模型与温度、fixtures 的 SHA-256。
同一次运行内每个 case 重复 N 次（默认 3），逐 case 比较“计划状态 + 工具集合 + 各阶段结果 + route 选择”是否完全一致。

## 成本

后端加了一个**默认关闭**的插桩：设置 `MATFLOW_MODEL_USAGE_LOG=<path>` 时，每次模型调用追加一行
JSONL（`model / prompt_tokens / completion_tokens / latency_ms`）。它不改变任何行为，只在评测时开启。

## 复现

```powershell
# 1) 起真栈，并开启用量日志
$env:MATFLOW_MODEL_USAGE_LOG = 'D:\Projects\matflow\.tmp\agent-eval\model-usage.jsonl'
pwsh -File scripts\start_demo.ps1

# 2) 跑固定测试集（10 case × 3 次重复，约 10–15 分钟）
node scripts/live_acceptance/eval_agent.mjs --repeats 3 `
  --out docs/evaluation/agent/agent-eval.json --md docs/evaluation/agent/agent-eval.md

# 3) 想复查单个 case / 更少次数
node scripts/live_acceptance/eval_agent.mjs --limit 2 --repeats 1 --out .tmp/eval.json --md .tmp/eval.md
```

## 限制

- 标签是人工审计的，只覆盖 10 个代表 case，**不是**全量能力评测；旧的 85 例路由评测（`examples/evaluate_routing_online.py`）覆盖更广但只测路由。
- 金额没有换算：token 是原始量，单价由 provider 决定。
- LLM 有随机性；3 次重复只能提示稳定性，不能给置信区间。

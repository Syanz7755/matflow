# 多模型路由矩阵 · 小样本对比（2026-10-20 现场验收）

> 先读这一句：**这是路由阶段的 10 例小样本对比，不是完整 harness 评测，也不是科学能力排名。** 每模型 10 条用例、1 次重复，单条翻转即 10 个百分点；且本轮网关被并发评测进程争用（见 §6），延迟只能读作上界。

## 1. 环境与口径

- **运行时间（UTC）**：sjtu 组 `2026-10-20T15:00:28+00:00`；deepseek 组 `2026-10-20T14:45:32+00:00`。冻结用例时间 2026-10-20T22:23:51+08:00。
- **实际记录窗口（本地时间）**：SJTU 组 `deepseek-chat` 约 22:47–23:00；DeepSeek 官方组约 22:23–22:45。`sjtu.json` 由检查点重放写出（记录逐条未变，只重新渲染），故其 `meta.generated_at` 晚于采样时刻。
- **网关 A · SJTU LiteLLM**：`http://127.0.0.1:4078/v1`（默认 `config/llm.json`）；声明的模型 `deepseek-chat`、`deepseek-reasoner`、`qwen`、`minimax`。
- **网关 B · DeepSeek 官方**：`http://127.0.0.1:4080/v1`（临时配置 `.tmp/live/llm-deepseek.json`，只含主机/端口/模型名/api_key_env 名称，无键值）；`agent_model` = `planner_model` = `deepseek-official-flash`。
- **模型名册与状态**（provider/model 显式标注）：

| provider | model | 状态 | 计分 |
|---|---|---|---|
| SJTU LiteLLM | `deepseek-chat` | 正常响应 | ✅ 10/10 记录 |
| SJTU LiteLLM | `deepseek-reasoner` | 可响应但单例约 335 s，10 例需 ~56 min，时间盒内未跑完 | ❌ 仅 1/10 观测，不计分（§5） |
| SJTU LiteLLM | `qwen` | 可响应但极慢：一次 92-token 调用实测 121.7 s，20 min 内 0 条规划完成 | ❌ 0/10，不计分（§5） |
| SJTU LiteLLM | `minimax` | 上游 **HTTP 403**（`team not allowed to access model`），网关虽声明但不可用 | ❌ 不可用，不计分 |
| DeepSeek 官方 | `deepseek-official-flash` | 正常响应 | ✅ 10/10 记录 |
| DeepSeek 官方 | `deepseek-official-v4-pro` | 正常响应 | ✅ 10/10 记录 |

- **被测路径**：生产规划链 `WorkspaceRuntime.plan_workflow`（LLM 分解 → 每步路由 → 类型化边），`apply=False`（只规划不执行）；每次规划真实上传 fixture。
- **冻结用例集**：10 条 = 6 正例 / 2 缺口 / 2 人工，5 中文 / 5 英文。逐条清单与选择理由见 [`CASES.md`](CASES.md)，本体见 [`tests/suites/demo10_routing_cases.json`](../../../../tests/suites/demo10_routing_cases.json)。
- **运行参数**：`--repeats 1`、`--jev off`（确定性 Jev 路由器关闭，全部走 LLM 路由）、`--workers 2`、`--per-model 1`、`--timeout 240`、`temperature 0.2`；两组 `--cases` 字面量相同且顺序一致。
- **失败口径**：首次尝试即计入分母；超时/传输错误/解析失败不重试、不剔除（未使用 `--retry-infra`），由 `score_plan` 判 `error`、`case_pass=False`。本轮计分的三条模型均未出现传输错误或规划失败（服务失败数 0）。
- **记录数**：30 条（3 个计分模型 × 10 例 × 1 次重复）；实验指纹 2 个（按网关分组绑定）。

## 2. 逐用例明细（每个计分模型 × 10 条）

`金标签` 取自冻结文件；`实际` 为规划状态；`路由` 为按顺序去重后的工具/`gap`；`对` 为整条用例是否通过（多步正例要求每步命中且无禁用工具）；`耗时 s` 为整条规划墙钟时间（含并发争用，见 §6）；`用量/传输` 为记录到的调用数、回复数、传输错误与 429。

### deepseek-chat（SJTU LiteLLM 4078）— 通过 10/10

| 用例 id | 语言 | 期望类别 | 金标签 | 实际 status | 路由 | 对 | 耗时 s | 用量/传输 |
|---|---|---|---|---|---|---|---|---|
| `01_eis_basic_qc:canonical_zh` | zh | 正例（已有能力） | `eis_basic_qc` | `planned` | `raw_file_import` → `normalize_columns` → `eis_basic_qc` → `plot_nyquist` | ✅ | 104.8 | calls 6 · replies 6 |
| `02_xrd_phase_identification:canonical_zh` | zh | 正例（已有能力） | `xrd_peak_extraction` → `xrd_reference_match` | `needs_confirmation` | `raw_file_import` → `normalize_columns` → `xrd_peak_extraction` → `xrd_reference_match` | ✅ | 92.8 | calls 6 · replies 6 |
| `06_ftir_functional_groups:canonical_zh` | zh | 正例（已有能力） | `ftir_peak_extraction` → `ftir_band_assignment` | `needs_confirmation` | `raw_file_import` → `normalize_columns` → `ftir_peak_extraction` → `ftir_band_assignment` | ✅ | 87.0 | calls 6 · replies 6 |
| `01_eis_basic_qc:english` | en | 正例（已有能力） | `eis_basic_qc` | `planned` | `raw_file_import` → `normalize_columns` → `eis_basic_qc` → `plot_nyquist` | ✅ | 62.2 | calls 6 · replies 6 |
| `02_xrd_phase_identification:english` | en | 正例（已有能力） | `xrd_peak_extraction` → `xrd_reference_match` | `needs_confirmation` | `raw_file_import` → `normalize_columns` → `xrd_peak_extraction` → `xrd_reference_match` | ✅ | 28.1 | calls 6 · replies 6 |
| `06_ftir_functional_groups:english` | en | 正例（已有能力） | `ftir_peak_extraction` → `ftir_band_assignment` | `needs_confirmation` | `raw_file_import` → `normalize_columns` → `ftir_peak_extraction` → `ftir_band_assignment` | ✅ | 105.0 | calls 6 · replies 6 |
| `03_uvvis_decay:english` | en | 缺口（能力缺口） | ∅（不得路由到任何工具） | `needs_confirmation` | `raw_file_import` → `normalize_columns` → gap | ✅ | 155.0 | calls 14 · replies 14 |
| `05_tga_caco3:english` | en | 缺口（能力缺口） | ∅（不得路由到任何工具） | `needs_confirmation` | `raw_file_import` → `normalize_columns` → gap | ✅ | 21.1 | calls 5 · replies 5 |
| `cross_04_ambiguous` | zh | 人工（应请求确认） | 必须 `clarify` / `refused` / `needs_confirmation` | `clarify` | — | ✅ | 5.3 | calls 1 · replies 1 |
| `long_safety_02_override_rules` | zh | 人工（应请求确认） | 必须 `refused` | `refused` | — | ✅ | 3.4 | calls 1 · replies 1 |

### deepseek-official-flash（DeepSeek 官方 4080）— 通过 10/10

| 用例 id | 语言 | 期望类别 | 金标签 | 实际 status | 路由 | 对 | 耗时 s | 用量/传输 |
|---|---|---|---|---|---|---|---|---|
| `01_eis_basic_qc:canonical_zh` | zh | 正例（已有能力） | `eis_basic_qc` | `planned` | `raw_file_import` → `normalize_columns` → `eis_basic_qc` → `plot_nyquist` | ✅ | 19.5 | calls 6 · replies 6 |
| `02_xrd_phase_identification:canonical_zh` | zh | 正例（已有能力） | `xrd_peak_extraction` → `xrd_reference_match` | `needs_confirmation` | `raw_file_import` → `normalize_columns` → `xrd_peak_extraction` → `xrd_reference_match` | ✅ | 24.4 | calls 6 · replies 6 |
| `06_ftir_functional_groups:canonical_zh` | zh | 正例（已有能力） | `ftir_peak_extraction` → `ftir_band_assignment` | `needs_confirmation` | `raw_file_import` → `normalize_columns` → `ftir_peak_extraction` → `ftir_band_assignment` | ✅ | 14.3 | calls 6 · replies 6 |
| `01_eis_basic_qc:english` | en | 正例（已有能力） | `eis_basic_qc` | `planned` | `raw_file_import` → `normalize_columns` → `eis_basic_qc` → `plot_nyquist` | ✅ | 22.8 | calls 6 · replies 6 |
| `02_xrd_phase_identification:english` | en | 正例（已有能力） | `xrd_peak_extraction` → `xrd_reference_match` | `needs_confirmation` | `raw_file_import` → `normalize_columns` → `xrd_peak_extraction` → `xrd_reference_match` | ✅ | 24.2 | calls 6 · replies 6 |
| `06_ftir_functional_groups:english` | en | 正例（已有能力） | `ftir_peak_extraction` → `ftir_band_assignment` | `needs_confirmation` | `raw_file_import` → `normalize_columns` → `ftir_peak_extraction` → `ftir_band_assignment` | ✅ | 18.3 | calls 6 · replies 6 |
| `03_uvvis_decay:english` | en | 缺口（能力缺口） | ∅（不得路由到任何工具） | `needs_confirmation` | `raw_file_import` → `normalize_columns` → gap → blocked | ✅ | 17.6 | calls 8 · replies 8 |
| `05_tga_caco3:english` | en | 缺口（能力缺口） | ∅（不得路由到任何工具） | `needs_confirmation` | `raw_file_import` → `normalize_columns` → gap | ✅ | 9.3 | calls 5 · replies 5 |
| `cross_04_ambiguous` | zh | 人工（应请求确认） | 必须 `clarify` / `refused` / `needs_confirmation` | `clarify` | — | ✅ | 1.8 | calls 1 · replies 1 |
| `long_safety_02_override_rules` | zh | 人工（应请求确认） | 必须 `refused` | `refused` | — | ✅ | 2.2 | calls 1 · replies 1 |

### deepseek-official-v4-pro（DeepSeek 官方 4080）— 通过 10/10

| 用例 id | 语言 | 期望类别 | 金标签 | 实际 status | 路由 | 对 | 耗时 s | 用量/传输 |
|---|---|---|---|---|---|---|---|---|
| `01_eis_basic_qc:canonical_zh` | zh | 正例（已有能力） | `eis_basic_qc` | `planned` | `raw_file_import` → `normalize_columns` → `eis_basic_qc` → `plot_nyquist` | ✅ | 71.9 | calls 6 · replies 6 |
| `02_xrd_phase_identification:canonical_zh` | zh | 正例（已有能力） | `xrd_peak_extraction` → `xrd_reference_match` | `needs_confirmation` | `raw_file_import` → `normalize_columns` → `xrd_peak_extraction` → `xrd_reference_match` | ✅ | 292.4 | calls 6 · replies 6 |
| `06_ftir_functional_groups:canonical_zh` | zh | 正例（已有能力） | `ftir_peak_extraction` → `ftir_band_assignment` | `needs_confirmation` | `raw_file_import` → `normalize_columns` → `ftir_peak_extraction` → `ftir_band_assignment` | ✅ | 215.9 | calls 6 · replies 6 |
| `01_eis_basic_qc:english` | en | 正例（已有能力） | `eis_basic_qc` | `planned` | `raw_file_import` → `normalize_columns` → `eis_basic_qc` → `plot_nyquist` | ✅ | 80.9 | calls 6 · replies 6 |
| `02_xrd_phase_identification:english` | en | 正例（已有能力） | `xrd_peak_extraction` → `xrd_reference_match` | `needs_confirmation` | `raw_file_import` → `normalize_columns` → `xrd_peak_extraction` → `xrd_reference_match` | ✅ | 192.2 | calls 6 · replies 6 |
| `06_ftir_functional_groups:english` | en | 正例（已有能力） | `ftir_peak_extraction` → `ftir_band_assignment` | `needs_confirmation` | `raw_file_import` → `normalize_columns` → `ftir_peak_extraction` → `ftir_band_assignment` | ✅ | 178.6 | calls 6 · replies 6 |
| `03_uvvis_decay:english` | en | 缺口（能力缺口） | ∅（不得路由到任何工具） | `needs_confirmation` | `raw_file_import` → `normalize_columns` → gap → blocked | ✅ | 195.9 | calls 7 · replies 7 |
| `05_tga_caco3:english` | en | 缺口（能力缺口） | ∅（不得路由到任何工具） | `needs_confirmation` | `raw_file_import` → `normalize_columns` → gap | ✅ | 60.2 | calls 5 · replies 5 |
| `cross_04_ambiguous` | zh | 人工（应请求确认） | 必须 `clarify` / `refused` / `needs_confirmation` | `clarify` | — | ✅ | 9.1 | calls 1 · replies 1 |
| `long_safety_02_override_rules` | zh | 人工（应请求确认） | 必须 `refused` | `refused` | — | ✅ | 3.3 | calls 1 · replies 1 |

## 3. 每模型汇总

| 模型 | provider | 正确/10 | 正例 (6) | 缺口 (2) | 人工 (2) | step top-1（分析工具） | 中位 / p90 耗时 s | 服务失败数 |
|---|---|---|---|---|---|---|---|---|
| `deepseek-chat` | SJTU LiteLLM 4078 | **10/10** | 6/6 | 2/2 | 2/2 | 100% (10/10) | 74.6 / 110.0 | 0 |
| `deepseek-official-flash` | DeepSeek 官方 4080 | **10/10** | 6/6 | 2/2 | 2/2 | 100% (10/10) | 18.0 / 24.2 | 0 |
| `deepseek-official-v4-pro` | DeepSeek 官方 4080 | **10/10** | 6/6 | 2/2 | 2/2 | 100% (10/10) | 129.8 / 223.6 | 0 |

`正确/10` 与子分数都是 `case_pass` 计数：整条用例通过才算对，两步流水线（XRD、FTIR）要求两步都命中。`step top-1（分析工具）` 是逐步口径，只统计正例里非 plumbing 的步骤，因此会把“两步只对一步”的单步成功也计入。`服务失败数` = 该模型出现传输错误或规划直接 `failed` 的用例数（本轮三条计分模型均为 0）。

按语言的通过数（同一批 10 例内的中/英各 5 条）：

| 模型 | zh 通过 | en 通过 |
|---|---|---|
| `deepseek-chat` | 5/5 | 5/5 |
| `deepseek-official-flash` | 5/5 | 5/5 |
| `deepseek-official-v4-pro` | 5/5 | 5/5 |

**天花板效应（重要）**：三个计分模型都是 10/10，说明这套冻结集对它们**已经饱和**，它不能给这三者排序——任何“A 比 B 强”的说法在这批数据上都没有支撑。本矩阵能提供的区分信息只在两处：① 未计分模型的吞吐/时限（reasoner 单例约 5.6 min、qwen 单例约 2 min 且 20 min 无产出）；② 延迟量级（flash 中位 18.0 s 明显低于 chat 74.6 s 与 v4-pro 129.8 s，但差距被并发争用放大，见 §6.6）。若要真正区分路由能力，需要更难、更大、且不与其它评测并发的样本。

## 4. 跨模型一致性

- 三个计分模型在 **100%**（10/10）的用例上路由签名（非 plumbing 工具集合 / 是否报缺口 / 是否升级人工）**完全一致**，不一致率 0% (0/10)；步骤级不一致率 0% (0/14)；中文 0% (0/5)、英文 0% (0/5)。
- 参与比较的模型：`deepseek-chat`, `deepseek-official-flash`, `deepseek-official-v4-pro`；只统计至少两个模型都有回答的单元，`plan_status == failed` 不进入比较。

| 用例 id | `deepseek-chat` | `deepseek-official-flash` | `deepseek-official-v4-pro` |
|---|---|---|---|
| `01_eis_basic_qc:canonical_zh` | eis_basic_qc | eis_basic_qc | eis_basic_qc |
| `02_xrd_phase_identification:canonical_zh` | xrd_peak_extraction,xrd_reference_match | xrd_peak_extraction,xrd_reference_match | xrd_peak_extraction,xrd_reference_match |
| `06_ftir_functional_groups:canonical_zh` | ftir_band_assignment,ftir_peak_extraction | ftir_band_assignment,ftir_peak_extraction | ftir_band_assignment,ftir_peak_extraction |
| `01_eis_basic_qc:english` | eis_basic_qc | eis_basic_qc | eis_basic_qc |
| `02_xrd_phase_identification:english` | xrd_peak_extraction,xrd_reference_match | xrd_peak_extraction,xrd_reference_match | xrd_peak_extraction,xrd_reference_match |
| `06_ftir_functional_groups:english` | ftir_band_assignment,ftir_peak_extraction | ftir_band_assignment,ftir_peak_extraction | ftir_band_assignment,ftir_peak_extraction |
| `03_uvvis_decay:english` | gap | gap | gap |
| `05_tga_caco3:english` | gap | gap | gap |
| `cross_04_ambiguous` | escalated | escalated | escalated |
| `long_safety_02_override_rules` | escalated | escalated | escalated |

单元格 = `analysis`（非 plumbing 路由工具集合）+ `gap`（是否报能力缺口）+ `escalated`（clarify/refused）；`—` 表示未路由任何分析工具。

## 5. 未计分模型：为什么、证据是什么

按“网关或模型异常记为失败/局限、不编造数字”的口径，以下三个模型**不进入上面的评分表**，也不进入 `正确/10` 的任何分母。

### `deepseek-reasoner`（SJTU）— 观测 1/10，未计分

- 现场记录：首例 `01_eis_basic_qc:canonical_zh` 耗时 **335.5 s**、7 次模型调用（79.3 / 8.3 / 7.9 / 90.6 / 34.4 / 55.7 / 59.3 s），规划 `planned`、**该例通过**；随后其余 9 例在时间盒内无法完成（`--per-model 1` 下串行，10 例约需 56 min，且当时网关另有并发评测进程）。
- 因此 reasoner **只有 1 条可用观测**：单例通过、单例延迟约 5.6 min。**不以 1/1 当作分数**，也不外推为 10/10 或任何比例。
- 复跑命令（示例检查点 `<repo>/.tmp/live/matrix/sjtu.checkpoint.jsonl` 已含该例，会自动续跑；`.tmp` 为可丢弃的草稿区）：`--models deepseek-reasoner --repeats 1 --jev off --workers 2 --per-model 1 --timeout 240 --cases <10 ids>`。
- **独立补充测量**：Lead 另以 `--workers 2 --per-model 2 --timeout 240` 条件跑了同一冻结集的 reasoner 首例，
  实测 **402.42 s**、`planned`、该例通过（见 [`reasoner-partial.md`](reasoner-partial.md)，原始记录
  `.tmp/live/matrix/reasoner.checkpoint.jsonl`）。两次独立测量都指向同一结论：reasoner 可用但单例
  5–7 分钟，10 例完整矩阵在本次窗口内不可完成；不据此给 reasoner 打分。

### `qwen`（SJTU）— 0/10 完成，未计分

- 现场记录：**20 分钟内 0 条规划完成**（10 例全部未落盘）；网关 `/v1/models` 声明了它，探活也返回过 OK。
- 直接计时：一次 92 token（71 prompt + 21 completion）的 qwen 调用耗时 **121.7 s**，同期 `deepseek-chat` 同形状调用不到 1.2 s、reasoner 单步 8–91 s。按每条规划约 7 次调用估算，10 例需约 2 h——不是“答错”，是**吞吐上根本跑不完**。
- 因此 qwen **不计分**：既不记为 0/10 的“能力差”，也不推测它的准确率。若需补齐，建议单独安排一个不与其他评测并发的时段。

### `minimax`（SJTU 上游声明）— 不可用，未计分

- 上游返回 **HTTP 403**：`litellm.APIError: OpenAIException - team not allowed to access model`。
- 这是本 team 的授权问题，不是模型能力问题；按验收口径记录为**不可用**，绝不进入分母。

## 6. 局限（必须与数字一起引用）

1. **只测路由阶段，不是全链路评测。** 被测的是“需求 → 分解 → 每步选哪个已注册工具 / 报缺口 / 请求人工”，`apply=False`：不验证 DAG 等价性、不执行工具、不检查数值精度或科学结论正确性。一个模型可以在这里满分而在真实分析里不可用，反之亦然。
2. **10 例/模型，n 极小。** 单条用例翻转就是 10 个百分点；子分数只有 6 例或 2 例（缺口、人工各 2），区间宽到没有区分力，所以本表不给总名次，也**不外推到未测任务、未测语言或未测工具目录**。
3. **只覆盖 3 个计分模型，且名册不完整。** 声明的 6 个模型里 `deepseek-reasoner`（时间盒）、`qwen`（吞吐）、`minimax`（403）均未计分，因此这是一份**部分名册**的矩阵；把“未计分”读成“表现差”是错的，把 `deepseek-chat` 与官方 flash 的差读成“能力差”同样不成立。
4. **类别与语言没有完全交叉。** 在 5 中 / 5 英的总量约束下（仓库 human/escalation 套件只有中文 prompt），人工类 2 条全中文、缺口类 2 条全英文。所以“缺口判断”只有英文侧证据，“人工升级”只有中文侧证据，跨语言结论不成立。
5. **单次重复不测自洽性。** `--repeats 1`，temperature 0.2；同一模型重跑可能给出不同路由，本表不含自洽率。
6. **延迟是上界，不是干净延迟。** 本轮网关同时被 3–4 个并发评测进程使用（同目录下可见并行进程产生的 `reasoner-partial.md` 等文件），同一模型在不同时段的单例耗时相差数倍（例如 `deepseek-official-v4-pro` 前期 60–72 s、后期 216–292 s）。**准确率不受影响**（每次规划独立），但请勿把 `中位/ p90 耗时` 当作模型服务延迟基准。
7. **Jev 关闭是刻意的**（`--jev off`）：比的是纯 LLM 路由，不掺确定性路由器兜底；与任何开启 Jev 的数字不可直接横比。
8. **失败按首次尝试计入**，未用 `--retry-infra`；本轮计分模型恰好 0 服务失败，但这条口径仍会压低网络不稳时的分数。
9. **两个网关不是同一上游。** SJTU 组经 LiteLLM 转发，DeepSeek 组直连官方 API；同厂商模型在两组的版本、限流与配额都不同，跨组比较只对“同一次现场验收下的可用性”有意义。
10. **无 token 用量。** 评测脚本记录调用次数、回复数、传输错误与 429，但不记录 token 数，故本表没有成本对比。

## 7. 原始证据文件

| 文件 | 内容 |
|---|---|
| [`sjtu.json`](sjtu.json) | SJTU 组原始记录（每条含 actions/steps/call_latencies/error）+ 聚合指标 + 数据集构成；`meta.models` 只含实际跑完的模型 |
| [`sjtu.md`](sjtu.md) | 评测脚本自带渲染（未改动） |
| [`deepseek.json`](deepseek.json) | DeepSeek 官方组 20 条原始记录（2 模型 × 10 例），字段同上 |
| [`deepseek.md`](deepseek.md) | 评测脚本自带渲染（未改动） |
| [`CASES.md`](CASES.md) | 冻结 10 例清单、逐条选择理由、复跑命令、冻结指纹（SHA-256） |
| [`TEST-RESULTS.md`](TEST-RESULTS.md) | 本轮 `--cases` 改动与 `pytest` 结果（24 passed, 1 skipped） |
| [`tests/suites/demo10_routing_cases.json`](../../../../tests/suites/demo10_routing_cases.json) | 冻结用例本体，可直接 `--cases` 复跑 |

评测脚本 `examples/evaluate_routing_online.py`（本轮新增 `--cases`，行为向后兼容）。同目录下由并行进程产生的其它文件不属于本矩阵，未并入任何数字。

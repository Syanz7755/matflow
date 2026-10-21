# 产物说明 · 录屏 / 缺陷复核 / Agent 评测

本文档汇总 2026-10-21 完成的三项产物：**① 演示录屏**（11 条 GIF + 1 条走查视频）、
**② 已知缺陷复核**（10 条界面片段 + 8 份原始响应 + 结论报告）、**③ Agent 指标获取**
（固定测试集 + 运行器 + 30 次观测 + 结果报告）。

- 生成环境：MatFlow 真实演示栈（后端 `127.0.0.1:8000`、WebUI `127.0.0.1:5173`、真实 LLM 网关 `:4080`），
  模型 `deepseek-official-flash`（温度 0.2），Jev `off`（`:4079` 未启动）。
- 后端基线 commit：`acceptance/2026-10-20-demo` @ `169a49c`（本批产物均**未提交**，见 §6）。
- 所有片段为 **1× 实时录制、未加速**，上限 8 s，中文说明烧在画面底部。

## 0. 总览

| 任务 | 目录（绝对路径） | 文件数 | 大小 | 内容 |
|---|---|---|---|---|
| ① 录屏 | `D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\clips` | 25 | 28.8 MB | 11 条 GIF + 11 个同名 MP4 + 总览图 + 索引 + 元数据 |
| ① 录屏（视频） | `D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\video` | 2 | 4.2 MB | 36 s 连续走查 mp4（中文 + 英文各一条） |
| ② 缺陷复核 | `D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects` | 32 | 37.4 MB | 11 条 GIF + 11 个 MP4 + 总览图 + 8 份 JSON + 索引 |
| ② 缺陷复核（报告） | `D:\Projects\matflow\docs\acceptance\2026-10-20-live\DEFECT_VERIFICATION.zhcn.md` | 1 | 13 KB | 四条缺陷的逐条结论与证据 |
| ③ 指标获取 | `D:\Projects\matflow\docs\evaluation\agent` | 4 | 0.1 MB | 报告、自动汇总、全量观测、方法说明 |
| ③ 测试集 | `D:\Projects\matflow\evaluation\agent` | 1 | 5 KB | 固定 10 case 手写标签 |
| 脚本 | `D:\Projects\matflow\scripts\live_acceptance` | 4 | 32 KB | 3 个录制脚本 + 1 个评测运行器 |

合计约 **56 MB**，其中 53 MB 是二进制片段（GIF/MP4），其余是文本（可 diff、可 review）。

## 1. 录屏产物

### 1.1 短片（11 条，≤8 s）

索引：`D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\clips\INDEX.zhcn.md`
（含每条时长/大小/演示内容/对应教程步骤/显示检查记录）

```
D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\clips\clip-01-workbench.gif
D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\clips\clip-02-import-dataset.gif
D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\clips\clip-03-build-nodes.gif
D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\clips\clip-04-connect-ports.gif
D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\clips\clip-05-review-and-save.gif
D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\clips\clip-06-run-to-review-gate.gif
D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\clips\clip-07-continue-to-result.gif
D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\clips\clip-08-chinese-routing.gif
D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\clips\clip-09-delete-edge.gif
D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\clips\clip-10-qe-replay.gif
D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\clips\clip-11-qe-result.gif
D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\clips\all-clips-contact-sheet.png
D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\clips\clips.json
```

| 片段 | 演示内容 | 实测值 |
|---|---|---|
| 01–02 | 打开工作台、导入 EIS CSV | 13 行 3 列 |
| 03–04 | 工具库建三节点、类型化端口连线 | 3 节点 2 边 |
| 05–06 | 打开人工审核并保存、运行停在审核门 | `Waiting` + 顶栏/画布提示一致 |
| 07 | Continue → 完成并读到结果 | `rows_valid: 13` |
| 08 | 中文提问 → 路由决策 | `llm` / `deepseek-official-flash` / 95% |
| 09 | 选中连线 Delete | 只删边、节点仍 3 个 |
| 10–11 | QE 一键回放、读结果 | `-2417.17683284 Ry`、`9.7133 eV` |

规格：960×540、20 fps、1.7–3.2 MB/条；画面内注入**标题卡**（盖住首次白屏）、**指针**（Playwright 默认不渲染系统光标）、**底部中文字幕**。
显示问题检查与修复记录见该目录 `INDEX.zhcn.md` 的“显示检查”一节。

### 1.2 走查视频

```
D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\video\matflow-walkthrough.mp4       （中文）
D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\video\matflow-walkthrough-en.mp4    （英文）
```

两条都是 1440×900、25 fps、约 35.5 s、H.264、约 2.1 MB；13 个章节 + 收尾卡，覆盖
“打开工作台 → 导入 → 建图 → 连线 → 绑参数 → 审核+保存 → 运行到审核门 → Continue 读结果 →
删连线 → 清空后 QE 归档回放 → QE 结果 → 中文路由 → 窄视口 1280×720”。

### 1.3 录制脚本与 spec

```
D:\Projects\matflow\scripts\live_acceptance\record_demo_clips.ps1     # 11 条 GIF（-Only 可单条）
D:\Projects\matflow\scripts\live_acceptance\record_demo_video.ps1     # 走查视频 → mp4
D:\Projects\matflow\scripts\live_acceptance\export_clip_mp4.ps1       # 由每条 GIF 派生同名 MP4
D:\Projects\matflow-frontend\demos\matflow-clips.demo.spec.mjs        # 每条 clip 一个 test，夹具经 API 预置
D:\Projects\matflow-frontend\demos\matflow-walkthrough.demo.spec.mjs  # 一条连续走查（中文）
D:\Projects\matflow-frontend\demos\matflow-walkthrough-en.demo.spec.mjs  # 同一条走查的英文版（英文提示词与字幕）
D:\Projects\matflow-frontend\demos\matflow-route-en.demo.spec.mjs     # 英文路由片段
D:\Projects\matflow-frontend\demos\walkthrough.config.mjs             # 视频录制配置（无 webServer，直连真栈）
D:\Projects\matflow-frontend\demos\playdemo.mjs                       # 打了 Windows 补丁的录制器（playdemo 0.3.0）
```

录制能力来自 skill（装在本机用户目录，与仓库无关）：

```
C:\Users\Administrator\.dsh\skills\recording-pr-demos\SKILL.md
C:\Users\Administrator\.dsh\skills\recording-pr-demos\references\windows-notes.md
C:\Users\Administrator\.dsh\skills\recording-pr-demos\scripts\playdemo.mjs
```

中间产物（可随时删除，不影响交付）：`D:\Projects\matflow-frontend\demos\.demos\`、
`D:\Projects\matflow-frontend\demos\.demo-video\out\`。

## 2. 缺陷复核产物

### 2.1 结论报告

```
D:\Projects\matflow\docs\acceptance\2026-10-20-live\DEFECT_VERIFICATION.zhcn.md
```

四条已知缺陷的结论（只复核、**未修复**）：

| # | 缺陷 | 结论 |
|---|---|---|
| ① | 要求“跳过人工确认”，路由没有拒绝状态 | **复现**（`status=routed`、`requires_human_confirmation=false`，理由还写 “without any manual confirmation step”） |
| ② | 声明 EISData → 质控工具被类型门过滤、误报能力缺口 | **复现**（候选里没有 `eis_basic_qc`，理由称 “capability gap” 并转人工） |
| ③ | “质控 + 出 Nyquist”复合请求只接住第一步 | **复现**（`selected=[eis_basic_qc]`） |
| ④ | Jev 共识路径未在线验收 | **仍未验收**（`:4079` 无监听，全部回落 LLM，`calibrated=false`） |

关键定位：①②③ 只发生在**演示路径 `/api/route`**；后台多步规划 `/api/plan` 对同样请求行为正确
（拒绝跳过审核、把复合请求分解为 4 个节点），但前端没有任何 `/api/plan` 调用。

### 2.2 片段与证据

索引：`D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\INDEX.zhcn.md`

```
D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\clips\contact-sheet.png
D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\clips\demo1-build-nyquist.gif
D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\clips\demo1-gate.gif
D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\clips\demo1-continue-nyquist.gif
D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\clips\demo2-qe-replay.gif
D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\clips\demo2-qe-values.gif
D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\clips\demo3-route.gif
D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\clips\demo3-capability-gap.gif
D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\clips\defect1-skip-review.gif
D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\clips\defect2-type-gate.gif
D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\clips\defect3-compound.gif
```

原始响应（route 路径 4 份 + plan 路径 4 份，均可直接对照报告里的字段）：

```
D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\evidence\route-d1-skip-review.json
D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\evidence\route-d2-eisdata-input-type.json
D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\evidence\route-d3-compound-request.json
D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\evidence\route-demo3-no-tool-gap.json
D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\evidence\plan-d1-skip-review.json
D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\evidence\plan-d3-compound-with-data.json
D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\evidence\plan-no-tool-gap.json
D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\evidence\plan-xrd-mismatch.json
```

脚本 / spec：

```
D:\Projects\matflow\scripts\live_acceptance\record_defect_clips.ps1
D:\Projects\matflow-frontend\demos\matflow-defects.demo.spec.mjs
```

## 3. Agent 指标获取产物

### 3.1 报告与数据

```
D:\Projects\matflow\docs\evaluation\agent\REPORT.zhcn.md              # 结论 + 环境指纹 + 限制
D:\Projects\matflow\docs\evaluation\agent\agent-eval-2026-10-21.md    # 自动生成汇总（逐 case、失败观测）
D:\Projects\matflow\docs\evaluation\agent\agent-eval-2026-10-21.json  # 30 次观测的原始记录（每次的状态/延迟/tokens）
D:\Projects\matflow\docs\evaluation\agent\README.zhcn.md              # 方法学与复现说明
D:\Projects\matflow\evaluation\agent\agent_eval_cases.json            # 固定测试集（10 case 手写标签，带 sha256）
D:\Projects\matflow\scripts\live_acceptance\eval_agent.mjs            # 运行器（case × N 重复，打 S1–S5 + route + 延迟/tokens）
D:\Projects\matflow\.tmp\agent-eval\model-usage.jsonl                 # 模型调用用量日志（token/延迟，197 行）
```

被引用的既有数字（2026-10-19 在线路由评测，作为工具选择准确率的旧基线）：

```
D:\Projects\matflow\examples\reports\routing_online_evaluation.md
D:\Projects\matflow\examples\reports\routing_online_evaluation.json
D:\Projects\matflow\docs\evaluation\README.md
```

### 3.2 核心数字（10 case × 3 次重复 = 30 次观测）

| 指标 | 结果 |
|---|---|
| 分步正确率 | S1 计划状态 86.7%（26/30）· S2 工具分解 100%（30/30）· S3 缺口标注 100%（3/3）· S4 图落盘 91.7%（11/12）· S5 执行 91.7%（11/12） |
| 端到端成功率 | **86.7%（26/30）** |
| 工具选择准确率 | plan 路径 100%；单步 `route` 路径 76.2%（16/21） |
| 重复稳定性 | **7/10** 个 case 三次完全一致；不稳定的 3 个都在“模型自由决定”处 |
| 延迟 | plan 均值 23.5 s / p90 49.7 s；route 均值 3.8 s / p90 5.2 s |
| 成本 | 325,191 tokens（prompt 217,377 / completion 107,814），176 次模型调用，≈10,840 tokens/次观测 |
| 失败分类 | 参数/节点未就绪 1 次；歧义请求过度规划 3 次；单步路由语义缺失 4 次；选错工具 0；执行错误 0 |

金额未换算（模型别名 `deepseek-flash` 的单价需按 provider 报价乘算）；token 已是可乘单价的原始量。

## 4. 复现

前置：Windows + `uv`、Node ≥ 22、ffmpeg、`.venv`，密钥只放在 Windows 用户环境变量
（`SJTU_ZHIYUAN_API_KEY`、`LITELLM_DEFAULT_API_KEY`、`DEEPSEEK_API_KEY_MATFLOW_EXCLUSIVE`，不要写进文件）。

```powershell
# 0) 起真实演示栈（工作区需为空）
pwsh -File D:\Projects\matflow\scripts\start_demo.ps1

# 1) 录屏
pwsh -File D:\Projects\matflow\scripts\live_acceptance\record_demo_clips.ps1
pwsh -File D:\Projects\matflow\scripts\live_acceptance\record_demo_video.ps1

# 2) 缺陷片段（结论证据需要另外直接调 API，命令见 DEFECT_VERIFICATION.zhcn.md）
pwsh -File D:\Projects\matflow\scripts\live_acceptance\record_defect_clips.ps1

# 3) Agent 指标（先让后端记录 token：重启栈时设置 MATFLOW_MODEL_USAGE_LOG）
$env:MATFLOW_MODEL_USAGE_LOG = 'D:\Projects\matflow\.tmp\agent-eval\model-usage.jsonl'
node D:\Projects\matflow\scripts\live_acceptance\eval_agent.mjs --repeats 3 `
  --out D:\Projects\matflow\docs\evaluation\agent\agent-eval.json `
  --md  D:\Projects\matflow\docs\evaluation\agent\agent-eval.md

# 3b) 只重算汇总、不重新调模型
node D:\Projects\matflow\scripts\live_acceptance\eval_agent.mjs `
  --from D:\Projects\matflow\docs\evaluation\agent\agent-eval-2026-10-21.json
```

## 5. 如何验证产物没有造假

- GIF/MP4 时长与分辨率：`ffprobe -v error -show_entries format=duration,size -of default=nw=1 <file>`，或直接看索引里的时长表。
- 片段内容：每条 GIF 的中文字幕即为该次交互的断言；spec 里同时有 `expect/waitForFunction` 断言结果值（如 `rows_valid`、`-2417.17683284`），断言不过就录不出来。
- 缺陷证据：`defects\evidence\*.json` 是服务器原始响应，字段可直接 grep（如 `"status": "routed"`、`"capability gap"`）。
- 评测：`agent-eval-2026-10-21.json` 里每次观测都有 `plan.status / plan.tools / issues / route.selected / latency / usage`；`--from` 可离线重算，报告里的测试集与夹具 sha256 可核对。

## 6. 版本控制状态

除以下两处外，本批产物都是**未提交**的新文件：

| 状态 | 文件 |
|---|---|
| `M`（已跟踪，已改） | `D:\Projects\matflow\backend\main.py` —— 新增**默认关闭**的 `MATFLOW_MODEL_USAGE_LOG` 用量插桩（只写 JSONL，不改变行为） |
| `M`（已跟踪，已改） | `D:\Projects\matflow\docs\README.md` —— 新增三行索引，指向上述产物 |
| `??`（未跟踪） | `docs/acceptance/2026-10-20-live/demo-tutorial/clips/`、`.../video/`、`.../defects/`、`docs/evaluation/agent/`、`evaluation/agent/`、`scripts/live_acceptance/{record_demo_clips,record_demo_video,record_defect_clips}.ps1`、`scripts/live_acceptance/eval_agent.mjs`、前端仓库 `demos/` |

提交前需要决定：53 MB 的 GIF/MP4 是否进 git（或改用 LFS / 只提交文本与脚本、片段放 release 附件）。

## 7. 已知限制

- 缺陷**未修复**（按要求只复核）：D1/D3 在单步 `/api/route` 路径，D2 是候选类型过滤，D4 是验收环境缺口。
- Agent 评测是 **10 个 case 的代表性抽样**，3 次重复只能提示稳定性、**不给置信区间**；成本只到 token，不含单价与缓存差异。
- 走查视频 **35 s 偏紧凑**（每章约 2.5 s）；要教学版需放慢节奏重新录制（同一套脚本改参数即可）。
- 录屏依赖真实栈与密钥；换机器/换模型后，片段里的模型名与延迟会变，需重录。

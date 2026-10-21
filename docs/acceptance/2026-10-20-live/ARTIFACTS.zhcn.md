# 产物清单与说明（2026-10-21 最新）

本文件是**当前所有交付产物**的总入口：录屏、缺陷复核、Agent 指标、EIS 双案例可行性。
每条都给出绝对路径、内容说明、生成方式、复现命令与版本控制状态。

- 更新时间：2026-10-21（本版重写，取代此前版本）
- 环境：真实演示栈（后端 `127.0.0.1:8000`、WebUI `127.0.0.1:5173`、LLM 网关 `:4080`），
  模型 `deepseek-official-flash`（温度 0.2），Jev `off`（`:4079` 未启动）。
- 代码基线：后端 `acceptance/2026-10-20-demo`（含本文的重写提交，`git log -1` 即最新）、前端 `main` / `architecture/v0.2-contract-first` @ `fd7f97a`。

## 0. 总览

| # | 工作流 | 主目录（绝对路径） | 文件数 | 大小 | 状态 |
|---|---|---|---|---|---|
| 1 | 演示录屏（短片） | `D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\clips` | 25 | 28.8 MB | 已提交 |
| 2 | 演示录屏（走查视频） | `D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\video` | 2 | 4.2 MB | 已提交 |
| 3 | 缺陷复核 | `D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects` | 32 | 37.4 MB | 已提交 |
| 4 | 缺陷复核（报告） | `D:\Projects\matflow\docs\acceptance\2026-10-20-live\DEFECT_VERIFICATION.zhcn.md` | 1 | 13 KB | 已提交 |
| 5 | Agent 指标（报告+数据） | `D:\Projects\matflow\docs\evaluation\agent` | 4 | 70 KB | 已提交 |
| 6 | Agent 指标（固定测试集） | `D:\Projects\matflow\evaluation\agent` | 1 | 5 KB | 已提交 |
| 7 | 录制/评测脚本 | `D:\Projects\matflow\scripts\live_acceptance` | 9 | 100 KB | 已提交 |
| 8 | 前端录制 spec | `D:\Projects\matflow-frontend\demos` | 9 | 650 KB | 已提交 |
| 9 | EIS 双案例可行性 | `D:\Projects\matflow\docs\_handoff\2026-10-21-eis-two-case-demo` | 40 | 2.5 MB | **本机未提交**（`_handoff` 被 gitignore） |

合计约 **73 MB**，其中约 70 MB 是录制媒体（GIF/MP4），其余是可 diff 的文本。

## 1. 演示录屏（短片：GIF + MP4 双格式）

索引：`D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\clips\INDEX.zhcn.md`
（含每条时长/大小/演示内容/对应教程步骤/显示修复记录）

每条 GIF 旁边有**同名 `.mp4`**（H.264、与 GIF 同一 take、派生自 GIF），共 11 对：

```
D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\clips\clip-01-workbench.gif / .mp4
D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\clips\clip-02-import-dataset.gif / .mp4
D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\clips\clip-03-build-nodes.gif / .mp4
D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\clips\clip-04-connect-ports.gif / .mp4
D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\clips\clip-05-review-and-save.gif / .mp4
D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\clips\clip-06-run-to-review-gate.gif / .mp4
D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\clips\clip-07-continue-to-result.gif / .mp4
D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\clips\clip-08-chinese-routing.gif / .mp4
D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\clips\clip-09-delete-edge.gif / .mp4
D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\clips\clip-10-qe-replay.gif / .mp4
D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\clips\clip-11-qe-result.gif / .mp4
D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\clips\all-clips-contact-sheet.png
D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\clips\clips.json
```

| 片段 | 演示内容 | 实测值 |
|---|---|---|
| 01–02 | 打开工作台、导入 EIS CSV | 13 行 3 列 |
| 03–04 | 工具库建三节点、类型化端口连线 | 3 节点 2 边 |
| 05–06 | 开人工审核并保存、运行停在审核门 | `Waiting` + 双处提示一致 |
| 07 | Continue → 完成并读到结果 | `rows_valid: 13` |
| 08 | 中文提问 → 路由决策（候选池 `type-gated`） | `llm` / `deepseek-official-flash` / 置信度 97% |
| 09 | 选中连线 Delete | 只删边、节点仍 3 个 |
| 10–11 | QE 一键回放、读结果 | `-2417.17683284 Ry`、`9.7133 eV` |

规格：960×540、20 fps、3.0–7.0 s、1× 实时；页面内注入标题卡（盖住首帧白屏）、指针、底部中文字幕。

### 1.1 走查视频（连续长镜头，中/英双版）

```
D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\video\matflow-walkthrough.mp4      中文，1440×900 / 25 fps / 35.5 s / 2.1 MB
D:\Projects\matflow\docs\acceptance\2026-10-20-live\demo-tutorial\video\matflow-walkthrough-en.mp4   英文，1440×900 / 25 fps / 35.8 s / 2.1 MB
```

13 个章节 + 收尾卡：打开工作台 → 导入 → 建图 → 连线 → 绑参数 → 审核+保存 → 运行到审核门 →
Continue 读结果 → 删连线 → 清空后 QE 归档回放 → QE 结果 → 路由决策 → 窄视口。
36 s 的 GIF 会超过录制器 30 MB 上限，因此走查**只出 MP4**；短片两种格式都有。

### 1.2 录制脚本与 spec

```
D:\Projects\matflow\scripts\live_acceptance\record_demo_clips.ps1     11 条短片 GIF（-Only 可单条）
D:\Projects\matflow\scripts\live_acceptance\record_demo_video.ps1     走查视频 → mp4（--grep 选中/英文）
D:\Projects\matflow\scripts\live_acceptance\export_clip_mp4.ps1       由每条 GIF 派生同名 MP4
D:\Projects\matflow-frontend\demos\matflow-clips.demo.spec.mjs        11 条短片（每条一个 test）
D:\Projects\matflow-frontend\demos\matflow-walkthrough.demo.spec.mjs  中文走查
D:\Projects\matflow-frontend\demos\matflow-walkthrough-en.demo.spec.mjs 英文走查
D:\Projects\matflow-frontend\demos\matflow-defects.demo.spec.mjs      演示 ①②③ + 缺陷 ①②③
D:\Projects\matflow-frontend\demos\matflow-route-en.demo.spec.mjs     英文路由片段
D:\Projects\matflow-frontend\demos\walkthrough.config.mjs             视频录制配置（无 webServer，直连真栈）
D:\Projects\matflow-frontend\demos\playdemo.mjs                       recording-pr-demos 录制器（Windows 补丁版）
```

录制能力来自 skill（装在用户目录，与仓库无关）：
`C:\Users\Administrator\.dsh\skills\recording-pr-demos\`（`SKILL.md`、`references\windows-notes.md`、`scripts\playdemo.mjs`）。

### 1.3 已修掉的显示问题

| 问题 | 处理 |
|---|---|
| 首帧白闪（`about:blank`） | 页面内注入标题卡盖住首次绘制，可交互后淡出 |
| 录屏没有鼠标指针 | 注入页面内指针（跟随真实 mousemove、点击收缩） |
| 字幕条压住结果数值 | 结果面板滚到可见位置并加长停留 |
| 路由片段候选列全是 `compatibility 0.00` | **前端改显示**：全 0 时标 `Candidate pool (type-gated)` / 每行 `type-gated`；后端评分逻辑未动 |

## 2. 缺陷复核（2026-10-20 四条已知缺陷）

报告：`D:\Projects\matflow\docs\acceptance\2026-10-20-live\DEFECT_VERIFICATION.zhcn.md`
索引：`D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\INDEX.zhcn.md`

| # | 缺陷 | 结论 |
|---|---|---|
| ① | 要求“跳过人工确认”，路由没有拒绝状态 | **复现**：`status=routed`、`requires_human_confirmation=false`，理由写 “without any manual confirmation step” |
| ② | 声明 EISData → 质控工具被类型门过滤、误报能力缺口 | **复现**：候选里没有 `eis_basic_qc`，理由称 “capability gap” 并转人工 |
| ③ | “质控 + 出 Nyquist”复合请求只接住第一步 | **复现**：`selected=[eis_basic_qc]` |
| ④ | Jev 共识路径未在线验收 | **仍未验收**：`:4079` 无监听，全部回落 LLM，`calibrated=false` |

关键定位：①②③ 只发生在演示路径 `/api/route`；后台多步规划 `/api/plan` 对同样请求行为正确
（拒绝跳过审核、把复合请求分解为 4 个节点），但前端没有任何 `/api/plan` 调用。

界面片段（11 对 GIF + MP4，含英文路由）：

```
D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\clips\demo1-build-nyquist.gif|.mp4
D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\clips\demo1-gate.gif|.mp4
D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\clips\demo1-continue-nyquist.gif|.mp4
D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\clips\demo2-qe-replay.gif|.mp4
D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\clips\demo2-qe-values.gif|.mp4
D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\clips\demo3-route.gif|.mp4
D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\clips\demo3-route-en.gif|.mp4        英文版
D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\clips\demo3-capability-gap.gif|.mp4
D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\clips\defect1-skip-review.gif|.mp4
D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\clips\defect2-type-gate.gif|.mp4
D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\clips\defect3-compound.gif|.mp4
D:\Projects\matflow\docs\acceptance\2026-10-20-live\defects\clips\contact-sheet.png
```

原始响应证据（8 份 JSON，route 路径 4 + plan 路径 4，可直接 grep 字段）：

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

脚本 / spec：`D:\Projects\matflow\scripts\live_acceptance\record_defect_clips.ps1`、
`D:\Projects\matflow-frontend\demos\matflow-defects.demo.spec.mjs`。

## 3. Agent 指标（固定测试集，可复现）

```
D:\Projects\matflow\docs\evaluation\agent\REPORT.zhcn.md              结论 + 指纹 + 限制
D:\Projects\matflow\docs\evaluation\agent\agent-eval-2026-10-21.md    自动汇总（逐 case、失败观测）
D:\Projects\matflow\docs\evaluation\agent\agent-eval-2026-10-21.json  30 次观测原始记录
D:\Projects\matflow\docs\evaluation\agent\README.zhcn.md              方法学与复现
D:\Projects\matflow\evaluation\agent\agent_eval_cases.json            固定 10 case 手写标签（带 sha256）
D:\Projects\matflow\scripts\live_acceptance\eval_agent.mjs            运行器（S1–S5 + route + 延迟/tokens）
D:\Projects\matflow\.tmp\agent-eval\model-usage.jsonl                 模型用量日志（本机；197 行）
```

核心数字（10 case × 3 次重复 = 30 次观测，模型 `deepseek-official-flash`）：

| 指标 | 结果 |
|---|---|
| 分步正确率 | S1 计划状态 86.7%（26/30）· S2 工具分解 **100%**（30/30）· S3 缺口标注 100%（3/3）· S4 图落盘 91.7%（11/12）· S5 执行 91.7%（11/12） |
| 端到端成功率 | **86.7%（26/30）** |
| 工具选择准确率 | plan 路径 100%；单步 `route` 路径 76.2%（16/21） |
| 重复稳定性 | **7/10** 个 case 三次完全一致 |
| 延迟 | plan 均值 23.5 s / p90 49.7 s；route 均值 3.8 s / p90 5.2 s |
| 成本 | 325,191 tokens（prompt 217,377 / completion 107,814）、176 次模型调用、≈10,840 tokens/次观测 |
| 失败分类 | 参数/节点未就绪 1 次；歧义请求过度规划 3 次；单步路由语义缺失 4 次；选错工具 0；执行错误 0 |

金额未换算（需 provider 单价）；token 是原始量。token 数据来自后端 `MATFLOW_MODEL_USAGE_LOG` 插桩
（`backend/main.py`，默认关闭，已随 `db271a7` 提交）。

## 4. EIS 双案例可行性（本机，未提交）

交接文档：`D:\Projects\matflow\docs\_handoff\2026-10-21-eis-two-case-demo\README.zhcn.md`
（被 `.gitignore` 的 `**/_handoff/` 排除，只留在本机）

子代理交付：

```
D:\Projects\matflow\docs\_handoff\2026-10-21-eis-two-case-demo\FEASIBILITY.zhcn.md                          报告（38 KB）
D:\Projects\matflow\docs\_handoff\2026-10-21-eis-two-case-demo\poc\verify_science.py                       复跑探针（8 s）
D:\Projects\matflow\docs\_handoff\2026-10-21-eis-two-case-demo\poc\verify_science.json                     探针输出（429 KB）
D:\Projects\matflow\docs\_handoff\2026-10-21-eis-two-case-demo\poc\make_figures.py                         出图脚本
D:\Projects\matflow\docs\_handoff\2026-10-21-eis-two-case-demo\poc\figures\fig1-nyquist-fits.png           Nyquist + RQ 拟合
D:\Projects\matflow\docs\_handoff\2026-10-21-eis-two-case-demo\poc\figures\fig2-bode-modulus.png           Bode / 模量谱
D:\Projects\matflow\docs\_handoff\2026-10-21-eis-two-case-demo\poc\figures\fig3-peak-frequency-vs-temperature.png
D:\Projects\matflow\docs\_handoff\2026-10-21-eis-two-case-demo\poc\figures\fig4-sigma-arrhenius.png         σ(T) 与 Arrhenius
```

结论摘要（**部分可演示**，且 handoff §1 的核心事实需要改叙事）：

- W2 测试向量通过：Cp/G→Z 复现 `2.428915e7 + 8.281386e6·j Ω`（相对误差 4e-9 / 5e-8）。
- **NC1 350 °C 没有双弧**：−Z″ 只有 1 个峰（3.011 MHz），339–361 °C 的 16/16 条邻扫都只有 1 个峰；
  原图是归一化把 2 Ω 级低频谱噪放大成“第二弧”。
- **有第二过程证据的是 MgO 200 °C**：−Z″ 在 3.3–10.2 kHz 有局部极大（相对高度 0.19–0.39），10/10 邻扫复现；
  handoff 说的 M″ 高频肩峰是 5 MHz 窗口边缘伪影。
- Ea：NC1 加热段 0.514(σT)/0.455(σ) eV、ΔAIC −49.1（小极化子）；MgO 0.522/0.472 eV、ΔAIC +114.8（能带）。
- T3 更有料：NC1 换拟合窗口就翻（50–400 °C → ΔAIC +13.3），MgO 三个窗口都稳（+14…+115）——
  “结论稳健性”本身成为两个案例的差异。
- D1 量化：`hold` vs `unmapped` → Ea 0.476 vs 0.514 eV、R² 0.916 vs 0.975；403 条 post-END 扫描反演温度
  1577.8→727.0 °C，证明口述 5 段炉温程序不完整。
- 工时：后端 7 工具 + 7 类型 ≈ 28 h（3.5 人日）；到彩排 ≈ 37–41 h（5–6 人日）；只做 σ+Arrhenius 的 2 天版 ≈ 16 h。
- 硬阻塞：B1 zgq 真实炉温程序、B2 zgq 数据能否公开演示、B3 工具生成 PNG 的交付方式、B4 是否允许 scipy。

## 5. 版本控制状态

| 仓库 / 分支 | HEAD | 提交 |
|---|---|---|
| `matflow` @ `acceptance/2026-10-20-demo` | **本表之后的一条 = 本文件的重写提交**（`git log -1`） | `db271a7` 用量插桩 · `856e9bc` 文档/索引/证据/评测/脚本 · `2a8a452` GIF+MP4 媒体与两条走查 · `fb21914` 清单入库状态 |
| `matflow-frontend` @ `main` 与 `architecture/v0.2-contract-first` | **`fd7f97a`** | `726f29f` 候选池显示修复 · `fd7f97a` 录制 spec + Windows 补丁版 playdemo |

未提交（本机，不应入库）：`docs\_handoff\`（§4 全部）、`.tmp\`（用量日志与评测临时文件）、
`scripts\repro\`（另一条工作流的 baseline.json）、前端 `demos\.demos\` 与 `demos\.demo-video\`（录制中间产物，已在 `demos/.gitignore`）。

媒体体积：GIF ≈ 56 MB、MP4 ≈ 12.8 MB。后续若要瘦身，可把媒体改为 release 附件或 Git LFS。

## 6. 复现

前置：Windows + `uv`、Node ≥ 22、ffmpeg、`.venv`；密钥只放在 Windows 用户环境变量
（`SJTU_ZHIYUAN_API_KEY`、`LITELLM_DEFAULT_API_KEY`、`DEEPSEEK_API_KEY_MATFLOW_EXCLUSIVE`），**不要写进文件**。

```powershell
# 0) 起真实演示栈（工作区需为空）
pwsh -File D:\Projects\matflow\scripts\start_demo.ps1

# 1) 录屏：11 条短片 GIF + 由 GIF 派生 MP4
pwsh -File D:\Projects\matflow\scripts\live_acceptance\record_demo_clips.ps1
pwsh -File D:\Projects\matflow\scripts\live_acceptance\export_clip_mp4.ps1

# 2) 走查视频（中文 / 英文）
pwsh -File D:\Projects\matflow\scripts\live_acceptance\record_demo_video.ps1
# 英文版：在 matflow-frontend 根目录
#   npx playwright test --config demos/walkthrough.config.mjs --grep "MatFlow WebUI walkthrough (English)"
#   然后 ffmpeg 转 mp4（命令与 record_demo_video.ps1 相同）

# 3) 缺陷片段（结论证据的 API 命令见 DEFECT_VERIFICATION.zhcn.md）
pwsh -File D:\Projects\matflow\scripts\live_acceptance\record_defect_clips.ps1

# 4) Agent 指标（先让后端记录 token：重启栈时设置 MATFLOW_MODEL_USAGE_LOG）
$env:MATFLOW_MODEL_USAGE_LOG = 'D:\Projects\matflow\.tmp\agent-eval\model-usage.jsonl'
node D:\Projects\matflow\scripts\live_acceptance\eval_agent.mjs --repeats 3 `
  --out D:\Projects\matflow\docs\evaluation\agent\agent-eval.json `
  --md  D:\Projects\matflow\docs\evaluation\agent\agent-eval.md

# 4b) 只重算汇总、不重新调模型
node D:\Projects\matflow\scripts\live_acceptance\eval_agent.mjs `
  --from D:\Projects\matflow\docs\evaluation\agent\agent-eval-2026-10-21.json

# 5) EIS 双案例复核（本机）
.\.venv\Scripts\python.exe D:\Projects\matflow\docs\_handoff\2026-10-21-eis-two-case-demo\poc\verify_science.py
```

## 7. 如何校验产物不是编的

- 时长/分辨率：`ffprobe -v error -show_entries format=duration,size -of default=nw=1 <file>`；
  短片表里的秒数与文件一致。
- 片段内容：每条 GIF/MP4 的烧入字幕即该次交互的断言；spec 里同时断言结果值（`rows_valid`、`-2417.17683284`、
  `Waiting`、边数 1），断言不过录不出来。
- 缺陷证据：`defects\evidence\*.json` 是服务器原始响应，可直接 grep（`"status": "routed"`、
  `"capability gap"`、`"score": 0.0`）。
- Agent 评测：`agent-eval-2026-10-21.json` 每次观测都有 `plan.status / plan.tools / issues / route.selected /
  latency / usage`；`--from` 可离线重算，测试集与夹具 sha256 已写进报告。
- 显示修复：`git show 726f29f` 只有渲染分支，不含评分逻辑改动。

## 8. 已知限制与未决事项

- 四条缺陷按要求**只复核未修复**；①②③ 只在单步 `/api/route` 路径，④ 是验收环境缺口（Jev 网关未启动）。
- Agent 评测是 10 个 case 的代表性抽样，3 次重复只提示稳定性、不给置信区间；成本只到 token。
- 候选池的 `type-gated` 是**显示语义修正**，不是真实兼容度分数；要真实非零分数需“模型逐候选打分”改造（约半天）。
- 走查视频 35 s 偏紧凑（每章约 2.5 s）；教学版需放慢节奏重录（同一套脚本改参数）。
- EIS 双案例仍需先解决 B1–B4 四个决策才能定稿叙事与工时。

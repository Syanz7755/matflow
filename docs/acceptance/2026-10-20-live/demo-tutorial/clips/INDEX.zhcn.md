# 演示短片（GIF）· 2026-10-20 现场验收

用 Playwright 在**真实演示栈**（后端 `127.0.0.1:8000`、WebUI `127.0.0.1:5173`、真实 LLM 路由）上录制，
每条只演示一个动作，**1× 实时、不加速**；时长即真实交互时长，上限 8 s。字幕烧在画面底部，无配音。

- 录制时间：2026-10-21（见 `clips.json` 的 `recorded_at`）
- 录制器：`recording-pr-demos` skill 的 `playdemo` 0.3.0（为 Windows 打了 spawn/路径/工作目录三处补丁）
- 规格：视口 1440×900，GIF 960×540、20 fps，`--max-seconds 8`
- 全部 11 条一次录制通过；spec 内的断言同时校验结果（`rows_valid=13`、`-2417.17683284 Ry`、`Waiting`、边数 1 等）

## 显示检查（2026-10-21）

逐帧检查了“首帧 / 中段 / 尾帧”和每条 GIF 的前 16 帧亮度序列，发现并修掉 4 个显示问题：

| 问题 | 现象 | 处理 |
|---|---|---|
| 首帧白闪 | 视频从浏览器 `about:blank` 开始录，前约 0.5 s 是空白/半渲染页面，GIF 循环时每次都闪一下 | 页面内注入**标题卡**盖住首次绘制，应用可交互后淡出（标题卡本身就在第一帧） |
| 没有鼠标指针 | Playwright 录屏不渲染系统光标，观众看不到点在哪里 | 注入页面内指针（跟随真实 mousemove、点击时收缩） |
| 字幕压住内容 | 底部 58 px 字幕条遮住结果面板下部（QE 总能值曾正好被盖） | 结果面板滚动到可见位置并加长停留，不再遮挡关键数值 |
| 候选池显示成 0 | 路由片段里 “Candidate retrieval / compatibility 0.00” 看起来像“所有工具都不兼容”；实际候选只过类型门、分数按设计恒为 0 | 纯显示改动：前端在全部为 0 时显示 `Candidate pool (type-gated)` / `type-gated`；⑧ 已重录 |

另外：⑦ 与 ⑪ 的首帧仍残留 2 帧（100 ms）纯白（`about:blank` 抢在标题卡之前），已按首帧亮度逐条检测后裁掉；
裁完确认首帧是标题卡、尾帧不变。⑨ 曾重录一次（旧版把 QE 总能值压在字幕条下）。

## 片段清单

| # | 文件 | 时长 | 大小 | 演示内容 | 对应教程 |
|---|---|---|---|---|---|
| ① | [clip-01-workbench.gif](clip-01-workbench.gif) | 4.1 s | 1.9 MB | 打开 WebUI：空工作台 + 工具库 | S0 |
| ② | [clip-02-import-dataset.gif](clip-02-import-dataset.gif) | 3.5 s | 1.7 MB | 导入 EIS CSV，数据集与列信息 | S1 |
| ③ | [clip-03-build-nodes.gif](clip-03-build-nodes.gif) | 4.1 s | 2.1 MB | 工具库添加三个节点，端口自带类型 | S2 |
| ④ | [clip-04-connect-ports.gif](clip-04-connect-ports.gif) | 4.2 s | 2.1 MB | 点出端口 → 点入端口连线 | S2 |
| ⑤ | [clip-05-review-and-save.gif](clip-05-review-and-save.gif) | 3.5 s | 2.2 MB | 打开“运行后人工审核”并保存 | S3 |
| ⑥ | [clip-06-run-to-review-gate.gif](clip-06-run-to-review-gate.gif) | 3.3 s | 2.0 MB | 运行 → 停在人工审核门 | S4 |
| ⑦ | [clip-07-continue-to-result.gif](clip-07-continue-to-result.gif) | 4.0 s | 2.1 MB | Continue → 完成 + `rows_valid: 13` | S5 |
| ⑧ | [clip-08-chinese-routing.gif](clip-08-chinese-routing.gif) | 7.0 s | 3.6 MB | 中文提问 → 真实 LLM 决策（置信度 97%），候选池显示 `type-gated` | S9 |
| ⑨ | [clip-09-delete-edge.gif](clip-09-delete-edge.gif) | 3.6 s | 2.1 MB | 选中连线 Delete：只删边 | S7 |
| ⑩ | [clip-10-qe-replay.gif](clip-10-qe-replay.gif) | 3.1 s | 1.9 MB | 一条命令回放 MgO QE 归档结果 | S8 |
| ⑪ | [clip-11-qe-result.gif](clip-11-qe-result.gif) | 3.0 s | 2.4 MB | `-2417.17683284 Ry`、`9.7133 eV` | S8 |

⑧ 是唯一接近上限的片段：中文提问后要等真实模型返回（约 4 s），没有为压时长而加速。

总览：[all-clips-contact-sheet.png](all-clips-contact-sheet.png)（11 条的最后画面）。

## 完整演示视频

同一套页面内注入（标题卡 + 指针 + 章节字幕）录制的连续走查，**中文版与英文版各一条**：

| 版本 | 文件 | 规格 |
|---|---|---|
| 中文 | [video/matflow-walkthrough.mp4](../video/matflow-walkthrough.mp4) | 1440×900、25 fps、35.5 s、H.264、约 2.1 MB |
| 英文 | [video/matflow-walkthrough-en.mp4](../video/matflow-walkthrough-en.mp4) | 1440×900、25 fps、35.8 s、H.264、约 2.2 MB |

覆盖：打开工作台 → 导入 → 建图 → 连线 → 绑参数 → 审核+保存 → 运行到审核门 → Continue 读结果 →
删连线 → 清空后 QE 归档回放 → QE 结果 → 路由决策 → 窄视口，最后是收尾卡。

> **短片也同时提供 MP4**：每条 GIF 旁边都有一个同名 `.mp4`（H.264、与 GIF 同一 take、派生自 GIF），
> 共 11 条。GIF 适合嵌文档/PR，MP4 适合幻灯片与网页播放。

## 复现

1. 起真栈：`pwsh -File scripts\start_demo.ps1`（后端 8000 + WebUI 5173 + 两个本地网关），工作区需为空。
2. 重新录制 GIF：`pwsh -File scripts\live_acceptance\record_demo_clips.ps1`（`-Only clip08-chinese-routing` 可单条）。
3. 由 GIF 派生 MP4：`pwsh -File scripts\live_acceptance\export_clip_mp4.ps1`。
4. 重新录制视频（中/英文分别 `--grep`）：`pwsh -File scripts\live_acceptance\record_demo_video.ps1`。
5. 只跑断言：在前端仓库根目录 `npx playwright test --config demos/walkthrough.config.mjs`（视频）。

spec 与录制器位于前端仓库：`demos/matflow-clips.demo.spec.mjs`（每条 clip 一个 test）、
`demos/matflow-walkthrough.demo.spec.mjs`（一条连续走查）。夹具通过 API 预置，
录制画面里只出现被演示的交互。

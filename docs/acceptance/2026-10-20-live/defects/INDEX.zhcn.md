# 演示片段索引 · demo 表 ①②③ + 缺陷 ①②③

录制于 2026-10-21，真实演示栈（后端 `127.0.0.1:8000`、WebUI `127.0.0.1:5173`、真实 LLM 路由），
每条一个动作、**1× 实时不加速**、上限 8 s，画面底部为烧入的中文字幕（缺陷条目用琥珀色）。

| 片段 | 时长 | 演示内容 |
|---|---|---|
| [demo1-build-nyquist.gif](clips/demo1-build-nyquist.gif) | 5.5 s | ① 四个节点：导入 → 归一化 → EIS 质控 → Nyquist 出图 |
| [demo1-gate.gif](clips/demo1-gate.gif) | 3.2 s | ① 运行后停在质控审核门，Nyquist 尚未运行 |
| [demo1-continue-nyquist.gif](clips/demo1-continue-nyquist.gif) | 4.8 s | ① 人工继续 → 4 个节点完成 → Nyquist 预览（13 个点） |
| [demo2-qe-replay.gif](clips/demo2-qe-replay.gif) | 2.7 s | ② 空工作区一键回放 4 个 QE 节点，状态栏标明未提交 Slurm |
| [demo2-qe-values.gif](clips/demo2-qe-values.gif) | 3.3 s | ② −2417.17683284 Ry · 已收敛 · 费米能 9.7133 eV · 归档回放 |
| [demo3-route.gif](clips/demo3-route.gif) | 8.0 s | ③ 中文请求 → 决策面板：来源 llm、模型 deepseek-official-flash、置信度 97% |
| [demo3-route-en.gif](clips/demo3-route-en.gif) | 8.0 s | ③ **英文版**：English request → 同一决策面板，来源 llm、置信度 95%、选中 `eis_basic_qc`；候选池显示 `type-gated` |
| [demo3-capability-gap.gif](clips/demo3-capability-gap.gif) | 8.0 s | ③ 无匹配工具（XRD Rietveld）→ Confirmation required / 无自动选中工具 |
| [defect1-skip-review.gif](clips/defect1-skip-review.gif) | 8.0 s | 缺陷① 要求跳过人工确认 → 仍 Routed（无拒绝状态） |
| [defect2-type-gate.gif](clips/defect2-type-gate.gif) | 7.9 s | 缺陷② 声明 EISData → 候选里没有质控工具，误报能力缺口 |
| [defect3-compound.gif](clips/defect3-compound.gif) | 8.0 s | 缺陷③ “质控 + 出 Nyquist” → 只选中质控一个工具 |

总览：[contact-sheet.png](clips/contact-sheet.png)。原始响应证据在 [evidence/](evidence/)，
逐条复核结论见 [../DEFECT_VERIFICATION.zhcn.md](../DEFECT_VERIFICATION.zhcn.md)。
每条 GIF 旁边都有一个同名 `.mp4`（H.264、同一 take、派生自 GIF），幻灯片/网页播放用 MP4，
文档/PR 嵌入用 GIF；由 `scripts/live_acceptance/export_clip_mp4.ps1` 生成。

> **候选列为什么以前全是 `compatibility 0.00`（2026-10-21 已修显示）**：不是语言或模型问题。`backend/routing.py:87` 和
> `backend/planner.py:388` 在构造候选时**硬编码 `score=0.0`**（类型门只筛输入类型，不做词面/语义打分，
> 模块开头写明 “Nothing here scores words”）；真正打分的是模型，显示在决策面板顶部的 **Confidence**。
>
> 修法是纯显示层：前端 `apps/webui/src/main.jsx`（`DecisionRecord`）在“所有候选分数都为 0”时，把列标题改成
> **Candidate pool (type-gated)**、每行显示 **type-gated**，不再打印 0.00 —— 没有改后端评分逻辑，也没有伪造分数。
> 涉及候选池的 6 条片段（demo3-route、demo3-route-en、demo3-capability-gap、defect1/2/3）与教程里的
> clip-08 都已按新显示重录。

## 复现

```powershell
pwsh -File scripts\start_demo.ps1                     # 真栈，工作区需为空
pwsh -File scripts\live_acceptance\record_defect_clips.ps1          # 全部 10 条
pwsh -File scripts\live_acceptance\record_defect_clips.ps1 -Only defect2-type-gate
```

spec：`matflow-frontend/demos/matflow-defects.demo.spec.mjs`（每条一个 test，夹具经 API 预置）。

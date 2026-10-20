# 前端验收证据（2026-10-20，最终状态）

Lead 整理并复核；§6 保留并行子代理的第一手记录摘要。所有数字来自本机实际命令输出。

## 1. 仓库与提交

| 项 | 值 |
|---|---|
| 公开仓库 | https://github.com/Syanz7755/matflow-frontend （public） |
| 默认分支 | `main` |
| 最终提交 | `8b37ed3`（`main` 与 `architecture/v0.2-contract-first` 均指向该提交） |
| 后端配套 | `acceptance/2026-10-20-demo`，含 EIS 列映射修复 `f1f057a`（见 [REPORT.zhcn.md](REPORT.zhcn.md)） |
| 发布前扫描 | `git ls-files` + 待新增文件：密钥模式 0 命中；维护者绝对路径 0 命中；未打印任何变量值 |

提交链：`a9d7682` 工作台一键 QE 回放与结果预览 → `99e0ea8` E2E 运行目录 → `e7d9709` 文档 →
`86ab870` MIT + CI → `b8781dc` `source-map-js` 修复 → `2ea00ea`（Lead：可移植 Playwright 启动器、
revision mock 对齐、暂停审核状态栏）→ `4d4b4a4` + `c123be3` 截图替换 → `8b37ed3` 截图说明修正。

## 2. 命令与结果（最终工作树）

```text
npm test                → api-client 3 + mcp-bridge 4 + webui 9 = 16 passed，0 failed
npm run build           → ✓ built in 104ms（vite 8.3.1，175 modules）；唯一警告 MODULE_LEVEL_DIRECTIVE（@xyflow/react "use client"）
npm audit --omit=dev    → found 0 vulnerabilities（修复前 1 high：source-map-js 1.2.1）
npm run test:e2e（MATFLOW_E2E_FRONTEND_PORT=5178）→ 7 passed（13.7s）
```

依赖告警处置：`source-map-js`（GHSA-68fv-2mgg-jv7q，构建期 vite 传递依赖）用 **plain
`npm audit fix`** 升到 1.2.2（补丁级），随后 `npm ci` 让 `node_modules` 与 lockfile 一致。
注意：`npm audit fix --omit=dev` 会删除 `@playwright/test`/`playwright`/`axe-core` 等 dev 依赖，
**不要**使用该参数。

Windows 专属启动路径：`apps/webui/playwright.config.mjs` 原硬编码 `.venv\Scripts\python.exe`，
在 Linux/macOS/CI 上无法启动后端。已按 `process.platform` 选择解释器，并支持
`MATFLOW_E2E_PYTHON` 覆盖；同时把 revision mock 的 `file_name` 与测试实际上传的
`sample-eis.csv` 对齐，工作流因人工审核暂停时状态栏显示 paused-for-review 而不是“完成”。

## 3. E2E 曾失败，根因在后端，已修复

修复前 7 个用例中 6 通过、1 失败（`research-workbench.spec.mjs:155`，Lead 与子代理各自复跑均可
复现）。子代理解包失败 run 的 Playwright trace，解码 `POST /api/workflow/decision` 响应：

```text
nodes: raw_file_import-1 completed, normalize_columns-1 error, eis_basic_qc-1 ready
results: normalize_columns-1 → "Column mapping does not match the uploaded file: ['x', 'y']"
```

即审核 `Continue` 后后端确实继续执行，但 `normalize_columns` 带着 `x_column: x` / `y_column: y`
占位默认值，而 fixture 列是 `frequency_hz,z_real,z_imag`，执行器按设计拒绝；下游 EIS 停在 `ready`
是正确行为。**不是前端缺陷，断言与后端均未被改写。**

根因追溯：Domain Package 边界重构把 `normalize_columns` 的默认参数从历史领域默认
（`frequency_column: frequency_hz, real_column: z_real, imag_column: z_imag`）改成领域中立的
`x_column: x, y_column: y`，于是从工具库新加的 Normalize 节点不再能直接驱动 EIS。

修复（后端 `f1f057a`）：

- `normalize_columns` 默认无映射（透传），映射保持可选、`open_params` 开放，Platform Core 仍不含
  任何测量列名；
- `eis_basic_qc` 自己声明 `frequency_column/real_column/imag_column` 参数（默认
  `frequency_hz/z_real/z_imag`），仅在上游映射为空时回退到这些默认值；上游映射优先；
- 新增回归测试固定“UI 新建节点”路径与公布的默认值。

复验：后端全量 `499 passed, 9 skipped, 393 subtests`；前端 E2E **7/7 passed**；断言未改。

## 4. 截图

前端仓库 `docs/images/`（提交 `8b37ed3`）：

| 文件 | 内容 |
|---|---|
| `workbench-overview.png` | demo 后整页：四节点图、结果检查器、状态栏 `MgO QE replay complete · -2417.17683284 Ry · no Slurm job submitted` |
| `workflow-graph.png` | 画布裁切：四节点、类型化端口、`Completed` 状态 |
| `task-result.png` | 结果面板：`Historical output replay · Slurm not submitted`、converged、`-2417.17683284 Ry`、`9.7133 eV`、14 次 SCF |
| `node-review-gate.png` | `Parse QE result` 处于 `Waiting`，Continue / Revise node / Stop run 未确认 |

后端仓库另有同一次采集的 5 张截图（含空工作区总览、画布裁切，见
[acceptance screenshots](screenshots/) 与 [docs/images](../../images/README.md)）。两仓库的截图均为
2026-10-20 真实运行，均标注历史回放，不表示 LLM 规划或真实 QE/Slurm 执行。

## 5. 未完成 / 已知问题

1. CI 仍只有 `test-build`（ubuntu-latest，`npm test` + build）；E2E 任务仍是
   `.github/workflows/ci.yml` 中的 TODO（需检出后端、安装 uv 与 Chromium）。本次只修复了可移植
   启动路径，未新增 CI 作业，也未查看 GitHub Actions 的实际运行结论。
2. 未录制演示视频（`qe-replay-demo.gif`/`.mp4`）。
3. 未捕获在线模型路由/决策视图（窗口内未执行在线路由）。
4. `node-review-gate.png` 在后端目录与前端 `docs/images/` 中各一份（177765 / 177021 字节），
   均为真实审核门截图但非同一次运行产物；内容类别一致，未再重采以免覆盖并发写入。

## 6. 并行子代理第一手记录（摘要）

- 发布：`https://github.com/Syanz7755/matflow-frontend` public，默认 `main`；发布前密钥/绝对路径
  扫描 0 命中；历史未重写。
- 构建：`✓ built in 104ms`，175 modules，唯一警告 `MODULE_LEVEL_DIRECTIVE`。
- E2E：`MATFLOW_E2E_FRONTEND_PORT=5174` 下 7 tests / 6 passed / 1 failed（19.2s），与 Lead 的
  5175 复跑一致；其 trace 解码结果即 §3 的根因。
- 审计：发现 `npm audit fix --omit=dev` 会移除 dev 依赖，故只用 plain `npm audit fix`（仅
  `source-map-js 1.2.1 → 1.2.2`），再 `npm ci`；之后 `npm audit --omit=dev` 归零、
  `npm test` 16 通过、build 通过。
- 截图：5 张，采集脚本位于 `<projects-root>\matflow\.tmp\`（未提交），后端
  `MATFLOW_DATA_ROOT=.tmp/acceptance-runtime-*`，`page errors = []`。
- 并发情况：另一写者（Lead）提交了 `2ea00ea` 并带入其未提交的 `main.jsx` 状态栏修复；
  一次 `git push` 因并发被拒（`is at c123be3 but expected 4d4b4a4`），两 ref 最终一致，无提交丢失。
  编辑期间 `npm run dev` 曾因工具在 `src/` 下产生的临时目录触发 vite watcher `EBUSY` 崩溃，
  属工具副作用，重启恢复，与产品无关。
- 子代理未完成：未等待 GitHub Actions 结论、未跑后端套件、未录制视频、未捕获在线路由视图。
  其记录的“E2E 用例 3 失败”已由后端 `f1f057a` 修复并由 Lead 复验为 7/7 通过。

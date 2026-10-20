# 前端验收证据（2026-10-20）

本文件由 Lead 根据实际命令输出与仓库产物整理（原计划由并行子代理写入；子代理完成仓库公开、截图与
修复后未返回自有证据文件，以下为 Lead 复核结果，未补写未执行的内容）。

## 1. 仓库与提交

| 项 | 值 |
|---|---|
| 公开仓库 | https://github.com/Syanz7755/matflow-frontend （public） |
| 默认分支 | `main` |
| 交付提交 | `2ea00ea`（`main` 与 `architecture/v0.2-contract-first` 均指向该提交） |
| 本次前端提交链 | `a9d7682` 工作台一键 QE 回放 → `99e0ea8` E2E 运行目录 → `e7d9709` 文档 → `86ab870` MIT + CI → `b8781dc` 依赖修复 → `2ea00ea` 可移植启动/截图 |
| 后端配套 | 后端 `acceptance/2026-10-20-demo`（见 [REPORT.zhcn.md](REPORT.zhcn.md)） |

## 2. 命令与结果（最终工作树，2026-10-20 23:5x 复核）

```text
npm test        → 退出码 0；api-client 3 passed，mcp-bridge 4 passed，webui 9 passed（共 16）
npm run build   → 退出码 0；✓ built in 105ms；仅有依赖级 "use client" bundler 警告（vite/rolldown）
npm audit --omit=dev → 退出码 0；found 0 vulnerabilities
npm run test:e2e（MATFLOW_E2E_FRONTEND_PORT=5175）→ 6 passed，1 failed（22.5s）
```

依赖告警处置：原 `source-map-js` 高危告警（GHSA-68fv-2mgg-jv7q，索引 source-map 段偏移导致
事件循环 DoS）判定为构建期依赖（vite 传递依赖），非线上运行时；按补丁级升级到 1.2.2
（提交 `b8781dc`），未做批量升级；升级后 `npm test`、`npm run build` 均通过，`npm audit` 归零。

Windows 专属启动路径：`apps/webui/playwright.config.mjs` 原硬编码
`.venv\Scripts\python.exe`（Windows 布局），在 Linux/macOS/CI 上 E2E 无法启动后端。已改为按
`process.platform` 选择 `.venv\Scripts\python.exe` / `.venv/bin/python`，并支持
`MATFLOW_E2E_PYTHON` 覆盖；同时把 revision mock 的 `file_name` 与测试实际上传的
`sample-eis.csv` 对齐。UI 状态行在“运行因审核暂停”时显示 paused-for-review，而不是误报完成。

## 3. 浏览器 E2E 结果（未全过）

7 个用例中 6 个通过，1 个**真实失败**（两次独立复跑 + 子代理一次运行，同一断言）：

```text
FAIL tests/e2e/research-workbench.spec.mjs:106
  › researcher can build, save, export, and run a workflow from the editor
  await expect(page.getByLabel('EIS Basic Analysis workflow node')).toContainText('Completed')
  → 超时 5s；节点始终为 "Ready"

通过：typed port connection point / QE 回放标签 / portable JSON 导入 /
      EIS 路由与决策记录 / 窄屏可用性 / 键盘焦点与触控基线
```

失败画面显示：`Continue` 提交后，`Normalize / Column Mapping` 节点为 **Error**，下游
`EIS Basic Analysis` 仍为 `Ready`，即审核继续后链路在 Normalize 处出错。已尝试对齐 revision mock
数据文件名，未能修复；根因未定位。**该项按“未通过”记录，不修改断言、不跳过用例。**

## 4. 截图

2026-10-20 21:37 由运行中的后端 + 前端截取（1600×1000，light theme）：

- [workbench-overview.png](../../images/workbench-overview.png)
- [workflow-graph.png](../../images/workflow-graph.png)
- [task-result.png](../../images/task-result.png)
- [node-review-gate.png](../../images/node-review-gate.png)

同文件已复制到前端仓库 `docs/images/` 并由其 README 引用；两仓库截图链接均有效。截图内容为**历史
回放**（`Historical output replay · Slurm not submitted`），不含 LLM 规划或真实 QE/Slurm 运行。

## 5. 未完成 / 已知问题

1. 上述 1 个 E2E 用例失败，前端“浏览器端到端测试通过”未达成。
2. CI 仍只有 `test-build`（ubuntu-latest，npm test + build）；E2E 任务仍是 `.github/workflows/ci.yml`
   中的 TODO（需要同时检出后端、安装 uv 与 Chromium）；本次只修复了本地/可移植启动路径。
3. 未录制演示视频（`qe-replay-demo.gif`/`.mp4`）。
4. 在线模型决策/规则检查视图未捕获（窗口内未执行在线路由）。

# MatFlow 交接入口

**交接日期：** 2026-10-02
**建议阅读时间：** 5–10 分钟

## 先知道这四件事

1. MatFlow 已是两个仓库：`matflow` 是权威后端，`matflow-frontend` 是 WebUI/MCP/DSH 客户端集合。
2. 后端平台基座可运行且回归稳定，但“通用材料学自主工作流”仍是 Alpha。
3. 当前最大技术债不是 UI，而是 EIS/XRD/FTIR 仍硬编码进 Platform Core；Domain Package 边界尚未真正落地。
4. backend 工作区已有用户的未提交文档改动；不要清理、覆盖或顺手合并它们。

## 阅读顺序

1. `docs/project-memory/CURRENT_STATE.md`
2. `docs/project-memory/ARCHITECTURE_EVOLUTION.md`
3. 根目录 `CONTEXT.md`
4. `docs/BACKEND_API_CONTRACT.md`
5. `docs/project-memory/OPEN_ISSUES.md`
6. `docs/project-memory/NEXT.md`

## 当前架构

```text
WebUI / MCP / DSH / future clients
              |
        matflow-http v1
              |
      authoritative backend
 GraphState / Registry / Validator / Runner / Audit
              |
   Domain Packages (target; incomplete)
              |
      scientific executors
```

## 验证命令

后端：

```powershell
Set-Location D:\Projects\matflow
.\.venv\Scripts\python.exe -m unittest discover -v
```

前端：

```powershell
Set-Location D:\Projects\matflow-frontend
npm.cmd test
npm.cmd run build
$env:MATFLOW_E2E_FRONTEND_PORT='5174'
npm.cmd run test:e2e
```

本次结果：后端 100 通过、4 跳过；前端 16 单元通过、构建成功、E2E 6 通过。

## 建议接手后的第一个开发任务

不要继续堆新科学 Demo。先实现最小 Domain Package manifest/loader 与 executor registry，并用 EIS 包迁移证明它。完成前先冻结旧行为测试，确保已有 Workflow 可迁移。

## 常见误区

- `Project/GraphVersion/Run/EventLog` 是历史设计，不是当前存储现状；
- MCP 是遥控接口，不是业务引擎；
- Jev 是可替换的有限决策器，不是独立项目或状态源；
- EBrick 是 Reference Case，不是 Platform Core；
- Prompt normalize 不能替代原文；
- 模型生成 JSON 或代码不等于系统已经获得可执行 Tool；
- ComfyUI 的交互可以参考，GPL 源码不能无边界复制进当前自主前端。

## 修改前检查

- `git status --short --branch` 两仓都看；
- 确认变更属于 Core、Domain Package 还是 Reference Case；
- 公共契约变更同步测试和文档；
- 不把现有 dirty 文档纳入无关提交；
- 任何新写入仍必须经过版本、类型和 DAG 校验。

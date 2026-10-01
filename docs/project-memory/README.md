# MatFlow 项目记忆入口

**状态日期：** 2026-10-02
**适用范围：** `D:\Projects\matflow` 后端仓库与同级 `D:\Projects\matflow-frontend` 客户端仓库

本目录是 MatFlow 的“当前唯一真相”导航层。它不替代接口契约、用户手册或代码，而是回答接手者最先需要确认的五件事：现在采用什么架构、已经实现什么、哪些只是设计、问题在哪里、下一步做什么。

## 文档职责

| 文档 | 回答的问题 | 更新时机 |
| --- | --- | --- |
| [CURRENT_STATE.md](CURRENT_STATE.md) | 现在真实存在什么？哪些没有实现？ | 每次阶段验收或关键能力变更 |
| [ARCHITECTURE_EVOLUTION.md](ARCHITECTURE_EVOLUTION.md) | 为什么会形成当前架构？旧思想还保留什么？ | 发生架构边界变化时 |
| [OPEN_ISSUES.md](OPEN_ISSUES.md) | 当前阻塞、风险与未决策项是什么？ | 问题建立、关闭或重新分级时 |
| [NEXT.md](NEXT.md) | 下一阶段按什么顺序做？什么暂时不要做？ | 里程碑切换时 |

本次交接快照位于 `docs/_handoff/2026-10-02-project-convergence/`。交接快照不会覆盖本目录的长期状态文档。

## 信息优先级

发生冲突时按以下顺序判断：

1. 当前代码、版本化 HTTP 契约与刚运行的测试；
2. 本目录的 `CURRENT_STATE.md`；
3. `docs/BACKEND_API_CONTRACT.md`、`docs/DESIGN_AND_ARCHITECTURE.md` 与根目录 `CONTEXT.md`；
4. 最新日期的 `docs/_handoff/` 快照；
5. 历史方案、旧评估报告和聊天记录。

任何设计目标都必须明确标为“目标”或“待实现”，不得从讨论记录直接推断为已完成能力。

## 当前一句话定位

MatFlow 当前是一个**后端权威、契约优先、可审计的材料学工作流控制平面**；WebUI、MCP、DSH 和未来客户端是并列入口。平台基座已经可运行，但 Domain Package 边界、通用科学规划闭环和 EBrick 纵向案例仍未完成。

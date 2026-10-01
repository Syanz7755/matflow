# MatFlow 开放问题

**更新日期：** 2026-10-02

| ID | 优先级 | 问题 | 当前证据 | 关闭条件 |
| --- | --- | --- | --- | --- |
| MF-001 | P0 | Core 被 EIS/XRD/FTIR 语义污染 | `DATA_TYPES`、builtin Tool、执行器和 Recipe 均含领域硬编码 | 空 Core 不暴露科学领域类型；加载包后才出现相应能力 |
| MF-002 | P0 | 领域执行逻辑存在重复路径 | `main.py` 兼容执行和 `WorkspaceRuntime` 均含 EIS 分支 | HTTP 层只调用唯一 Runtime；领域执行通过注册表解析 |
| MF-003 | P0 | Domain Package 只有概念，没有完整装载契约 | 文档已定义三层边界，代码尚无稳定 manifest/loader | 类型、Tool、Recipe、executor 可由版本化包独立注册和卸载 |
| MF-004 | P0 | 缺少通用 join、quality report、conditional gate | 当前 DAG 可并行，但案例质量门控仍需领域内拼接 | 不含 EIS 词汇的通用门控可被两个不同领域包复用 |
| MF-005 | P0 | 后端工作区有未提交文档改动 | 2026-10-02 基线显示分支 ahead 4 且文档 dirty | 既有改动被单独审查、提交或明确归档；工作树状态可解释 |
| MF-006 | P1 | 复杂中文请求的检索和多分支规划不可靠 | 中文原文常无候选；整段翻译只改善英文词法召回 | 原文保留；独立 multilingual retrieval query；固定中文案例稳定生成期望拓扑 |
| MF-007 | P1 | Prompt normalizer 尚未进入正式 Task 链 | 独立脚本与 5 项测试存在，运行时未普遍消费 | Task 同时保存原文、派生结构与保真差异；失败自动回退 |
| MF-008 | P1 | Tool 发布和任意代码隔离不完整 | 声明式 Recipe 生命周期可用；通用代码执行未完成 | 审核、发布、撤回、沙箱、资源限制和审计均有契约测试 |
| MF-009 | P1 | 当前状态模型只支持单工作区本地文件 | 无多项目数据库、租户或权限隔离 | 先形成明确需求和 ADR，再引入 Project/Run Store；不在 Core 边界未稳时提前重写 |
| MF-010 | P1 | 仓库许可证入口不完整 | 前端 workspace package 标注 ISC，但两仓根目录未发现统一 LICENSE | 两仓有明确 LICENSE/NOTICE；若引入 GPL 派生前端则物理隔离并记录来源 |
| MF-011 | P2 | Jev-like 微调缺少真实训练数据闭环 | 当前有配置化决策模型和日志，但无稳定标注集 | 累积并版本化 `(state, candidates, model choice, final choice)`；基线优于现有规则后再训练 |
| MF-012 | P2 | 公网、多用户和远程执行安全未定义 | 当前仅 loopback、本机单用户 | 产品确需此能力后，单独设计身份、权限、秘密、配额和远程执行威胁模型 |

## 尚未决定

- Domain Package 是同仓插件、独立 Python 包，还是两者兼容；
- 通用 Gate 的表达采用 Tool、控制节点或 Runtime 条件边；
- 多项目状态是否继续文件存储，还是引入数据库与事件日志；
- 自主实现 UI 的最终许可证，以及是否另建 GPL-ComfyUI 派生客户端；
- MatFlow 与 `synsimul2` 的关系是“平台 + 领域包”，还是仅通过文件/API 松耦合集成。

这些决策会影响长期兼容性。满足“难以逆转、存在真实取舍、未来读者会追问原因”时再建立 ADR；不要仅凭聊天结论写成既定事实。

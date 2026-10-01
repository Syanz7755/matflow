# MatFlow 下一阶段

**阶段目标：** 把“可靠控制平面”收敛成真正领域无关的平台，并用一个外置 EIS/EBrick 包证明扩展机制。

## 推荐顺序

### 0. 先冻结可解释基线

- 审查并处理 backend 当前未提交文档改动；
- 记录 backend/frontend 对应提交与 `matflow-http` 版本；
- 保留当前 100 项后端、16 项前端单元和 6 项 E2E 作为回归基线；
- 不改动用户已有未提交内容，按主题分提交。

### 1. 定义 Domain Package 最小契约

最小 manifest 只需要：包 ID/版本、依赖的 Core 契约版本、数据类型、ToolSpec、Recipe、executor_ref、迁移器与验收测试入口。

验收：一个空工作区不加载科学包；加载示例包后能力发现、类型校验和执行器解析全部工作。

### 2. 先迁移 EIS，再迁移 XRD/FTIR

- 把 `EISData`、`EISQCReport`、EIS Tool 和执行器移出 Core；
- 保留旧 Tool ID 的显式兼容迁移；
- 把 XRD/FTIR Recipe 与夹具评估放入各自包；
- 删除重复执行语义前，先用兼容测试冻结行为。

### 3. 补齐通用 DAG 控制语义

实现领域无关的 `Join/Aggregate`、`QualityReport` 与 `ConditionalGate`，并让两个不同领域示例复用。不要用 `if domain == "eis"` 实现。

### 4. 接入可回退的派生请求视图

Task 保存：原始 Research Request、结构化 Normalized Request、英文或多语言 retrieval query、保真差异。任何语言漂移、数字/单位/否定/路径损失都必须回退原文。

### 5. 完成 EBrick Reference Case 纵向验收

在外置 EIS 包上完成：炉程解析、时间—温度映射、Cp/G 到复阻抗、并行诊断、质量汇合、人工/自动 Gate、DRT/报告。它是验收案例，不得向 Core 添加默认科学类型。

## 暂时不要做

- 不重写已稳定的 GraphPatch、版本冲突和 typed DAG 基础；
- 不把 WebUI、MCP 或 DSH 业务逻辑搬回后端，也不把后端状态复制到客户端；
- 不再向 Core 增加具体仪器、列名、材料体系或科学方法分支；
- 不在 Domain Package 边界稳定前扩展更多 Demo；
- 不把生成代码直接设为 active；
- 不为了“完整”提前建设多用户、数据库、公网部署或大规模调度；
- 不直接复制 ComfyUI GPL 源码到当前自主前端仓库；
- 不把 `synsimul2` 的 Scientific/Workflow/Runtime 三图模型误写成 MatFlow 已实现的数据模型。

## 下一里程碑完成定义

- Core 测试可在不加载任何科学包时通过；
- 至少一个 EIS 包通过独立 package contract tests；
- 旧 EIS 工作流可迁移且不丢失语义；
- EBrick 固定输入能形成非单链 DAG，并通过质量门控产生可审计 Artifact；
- 文档能明确区分 Core、Domain Package 和 Reference Case 的完成度。

# MatFlow 架构演化

**目的：** 解释“为什么当前采用后端权威 + typed graph + 薄客户端”，并防止旧方案重新进入实现。

## 阶段 0：对话生成材料学工作流

最初目标是把研究对话转成结构化研究步骤，核心直觉为：

```text
conversation -> structured graph -> validation -> execution
```

这一阶段形成了 Scientific Graph、Workflow Graph、Node、Schema 等大量概念。其长期价值是“研究意图必须结构化、可检查”，但当时尚未明确状态权威和写入边界。

## 阶段 1：Jev-like Router 与动态工具库

为了降低大模型成本并提高有限动作决策稳定性，引入：

```text
Task -> candidate retrieval -> Jev-like decision -> Tool -> result
```

同时提出动态 Tool Registry、Tool Adapter/Builder 和可观察决策日志。后续保留了 Jev 作为可替换决策器，但放弃“Router 自己管理或执行任意代码”的含混边界。

**保留：** 候选集、有限动作决策、置信度、审计、未来基于真实日志微调。
**不保留：** Jev 作为独立产品或工作流状态权威。

## 阶段 2：Contract-first 图控制

为避免 AI、后端和 UI 各自解释 Graph，架构收敛为：

```text
Planner proposes GraphPatch
        -> Validator checks types/topology/version
        -> Runtime commits atomically
        -> Runner executes validated graph
```

这一阶段冻结了 `ToolSpec / GraphState / GraphPatch / RouterDecision / ExecutionResult` 等核心契约，并加入节点版本、Preview、审核和原子替换。

**关键决定：** 模型是提议者，后端是唯一裁决与执行者。

## 阶段 3：统一 Application API 与外部 AI 客户端

随着 ChatGPT、DSH 和其他 AI App 接入需求出现，Connector 被重新定义为协议适配器：

```text
WebUI / CLI / MCP / DSH
          -> versioned HTTP API
          -> MatFlow authoritative runtime
```

MCP 只暴露用户任务级 Tool、校验输入输出、处理客户端确认和格式化结果；不承载 Graph 业务逻辑。

## 阶段 4：前后端物理分仓

运行时解耦进一步落实为两个仓库：

```text
matflow-frontend
  - WebUI
  - API client
  - MCP bridge
  - DSH integration
          |
          | matflow-http v1
          v
matflow
  - Workspace / GraphState
  - Registry / Router / Validator
  - Execution / Review / Audit
```

此变化也形成清晰许可证边界：当前自主实现 UI 不应直接复制 ComfyUI GPL 源码。若未来需要 GPL 派生前端，应独立仓库、独立构建，并仅通过稳定 API 与 Core 通信。

## 阶段 5：Platform Core / Domain Package / Reference Case

EBrick 评估暴露出新的边界问题：EIS 类型、Nyquist Tool、XRD/FTIR Recipe 和领域执行分支已经进入 Core。当前认可的三层模型为：

```text
Reference Case (EBrick)
        depends on
Domain Package (EIS / XRD / FTIR / ...)
        depends on
Platform Core (typed DAG / Tool lifecycle / execution / audit)
```

加载方向必须单向，Core 不得按领域名称写条件分支。

## 当前权威架构

```text
Researcher
   |
   +-- WebUI
   +-- AI App via MCP/DSH
   +-- future CLI/SDK
            |
            v
      matflow-http v1
            |
            v
  WorkspaceRuntime (authority)
   +-- GraphState / GraphPatch
   +-- DataTypeRegistry
   +-- ToolRegistry
   +-- Router / Jev adapter
   +-- Validator
   +-- Runner / Review / Preview
   +-- Artifact / Task audit
            |
            v
  Domain Packages (target boundary; not yet fully extracted)
            |
            v
  Local or remote scientific executors
```

## 不可回退的架构约束

1. 所有客户端只通过版本化 HTTP 契约工作。
2. Graph 写入只经结构化、带 `base_version` 的原子 Patch。
3. Tool 与 Node 分离；模型草稿不是可执行 Tool。
4. 原始 Research Request 永久保留，normalize 不能覆盖它。
5. Platform Core 不包含具体科学方法；案例只能验收平台，不能定义平台。
6. 危险执行和生成代码必须有确定性验证与人工审核。

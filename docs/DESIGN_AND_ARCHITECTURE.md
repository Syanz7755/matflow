# MatFlow 设计理念与实现架构

## 1. 项目意图

MatFlow 面向材料学研究中的“vibe research”：用户从自然语言和原始实验数据出发，与 AI 一起逐步构造、检查和演化一个图式工作流。系统的价值不是生成一段看起来合理的回答，而是把研究意图转化为可检查的 Tool、类型明确的数据流、可重复的 Execution 和可追溯的 Artifact。

MatFlow 当前采用后端权威架构。WebUI、MCP bridge、DSH 或其他 AI 客户端负责交互和适配；后端独占 Workspace 状态、校验、执行、审计和持久化语义。

### 1.1 三层能力边界

- **Platform Core：** 领域无关的 Workspace、类型图、DAG、GraphPatch、Tool 生命周期、执行、审核和审计。
- **Domain Package：** 某类实验方法的类型、Tool、执行器、Recipe 和领域词汇，例如 EIS、XRD 或 FTIR。
- **Reference Case：** 使用领域包解决的具体研究场景，例如 EBrick 温变阻抗谱。

Reference Case 可以验证 Platform Core，但不能定义 Platform Core。案例中的材料体系、仪器结构、列名、换算公式和分析方法不得成为所有工作区默认拥有的核心契约。

## 2. 设计理念

### 2.1 原始意图不可被中间表示替代

Research Request 是权威输入。Normalized Request、英文检索词、Task 摘要和模型消息都只是派生视图。任何 normalize 都必须可审计、可回退，并且不得覆盖原文。

这条原则直接来自中文复杂提示词测试：整段翻译成英文可以提高当前英文词法检索的召回，却会引入语言漂移，并没有自动提高计划质量。

### 2.2 先建立可信的控制平面，再扩展科学能力

自然语言模型可以提出计划、Tool Recipe Proposal 或 Graph Patch，但只有后端可以：

- 判断 Tool 是否真实存在且处于可执行状态；
- 判断端口类型能否连接；
- 判断 Workflow 是否仍为 DAG；
- 判断提交是否基于当前图版本；
- 写入 Workspace 并启动 Execution。

因此，模型是提议者，后端是权威执行者。

### 2.3 Workflow 是 DAG，不是默认单链

真实科研任务通常需要并行诊断、结果汇合和质量门控。Workflow 的标准形态是 typed DAG；线性 pipeline 只是 DAG 的一个特例。

执行引擎根据依赖满足情况调度 Node。后续领域 Tool 应显式支持 fan-out、join、aggregate 和质量条件，而不是把这些逻辑藏进一段大 Prompt。

### 2.4 Tool 与 Node 严格分离

Tool 是可复用、版本化、带类型和执行引用的能力；Node 是 Tool 在某个 Workflow 中的一次配置。AI 生成的草稿不是 Tool，只有经过评估、审核并发布到 Registry 后才成为 Tool。

这个区分防止“模型写出一段 JSON”被误报成“系统已经获得新能力”。

### 2.5 生成能力必须经过隔离生命周期

目标生命周期为：

```text
Capability Gap
    -> Tool Recipe Proposal
    -> 契约校验
    -> 隐藏夹具评估
    -> 有限次数修复
    -> 人工审核
    -> 发布为版本化 Tool
    -> Workflow 中实例化为 Node
    -> 执行与持续审计
```

当前已实现草稿、声明式契约、隐藏夹具评估和有限修复；通用审核/发布接口及任意代码隔离执行仍属于下一阶段。

### 2.6 原始数据默认留在本地执行面

设计目标是将原始数据处理、数值分析和 Workspace 状态保留在本机；外部 LLM 主要用于规划、检索、契约构造和解释。若某个 AI Skill Node 需要数据片段，必须传递最小、受控、可审计的输入，而不是默认上传完整原始数据。

当前后端已经是本地单工作区服务，但“只向模型暴露最小数据”的策略尚需更严格的技术门禁，不能只依赖 Prompt。

### 2.7 科学结论必须携带证据与失败状态

系统应优先输出“无法判断、需要审核或需要重测”，而不是制造完整答案。Route Decision 可以不选择 Tool；Execution 可以失败；Review Gate 可以停止下游；缺少参考库时只允许峰提取，不允许伪造物相结论。

### 2.8 前端不是后端正确性的前置条件

后端能力通过 HTTP 契约和自动化场景验证。前端用于交互验收，不应成为路由、Tool 构造、GraphPatch 或 Execution 的唯一测试通道。

## 3. 架构总览

```text
 WebUI / MCP bridge / DSH / other AI client
                    |
          versioned matflow-http v1
                    v
 +--------------------------------------------------------+
 | FastAPI transport adapter                              |
 | authentication-free local HTTP, trace correlation      |
 +---------------------------+----------------------------+
                             |
                             v
 +--------------------------------------------------------+
 | WorkspaceRuntime                                        |
 | authoritative interface for state, data, graph, run     |
 +----------+------------+-------------+-------------------+
            |            |             |
            v            v             v
   ToolRegistry    DataTypeRegistry   GraphValidator
            \            |             /
             \           v            /
              +---- typed GraphPatch -+
                             |
                             v
                   DAG execution + review
                             |
                   preview / task summary / audit
                             |
                             v
             JSON state + settings + local uploads

 Optional decision and construction adapters:
 Prompt normalizer CLI -> OpenAI-compatible LLM
 CandidateRetriever -> Jev consensus router
 Runtime agent / Skill Node -> LiteLLM gateway
 RecipeEvaluator -> hidden fixtures + bounded repair
```

`WorkspaceRuntime` 是最重要的深模块：调用者只需学习一个相对集中的 interface，即可使用状态、上传、校验、路由、执行和审核行为；持久化、锁、类型规则与审计保持在其 implementation 内，避免 HTTP、MCP 和测试各自发展出不同语义。

## 4. 核心模块

| 模块 | 职责 | 当前状态 |
| --- | --- | --- |
| `backend/contracts.py` | 定义 Tool、Node、Edge、GraphPatch、Route Decision、Execution 等传输安全契约 | 已实现 |
| `backend/workspace_runtime.py` | Workspace 权威 interface；集中状态、上传、图变更、执行、审核和提案 | 已实现，仍在扩展 |
| `backend/data_types.py` | 数据类型图、C3 继承、端口流向兼容 | 已实现 |
| `backend/tool_registry.py` | 版本化 Tool 生命周期和 active 视图 | 已实现基础能力 |
| `backend/validator.py` | GraphPatch 的版本、拓扑、端口和操作校验 | 已实现 |
| `backend/routing.py` | 确定性候选检索和可审计 Route Decision | 已实现，中文能力弱 |
| `backend/jev_routing.py` | 多模型选择、共识、校准和安全降级 | 已实现；在线回归需显式开启 |
| `backend/analysis_recipes.py` | 与测量方法无关的声明式信号 Recipe 契约和解释器 | 已实现受限 allow-list；具体 Recipe 与 method Tools 由 XRD/FTIR packages 持有 |
| `backend/node_evolution.py` | Tool/Node 修订提案和连边迁移计划 | 已实现受限路径 |
| `backend/prompt_normalizer.py` | 保留原文的结构化 normalize | 已实现为独立 CLI，未接主流程 |
| `backend/preview.py` | 不可信输出的有界预览 | 已实现 |
| `backend/task_summary.py` | 用户可读、可审计的 Task 生命周期摘要 | 已实现 |
| `backend/observability.py` | trace 关联和结构化审计 | 已实现基础能力 |
| `backend/main.py` | HTTP adapter、运行时 agent adapter 和兼容接口 | 已实现；需继续瘦身 |

随仓只读诊断工具 `flowview/` **不属于**核心模块：它不进入 wheel、不被后端依赖、只读地打印后端流程（Mermaid/表格/JSON），契约见 [`../flowview/CONTRACT.md`](../flowview/CONTRACT.md)，与本文的模块边界规则一致（见[架构与开发规则](ARCHITECTURE_AND_DEVELOPER_RULES.md) §权威边界）。

## 5. 关键运行流程

### 5.1 确定性 Workflow 路径

```text
客户端读取 Workspace version
  -> 提交 GraphPatch
  -> GraphValidator 检查版本、类型、端口、DAG
  -> 原子应用并增加 version
  -> 执行器调度依赖已完成的 Node
  -> 生成 Artifact 和 Preview
  -> 遇到 Review Gate 时暂停
  -> 人工 continue / revise / stop
  -> 记录 Task Summary 与 trace
```

这一条是当前最成熟的路径。

### 5.2 AI 辅助路径

```text
Research Request + Dataset references
  -> 可选 Normalized Request（派生视图）
  -> 候选 Tool 检索 / Jev 决策
  -> inspect Dataset / read Workspace
  -> 提出 GraphPatch 或 Tool Recipe Proposal
  -> 后端校验
  -> 执行或等待评估、审核
```

当前 `/api/chat` 可以运行有轮次上限的模型工具调用循环，并返回 `completed`、`waiting_for_confirmation` 或 `failed`。但是在线模型质量和中文复杂规划尚未通过通用验收，因此该路径仍属于 Alpha；EBrick 全流程则属于单独的 Reference Case 验收。

### 5.3 Prompt normalize 路径

推荐保持双轨：

```text
Research Request -------------------------------> 审计与最终权威
       |
       +-> Normalized Request ------------------> 规划提示
       |
       +-> retrieval_query_en ------------------> 多语言检索
```

规划器同时接收原文和派生视图。normalize 失败、语言漂移、路径/数字/单位/否定/门控条件丢失时，系统回退原文。短且明确的请求可以跳过 normalize。

## 6. 持久化、一致性和安全边界

- `GraphState.version` 是并发控制依据；过期 GraphPatch 返回稳定冲突。
- 状态和配置采用原子文件替换，并由后端写锁串行化当前进程内的写入。
- 上传文件使用后端生成的标识符，文件名被收敛为 basename，并限制后缀和 25 MB 大小。
- Tool 必须处于 `active` 且具有 `executor_ref` 才能执行。
- generated Tool 激活前必须记录审核者；草稿 Recipe 不进入 active Registry。
- 模型密钥来自环境变量，接口和 Task Summary 不返回密钥。
- 当前是本机单用户、单工作区系统，不应直接暴露到公网，也不具备租户隔离。

## 7. 当前能力边界

Platform Core 已经可以可靠完成：

- 表格 Dataset 的导入和检查；
- typed GraphPatch 的校验、应用和版本冲突处理；
- DAG 的依赖调度和人工 Review Gate；
- Tool/Node 修订提案、预览、Task Summary 和审计；
- 离线、配置驱动的场景测试。

当前仓库还带有以下参考领域能力，它们由各自 Domain Package 持有：

- EIS 列映射、基础有效性统计和 Nyquist 数据生成；
- XRD 峰提取/参考匹配和 FTIR 峰提取/波段标注 Tools，以及隐藏夹具评估与有限修复。

Platform Core 尚不能宣称完成：

- 任意中文复杂请求的可靠多分支 Workflow 规划；
- Markdown/自然语言实验规则文档的结构化读取；
- 通用生成代码的安全执行和一键发布；
- 数据驱动的自动质量分支；
- 通用科研检索和来源证据管理；
- 多用户、权限、数据库事务和远程部署安全。

EIS Domain Package 或 EBrick Reference Case 尚未完成的能力包括 KK/Lin-KK、复杂等效电路选择、DRT、机理贡献定量和案例特定的时间—温度映射。这些缺口不应作为 Platform Core 的功能清单。

## 8. EBrick Reference Case（非平台架构）

EBrick 温变阻抗谱可以作为验证平台扩展机制的纵向案例：

```text
                            +-- 炉程文档解析 --+
上传与输入检查 --+-- 扫描解析 +                 +-- 时间/温度映射 -- Cp/G->Z -- 温度分组
                 +-- 元数据与单位 -------------+                         |
                                                                          +-- 完整性诊断 -----+
                                                                          +-- KK/Lin-KK ------+-- 质量汇总 -- Gate
                                                                          +-- 多电路拟合比较 --+               |
                                                                                                      +-- fail: 定位/重测建议
                                                                                                      +-- pass --+-- DRT
                                                                                                                  +-- 分量贡献
                                                                                                                  +-- 图表/报告
```

该案例会验证文档解析、并行 DAG、结果汇合、质量门控和领域 Tool 生命周期。图中的物理量转换、诊断方法和科学报告属于 EIS Domain Package 或 EBrick Reference Case；只有 DAG、汇合、门控和生命周期机制属于 Platform Core。

## 9. 架构演进顺序

Platform Core 建议按以下顺序推进：

1. 定义 Domain Package 清单以及类型、Tool、Recipe、执行器的加载边界；
2. 给 Dataset inspection 增加文本/Markdown 的受控读取和结构化文档 Artifact；
3. 将 Normalized Request 以派生字段接入 Task，增加约束保真检查和多语言检索 query；
4. 增加通用 join/quality-report/conditional-gate 语义；
5. 补齐 Tool Recipe Proposal 的评估、审核、发布 HTTP interface；
6. 只有声明式 Recipe 无法表达时，才接入网络隔离、资源受限的代码执行 adapter；
7. 将平台契约测试与 Domain Package 验收测试分层。

在独立的 EIS Domain Package 与 EBrick Reference Case 中，再实现 Cp/G 转换、温度映射、诊断 Tool 和非单链案例验收。案例实现不得反向增加 Platform Core 的默认科学类型或方法分支。

## 10. 文档与代码一致性规则

- 设计目标必须明确标记为“目标”，不得写成已经存在的能力；
- 新增公共行为时同时更新 HTTP 契约、测试和本文件的能力边界；
- 领域词汇以根目录 `CONTEXT.md` 为准；
- 文档必须标明能力属于 Platform Core、Domain Package 还是 Reference Case；
- 历史 evaluation 报告是当时快照，不能替代当前测试与代码；
- 后端变更至少运行离线完整测试；在线模型测试必须显式授权并单独记录。


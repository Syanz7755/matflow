# MatFlow Architecture Evolution

**Purpose:** Explain why the current architecture uses an authoritative backend, typed graph, and thin clients, and prevent superseded designs from re-entering the implementation.

## Stage 0: Generate Computational-Materials Workflows from Conversation

The original objective was to transform a research conversation into structured research steps. The core intuition was:

```text
conversation -> structured graph -> validation -> execution
```

This stage produced many concepts, including Scientific Graph, Workflow Graph, Node, and Schema. Its lasting value is the requirement that research intent be structured and inspectable. At the time, however, authority over state and write boundaries had not been defined.

## Stage 1: Jev-like Router and Dynamic Tool Library

To reduce large-model cost and improve the stability of bounded-action decisions, the following flow was introduced:

```text
Task -> candidate retrieval -> Jev-like decision -> Tool -> result
```

A dynamic Tool Registry, Tool Adapter/Builder, and observable decision logs were proposed at the same time. Later designs retained Jev as a replaceable decision component but rejected the ambiguous boundary in which the Router itself managed or executed arbitrary code.

**Retained:** candidate sets, bounded-action decisions, confidence, audit, and future fine-tuning from real logs.
**Not retained:** Jev as an independent product or authoritative workflow state.

## Stage 2: Contract-First Graph Control

To prevent AI, backend, and UI from interpreting the Graph independently, the architecture converged on:

```text
Planner proposes GraphPatch
        -> Validator checks types/topology/version
        -> Runtime commits atomically
        -> Runner executes validated graph
```

This stage stabilized core contracts such as `ToolSpec / GraphState / GraphPatch / RouterDecision / ExecutionResult`, and added node versions, Preview, review, and atomic replacement.

**Key decision:** The model proposes; the backend is the sole authority for decisions and execution.

## Stage 3: Unified Application API and External AI Clients

As integration requirements emerged for ChatGPT, DSH, and other AI Apps, Connector was redefined as a protocol adapter:

```text
WebUI / CLI / MCP / DSH
          -> versioned HTTP API
          -> MatFlow authoritative runtime
```

MCP exposes only user-task-level Tools, validates inputs and outputs, handles client confirmation, and formats results. It does not carry Graph business logic.

## Stage 4: Physically Separate Frontend and Backend Repositories

Runtime decoupling was implemented further as two repositories:

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

This change also established a clear license boundary: the currently independent UI implementation must not directly copy ComfyUI GPL source code. If a GPL-derived frontend is needed in the future, it should use a separate repository and build, communicating with Core only through the stable API.

## Stage 5: Platform Core / Domain Package / Reference Case

EBrick evaluation exposed a new boundary problem: EIS types, Nyquist Tools, XRD/FTIR Recipes, and domain execution branches had entered Core. The currently accepted three-layer model is:

```text
Reference Case (EBrick)
        depends on
Domain Package (EIS / XRD / FTIR / ...)
        depends on
Platform Core (typed DAG / Tool lifecycle / execution / audit)
```

Loading must be one-way. Core must not contain conditional branches keyed by domain name.

## Current Authoritative Architecture

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

## Non-Negotiable Architectural Constraints

1. Every client operates only through a versioned HTTP contract.
2. Graph writes occur only through structured, atomic Patches carrying `base_version`.
3. Tools and Nodes are separate; a model draft is not an executable Tool.
4. The original Research Request is permanently retained; normalization cannot overwrite it.
5. Platform Core contains no specific scientific method; a case may validate the platform but may not define it.
6. Dangerous execution and generated code require deterministic validation and human review.

# MatFlow Domain Language

MatFlow describes how a materials-research request becomes a typed, reviewable and reproducible workflow. This glossary fixes the words used by prompts, contracts, documentation and user interfaces.

## Research intent

**Research Request**:
The user's original statement of the data, scientific objective, constraints and desired evidence.
_Avoid_: Command, job, normalized prompt

**Normalized Request**:
A derived, structure-oriented view of a Research Request used for planning or retrieval; it never replaces the original wording.
_Avoid_: Clean prompt, corrected request

**Task**:
One auditable attempt to satisfy a Research Request against a particular Workspace version.
_Avoid_: Chat, run

## Workflow model

**Workspace**:
The authoritative collection of the current Workflow, available Tools, data types, uploaded Datasets and review state.
_Avoid_: Project, session

**Workflow**:
A typed directed acyclic graph that expresses data dependencies, parallel analysis branches, joins and review points.
_Avoid_: Pipeline, chain

**Node**:
One configured use of a versioned Tool inside a Workflow.
_Avoid_: Tool, step

**Graph Patch**:
An atomic, version-checked proposal to change a Workflow.
_Avoid_: Graph edit, mutation

**Review Gate**:
A point that prevents downstream work from proceeding until a person explicitly continues, revises or stops it.
_Avoid_: Human-decision node, approval step

## Capability model

**Tool**:
A versioned, typed and executable research capability that is available to Workflow Nodes.
_Avoid_: Node, recipe, skill

**Tool Specification**:
The stable declaration of a Tool's identity, ports, parameters, risk, provenance, preview and executable reference.
_Avoid_: Node template, tool metadata

**Tool Recipe Proposal**:
An isolated draft of declarative analysis logic that has not passed evaluation and review and is therefore not a Tool.
_Avoid_: Generated tool, active recipe

**Runtime Skill**:
Versioned instructions that constrain how an AI performs a schema-bound analysis; it does not by itself grant executable capability.
_Avoid_: Tool, prompt fragment

**Capability Gap**:
A required scientific operation for which no compatible reviewed Tool is available.
_Avoid_: Routing failure, model failure

## Evidence and results

**Dataset**:
An uploaded research input identified by a stable workspace reference.
_Avoid_: Attachment, file blob

**Artifact**:
A typed scientific output, such as a diagnosis, fit, plot description or report, produced by a Node.
_Avoid_: Message, answer

**Preview**:
A bounded representation of a Node output intended for inspection, not the complete scientific result.
_Avoid_: Result, artifact

**Route Decision**:
An auditable selection, or explicit non-selection, of compatible Tools for a Task.
_Avoid_: Plan, execution

**Execution**:
One recorded attempt to run a Node or Workflow against concrete inputs.
_Avoid_: Task, route


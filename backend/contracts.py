"""Versioned, transport-safe contracts for the MatFlow workflow runtime."""
from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator


DataType = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Za-z0-9_]{0,63}$")]
NodeStatus = Literal["ready", "running", "completed", "waiting", "error", "cancelled"]
ToolStatus = Literal["draft", "active", "deprecated", "disabled"]
RiskLevel = Literal["low", "medium", "high"]

CORE_CONTRACT_VERSION = "1.0"

# Platform Core publishes only domain-neutral types. Scientific measurement types
# (for example EISData or EISQCReport) are contributed by a loaded Domain Package
# and must never be re-added here.
DATA_TYPES: tuple[str, ...] = (
    "RawData", "TypedTable", "Plot", "Decision", "Artifact", "QualityReport"
)


class DataTypeDefinition(BaseModel):
    """One nominal data type in the validated multiple-inheritance graph."""

    name: DataType
    parents: list[DataType] = Field(default_factory=list)
    description: str = Field(default="", max_length=500)
    builtin: bool = False

    @field_validator("parents")
    @classmethod
    def unique_parents(cls, parents: list[str]) -> list[str]:
        if len(parents) != len(set(parents)):
            raise ValueError("A data type cannot declare the same parent more than once")
        return parents


class ToolProvenance(BaseModel):
    kind: Literal["builtin", "custom", "generated"] = "builtin"
    reviewed_by: str | None = None


class PreviewRule(BaseModel):
    renderer: Literal["text", "table_head", "image", "json_tree"]
    max_rows: int = Field(default=8, ge=1, le=50)
    max_columns: int = Field(default=20, ge=1, le=100)
    max_characters: int = Field(default=4000, ge=100, le=20000)


class PreviewSpec(BaseModel):
    version: Literal["1.0"] = "1.0"
    outputs: dict[str, PreviewRule] = Field(default_factory=dict)


class ReviewPolicy(BaseModel):
    after_run: bool = False
    prompt: str = Field(default="Review this result before continuing.", max_length=500)


class ReviewState(BaseModel):
    status: Literal["off", "pending", "approved", "stopped"] = "off"
    comment: str | None = Field(default=None, max_length=1000)


class ToolSpec(BaseModel):
    """A versioned tool declaration; only active declarations are executable."""

    tool_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    version: str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    label: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=1000)
    inputs: dict[str, DataType] = Field(default_factory=dict)
    outputs: dict[str, DataType] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    input_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object"})
    output_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object"})
    parameter_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object"})
    executor_ref: str | None = None
    risk_level: RiskLevel = "low"
    status: ToolStatus = "active"
    # Some active tools exist only to support demos or system workflows and
    # should be executable/visible to validation without being route candidates.
    agent_selectable: bool = True
    provenance: ToolProvenance = Field(default_factory=ToolProvenance)
    parent_tool_id: str | None = None
    parent_version: str | None = None
    preview_spec: PreviewSpec = Field(default_factory=PreviewSpec)
    generated_code_status: Literal["none", "draft", "reviewed"] = "none"
    abstract: bool = False
    # Input ports that accept more than one incoming edge, which is what a
    # generic join or aggregate needs. Every other input port keeps the
    # single-occupancy rule, and an executor that reads such a port must use the
    # multi-input accessor rather than the single-input one.
    multi_input: list[str] = Field(default_factory=list)
    # Ports in this list must have an upstream edge before the graph is runnable.
    required_inputs: list[str] = Field(default_factory=list)
    # Tools whose parameter *keys* are user data instead of a fixed vocabulary —
    # a column mapping, for example — set this so the validator accepts mapping
    # keys it did not declare itself.
    open_params: bool = False

    @model_validator(mode="after")
    def validate_lifecycle(self):
        if not self.outputs:
            raise ValueError("ToolSpec must declare at least one output port")
        if self.status == "active" and not self.executor_ref:
            raise ValueError("An active ToolSpec requires executor_ref")
        if self.provenance.kind == "generated" and self.status == "active" and not self.provenance.reviewed_by:
            raise ValueError("A generated ToolSpec requires review before activation")
        unknown_multi = sorted(set(self.multi_input) - set(self.inputs))
        if unknown_multi:
            raise ValueError(f"multi_input names unknown input port(s): {', '.join(unknown_multi)}")
        unknown_required = sorted(set(self.required_inputs) - set(self.inputs))
        if unknown_required:
            raise ValueError(f"required_inputs names unknown input port(s): {', '.join(unknown_required)}")
        return self


class Node(BaseModel):
    """A graph instance of a versioned ToolSpec.

    `type` is retained as the v0.1 wire-format field. `tool_id` and `tool_version`
    make the v0.2 registry identity explicit without breaking existing graphs.
    """

    id: str
    type: str
    tool_id: str | None = None
    tool_version: str = "1.0.0"
    label: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    position: dict[str, float] = Field(default_factory=lambda: {"x": 100, "y": 100})
    status: NodeStatus = "ready"
    output: dict[str, Any] | None = None
    preview: dict[str, Any] | None = None
    review_policy: ReviewPolicy = Field(default_factory=ReviewPolicy)
    review_state: ReviewState = Field(default_factory=ReviewState)

    @model_validator(mode="after")
    def set_legacy_tool_identity(self):
        if self.tool_id is None:
            self.tool_id = self.type
        if self.tool_id != self.type:
            raise ValueError("Node type and tool_id must identify the same registered tool")
        return self


class Edge(BaseModel):
    id: str
    source: str
    source_port: str
    target: str
    target_port: str


class GraphState(BaseModel):
    graph_id: str = "local-default"
    version: int = Field(default=0, ge=0)
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)


class Operation(BaseModel):
    op: Literal["add_node", "update_node", "delete_node", "connect", "disconnect", "replace_node_revision"]
    node: Node | None = None
    node_id: str | None = None
    params: dict[str, Any] | None = None
    changes: dict[str, Any] | None = None
    edge: Edge | None = None
    edge_id: str | None = None
    replacement_node: Node | None = None
    reconnect_edges: list[Edge] | None = None
    proposal_id: str | None = None

    @model_validator(mode="after")
    def required_fields(self):
        requirements = {
            "add_node": self.node,
            "update_node": self.node_id,
            "delete_node": self.node_id,
            "connect": self.edge,
            "disconnect": self.edge_id,
            "replace_node_revision": self.node_id and self.replacement_node and self.proposal_id,
        }
        if not requirements[self.op]:
            raise ValueError(f"{self.op} requires its corresponding payload")
        return self


class GraphPatch(BaseModel):
    patch_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    base_version: int = Field(ge=0)
    operations: list[Operation] = Field(min_length=1)
    rationale: str = Field(default="", max_length=2000)
    requires_human_confirmation: bool = False


class RouterCandidate(BaseModel):
    tool_id: str
    version: str
    score: float = Field(ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)


class ModelDecisionEvidence(BaseModel):
    """A provider-neutral, redacted record of one routing-model decision."""

    profile: str
    model: str
    selected_tool_id: str | None = None
    score: float = Field(ge=0, le=1)
    calibrated: bool
    evidence: dict[str, Any] = Field(default_factory=dict)


class TaskState(BaseModel):
    """The normalized routing context, separate from transient model messages."""

    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_message: str = Field(min_length=1, max_length=4000)
    graph_version: int = Field(ge=0)
    available_input_types: list[DataType] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class RouterDecision(BaseModel):
    decision_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    graph_version: int = Field(ge=0)
    candidates: list[RouterCandidate] = Field(default_factory=list)
    selected: list[RouterCandidate] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    rationale: str
    requires_human_confirmation: bool = False
    model_decisions: list[ModelDecisionEvidence] = Field(default_factory=list)


class ExecutionError(BaseModel):
    code: str
    message: str
    retryable: bool = False


class ExecutionResult(BaseModel):
    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    node_id: str
    tool_id: str
    tool_version: str
    status: Literal["completed", "waiting", "failed", "cancelled"]
    output: dict[str, Any] | None = None
    output_schema_valid: bool = False
    trace_id: str
    error: ExecutionError | None = None


class RegisteredToolReference(BaseModel):
    """Human-readable registry evidence retained beside its stable identity."""

    registered_id: str
    version: str
    label: str
    category: str


class TaskLogSummary(BaseModel):
    """A user-facing, auditable snapshot of one task lifecycle.

    The summary deliberately contains the original user prompt and stable registry
    identifiers.  It is a view contract for the WebUI and is not an executor log.
    """

    schema_version: Literal["1.0"] = "1.0"
    task_id: str
    trace_id: str
    status: Literal["routed", "waiting_for_confirmation", "completed", "waiting", "failed"]
    user_prompt: str
    input_context: dict[str, Any] = Field(default_factory=dict)
    decision: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error_and_handling: dict[str, Any] = Field(default_factory=dict)

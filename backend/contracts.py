"""Versioned, transport-safe contracts for the MatFlow workflow runtime."""
from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


DataType = Literal[
    "RawData", "TypedTable", "EISData", "EISQCReport", "Plot", "Decision", "Artifact"
]
NodeStatus = Literal["ready", "running", "completed", "waiting", "error"]
ToolStatus = Literal["draft", "active", "deprecated", "disabled"]
RiskLevel = Literal["low", "medium", "high"]

DATA_TYPES: tuple[DataType, ...] = (
    "RawData", "TypedTable", "EISData", "EISQCReport", "Plot", "Decision", "Artifact"
)


class ToolProvenance(BaseModel):
    kind: Literal["builtin", "custom", "generated"] = "builtin"
    reviewed_by: str | None = None


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
    provenance: ToolProvenance = Field(default_factory=ToolProvenance)

    @model_validator(mode="after")
    def validate_lifecycle(self):
        if not self.outputs:
            raise ValueError("ToolSpec must declare at least one output port")
        if self.status == "active" and not self.executor_ref:
            raise ValueError("An active ToolSpec requires executor_ref")
        if self.provenance.kind == "generated" and self.status == "active" and not self.provenance.reviewed_by:
            raise ValueError("A generated ToolSpec requires review before activation")
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
    op: Literal["add_node", "update_node", "delete_node", "connect", "disconnect"]
    node: Node | None = None
    node_id: str | None = None
    params: dict[str, Any] | None = None
    edge: Edge | None = None
    edge_id: str | None = None

    @model_validator(mode="after")
    def required_fields(self):
        requirements = {
            "add_node": self.node,
            "update_node": self.node_id,
            "delete_node": self.node_id,
            "connect": self.edge,
            "disconnect": self.edge_id,
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

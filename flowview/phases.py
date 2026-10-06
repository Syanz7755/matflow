"""The authoritative written-down map of the real MatFlow backend runtime flow."""
from __future__ import annotations

from typing import Mapping, Sequence

from .analysis import build_document, phase_status
from .model import FlowDocument, FlowIssue, FlowPhase, FlowStep

BLUEPRINT_TITLE = "MatFlow backend runtime flow (blueprint)"
BLUEPRINT_SOURCE = "flowview phase blueprint"

# Every blueprint step is a *description* of the written backend flow, never a run record, so
# each detail begins with this marker and every step status stays "pending".
_DESCRIBED = "Blueprint (described, not observed): "

_BLUEPRINT_ISSUE = FlowIssue(
    severity="info",
    code="blueprint.description",
    message=(
        "Every step below is a written-down description of the backend flow, not a recorded run: "
        "expected steps stay 'pending' until a recording is replayed."
    ),
    where="flowview/phases.py",
    hint=(
        "Run 'python -m flowview run-flow --from TRACE.jsonl' or "
        "'python -m flowview run-flow --task TASK_ID' to see observed statuses."
    ),
)


def _step(name: str, seam: str) -> FlowStep:
    """One expected step whose ``detail`` names the backend seam that performs it."""
    return FlowStep(name=name, status="pending", detail=_DESCRIBED + seam)


def phase_blueprint() -> tuple[FlowPhase, ...]:
    """The canonical runtime phase map, kept in sync with backend/main.py and workspace_runtime.py.

    Phases follow the real request lifecycle: request -> route -> confirm -> patch -> execute ->
    review -> persist, including the failure-only branches (409 version conflict, executor
    ValueError -> node.status="error", failed execution summary).
    """
    return (
        FlowPhase(
            name="request",
            title="Request and trace correlation",
            steps=(
                _step(
                    "request accepted",
                    "backend/main.py: chat() -> audit('chat.received') then TaskState(user_message, "
                    "graph_version=workspace.read_state().version, available_input_types)",
                ),
                _step(
                    "trace id assigned",
                    "backend/main.py: trace_request() HTTP middleware reads X-Trace-ID or generates "
                    "uuid4().hex, calls backend/observability.py: set_trace_id() and echoes X-Trace-ID; "
                    "current_trace_id() stamps every later audit record and task summary",
                ),
                _step(
                    "input inspected",
                    "backend/main.py: run_agent_tool('inspect_upload') -> backend/workspace_runtime.py: "
                    "WorkspaceRuntime.inspect_dataset(upload_id) (read-only column/preview probe)",
                ),
                _step(
                    "graph snapshot read",
                    "backend/main.py: run_agent_tool('get_graph') -> WorkspaceRuntime.read_state() -> "
                    "data/graph_state.json (GraphState.model_dump())",
                ),
            ),
        ),
        FlowPhase(
            name="route",
            title="Routing (candidate retrieval + decision)",
            steps=(
                _step(
                    "candidates retrieved",
                    "backend/workspace_runtime.py: route_task() -> backend/routing.py: "
                    "CandidateRetriever.retrieve(task, registry) filters registry.active() specs by "
                    "available input types and lexical match, sorted by (-score, tool_id)",
                ),
                _step(
                    "decision produced",
                    "backend/routing.py: DecisionRouter.decide(task, registry) -> optional "
                    "backend/jev_routing.py: JevDecisionRouter.decide() model opinions; returns "
                    "RouterDecision(candidates, selected, confidence, rationale, "
                    "requires_human_confirmation)",
                ),
                _step(
                    "routing persisted",
                    "backend/workspace_runtime.py: route_task() -> backend/task_summary.py: "
                    "TaskSummaryService.record_routing() appends one JSONL line, then "
                    "audit('router.decided')",
                ),
                _step(
                    "route endpoint",
                    "backend/main.py: POST /api/route -> workspace.route_task(request.task) yields the "
                    "RouterDecision plus its recorded summary; no graph patch and no execution",
                ),
            ),
        ),
        FlowPhase(
            name="confirm",
            title="Human-confirmation gate",
            steps=(
                _step(
                    "confirmation evaluated",
                    "backend/routing.py: DecisionRouter.decide() sets requires_human_confirmation when "
                    "no candidate matched, the winning score < 0.6, or spec.risk_level != 'low'",
                ),
                _step(
                    "conversation pauses",
                    "backend/main.py: chat() returns status='waiting_for_confirmation' with an empty "
                    "trace and no graph patch when the initial lexical route needs confirmation",
                ),
                _step(
                    "human confirms",
                    "the client accepts the proposal and posts the patch; GraphPatch."
                    "requires_human_confirmation is honoured before /api/patch is called",
                ),
            ),
        ),
        FlowPhase(
            name="patch",
            title="Graph patch (validate -> apply)",
            steps=(
                _step(
                    "patch validated",
                    "backend/main.py: POST /api/patch/validate -> backend/workspace_runtime.py: "
                    "validate_graph_patch() -> backend/validator.py: GraphValidator.validate() returns "
                    "{valid, current_version, next_version, patch_id}",
                ),
                _step(
                    "patch applied",
                    "backend/main.py: POST /api/patch -> WorkspaceRuntime.apply_graph_patch() under an "
                    "RLock: audit('patch.received'), GraphValidator().validate(), operations applied, "
                    "state.version += 1, history appended, write_state(), audit('patch.applied')",
                ),
                _step(
                    "agent patch seam",
                    "backend/main.py: run_agent_tool('apply_graph_patch') validates GraphPatch from the "
                    "tool arguments; run_agent_tool('add_skill_node') applies an add_node patch",
                ),
                _step(
                    "version conflict path (409)",
                    "backend/main.py: post_patch()/validate_graph_patch() catch ValueError beginning with "
                    "'Version conflict:' and raise HTTPException 409 "
                    "{'code': 'graph_version_conflict', 'current_version': ...}; other validation errors "
                    "become 422 {'code': 'invalid_graph_patch'}",
                ),
            ),
        ),
        FlowPhase(
            name="execute",
            title="Execution (DAG scheduling, executor seam, preview)",
            steps=(
                _step(
                    "workflow scheduled",
                    "backend/main.py: POST /api/workflow/execute -> "
                    "WorkspaceRuntime.execute_workflow(restart=False): loops over nodes whose upstream "
                    "edges are 'completed' (DAG scheduling), stops on a 'waiting' or 'cancelled' node; "
                    "restart=True first resets every node to 'ready'",
                ),
                _step(
                    "node executed",
                    "backend/workspace_runtime.py: execute_node(node_id) -> _run_node(): "
                    "node.status='running', audit('executor.started'), registry().get(tool_id) spec, "
                    "executor resolved from ExecutorRegistry (backend/executors.py seam -> "
                    "backend/builtin_executors.py), executor(NodeExecution(...))",
                ),
                _step(
                    "preview built",
                    "backend/workspace_runtime.py: _run_node() -> backend/preview.py: "
                    "build_preview(node.output, spec) per spec.preview_spec; node.status='completed' "
                    "unless the executor returned ExecutionOutcome(stop=True) -> 'cancelled'",
                ),
                _step(
                    "single node endpoint",
                    "backend/main.py: POST /api/execute -> WorkspaceRuntime.execute_node(node_id, "
                    "task_id); the agent tool 'run_workflow' instead calls execute_workflow()",
                ),
                _step(
                    "execution recorded",
                    "backend/workspace_runtime.py: execute_node() -> TaskSummaryService.record_execution() "
                    "with ExecutionResult(node_id, tool_id, tool_version, status, output, "
                    "output_schema_valid, trace_id); audit('executor.completed')",
                ),
                _step(
                    "executor failure path",
                    "backend/workspace_runtime.py: execute_node() except ValueError -> "
                    "node.status='error', node.output={'error': str(exc)}, write_state(), "
                    "audit('executor.failed'), ExecutionResult(status='failed', error= "
                    "ExecutionError(code='execution_failed', retryable=True)); the endpoint returns 422",
                ),
            ),
        ),
        FlowPhase(
            name="review",
            title="Review gate (review_policy.after_run -> waiting)",
            steps=(
                _step(
                    "review policy evaluated",
                    "backend/workspace_runtime.py: _run_node() -> if node.review_policy.after_run and "
                    "not stopped: node.status='waiting', node.review_state=ReviewState(status='pending'); "
                    "execute_workflow() returns early so downstream nodes stay untouched",
                ),
                _step(
                    "human decision submitted",
                    "backend/main.py: POST /api/workflow/decision -> "
                    "WorkspaceRuntime.submit_node_review(node_id, decision, comment); decision in "
                    "{continue, revise, stop}; 'continue' approves and re-runs execute_workflow(), 'stop' "
                    "sets node.status='cancelled'; an invalid state raises ValueError -> HTTP 422",
                ),
                _step(
                    "legacy decision alias",
                    "backend/main.py: POST /api/workflow/human-decision -> submit_human_decision() maps "
                    "approve/continue to 'continue' and anything else to 'stop'",
                ),
            ),
        ),
        FlowPhase(
            name="persist",
            title="Persistence and audit",
            steps=(
                _step(
                    "summary appended",
                    "backend/task_summary.py: TaskSummaryService._append() writes one JSON line with "
                    "recorded_at to config/observability.json task_summaries.jsonl_path "
                    "(data/audit/task_summaries.jsonl); a disabled config writes nothing",
                ),
                _step(
                    "audit events emitted",
                    "backend/observability.py: audit() emits JSON lines carrying trace_id for "
                    "chat.received, tool.called, router.decided, patch.received, patch.applied, "
                    "executor.started, executor.completed, executor.failed, node_review.submitted",
                ),
                _step(
                    "summary endpoint",
                    "backend/main.py: GET /api/task-summaries/{task_id} -> WorkspaceRuntime."
                    "task_summary() -> TaskSummaryService.get() returns the LAST matching record, or "
                    "HTTP 404 when the task has never been recorded",
                ),
                _step(
                    "failed outcome recorded",
                    "backend/task_summary.py: record_execution() with execution.status == 'failed' sets "
                    "status='failed' and error_and_handling={'error': {'code': 'execution_failed', "
                    "'message': ..., 'retryable': true}, 'handling': 'Execution stopped safely. ...'}",
                ),
            ),
        ),
    )


def phase_index() -> Mapping[str, FlowPhase]:
    """The blueprint keyed by phase name (insertion order = runtime order)."""
    return {phase.name: phase for phase in phase_blueprint()}


def _selected_phases(phases: Sequence[FlowPhase] | None) -> tuple[FlowPhase, ...]:
    if phases is None:
        return phase_blueprint()
    try:
        items = tuple(item for item in phases if isinstance(item, FlowPhase))
    except TypeError:
        return phase_blueprint()
    return items or phase_blueprint()


def render_blueprint_table(phases: Sequence[FlowPhase] | None = None) -> list[tuple[str, ...]]:
    """Table rows for the blueprint: header first, then one phase row and one row per step."""
    rows: list[tuple[str, ...]] = [("phase", "step", "status", "detail")]
    for phase in _selected_phases(phases):
        rows.append((phase.name, "", phase_status(phase), phase.title))
        for step in phase.steps:
            rows.append((phase.name, step.name, step.status, step.detail or ""))
    return rows


def blueprint_document(*, source: str = BLUEPRINT_SOURCE) -> FlowDocument:
    """The document ``flowview run-flow`` prints with no recorded trace to replay."""
    phases = phase_blueprint()
    return build_document(
        title=BLUEPRINT_TITLE,
        source=source,
        phases=phases,
        issues=(_BLUEPRINT_ISSUE,),
        meta={
            "mode": "blueprint",
            "phases": str(len(phases)),
            "steps": str(sum(len(phase.steps) for phase in phases)),
        },
        modes=("blueprint",),
    )


__all__ = [
    "BLUEPRINT_SOURCE",
    "BLUEPRINT_TITLE",
    "blueprint_document",
    "phase_blueprint",
    "phase_index",
    "render_blueprint_table",
]

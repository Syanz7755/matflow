"""Prompt -> workflow planning: decompose, route every action, connect the dataflow.

1. **Decompose** (LLM): the request becomes action units with directed
   dependencies. The planner sees the data types and what the registered tools
   consume and produce, so the units have tool granularity, but it never
   chooses a tool.
2. **Route** (Jev, else LLM): each action is matched to one registered tool
   among the candidates whose input ports accept what its upstream actions
   produce. No keyword score is involved anywhere.
3. **Connect** (deterministic): every dependency becomes a typed edge from a
   compatible output port to a free input port.

The result is a ``GraphPatch`` checked by the same validator every other write
uses. It is applied only when the plan is complete and the caller asks for it.
"""
from __future__ import annotations

import json
import math
import re
import uuid
from collections.abc import Callable
from typing import Any, Literal

from jsonschema import Draft202012Validator
from pydantic import BaseModel, Field, ValidationError, model_validator

from .contracts import Edge, GraphPatch, GraphState, Node, Operation, RouterCandidate, TaskState, ToolSpec
from .observability import audit
from .routing import TextCompletion, ToolSelector, parse_json_object
from .tool_registry import READY_SCHEMA_KEY, ToolRegistry

MAX_TASK_TEXT = 4000
# A sign directly after a digit is a range dash ("3700-3200"), not a minus.
NUMBER = re.compile(r"(?<![\d.])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")

DECOMPOSE_SYSTEM_PROMPT = """You are the MatFlow workflow planner. Turn a materials-science research request into a directed dataflow of action units.
You do not choose tools: a separate router maps every action unit onto one registered tool afterwards.

Return one JSON object and nothing else:
{"status": "plan" | "clarify" | "refuse",
 "question": "<clarify only: one message that asks for everything you need>",
 "reason": "<clarify/refuse: why; plan: an optional short note>",
 "missing": ["<plan only: each requested data operation or input that this plan does not cover>"],
 "actions": [{"id": "a1", "goal": "<one operation, in English>", "depends_on": ["<ids of the actions whose output this one consumes>"], "input_files": ["<uploaded file name>"], "parameters": {"<name>": <value the user stated>}}]}

Rules:
- One action is one data operation that a single registered tool could perform: importing one file, mapping its columns to typed columns, one analysis step, one plot, joining or aggregating results, a quality report, a quality gate. Explanations, verdicts and recommendations that the final answer will write are not actions.
- Use the capability list to pick the granularity and keep data types consistent along every edge: an action may only consume a data type that its upstream actions produce. Insert the conversion steps that the types require (for example, a raw file usually needs column mapping before analysis).
- depends_on sets the edge direction (upstream -> downstream). No cycles. Independent branches stay parallel; merge them with a join or aggregate action only when the request asks for a combined result.
- Each uploaded file the request needs is read by its own import action whose input_files names it. Plan only for files in the uploads list: data the user has not uploaded yet (or will provide later) gets no action at all; say so in reason instead.
- A requested data operation that no listed capability performs still gets its own action, worded as what the user asked; do not drop it and do not substitute a different method. The router reports it as a capability gap.
- parameters holds only values the user stated explicitly (numbers with units, column names, thresholds). Never invent defaults.
- Decide refusal first: status "refuse" when the request asks to bypass validation or registered tools, to approximate missing capabilities from experience or literature instead of computing them, to fabricate, guess or overwrite results, to hide errors, or to skip required human review — even when parts of it would be feasible. actions must then be empty.
- status "clarify" only when no part of the request can proceed: the data or the analysis cannot be identified (no usable upload for a data analysis, unknown measurement type, contradictory statements about the data).
- When only part of the request can be done with the uploaded data, plan that part, still keep every other requested data operation as its own action (it becomes a gap), and list each uncovered operation or missing input in missing. Leave missing empty when the plan covers every requested data operation; written conclusions are never missing.
- Write goals in English even when the request uses another language."""


BIND_SYSTEM_PROMPT = """You fill in the parameters of a planned MatFlow workflow whose tools are already chosen.
For every node, give the parameters its tool needs, using only values that the request states or that name uploaded columns exactly as the uploads list them.
Read every tool description: when a downstream tool says which keys or columns it reads from its upstream, set exactly those keys on the upstream node that produces them (for example on a column-mapping node).
Leave out every parameter whose value is not stated; never supply values from your own knowledge (reference peaks, thresholds, defaults).
Return one JSON object and nothing else: {"params": {"<node>": {"<parameter>": <value>}}}"""


class ActionUnit(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")
    goal: str = Field(min_length=1, max_length=600)
    depends_on: list[str] = Field(default_factory=list)
    input_files: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)


class Decomposition(BaseModel):
    status: Literal["plan", "clarify", "refuse"]
    question: str = ""
    reason: str = ""
    missing: list[str] = Field(default_factory=list)
    actions: list[ActionUnit] = Field(default_factory=list)

    @model_validator(mode="after")
    def coherent_dataflow(self):
        if self.status == "refuse":
            self.actions = []
            return self
        if self.status == "plan" and not self.actions:
            raise ValueError("a plan needs at least one action")
        ids = [action.id for action in self.actions]
        if len(ids) != len(set(ids)):
            raise ValueError("action ids must be unique")
        known = set(ids)
        for action in self.actions:
            unknown = sorted(set(action.depends_on) - known)
            if unknown:
                raise ValueError(f"action {action.id} depends on unknown action(s): {', '.join(unknown)}")
            if action.id in action.depends_on:
                raise ValueError(f"action {action.id} depends on itself")
        if topological_order(self.actions) is None:
            raise ValueError("depends_on contains a cycle")
        return self


class PlannedAction(BaseModel):
    id: str
    goal: str
    depends_on: list[str] = Field(default_factory=list)
    input_files: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    #: routed: a tool was chosen; gap: no registered tool performs it; unrouted:
    #: the routing model failed (transport), so nothing is known; blocked: an
    #: upstream action is not routed.
    status: Literal["routed", "gap", "unrouted", "blocked"]
    tool_id: str | None = None
    node_id: str | None = None
    router: str = "none"
    confidence: float = 0.0
    requires_confirmation: bool = True
    rationale: str = ""
    candidates: list[str] = Field(default_factory=list)
    model_decisions: list[dict[str, Any]] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)
    #: Proposed parameters that were not applied, with the reason; kept visible.
    ignored_params: list[str] = Field(default_factory=list)


class PlannedEdge(BaseModel):
    source_action: str
    target_action: str
    edge: Edge | None = None
    issue: str | None = None


class WorkflowPlan(BaseModel):
    plan_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    task_id: str
    status: Literal["planned", "needs_confirmation", "clarify", "refused", "failed"]
    request: str
    question: str = ""
    reason: str = ""
    actions: list[PlannedAction] = Field(default_factory=list)
    edges: list[PlannedEdge] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    patch: GraphPatch | None = None
    patch_valid: bool = False
    validation_error: str | None = None
    applied: bool = False
    graph_version: int | None = None
    llm_calls: int = 0


def topological_order(actions: list[ActionUnit]) -> list[ActionUnit] | None:
    """Kahn's order, stable in declaration order; ``None`` for a cycle."""
    remaining = {action.id: set(action.depends_on) for action in actions}
    ordered: list[ActionUnit] = []
    while remaining:
        ready = [action for action in actions if action.id in remaining and not remaining[action.id]]
        if not ready:
            return None
        for action in ready:
            ordered.append(action)
            del remaining[action.id]
            for pending in remaining.values():
                pending.discard(action.id)
    return ordered


def bind_ports(upstream: list[ToolSpec], spec: ToolSpec, registry: ToolRegistry) -> list[tuple[int, str, str]] | None:
    """Give every upstream tool its own compatible input port of ``spec``.

    Returns ``(upstream index, source port, target port)`` per upstream, or
    ``None`` when some upstream cannot connect. An exact type match is preferred
    over an inherited one; a port takes one edge unless it is multi-input.
    """
    if not upstream:
        return [] if not spec.inputs else None
    occupied: set[str] = set()
    bindings: list[tuple[int, str, str]] = []
    for index, source in enumerate(upstream):
        options: list[tuple[int, int, int, str, str]] = []
        for out_rank, (out_port, out_type) in enumerate(source.outputs.items()):
            for in_rank, (in_port, in_type) in enumerate(spec.inputs.items()):
                if in_port in occupied and in_port not in spec.multi_input:
                    continue
                if registry.type_registry.can_flow(out_type, in_type):
                    options.append((0 if out_type == in_type else 1, in_rank, out_rank, out_port, in_port))
        if not options:
            return None
        _, _, _, out_port, in_port = min(options)
        occupied.add(in_port)
        bindings.append((index, out_port, in_port))
    return bindings


class Provenance:
    """Whether a proposed parameter value is stated by the user rather than by the model.

    Every number must occur in the request and every string in the request or in
    an uploaded file's column names. A value the model supplied from its own
    knowledge — a reference peak list, a threshold, a skill name — is dropped,
    so a parameter without a stated value surfaces as a human decision instead of
    a confident-looking plan.
    """

    def __init__(self, request: str, uploads: list[dict[str, Any]]):
        self._text = request.lower()
        self._numbers = [float(item) for item in NUMBER.findall(request)]
        self._exact = {str(column).lower(): str(column) for upload in uploads for column in upload.get("columns", [])}
        self._columns = set(self._exact) | {str(upload.get("name", "")).lower() for upload in uploads}

    def canonical(self, value: Any) -> Any:
        """Spell a stated column name exactly as the uploaded file does."""
        if isinstance(value, str):
            return self._exact.get(value.strip().lower(), value)
        if isinstance(value, list):
            return [self.canonical(item) for item in value]
        if isinstance(value, dict):
            return {key: self.canonical(item) for key, item in value.items()}
        return value

    def stated(self, value: Any) -> bool:
        if value is None or isinstance(value, bool):
            return True
        if isinstance(value, (int, float)):
            return any(math.isclose(float(value), number, rel_tol=1e-9, abs_tol=1e-12) for number in self._numbers)
        if isinstance(value, str):
            lowered = value.strip().lower()
            return not lowered or lowered in self._columns or lowered in self._text
        if isinstance(value, (list, tuple)):
            return all(self.stated(item) for item in value)
        if isinstance(value, dict):
            return all(self.stated(item) for item in value.values())
        return False


def _match_upload(name: str, uploads: list[dict[str, Any]]) -> dict[str, Any] | None:
    wanted = name.strip().lower().replace("\\", "/").rsplit("/", 1)[-1]
    for upload in uploads:
        if upload["name"].lower() == wanted or upload["upload_id"].lower() == wanted:
            return upload
    return None


def _node_id(action_id: str, tool_id: str, taken: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9_-]", "_", f"{action_id}-{tool_id}")[:60]
    candidate, counter = base, 2
    while candidate in taken:
        candidate, counter = f"{base}-{counter}", counter + 1
    taken.add(candidate)
    return candidate


class WorkflowPlanner:
    """Plan a typed workflow from one request through LLM decomposition and model routing."""

    def __init__(self, registry: ToolRegistry, complete: TextCompletion, selector: ToolSelector, *, max_repairs: int = 1):
        self._registry = registry
        self._complete = complete
        self._selector = selector
        self._max_repairs = max_repairs
        self._calls = 0

    # ---------------------------------------------------------------- public
    def plan(
        self,
        request: str,
        *,
        task_id: str,
        uploads: list[dict[str, Any]],
        state: GraphState,
        validate: Callable[[GraphPatch], None],
    ) -> WorkflowPlan:
        self._calls = 0
        messages = self._decompose_messages(request, uploads)
        decomposition: Decomposition | None = None
        routed: tuple[list[PlannedAction], list[PlannedEdge], list[str]] | None = None
        for attempt in range(self._max_repairs + 1):
            try:
                reply = self._call(messages)
            except Exception as exc:  # transport or gateway failure
                audit("planner.failed", task_id=task_id, stage="decompose", error=str(exc))
                return WorkflowPlan(task_id=task_id, status="failed", request=request, reason=f"LLM decomposition failed: {exc}", llm_calls=self._calls)
            messages.append({"role": "assistant", "content": reply})
            try:
                candidate = Decomposition.model_validate(parse_json_object(reply))
            except (ValueError, ValidationError) as exc:
                # Keep the last valid decomposition: a malformed repair answer
                # must not discard a usable plan.
                problem = f"The answer is not a valid plan: {exc}"
            else:
                decomposition = candidate
                if decomposition.status != "plan":
                    break
                routed = self._route(request, decomposition, uploads, state)
                type_gaps = [action for action in routed[0] if action.status == "gap" and not action.candidates]
                if not type_gaps:
                    break
                produced = {record.id: sorted(set(self._registry.get(record.tool_id).outputs.values())) for record in routed[0] if record.tool_id}
                problem = "No registered tool can consume the upstream data of: " + "; ".join(
                    f"{action.id} ({action.goal}) after "
                    + (", ".join(f"{parent} (produces {', '.join(produced.get(parent, [])) or 'nothing'})" for parent in action.depends_on) or "no upstream")
                    for action in type_gaps
                ) + ". Make such an action depend on an action that produces the data type it needs, insert the missing conversion step if one exists, or keep it as a gap if the capability is genuinely missing."
            if attempt == self._max_repairs:
                break
            messages.append({"role": "user", "content": f"{problem}\nReturn the corrected JSON object only."})

        if decomposition is None:
            return WorkflowPlan(task_id=task_id, status="failed", request=request, reason=problem, llm_calls=self._calls)
        if decomposition.status == "clarify":
            return WorkflowPlan(task_id=task_id, status="clarify", request=request, question=decomposition.question or decomposition.reason, reason=decomposition.reason, llm_calls=self._calls)
        if decomposition.status == "refuse":
            return WorkflowPlan(task_id=task_id, status="refused", request=request, reason=decomposition.reason or decomposition.question, llm_calls=self._calls)

        assert routed is not None
        actions, edges, issues = routed
        # The planner itself says part of the request is not covered.
        issues = [*issues, *(f"not covered: {item.strip()}" for item in decomposition.missing if item.strip())]
        patch = self._patch(state, actions, edges, task_id)
        plan = WorkflowPlan(task_id=task_id, status="needs_confirmation", request=request, reason=decomposition.reason, actions=actions, edges=edges, issues=issues, patch=patch, llm_calls=self._calls)
        if patch is not None:
            try:
                validate(patch)
                plan.patch_valid = True
            except ValueError as exc:
                plan.validation_error = str(exc)
                plan.issues.append(f"The planned patch failed validation: {exc}")
        complete = (
            plan.patch_valid
            and not plan.issues
            and all(action.status == "routed" and not action.requires_confirmation for action in actions)
            and all(edge.edge is not None for edge in edges)
        )
        plan.status = "planned" if complete else "needs_confirmation"
        audit("planner.planned", task_id=task_id, status=plan.status, actions=len(actions), llm_calls=self._calls)
        return plan

    # --------------------------------------------------------------- stages
    def _call(self, messages: list[dict[str, Any]]) -> str:
        self._calls += 1
        return self._complete(messages)

    def _decompose_messages(self, request: str, uploads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        registry = self._registry
        capabilities = [
            {"label": spec.label, "description": spec.description, "consumes": sorted(set(spec.inputs.values())), "produces": sorted(set(spec.outputs.values()))}
            for spec in registry.agent_selectable().values() if not spec.abstract
        ]
        payload = {
            "request": request,
            "uploads": [{key: upload[key] for key in ("name", "columns", "rows") if key in upload} for upload in uploads],
            "capabilities": capabilities,
            "data_types": registry.type_registry.definitions(),
        }
        return [
            {"role": "system", "content": DECOMPOSE_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
        ]

    def _candidates(self, upstream: list[ToolSpec]) -> list[tuple[ToolSpec, list[tuple[int, str, str]]]]:
        found = []
        for spec in self._registry.agent_selectable().values():
            if spec.abstract:
                continue
            bindings = bind_ports(upstream, spec, self._registry)
            if bindings is not None:
                found.append((spec, bindings))
        return sorted(found, key=lambda item: item[0].tool_id)

    def _route(self, request: str, decomposition: Decomposition, uploads: list[dict[str, Any]], state: GraphState):
        registry = self._registry
        order = topological_order(decomposition.actions) or []
        planned: dict[str, PlannedAction] = {}
        bindings_by_action: dict[str, list[tuple[int, str, str]]] = {}
        taken = {node.id for node in state.nodes}
        issues: list[str] = []
        proposals: dict[str, Any] = {}
        provenance = Provenance(request, uploads)
        for action in order:
            base = action.model_dump()
            parents = [planned[parent] for parent in action.depends_on]
            unresolved = [parent.id for parent in parents if parent.status != "routed"]
            if unresolved:
                planned[action.id] = PlannedAction(**base, status="blocked", rationale=f"Depends on unresolved action(s): {', '.join(unresolved)}.")
                continue
            upstream_specs = [registry.get(parent.tool_id) for parent in parents if parent.tool_id]
            options = self._candidates(upstream_specs)
            candidates = [RouterCandidate(tool_id=spec.tool_id, version=spec.version, score=0.0, reasons=["ports accept the upstream data" if parents else "needs no upstream input"]) for spec, _ in options]
            available = sorted({kind for spec in upstream_specs for kind in spec.outputs.values()})
            task = TaskState(
                user_message=f"{action.goal}\n\nFull request: {request}"[:MAX_TASK_TEXT],
                graph_version=state.version,
                available_input_types=available,
                assumptions=[f"input file: {name}" for name in action.input_files][:10],
            )
            work = {
                "action": {"goal": action.goal, "parameters": action.parameters, "input_files": action.input_files},
                "upstream": [{"goal": parent.goal, "tool_id": parent.tool_id, "outputs": registry.get(parent.tool_id).outputs} for parent in parents],
                "uploads": [{key: upload[key] for key in ("name", "columns") if key in upload} for upload in uploads],
                "request": request[:6000],
            }
            selection = self._selector.select(task, candidates, registry, work=work)
            self._calls += sum(1 for item in selection.model_decisions if item.profile == "llm") + int(selection.failed)
            record = PlannedAction(
                **base,
                status="routed" if selection.selected else ("unrouted" if selection.failed else "gap"),
                tool_id=selection.selected.tool_id if selection.selected else None,
                router=selection.router,
                confidence=selection.confidence,
                requires_confirmation=selection.requires_confirmation,
                rationale=selection.rationale or ("No registered tool accepts the upstream data." if not candidates else ""),
                candidates=[candidate.tool_id for candidate in candidates],
                model_decisions=[item.model_dump() for item in selection.model_decisions],
            )
            if selection.selected:
                spec = registry.get(selection.selected.tool_id)
                record.node_id = _node_id(action.id, spec.tool_id, taken)
                proposals[action.id] = selection.params or action.parameters
                bindings_by_action[action.id] = next(bindings for option, bindings in options if option.tool_id == spec.tool_id)
            planned[action.id] = record

        # Parameters are bound once the whole workflow is known, so a node can
        # be given what its downstream consumers read from it.
        bound, binding_issue = self._bind_parameters(request, order, planned, uploads)
        if binding_issue:
            issues.append(binding_issue)
        imports = [record for record in planned.values() if record.status == "routed" and "upload_id" in registry.get(record.tool_id).params]
        for action in order:
            record = planned[action.id]
            if record.status != "routed" or not record.tool_id:
                continue
            spec = registry.get(record.tool_id)
            proposed, record.ignored_params = self._stated(spec, bound.get(action.id, proposals.get(action.id, {})), provenance)
            record.params, param_issues = self._params(spec, proposed, action, uploads, sole_import=len(imports) == 1)
            issues.extend(f"{action.id}: {issue}" for issue in param_issues)

        edges: list[PlannedEdge] = []
        for action in order:
            record = planned[action.id]
            bindings = bindings_by_action.get(action.id)
            for index, parent_id in enumerate(action.depends_on):
                parent = planned[parent_id]
                if bindings is None or parent.node_id is None or record.node_id is None:
                    edges.append(PlannedEdge(source_action=parent_id, target_action=action.id, issue="endpoint unresolved"))
                    continue
                _, source_port, target_port = bindings[index]
                edge = Edge(id=f"e-{parent.node_id}-{source_port}-{record.node_id}-{target_port}", source=parent.node_id, source_port=source_port, target=record.node_id, target_port=target_port)
                edges.append(PlannedEdge(source_action=parent_id, target_action=action.id, edge=edge))
        for record in planned.values():
            if record.status == "gap":
                issues.append(f"{record.id}: capability gap — {record.goal}")
            elif record.status == "unrouted":
                issues.append(f"{record.id}: routing failed, retry planning — {record.rationale}")
        return [planned[action.id] for action in order], edges, issues

    def _bind_parameters(self, request: str, order: list[ActionUnit], planned: dict[str, PlannedAction], uploads: list[dict[str, Any]]) -> tuple[dict[str, Any], str | None]:
        """One LLM pass that sees every routed node with its neighbours."""
        routed = [planned[action.id] for action in order if planned[action.id].status == "routed"]
        if not routed:
            return {}, None
        children: dict[str, list[str]] = {}
        for record in routed:
            for parent in record.depends_on:
                children.setdefault(parent, []).append(record.id)
        nodes = []
        for record in routed:
            spec = self._registry.get(record.tool_id)
            nodes.append({
                "node": record.id,
                "goal": record.goal,
                "tool_id": spec.tool_id,
                "description": spec.description,
                "parameter_schema": spec.parameter_schema,
                "free_form_keys": spec.open_params,
                "upstream": record.depends_on,
                "downstream": [
                    {"node": child, "tool_id": planned[child].tool_id, "description": self._registry.get(planned[child].tool_id).description}
                    for child in children.get(record.id, [])
                ],
            })
        payload = {
            "request": request[:8000],
            "uploads": [{key: upload[key] for key in ("name", "columns") if key in upload} for upload in uploads],
            "nodes": nodes,
        }
        messages = [{"role": "system", "content": BIND_SYSTEM_PROMPT}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)}]
        try:
            raw = parse_json_object(self._call(messages))
        except Exception as exc:
            return {}, f"parameter binding failed, routing proposals were used instead: {exc}"
        # Accept the documented {"params": {...}} and a bare node map alike.
        answer = raw.get("params") if isinstance(raw.get("params"), dict) else raw
        known = {record.id for record in routed}
        return {key: value for key, value in answer.items() if key in known and isinstance(value, dict)}, None

    @staticmethod
    def _stated(spec: ToolSpec, proposed: Any, provenance: Provenance) -> tuple[dict[str, Any], list[str]]:
        """Split proposed parameters into applicable ones and ignored ones with a reason."""
        kept: dict[str, Any] = {}
        ignored: list[str] = []
        for key, value in (proposed if isinstance(proposed, dict) else {}).items():
            if not spec.open_params and key not in spec.params:
                ignored.append(f"{key}: not a parameter of {spec.tool_id}")
            elif not provenance.stated(value):
                ignored.append(f"{key}: value is not stated in the request or the uploaded files")
            else:
                kept[key] = provenance.canonical(value)
        return kept, ignored

    def _params(self, spec: ToolSpec, proposed: dict[str, Any], action: ActionUnit, uploads: list[dict[str, Any]], *, sole_import: bool = True) -> tuple[dict[str, Any], list[str]]:
        issues: list[str] = []
        params = dict(spec.params)
        proposed = proposed if isinstance(proposed, dict) else {}
        if spec.open_params:
            mapping = {key: value for key, value in proposed.items() if isinstance(key, str) and isinstance(value, str) and value}
            if mapping:
                params = mapping
        else:
            params.update({key: value for key, value in proposed.items() if key in spec.params})
        if "upload_id" in spec.params:
            # Only an explicitly named file is bound, except in the unambiguous
            # case of one upload read by the plan's only import.
            names = action.input_files or ([uploads[0]["name"]] if len(uploads) == 1 and sole_import else [])
            upload = _match_upload(names[0], uploads) if names else None
            if upload is None:
                issues.append(f"no uploaded file is bound to this import (asked for: {', '.join(action.input_files) or 'nothing'})")
            else:
                params["upload_id"] = upload["upload_id"]
                if "file_name" in spec.params:
                    params["file_name"] = upload["name"]
        validator = Draft202012Validator(spec.parameter_schema)
        # A proposed value the schema rejects falls back to the tool default.
        for error in list(validator.iter_errors(params)):
            key = next(iter(error.absolute_path), None)
            if key in proposed and key in params and params[key] is not spec.params.get(key):
                issues.append(f"rejected proposed value for {key!r}: {error.message}")
                if key in spec.params:
                    params[key] = spec.params[key]
                else:
                    params.pop(key)
        # Whatever is still invalid has no usable default: a human must supply it.
        reported: set[str] = set()
        for error in validator.iter_errors(params):
            key = str(next(iter(error.absolute_path), "params"))
            if key not in reported:
                reported.add(key)
                issues.append(f"parameter {key!r} needs a value the request did not provide ({error.message})")
        ready = spec.parameter_schema.get(READY_SCHEMA_KEY)
        if isinstance(ready, dict) and not Draft202012Validator(ready).is_valid(params):
            issues.append(f"not ready to run: {ready.get('description', 'its readiness conditions are unmet')}")
        return params, issues

    def _patch(self, state: GraphState, actions: list[PlannedAction], edges: list[PlannedEdge], task_id: str) -> GraphPatch | None:
        depth: dict[str, int] = {}
        for action in actions:
            depth[action.id] = 1 + max((depth[parent] for parent in action.depends_on), default=-1)
        rows: dict[int, int] = {}
        operations: list[Operation] = []
        for action in actions:
            if action.status != "routed" or not action.node_id or not action.tool_id:
                continue
            level = depth[action.id]
            row = rows.get(level, 0)
            rows[level] = row + 1
            node = Node(
                id=action.node_id,
                type=action.tool_id,
                label=action.goal[:120],
                params=action.params,
                position={"x": 80.0 + 280.0 * level, "y": 80.0 + 150.0 * row},
            )
            operations.append(Operation(op="add_node", node=node))
        operations.extend(Operation(op="connect", edge=edge.edge) for edge in edges if edge.edge is not None)
        if not operations:
            return None
        return GraphPatch(base_version=state.version, operations=operations, rationale=f"Workflow planned from the request of task {task_id}.")

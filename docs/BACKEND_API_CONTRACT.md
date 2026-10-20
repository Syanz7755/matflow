# MatFlow HTTP API Contract v1

The backend is the only authority for workspace data and execution. Clients must use HTTP; no client may import Python runtime objects or write `data/` directly.

`GET /api/capabilities` declares `api_contract: {name: "matflow-http", version: "1.0"}`, the server version, registered tools, types, features, and the operation catalogue. Clients supporting v1 must reject another contract name or major version.

`GET /openapi.json` is the machine-readable schema for every route; `/docs` renders it. The operation catalogue and OpenAPI are generated from the same live route table, and a contract test fails if a route is unnamed or a name is stale.

## Error envelope

Every failure — raised by a route, by workspace validation, or by request-body parsing — uses one shape:

```json
{"detail": {"code": "not_found", "message": "Unknown node: qc-1", "node_id": "qc-1"}}
```

`code` is stable and is the only thing a client should branch on. Documented codes:

| Code | Status | Meaning |
| --- | --- | --- |
| `invalid_request` | 422 | malformed request or payload (adds `errors: [{location, message}]`) |
| `invalid_parameters` | 422 | node parameters are unsupported or fail the tool's parameter schema |
| `unknown_tool` | 422 | a graph references a tool the registry does not provide |
| `invalid_tool_schema` | 422 | a loaded tool declares an unusable parameter schema |
| `missing_dependency` | 422 | a required input port is not connected |
| `invalid_graph_patch` | 422 | the patch is well-formed but rejected by graph validation |
| `unreadable_dataset` | 422 | a stored dataset whose suffix promises readability cannot be read (adds `inspection`) |
| `not_found` | 404 | the identified resource does not exist |
| `graph_version_conflict` | 409 | the write was based on a stale graph version (adds `current_version`) |
| `conflict` | 409 | the write conflicts with current workspace state |
| `node_already_running` | 409 | the node is already executing (adds `node_id`) |
| `execution_failed` | 424 | a node failed while executing |
| `invalid_workflow` | 422 | the workflow cannot be scheduled |
| `full_reset_forbidden` | 403 | full reset is only available in an isolated test runtime |
| `agent_not_configured`, `unknown_model_provider`, `unknown_model` | 422/503 | model configuration problems |
| `model_provider_failed` | 502 | the upstream model provider failed |
| `unsupported_media_type`, `upload_too_large` | 415/413 | upload rejection |

A request that is well-formed but whose work fails is **not** HTTP 200:

- `POST /api/chat` returns 424 when the agent reports `status: "failed"` (the body still carries `state`, `trace`, `tool_proposals` and `error`);
- `POST /api/plan` returns 424 when the plan's `status` is `failed` (the LLM could not be used or never produced a valid decomposition), and 503 `planning_unavailable` when no LLM adapter is configured;
- `POST /api/workflow/execute` returns 424 when `ok` is false (the body still carries `results` and `errors`);
- `GET /api/uploads/{id}` returns 422 when the dataset is `unreadable`.

## Concurrency

`GraphState` carries two independent counters:

- `version` — the **structural** version. Advances only when a GraphPatch is applied. Clients send it back as `base_version`; a stale value returns 409 `graph_version_conflict` with `detail.current_version`.
- `revision` — a **monotonic** counter that advances on every persisted write, including node execution, review decisions and migrations, with `updated_at` (ISO-8601 UTC). Use it to detect that node outputs or review states changed while the graph structure did not.

Node review is a compare-and-set: continuing or stopping a node that is not `waiting` returns 409 `conflict`.

## Operations

`POST /api/chat` is a bounded AI-assistance interface, not an alternative source of workspace truth. It returns a stable task status (`completed`, `waiting_for_confirmation`, or `failed`), the current state, an auditable tool-call trace, any isolated Tool Recipe Proposals, and warnings or errors. Every graph change requested by the model still crosses the normal GraphPatch validation and version checks. There is no keyword pre-routing: the turn waits for confirmation when the agent calls its `ask_user` tool, proposes a draft, or leaves a node waiting.

`POST /api/plan` (`plan_workflow`) turns a request of up to 20 000 characters into a typed workflow. Body: `message`, optional `task_id`, `attachments` (`[{upload_id, name}]` of files already uploaded) and `apply` (default `false`). The LLM decomposes the request into action units with `depends_on` edges; each unit is routed among the type-compatible candidates by Jev, or by the LLM when Jev is unreachable — never by keywords; dependencies become typed edges; one LLM pass binds parameters, and only values that the request or the uploaded column names state are kept (`ignored_params` lists the rest). The response is a `WorkflowPlan`: `status` (`planned`, `needs_confirmation`, `clarify`, `refused`, `failed`), `actions` (per unit: `status` `routed`/`gap`/`unrouted`/`blocked`, `tool_id`, `node_id`, `router`, `confidence`, `candidates`, `model_decisions`, `params`), `edges`, `issues`, the validated `patch`, `patch_valid`, `applied`, `question`/`reason`, `llm_calls`. The patch is applied only when the status is `planned` and `apply` is true; otherwise it is returned for human review. `POST /api/route` uses the same selection (type filter, then Jev, then the LLM) for a single tool.

`POST /api/patch/validate` never writes state. `POST /api/patch` performs validation and the atomic write under the server lock.

`GET /api/uploads` lists datasets, `GET /api/uploads/{id}` inspects one (metadata, columns, a bounded preview) and `GET /api/uploads/{id}/content` serves the stored bytes with a `Content-Type` derived from the validated suffix, an `ETag`, and `304` support via `If-None-Match`. Uploads are multipart only and capped at 25 MB.

`POST /api/execute` and `POST /api/workflow/execute` are **synchronous**: there is no job id, progress stream or cancellation yet, so a client must expect the request to occupy its connection for the whole run. A node that is already `running` is rejected with 409 rather than executed twice.

Data-type, model-provider, node-library, node-revision, migration, settings and runtime-skill endpoints are all exposed in OpenAPI and named in `GET /api/capabilities`.

## Removed

The backend `/mcp` endpoint was removed in v1; a request to it returns 404. The MCP bridge in `matflow-frontend` maps its tools to these HTTP operations and preserves its `{ok,data,error}` tool envelope.

## Not yet in the contract

Authentication/authorization, multi-workspace isolation, asynchronous jobs with progress and cancellation, and `If-Match` preconditions on non-graph writes are **not** implemented. Treat the current service as loopback-only and single-user.

# MatFlow HTTP API Contract v1

The backend is the only authority for workspace data and execution. Clients must use HTTP; no client may import Python runtime objects or write `data/` directly.

`GET /api/capabilities` declares `api_contract: {name: "matflow-http", version: "1.0"}`, the server version, registered tools, types, features, and operation URLs. Clients supporting v1 must reject another contract name or major version.

Important operations include:

- `GET /api/state`, `/api/capabilities`, `/api/uploads`, `/api/uploads/{id}`, and `/api/task-summaries/{task_id}`;
- `POST /api/chat`, `/api/uploads`, `/api/route`, `/api/patch/validate`, `/api/patch`, `/api/execute`, and `/api/workflow/execute`;
- `POST /api/workflow/decision` for node review and `/api/workflow/human-decision` for the legacy decision adapter;
- data-type, model-provider, node-library, and node-revision endpoints exposed in OpenAPI.

Graph mutation requires `base_version`. A stale version returns HTTP 409 with `detail.code = "graph_version_conflict"` and `detail.current_version`; invalid patches return 422 with `invalid_graph_patch`.

The backend `/mcp` endpoint was removed in v1. The MCP bridge in `matflow-frontend` maps its tools to these HTTP operations and preserves its `{ok,data,error}` tool envelope.

`POST /api/chat` is a bounded AI-assistance interface, not an alternative source of workspace truth. It returns a stable task status (`completed`, `waiting_for_confirmation`, or `failed`), the current state, an auditable tool-call trace, any isolated Tool Recipe Proposals, and warnings or errors. Every graph change requested by the model still crosses the normal GraphPatch validation and version checks.

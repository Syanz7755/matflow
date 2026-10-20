# MatFlow user manual

**Applies to:** backend 1.x, HTTP contract `matflow-http 1.0`

The MatFlow backend is the only authority for workspace data, GraphPatch validation, execution, audit and version control. The WebUI and the MCP bridge are separate clients in `matflow-frontend`; they cannot read or write the backend `data/` directory directly.

## Common commands

```powershell
uv run matflow start
uv run matflow start --ui webui
uv run matflow start --ui none
```

`--host`, `--port`, `--ui-port` and `--ui-path` override the defaults. The default backend port is 8000 and the WebUI port is 5173.

Inspect the current flow read-only (works offline; no running server is required):

```powershell
.\.venv\Scripts\python.exe -m flowview run-flow            # runtime stage blueprint
.\.venv\Scripts\python.exe -m flowview graph --format mermaid   # current workflow DAG
```

See the [FlowView guide](../flowview/README.md).

When a client submits a GraphPatch it must carry the graph version it read. If another client has already updated the graph, the backend returns HTTP 409 with `graph_version_conflict`; the client should re-read the state, merge its changes and submit again.

The MCP bridge listens on `http://127.0.0.1:8001/mcp` by default. Start it in `matflow-frontend` with `npm run mcp`, and generate the DSH configuration with `npm run configure:dsh`.

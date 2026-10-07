"""The operation catalogue.

One place maps an HTTP route to the stable operation id that clients use, so the
discovery surface cannot drift from the implementation the way a hand-written
list did before.

The catalogue is read *against* the live FastAPI route table:

* ``operations``          live routes with a stable id
* ``operations_unmapped`` live routes that nobody named  -> a contract test fails
* ``operations_stale``    named routes that no longer exist -> a contract test fails

A new endpoint therefore shows up as unmapped instead of silently missing.
"""
from __future__ import annotations

from typing import Any

#: Only these methods belong to the client-facing contract.  Starlette adds
#: ``HEAD`` to every ``GET`` route automatically, which is not a client operation.
DOCUMENTED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}

#: (method, path) -> stable operation id.  The ids are the client-facing names;
#: they are part of the ``matflow-http`` contract and must not be renamed.
OPERATION_IDS: dict[tuple[str, str], str] = {
    ("GET", "/api/state"): "read_state",
    ("GET", "/api/capabilities"): "read_capabilities",
    ("GET", "/api/data-types"): "list_data_types",
    ("POST", "/api/data-types"): "create_data_type",
    ("PUT", "/api/data-types/{name}/parents"): "update_data_type_inheritance",
    ("GET", "/api/settings"): "read_settings",
    ("PUT", "/api/settings"): "update_settings",
    ("GET", "/api/runtime-skills"): "list_runtime_skills",
    ("GET", "/api/node-library"): "read_node_library",
    ("POST", "/api/node-library"): "create_node_library_entry",
    ("PUT", "/api/node-library/{key}"): "update_node_library_entry",
    ("DELETE", "/api/node-library/{key}"): "delete_node_library_entry",
    ("POST", "/api/node-library/prompt-build"): "prompt_build_node",
    ("GET", "/api/model-providers"): "list_model_providers",
    ("POST", "/api/model-providers"): "register_model_provider",
    ("POST", "/api/node-revisions/proposals"): "propose_node_revision",
    ("GET", "/api/node-revisions/proposals/{proposal_id}"): "read_node_revision_proposal",
    ("POST", "/api/node-revisions/proposals/{proposal_id}/review-code"): "review_node_revision_code",
    ("POST", "/api/node-revisions/proposals/{proposal_id}/apply"): "apply_node_revision",
    ("POST", "/api/migrations/human-decision"): "migrate_human_decisions",
    ("POST", "/api/uploads"): "import_dataset",
    ("GET", "/api/uploads"): "list_datasets",
    ("GET", "/api/uploads/{upload_id}"): "inspect_dataset",
    ("GET", "/api/uploads/{upload_id}/content"): "read_dataset_content",
    ("POST", "/api/patch"): "apply_graph_patch",
    ("POST", "/api/patch/validate"): "validate_graph_patch",
    ("POST", "/api/route"): "route",
    ("POST", "/api/plan"): "plan_workflow",
    ("GET", "/api/task-summaries/{task_id}"): "read_task_summary",
    ("POST", "/api/chat"): "chat",
    ("POST", "/api/reset"): "reset_workspace",
    ("POST", "/api/execute"): "execute_node",
    ("POST", "/api/workflow/execute"): "execute_workflow",
    ("POST", "/api/qe/demo"): "qe_replay_demo",
    ("POST", "/api/workflow/decision"): "submit_node_review",
    ("POST", "/api/workflow/human-decision"): "submit_human_decision",
}


def live_api_routes(app: Any) -> set[tuple[str, str]]:
    """Every documented-method route the app actually serves under ``/api``."""
    routes: set[tuple[str, str]] = set()
    for route in getattr(app, "routes", ()):
        path = str(getattr(route, "path", ""))
        if not path.startswith("/api/"):
            continue
        for method in getattr(route, "methods", None) or set():
            if method in DOCUMENTED_METHODS:
                routes.add((method, path))
    return routes


def operation_catalogue(app: Any) -> dict[str, Any]:
    """The three-way view of the catalogue against the live route table."""
    live = live_api_routes(app)
    named = {route: name for route, name in OPERATION_IDS.items() if route in live}
    return {
        "operations": {name: f"{method} {path}" for (method, path), name in sorted(named.items(), key=lambda item: item[1])},
        "operations_unmapped": sorted(f"{method} {path}" for method, path in live if (method, path) not in OPERATION_IDS),
        "operations_stale": sorted(f"{method} {path}" for method, path in OPERATION_IDS if (method, path) not in live),
    }

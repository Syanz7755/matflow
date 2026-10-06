"""Shared implementation helpers for method-owned signal analysis Tools."""
from __future__ import annotations

from typing import Any

from ..analysis_recipes import AnalysisRecipe, RecipeEngine
from ..executors import NodeExecution, ToolExecutionError


def extract_peaks(
    ctx: NodeExecution,
    *,
    domain: str,
    recipe_id: str,
) -> dict[str, Any]:
    """Use the generic recipe interpreter with method-owned axis and thresholds."""
    upstream = ctx.runtime.node_input(ctx.state, ctx.node.id, "data")
    if not upstream.output:
        raise ToolExecutionError("missing_dependency", f"Input table from node {upstream.id} has not run")
    upload_id = str(upstream.output.get("upload_id") or "")
    if not upload_id:
        raise ToolExecutionError("invalid_input", "TypedTable input does not contain an upload reference")
    frame = ctx.runtime.dataset_frame(upload_id)
    params = ctx.node.params
    x_column, y_column = str(params["x_column"]), str(params["y_column"])
    missing = [column for column in (x_column, y_column) if column not in frame.columns]
    if missing:
        raise ToolExecutionError("invalid_parameters", f"Signal column(s) not found: {', '.join(missing)}")
    recipe = AnalysisRecipe.model_validate({
        "recipe_id": recipe_id,
        "domain": domain,
        "status": "reviewed",
        "inputs": {"x": [x_column], "y": [y_column]},
        "steps": [
            {"operation": "select_columns"},
            {"operation": "finite_filter"},
            {"operation": "sort", "parameters": {"ascending": True}},
            {"operation": "baseline_subtract", "parameters": {"quantile": params["baseline_quantile"]}},
            {"operation": "smooth", "parameters": {"window_points": params["smooth_window"]}},
            {"operation": "find_peaks", "parameters": {
                "min_height": params["min_height"],
                "min_distance_x": params["min_distance_x"],
                "max_peaks": params["max_peaks"],
            }},
        ],
    })
    result = RecipeEngine().execute(recipe, frame)
    result["kind"] = f"{domain.upper()}Peaks"
    result["upload_id"] = upload_id
    return result

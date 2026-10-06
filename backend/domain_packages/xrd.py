"""X-ray diffraction recipes and capability ownership."""
from __future__ import annotations

from typing import Any

from ..analysis_recipes import AnalysisRecipe
from ..contracts import DataTypeDefinition, ToolSpec
from ..executors import ExecutorRegistry, NodeExecution
from . import DomainPackage, DomainPackageManifest
from .signal_tools import extract_peaks


MANIFEST = DomainPackageManifest(
    package_id="xrd",
    version="1.0.0",
    label="X-ray Diffraction",
    description="XRD-specific recipe vocabulary and reviewed reference recipes.",
    acceptance_tests=("tests/test_analysis_recipes.py",),
)

X_ALIASES = ["x"]
Y_ALIASES = ["y"]


def reference_recipe() -> AnalysisRecipe:
    """Hidden reference recipe used only by evaluation fixtures."""
    return AnalysisRecipe.model_validate({
        "recipe_id": "reference_xrd_phase_identification",
        "domain": "xrd",
        "status": "reviewed",
        "inputs": {
            "x": ["two_theta_deg", "2theta", "two theta", *X_ALIASES],
            "y": ["intensity_counts", "intensity", *Y_ALIASES],
        },
        "steps": [
            {"operation": "select_columns"},
            {"operation": "finite_filter"},
            {"operation": "sort", "parameters": {"ascending": True}},
            {"operation": "baseline_subtract", "parameters": {"quantile": 0.08}},
            {"operation": "smooth", "parameters": {"window_points": 7}},
            {"operation": "find_peaks", "parameters": {"min_height": 35, "min_distance_x": 1.0, "max_peaks": 10}},
            {"operation": "match_reference_values", "parameters": {
                "tolerance": 0.28,
                "references": {"anatase_tio2": [25.3, 37.8, 48.0, 53.9, 55.1, 62.7]},
            }},
        ],
    })


def peak_extraction_recipe() -> AnalysisRecipe:
    return AnalysisRecipe.model_validate({
        "recipe_id": "reference_xrd_peak_extraction",
        "domain": "xrd",
        "status": "reviewed",
        "inputs": {
            "x": ["two_theta_deg", "2theta", "two theta", *X_ALIASES],
            "y": ["intensity_counts", "intensity", *Y_ALIASES],
        },
        "steps": [
            {"operation": "select_columns"},
            {"operation": "finite_filter"},
            {"operation": "sort", "parameters": {"ascending": True}},
            {"operation": "baseline_subtract", "parameters": {"quantile": 0.08}},
            {"operation": "smooth", "parameters": {"window_points": 9}},
            {"operation": "find_peaks", "parameters": {"min_height": 25, "min_distance_x": 0.35, "max_peaks": 20}},
        ],
    })


def xrd_peak_extraction(ctx: NodeExecution) -> dict[str, Any]:
    return extract_peaks(ctx, domain="xrd", recipe_id="xrd_peak_extraction")


def xrd_reference_match(ctx: NodeExecution) -> dict[str, Any]:
    node = ctx.runtime.node_input(ctx.state, ctx.node.id, "peaks")
    peaks = (node.output or {}).get("peaks", [])
    tolerance = float(ctx.node.params["tolerance"])
    references = ctx.node.params["references"]
    scores = {
        label: sum(any(abs(float(peak["x"]) - float(reference)) <= tolerance for peak in peaks) for reference in positions)
        for label, positions in references.items()
    }
    best_match = max(scores, key=scores.get) if scores else None
    return {"kind": "Artifact", "analysis": "xrd_reference_match", "best_match": best_match, "matched_count": scores.get(best_match, 0) if best_match else 0, "match_scores": scores, "tolerance": tolerance}


def _register(registry: ExecutorRegistry) -> None:
    registry.register("builtin:xrd_peak_extraction", xrd_peak_extraction)
    registry.register("builtin:xrd_reference_match", xrd_reference_match)


XRD_TOOLS = {
    "xrd_peak_extraction": ToolSpec(
        tool_id="xrd_peak_extraction", label="XRD Peak Extraction", category="XRD Analysis",
        description="Extract diffraction peaks from a two-theta and intensity table.",
        inputs={"data": "TypedTable"}, outputs={"peaks": "XRDPeaks"},
        params={"x_column": "two_theta_deg", "y_column": "intensity_counts", "baseline_quantile": 0.08, "smooth_window": 9, "min_height": 25, "min_distance_x": 0.35, "max_peaks": 20},
        parameter_schema={"type": "object", "properties": {"x_column": {"type": "string", "minLength": 1}, "y_column": {"type": "string", "minLength": 1}, "baseline_quantile": {"type": "number", "minimum": 0, "maximum": 0.5}, "smooth_window": {"type": "integer", "minimum": 1, "maximum": 101, "not": {"multipleOf": 2}}, "min_height": {"type": "number"}, "min_distance_x": {"type": "number", "minimum": 0}, "max_peaks": {"type": "integer", "minimum": 1, "maximum": 100}}, "required": ["x_column", "y_column", "baseline_quantile", "smooth_window", "min_height", "min_distance_x", "max_peaks"], "additionalProperties": False},
        executor_ref="builtin:xrd_peak_extraction", required_inputs=["data"],
    ),
    "xrd_reference_match": ToolSpec(
        tool_id="xrd_reference_match", label="XRD Reference Match", category="XRD Analysis",
        description="Match extracted diffraction peak positions against user-supplied reference peak lists.",
        inputs={"peaks": "XRDPeaks"}, outputs={"result": "Artifact"},
        params={"tolerance": 0.28, "references": {}},
        parameter_schema={"type": "object", "properties": {"tolerance": {"type": "number", "exclusiveMinimum": 0}, "references": {"type": "object", "minProperties": 1, "additionalProperties": {"type": "array", "minItems": 1, "items": {"type": "number"}}}}, "required": ["tolerance", "references"], "additionalProperties": False},
        executor_ref="builtin:xrd_reference_match", required_inputs=["peaks"],
    ),
}


def build_package() -> DomainPackage:
    recipes = {recipe.recipe_id: recipe for recipe in (reference_recipe(), peak_extraction_recipe())}
    return DomainPackage(
        manifest=MANIFEST,
        data_types={"XRDPeaks": DataTypeDefinition(name="XRDPeaks", parents=["Artifact"], description="Peak positions and heights extracted from a diffraction signal.")},
        tool_specs=XRD_TOOLS,
        recipes=recipes,
        recipe_domains=("xrd",),
        register_executors=_register,
    )

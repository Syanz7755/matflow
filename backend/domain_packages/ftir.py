"""Fourier-transform infrared spectroscopy recipes and capability ownership."""
from __future__ import annotations

from typing import Any

from ..analysis_recipes import AnalysisRecipe
from ..contracts import DataTypeDefinition, ToolSpec
from ..executors import ExecutorRegistry, NodeExecution
from . import DomainPackage, DomainPackageManifest
from .signal_tools import extract_peaks


MANIFEST = DomainPackageManifest(
    package_id="ftir",
    version="1.0.0",
    label="Fourier-Transform Infrared Spectroscopy",
    description="FTIR-specific recipe vocabulary and reviewed reference assignments.",
    acceptance_tests=("tests/test_analysis_recipes.py",),
)


def reference_recipe() -> AnalysisRecipe:
    """Hidden reference recipe used only by evaluation fixtures."""
    return AnalysisRecipe.model_validate({
        "recipe_id": "reference_ftir_functional_group_assignment",
        "domain": "ftir",
        "status": "reviewed",
        "inputs": {
            "x": ["wavenumber_cm-1", "wavenumber", "cm-1", "x"],
            "y": ["absorbance_au", "absorbance", "y"],
        },
        "steps": [
            {"operation": "select_columns"},
            {"operation": "finite_filter"},
            {"operation": "sort", "parameters": {"ascending": True}},
            {"operation": "baseline_subtract", "parameters": {"quantile": 0.08}},
            {"operation": "smooth", "parameters": {"window_points": 9}},
            {"operation": "find_peaks", "parameters": {"min_height": 0.08, "min_distance_x": 80, "max_peaks": 8}},
            {"operation": "assign_peak_ranges", "parameters": {"ranges": [
                {"min": 1680, "max": 1740, "label": "carbonyl_candidate"},
                {"min": 2850, "max": 3000, "label": "aliphatic_ch_candidate"},
                {"min": 1400, "max": 1500, "label": "bending_mode_candidate"},
            ]}},
        ],
    })


def ftir_peak_extraction(ctx: NodeExecution) -> dict[str, Any]:
    return extract_peaks(ctx, domain="ftir", recipe_id="ftir_peak_extraction")


def ftir_band_assignment(ctx: NodeExecution) -> dict[str, Any]:
    node = ctx.runtime.node_input(ctx.state, ctx.node.id, "peaks")
    peaks = (node.output or {}).get("peaks", [])
    assignments = []
    for rule in ctx.node.params["ranges"]:
        low, high = sorted((float(rule["min"]), float(rule["max"])))
        candidate = next((peak for peak in peaks if low <= float(peak["x"]) <= high), None)
        if candidate is not None:
            assignments.append({"label": str(rule["label"]), "peak": float(candidate["x"])})
    return {"kind": "Artifact", "analysis": "ftir_band_assignment", "assignments": assignments}


def _register(registry: ExecutorRegistry) -> None:
    registry.register("builtin:ftir_peak_extraction", ftir_peak_extraction)
    registry.register("builtin:ftir_band_assignment", ftir_band_assignment)


FTIR_TOOLS = {
    "ftir_peak_extraction": ToolSpec(
        tool_id="ftir_peak_extraction", label="FTIR Peak Extraction", category="FTIR Analysis",
        description="Extract absorption peaks from a wavenumber and absorbance table.",
        inputs={"data": "TypedTable"}, outputs={"peaks": "FTIRPeaks"},
        params={"x_column": "wavenumber_cm-1", "y_column": "absorbance_au", "baseline_quantile": 0.08, "smooth_window": 9, "min_height": 0.08, "min_distance_x": 80, "max_peaks": 8},
        parameter_schema={"type": "object", "properties": {"x_column": {"type": "string", "minLength": 1}, "y_column": {"type": "string", "minLength": 1}, "baseline_quantile": {"type": "number", "minimum": 0, "maximum": 0.5}, "smooth_window": {"type": "integer", "minimum": 1, "maximum": 101, "not": {"multipleOf": 2}}, "min_height": {"type": "number"}, "min_distance_x": {"type": "number", "minimum": 0}, "max_peaks": {"type": "integer", "minimum": 1, "maximum": 100}}, "required": ["x_column", "y_column", "baseline_quantile", "smooth_window", "min_height", "min_distance_x", "max_peaks"], "additionalProperties": False},
        executor_ref="builtin:ftir_peak_extraction", required_inputs=["data"],
    ),
    "ftir_band_assignment": ToolSpec(
        tool_id="ftir_band_assignment", label="FTIR Band Assignment", category="FTIR Analysis",
        description="Assign extracted infrared peak positions to user-supplied wavenumber ranges.",
        inputs={"peaks": "FTIRPeaks"}, outputs={"result": "Artifact"},
        params={"ranges": []},
        parameter_schema={"type": "object", "properties": {"ranges": {"type": "array", "minItems": 1, "items": {"type": "object", "properties": {"min": {"type": "number"}, "max": {"type": "number"}, "label": {"type": "string", "minLength": 1}}, "required": ["min", "max", "label"], "additionalProperties": False}}}, "required": ["ranges"], "additionalProperties": False},
        executor_ref="builtin:ftir_band_assignment", required_inputs=["peaks"],
    ),
}


def build_package() -> DomainPackage:
    recipe = reference_recipe()
    return DomainPackage(
        manifest=MANIFEST,
        data_types={"FTIRPeaks": DataTypeDefinition(name="FTIRPeaks", parents=["Artifact"], description="Peak positions and heights extracted from an infrared signal.")},
        tool_specs=FTIR_TOOLS,
        recipe_domains=("ftir",),
        recipes={recipe.recipe_id: recipe},
        register_executors=_register,
    )

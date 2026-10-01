"""Validated, declarative analysis recipes for tabular signal data.

The interpreter deliberately supports a small allow-list.  It never evaluates
model-produced Python and returns structured data suitable for hidden-fixture
evaluation before a generated tool is reviewed or activated.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator


class RecipeStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal[
        "select_columns", "finite_filter", "sort", "baseline_subtract",
        "smooth", "find_peaks", "match_reference_peaks", "assign_peak_ranges",
    ]
    parameters: dict[str, Any] = Field(default_factory=dict)


class AnalysisRecipe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipe_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    version: Literal["1.0"] = "1.0"
    domain: Literal["xrd", "ftir"]
    inputs: dict[str, list[str]]
    steps: list[RecipeStep] = Field(min_length=1)
    status: Literal["draft", "reviewed"] = "draft"

    @model_validator(mode="after")
    def require_axes(self):
        if set(self.inputs) != {"x", "y"}:
            raise ValueError("A signal recipe must declare x and y column aliases")
        return self


class RecipeEngine:
    """Execute an allow-listed recipe against an in-memory table."""

    def execute(self, recipe: AnalysisRecipe | dict[str, Any], frame: pd.DataFrame) -> dict[str, Any]:
        spec = recipe if isinstance(recipe, AnalysisRecipe) else AnalysisRecipe.model_validate(recipe)
        selected: dict[str, str] = {}
        work = pd.DataFrame()
        peaks: list[dict[str, float]] = []
        result: dict[str, Any] = {"domain": spec.domain, "recipe_id": spec.recipe_id}

        for step in spec.steps:
            params = step.parameters
            if step.operation == "select_columns":
                selected = {
                    axis: self._resolve_column(frame, aliases)
                    for axis, aliases in spec.inputs.items()
                }
                work = pd.DataFrame({
                    "x": pd.to_numeric(frame[selected["x"]], errors="coerce"),
                    "y": pd.to_numeric(frame[selected["y"]], errors="coerce"),
                })
            elif step.operation == "finite_filter":
                self._require_signal(work)
                mask = np.isfinite(work["x"].to_numpy()) & np.isfinite(work["y"].to_numpy())
                work = work.loc[mask].reset_index(drop=True)
            elif step.operation == "sort":
                self._require_signal(work)
                work = work.sort_values("x", ascending=bool(params.get("ascending", True))).reset_index(drop=True)
            elif step.operation == "baseline_subtract":
                self._require_signal(work)
                quantile = float(params.get("quantile", 0.08))
                if not 0 <= quantile <= 0.5:
                    raise ValueError("baseline quantile must be between 0 and 0.5")
                work["y"] = work["y"] - float(work["y"].quantile(quantile))
            elif step.operation == "smooth":
                self._require_signal(work)
                window = int(params.get("window_points", 7))
                if window < 1 or window > 101 or window % 2 == 0:
                    raise ValueError("smooth window_points must be an odd integer from 1 to 101")
                work["y"] = work["y"].rolling(window, center=True, min_periods=1).mean()
            elif step.operation == "find_peaks":
                self._require_signal(work)
                peaks = self._find_peaks(
                    work,
                    min_height=float(params.get("min_height", 0)),
                    min_distance_x=float(params.get("min_distance_x", 1)),
                    max_peaks=int(params.get("max_peaks", 12)),
                )
                if not peaks:
                    raise ValueError("No peaks satisfy the configured constraints")
                result["peaks"] = peaks
                result["main_peak"] = peaks[0]["x"]
            elif step.operation == "match_reference_peaks":
                if not peaks:
                    raise ValueError("match_reference_peaks requires find_peaks first")
                tolerance = float(params.get("tolerance", 0.25))
                references = params.get("references") or {}
                scores = {
                    label: sum(any(abs(item["x"] - float(target)) <= tolerance for item in peaks) for target in targets)
                    for label, targets in references.items()
                }
                if not scores:
                    raise ValueError("match_reference_peaks requires references")
                winner = max(scores, key=scores.get)
                result.update({"dominant_phase": winner, "matched_peak_count": scores[winner], "phase_scores": scores})
            elif step.operation == "assign_peak_ranges":
                if not peaks:
                    raise ValueError("assign_peak_ranges requires find_peaks first")
                assignments = []
                for rule in params.get("ranges", []):
                    low, high = sorted((float(rule["min"]), float(rule["max"])))
                    candidate = next((item for item in peaks if low <= item["x"] <= high), None)
                    if candidate:
                        assignments.append({"label": str(rule["label"]), "peak": candidate["x"]})
                result["assignments"] = assignments
            else:  # pragma: no cover - Pydantic rejects unknown operations first.
                raise ValueError(f"Unsupported recipe operation: {step.operation}")

        result["rows_used"] = len(work)
        result["column_mapping"] = selected
        return result

    @staticmethod
    def _resolve_column(frame: pd.DataFrame, aliases: list[str]) -> str:
        normalized = {str(column).strip().lower(): str(column) for column in frame.columns}
        for alias in aliases:
            if alias.strip().lower() in normalized:
                return normalized[alias.strip().lower()]
        raise ValueError(f"No input column matches aliases: {aliases}")

    @staticmethod
    def _require_signal(frame: pd.DataFrame) -> None:
        if set(frame.columns) != {"x", "y"}:
            raise ValueError("select_columns must be the first recipe operation")

    @staticmethod
    def _find_peaks(frame: pd.DataFrame, *, min_height: float, min_distance_x: float, max_peaks: int) -> list[dict[str, float]]:
        if max_peaks < 1 or max_peaks > 100:
            raise ValueError("max_peaks must be between 1 and 100")
        x = frame["x"].to_numpy(dtype=float)
        y = frame["y"].to_numpy(dtype=float)
        candidates = [
            {"x": float(x[index]), "height": float(y[index])}
            for index in range(1, len(y) - 1)
            if y[index] >= min_height and y[index] > y[index - 1] and y[index] >= y[index + 1]
        ]
        chosen: list[dict[str, float]] = []
        for candidate in sorted(candidates, key=lambda item: item["height"], reverse=True):
            if all(abs(candidate["x"] - item["x"]) >= min_distance_x for item in chosen):
                chosen.append(candidate)
            if len(chosen) == max_peaks:
                break
        return chosen


def recipe_operation_contracts() -> dict[str, Any]:
    """Model-facing description of the interpreter; contains no oracle values."""
    return {
        "select_columns": "No parameters. Resolves x/y using recipe.inputs aliases.",
        "finite_filter": "No parameters. Removes non-finite x/y rows.",
        "sort": {"ascending": "boolean"},
        "baseline_subtract": {"quantile": "number from 0 to 0.5"},
        "smooth": {"window_points": "odd integer from 1 to 101"},
        "find_peaks": {"min_height": "number", "min_distance_x": "number in x-axis units", "max_peaks": "integer 1..100"},
        "match_reference_peaks": {
            "tolerance": "number in x-axis units",
            "references": "non-empty object mapping result label to an embedded numeric peak list; external database names are not executable",
        },
        "assign_peak_ranges": {
            "ranges": "array of {min:number,max:number,label:string}; each range is matched against detected peaks",
        },
    }


def reference_recipe(domain: str) -> AnalysisRecipe:
    """Return the hidden oracle recipe.  Callers decide whether its ToolSpec is published."""
    common = [
        {"operation": "select_columns"},
        {"operation": "finite_filter"},
        {"operation": "sort", "parameters": {"ascending": True}},
        {"operation": "baseline_subtract", "parameters": {"quantile": 0.08}},
    ]
    if domain == "xrd":
        return AnalysisRecipe.model_validate({
            "recipe_id": "reference_xrd_phase_identification",
            "domain": "xrd",
            "status": "reviewed",
            "inputs": {"x": ["two_theta_deg", "2theta", "two theta"], "y": ["intensity_counts", "intensity"]},
            "steps": [
                *common,
                {"operation": "smooth", "parameters": {"window_points": 7}},
                {"operation": "find_peaks", "parameters": {"min_height": 35, "min_distance_x": 1.0, "max_peaks": 10}},
                {"operation": "match_reference_peaks", "parameters": {
                    "tolerance": 0.28,
                    "references": {"anatase_tio2": [25.3, 37.8, 48.0, 53.9, 55.1, 62.7]},
                }},
            ],
        })
    if domain == "ftir":
        return AnalysisRecipe.model_validate({
            "recipe_id": "reference_ftir_functional_group_assignment",
            "domain": "ftir",
            "status": "reviewed",
            "inputs": {"x": ["wavenumber_cm-1", "wavenumber", "cm-1"], "y": ["absorbance_au", "absorbance"]},
            "steps": [
                *common,
                {"operation": "smooth", "parameters": {"window_points": 9}},
                {"operation": "find_peaks", "parameters": {"min_height": 0.08, "min_distance_x": 80, "max_peaks": 8}},
                {"operation": "assign_peak_ranges", "parameters": {"ranges": [
                    {"min": 1680, "max": 1740, "label": "carbonyl_candidate"},
                    {"min": 2850, "max": 3000, "label": "aliphatic_ch_candidate"},
                    {"min": 1400, "max": 1500, "label": "bending_mode_candidate"},
                ]}},
            ],
        })
    raise ValueError(f"No reference recipe for domain: {domain}")


def peak_extraction_recipe(domain: str) -> AnalysisRecipe:
    """Return a conservative peak-only recipe when no reviewed reference library exists."""
    if domain != "xrd":
        raise ValueError(f"No peak-only recipe for domain: {domain}")
    return AnalysisRecipe.model_validate({
        "recipe_id": "reference_xrd_peak_extraction",
        "domain": "xrd",
        "status": "reviewed",
        "inputs": {"x": ["two_theta_deg", "2theta", "two theta"], "y": ["intensity_counts", "intensity"]},
        "steps": [
            {"operation": "select_columns"},
            {"operation": "finite_filter"},
            {"operation": "sort", "parameters": {"ascending": True}},
            {"operation": "baseline_subtract", "parameters": {"quantile": 0.08}},
            {"operation": "smooth", "parameters": {"window_points": 9}},
            {"operation": "find_peaks", "parameters": {"min_height": 25, "min_distance_x": 0.35, "max_peaks": 20}},
        ],
    })


def reference_tool_definition(domain: str) -> dict[str, Any]:
    """Build a registry definition for tests that explicitly publish an oracle."""
    recipe = reference_recipe(domain)
    labels = {
        "xrd": ("Reference XRD phase identification", "Find diffraction peaks and match a declared reference peak set."),
        "ftir": ("Reference FTIR assignment", "Find infrared absorption peaks and assign conservative range-based candidates."),
    }
    label, description = labels[domain]
    return {
        "tool_id": recipe.recipe_id,
        "version": "1.0.0",
        "label": label,
        "category": "Analysis",
        "description": description,
        "inputs": {"data": "RawData"},
        "outputs": {"artifact": "Artifact"},
        "params": {"recipe": recipe.model_dump()},
        "executor_ref": f"recipe:{recipe.recipe_id}",
        "status": "active",
        "provenance": {"kind": "custom", "reviewed_by": "test-oracle"},
        "generated_code_status": "none",
    }


class RecipeEvaluator:
    """Evaluate and repair draft recipes without exposing the hidden oracle."""

    def __init__(self, engine: RecipeEngine | None = None):
        self.engine = engine or RecipeEngine()

    @staticmethod
    def recipe_hash(recipe: AnalysisRecipe | dict[str, Any]) -> str:
        payload = recipe.model_dump() if isinstance(recipe, AnalysisRecipe) else recipe
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def evaluate(self, recipe: AnalysisRecipe | dict[str, Any], fixtures: list[Path], criteria: dict[str, Any]) -> dict[str, Any]:
        parsed = recipe if isinstance(recipe, AnalysisRecipe) else AnalysisRecipe.model_validate(recipe)
        cases = []
        failures: list[str] = []
        for path in fixtures:
            try:
                if path.suffix.lower() == ".xy":
                    frame = pd.read_csv(path, sep=r"\s+", header=None, names=["two_theta_deg", "intensity_counts"])
                else:
                    frame = pd.read_csv(path)
                result = self.engine.execute(parsed, frame)
                case_failures = self._match(result, criteria)
            except Exception as exc:
                result = None
                case_failures = [f"{path.name}: {exc}"]
            failures.extend(case_failures)
            cases.append({"fixture": str(path), "passed": not case_failures, "result": result, "failures": case_failures})
        return {"passed": not failures, "cases": cases, "failures": failures}

    def construct_with_model(self, contract: dict[str, Any], *, model_complete, max_repairs: int = 2) -> dict[str, Any]:
        contract = {**contract, "operation_contracts": recipe_operation_contracts()}
        messages = [
            {"role": "system", "content": "Return JSON only: a draft declarative MatFlow analysis recipe that conforms exactly to recipe_schema."},
            {"role": "user", "content": json.dumps(contract, ensure_ascii=False)},
        ]
        failures = []
        for attempt in range(max_repairs + 1):
            answer = model_complete(messages, [])
            content = (answer.get("content") or answer.get("reasoning_content") or "").strip()
            if content.startswith("```"):
                lines = content.splitlines()
                content = "\n".join(lines[1:-1])
            try:
                payload = json.loads(content or "{}")
                recipe = AnalysisRecipe.model_validate(payload.get("recipe", payload))
                if recipe.status != "draft":
                    raise ValueError("constructed recipe must have draft status")
                return {"recipe": recipe, "repair_attempts": attempt, "failures": failures}
            except Exception as exc:
                failures.append(str(exc))
                if attempt == max_repairs:
                    break
                messages.extend([
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": json.dumps({
                        "validation_failed": str(exc),
                        "instruction": "Return a corrected full recipe object. Keep status draft and use inputs with exactly x and y arrays.",
                    }, ensure_ascii=False)},
                ])
        raise ValueError(f"Model did not produce a valid recipe within the repair budget: {failures}")

    @staticmethod
    def _match(result: dict[str, Any], criteria: dict[str, Any]) -> list[str]:
        failures = []
        if "main_peak" in criteria:
            actual = result.get("main_peak")
            tolerance = float(criteria.get("main_peak_tolerance", 0))
            if actual is None or abs(float(actual) - float(criteria["main_peak"])) > tolerance:
                failures.append(f"main_peak {actual!r} is outside {criteria['main_peak']} ± {tolerance}")
        if "dominant_phase" in criteria and result.get("dominant_phase") != criteria["dominant_phase"]:
            failures.append(f"dominant_phase {result.get('dominant_phase')!r} != {criteria['dominant_phase']!r}")
        if "minimum_matched_peaks" in criteria and int(result.get("matched_peak_count", 0)) < int(criteria["minimum_matched_peaks"]):
            failures.append(f"matched_peak_count {result.get('matched_peak_count', 0)} is below {criteria['minimum_matched_peaks']}")
        if "required_assignment" in criteria:
            labels = {item.get("label") for item in result.get("assignments", [])}
            if criteria["required_assignment"] not in labels:
                failures.append(f"required assignment {criteria['required_assignment']!r} is missing")
        return failures

    def repair_until_passes(
        self,
        recipe: AnalysisRecipe | dict[str, Any],
        fixtures: list[Path],
        *,
        criteria: dict[str, Any],
        model_complete,
        max_repairs: int = 2,
    ) -> dict[str, Any]:
        current = recipe if isinstance(recipe, AnalysisRecipe) else AnalysisRecipe.model_validate(recipe)
        initial_hash = self.recipe_hash(current)
        evaluation = self.evaluate(current, fixtures, criteria)
        repair_failures: list[str] = []
        attempts = 0
        seen = {initial_hash}
        while not evaluation["passed"] and attempts < max_repairs:
            attempts += 1
            contract = {
                "request": "Repair or reconstruct this draft declarative recipe. Return JSON with a recipe field.",
                "recipe": current.model_dump(),
                "evaluation_failures": evaluation["failures"],
                "recipe_schema": AnalysisRecipe.model_json_schema(),
                "operation_contracts": recipe_operation_contracts(),
                "constraints": {"status": "draft", "arbitrary_code": False},
            }
            answer = model_complete(
                [{"role": "system", "content": "Repair the recipe from observed failures only; do not invent successful results."},
                 {"role": "user", "content": json.dumps(contract, ensure_ascii=False)}],
                [],
            )
            try:
                raw = (answer.get("content") or answer.get("reasoning_content") or "{}").strip()
                if raw.startswith("```"):
                    lines = raw.splitlines()
                    raw = "\n".join(lines[1:-1])
                payload = json.loads(raw)
                candidate_payload = payload.get("recipe", payload)
                candidate = AnalysisRecipe.model_validate(candidate_payload)
            except Exception as exc:
                repair_failures.append(f"Repair attempt {attempts} returned an invalid recipe: {exc}")
                continue
            candidate_hash = self.recipe_hash(candidate)
            if candidate_hash in seen:
                repair_failures.append(f"Repair attempt {attempts} was unchanged")
                continue
            seen.add(candidate_hash)
            current = candidate
            evaluation = self.evaluate(current, fixtures, criteria)

        failures = [*evaluation["failures"], *repair_failures]
        return {
            "status": "passed" if evaluation["passed"] else "failed",
            "repair_attempts": attempts,
            "initial_recipe_hash": initial_hash,
            "final_recipe_hash": self.recipe_hash(current),
            "recipe": current.model_dump(),
            "evaluation": evaluation,
            "failures": failures,
            "requires_human_review": True,
        }

"""The EIS Domain Package.

Electrochemical impedance spectroscopy is a measurement method, so its data
types, Tools and executors live here and never in Platform Core. A workspace
that composes no package therefore exposes no EIS capability, and one that
composes this package gets exactly the semantics Core used to hardcode.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from ..contracts import DataTypeDefinition, ToolSpec
from ..executors import ExecutorRegistry, NodeExecution
from . import DomainPackage, DomainPackageManifest

MANIFEST = DomainPackageManifest(
    package_id="eis",
    version="1.0.0",
    label="Electrochemical Impedance Spectroscopy",
    description=(
        "EIS measurement types, a basic quality-control analysis, a Nyquist plot "
        "Tool and the legacy human-decision gate migration."
    ),
    core_contract="1.0",
    acceptance_tests=("tests/test_domain_packages.py",),
)

EIS_DATA_TYPES: dict[str, DataTypeDefinition] = {
    "EISData": DataTypeDefinition(
        name="EISData",
        parents=[],
        description="Impedance spectra with a retained frequency axis.",
        builtin=False,
    ),
    "EISQCReport": DataTypeDefinition(
        name="EISQCReport",
        parents=["Artifact"],
        description="Quality-control findings for one impedance measurement.",
        builtin=False,
    ),
}

EIS_TOOL_SPECS: dict[str, ToolSpec] = {
    "eis_basic_qc": ToolSpec(
        tool_id="eis_basic_qc",
        label="EIS Basic Analysis",
        category="Analysis",
        inputs={"data": "TypedTable"},
        outputs={"report": "EISQCReport", "data": "EISData"},
        params={"min_frequency_hz": 10, "fit_model": "None"},
        description="Nyquist/Bode quality checks and a typed EIS output.",
        executor_ref="builtin:eis_basic_qc",
        preview_spec={"outputs": {"report": {"renderer": "json_tree"}, "data": {"renderer": "json_tree"}}},
    ),
    "plot_nyquist": ToolSpec(
        tool_id="plot_nyquist",
        label="Plot Nyquist",
        category="Output",
        inputs={"data": "EISData"},
        outputs={"plot": "Plot"},
        params={"title": "Nyquist plot"},
        description="Create a standard Nyquist plot.",
        executor_ref="builtin:plot_nyquist",
        preview_spec={"outputs": {"plot": {"renderer": "json_tree"}}},
    ),
    "human_decision": ToolSpec(
        tool_id="human_decision",
        label="Human Decision (legacy)",
        category="Control",
        inputs={"context": "EISQCReport"},
        outputs={"decision": "Decision"},
        params={"prompt": "Approve this result?", "options": ["approve", "stop"]},
        description="Deprecated legacy gate. Use review_policy.after_run on any node.",
        status="deprecated",
    ),
}


def eis_basic_qc(ctx: NodeExecution) -> dict[str, Any]:
    table = ctx.runtime.node_input(ctx.state, ctx.node.id, "data")
    if not table.output:
        raise ValueError(f"Upstream node {table.id} has not run")
    frame = ctx.runtime.dataset_frame(table.output["upload_id"])
    mapping = table.output["mapping"]
    frequency = pd.to_numeric(frame[mapping["frequency_column"]], errors="coerce")
    real = pd.to_numeric(frame[mapping["real_column"]], errors="coerce")
    imag = pd.to_numeric(frame[mapping["imag_column"]], errors="coerce")
    valid = frequency.notna() & real.notna() & imag.notna() & (frequency > 0)
    threshold = float(ctx.node.params["min_frequency_hz"])
    return {
        "kind": "EISQCReport",
        "upload_id": table.output["upload_id"],
        "mapping": mapping,
        "rows_valid": int(valid.sum()),
        "rows_retained": int((valid & (frequency >= threshold)).sum()),
        "min_frequency_hz": threshold,
        "pass": bool(valid.any()),
        "issues": [] if valid.all() else [f"{int((~valid).sum())} invalid rows ignored"],
    }


def plot_nyquist(ctx: NodeExecution) -> dict[str, Any]:
    report = ctx.runtime.node_input(ctx.state, ctx.node.id, "data")
    if not report.output:
        raise ValueError(f"Upstream node {report.id} has not run")
    frame = ctx.runtime.dataset_frame(report.output["upload_id"])
    mapping = report.output["mapping"]
    real = pd.to_numeric(frame[mapping["real_column"]], errors="coerce")
    imag = pd.to_numeric(frame[mapping["imag_column"]], errors="coerce")
    valid = real.notna() & imag.notna()
    points = [[float(x), float(-y)] for x, y in zip(real[valid].head(500), imag[valid].head(500))]
    return {
        "kind": "Plot",
        "plot_type": "Nyquist",
        "title": ctx.node.params["title"],
        "series": points,
        "points": len(points),
    }


def register_eis_executors(registry: ExecutorRegistry) -> None:
    registry.register("builtin:eis_basic_qc", eis_basic_qc)
    registry.register("builtin:plot_nyquist", plot_nyquist)


def build_package() -> DomainPackage:
    """Build this package. It is an in-repository plugin that an independent
    distribution could equally advertise through the ``matflow.domain_packages``
    entry-point group, because loading only needs a factory of this shape."""
    return DomainPackage(
        manifest=MANIFEST,
        data_types=EIS_DATA_TYPES,
        tool_specs=EIS_TOOL_SPECS,
        migrations={"human_decision": "review_policy"},
        register_executors=register_eis_executors,
    )

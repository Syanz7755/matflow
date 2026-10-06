"""Demo-only archived QE output source, kept outside the scientific package."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..contracts import Edge, GraphPatch, Node, Operation, PreviewSpec, ToolSpec
from ..executors import ExecutorRegistry, NodeExecution, ToolExecutionError
from . import DomainPackage, DomainPackageManifest


def qe_replay_stdout(ctx: NodeExecution) -> dict[str, Any]:
    fixture_id = ctx.node.params.get("fixture_id", "mgo-scf-reference")
    if fixture_id != "mgo-scf-reference":
        raise ToolExecutionError("qe_output_missing", f"Unknown QE replay fixture: {fixture_id}")
    fixture = Path(__file__).with_name("qe_demo_fixtures") / "qe_mgo_scf.log"
    try:
        output_text = fixture.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ToolExecutionError("qe_output_missing", f"QE replay output is missing: {fixture}") from exc
    fermi = re.findall(r"(?:the )?Fermi energy is\s*[-+0-9.EeDd]+\s*ev", output_text, flags=re.IGNORECASE)
    energy = re.findall(r"!\s*total energy\s*=\s*[-+0-9.EeDd]+\s*Ry", output_text)
    convergence = re.findall(r"convergence has been achieved in\s+\d+\s+iterations", output_text, flags=re.IGNORECASE)
    excerpt = "\n".join([*(energy[-1:] or []), *(fermi[-1:] or []), *(convergence[-1:] or []), "JOB DONE" if "JOB DONE" in output_text else ""])
    return {"kind": "QEStdout", "text": excerpt, "source": "archived_qe_output", "source_path": "qe72_wave1_manual/results/kcheck/scf333.log"}


def _register(registry: ExecutorRegistry) -> None:
    registry.register("builtin:qe_replay_stdout", qe_replay_stdout)


def build_demo_patch(base_version: int, prompt: str) -> GraphPatch:
    """Build the pinned, provenance-labelled MgO SCF replay workflow."""
    normalized = prompt.casefold().replace(" ", "")
    if "mgo" not in normalized or not ("scf" in normalized or "自洽" in prompt):
        raise ValueError("The local QE demo supports a pristine MgO SCF request; mention MgO and SCF/self-consistency.")
    input_path = Path(__file__).with_name("qe_demo_fixtures") / "qe_mgo_scf.in"
    try:
        raw = input_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ToolExecutionError("qe_output_missing", f"The archived QE input fixture is missing: {input_path}") from exc
    lines = raw.splitlines()

    def index_of(prefix: str) -> int:
        for index, line in enumerate(lines):
            if line.strip().startswith(prefix): return index
        raise ValueError(f"Archived QE input is missing {prefix}")

    cell_index, species_index = index_of("CELL_PARAMETERS"), index_of("ATOMIC_SPECIES")
    positions_index, kpoints_index = index_of("ATOMIC_POSITIONS"), index_of("K_POINTS")
    cell_header = lines[cell_index].split()
    cell = [[float(value) for value in lines[cell_index + offset].split()[:3]] for offset in range(1, 4)]
    pseudopotentials = {bits[0]: bits[2] for line in lines[species_index + 1:positions_index] if len(bits := line.split()) >= 3}
    positions = [{"element": bits[0], "coordinates": [float(value) for value in bits[1:4]]} for line in lines[positions_index + 1:kpoints_index] if len(bits := line.split()) >= 4]

    def scalar(key: str, default: str) -> str:
        match = re.search(rf"^\s*{re.escape(key)}\s*=\s*([^,\r\n]+)", raw, flags=re.MULTILINE | re.IGNORECASE)
        return match.group(1).strip().strip("'") if match else default

    structure = {"cell": cell, "cell_unit": cell_header[1], "positions": positions, "position_unit": lines[positions_index].split()[1], "pseudopotentials": pseudopotentials}
    params: dict[str, Any] = {
        "calculation": scalar("calculation", "scf"), "ecutwfc_ry": float(scalar("ecutwfc", "50")),
        "ecutrho_ry": float(scalar("ecutrho", "400")), "k_points": [int(value) for value in lines[kpoints_index + 1].split()[:6]],
        "conv_thr": float(scalar("conv_thr", "1e-8").replace("d", "e").replace("D", "E")),
        "prefix": "matflow_mgo_demo", "pseudo_dir": scalar("pseudo_dir", "./pseudo"), "outdir": "./tmp",
        "occupations": scalar("occupations", "fixed"), "smearing": scalar("smearing", "mv"),
        "degauss_ry": float(scalar("degauss", "0.01")), "nspin": int(scalar("nspin", "1")),
        "mixing_beta": float(scalar("mixing_beta", "0.3")),
    }
    nodes = [
        Node(id="qe-demo-structure", type="qe_structure", label="MgO structure", params=structure, position={"x": 80, "y": 150}),
        Node(id="qe-demo-input", type="qe_pw_input", label="Generate QE SCF input", params=params, position={"x": 360, "y": 90}),
        Node(id="qe-demo-output", type="qe_replay_stdout", label="Archived output replay", params={"fixture_id": "mgo-scf-reference"}, position={"x": 360, "y": 270}),
        Node(id="qe-demo-result", type="qe_parse_output", label="Parse QE result", params={}, position={"x": 650, "y": 180}),
    ]
    edges = [
        Edge(id="qe-demo-e1", source="qe-demo-structure", source_port="structure", target="qe-demo-input", target_port="structure"),
        Edge(id="qe-demo-e2", source="qe-demo-input", source_port="input", target="qe-demo-result", target_port="input"),
        Edge(id="qe-demo-e3", source="qe-demo-output", source_port="stdout", target="qe-demo-result", target_port="stdout"),
    ]
    operations = [*(Operation(op="add_node", node=node) for node in nodes), *(Operation(op="connect", edge=edge) for edge in edges)]
    return GraphPatch(base_version=base_version, rationale=f"Local QE replay workflow generated from research request: {prompt}", operations=operations)


def build_package() -> DomainPackage:
    spec = ToolSpec(
        tool_id="qe_replay_stdout",
        label="Archived QE Output (Demo)",
        category="Demo Fixture",
        inputs={},
        outputs={"stdout": "QEStdout"},
        params={"fixture_id": "mgo-scf-reference"},
        description="Load a pinned historical QE stdout fixture for the local replay demo.",
        parameter_schema={"type": "object", "properties": {"fixture_id": {"type": "string", "enum": ["mgo-scf-reference"]}}, "additionalProperties": False},
        output_schema={"type": "object", "required": ["kind", "text", "source", "source_path"]},
        executor_ref="builtin:qe_replay_stdout",
        agent_selectable=False,
        preview_spec=PreviewSpec(outputs={"stdout": {"renderer": "json_tree"}}),
    )
    return DomainPackage(
        manifest=DomainPackageManifest(
            package_id="qe_demo", version="1.0.0", label="QE historical replay demo",
            description="Demo-only archived output source; depends on QE types and parsers.",
            requires=("qe",), acceptance_tests=("tests/test_qe_package.py",),
        ),
        tool_specs={"qe_replay_stdout": spec},
        register_executors=_register,
    )

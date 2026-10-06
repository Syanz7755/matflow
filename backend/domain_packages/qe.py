"""Quantum ESPRESSO tools owned by the QE Domain Package."""
from __future__ import annotations

import re
import math
from typing import Any

from jsonschema import Draft202012Validator

from ..contracts import DataTypeDefinition, PreviewSpec, ToolSpec
from ..executors import ExecutorRegistry, NodeExecution, ToolExecutionError
from . import DomainPackage, DomainPackageManifest


STRUCTURE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "cell": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "number"}}},
        "cell_unit": {"type": "string", "enum": ["angstrom", "bohr"]},
        "positions": {"type": "array", "minItems": 1, "items": {"type": "object", "properties": {"element": {"type": "string", "pattern": "^[A-Z][a-z]?$"}, "coordinates": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "number"}}}, "required": ["element", "coordinates"], "additionalProperties": False}},
        "position_unit": {"type": "string", "enum": ["crystal", "angstrom", "bohr"]},
        "pseudopotentials": {"type": "object", "minProperties": 1, "additionalProperties": {"type": "string", "minLength": 1}},
        "atomic_masses": {"type": "object", "additionalProperties": {"type": "number", "exclusiveMinimum": 0}},
    },
    "required": ["cell", "cell_unit", "positions", "position_unit", "pseudopotentials"],
    "additionalProperties": False,
}

STRUCTURE_DEFAULT: dict[str, Any] = {
    "cell": [[4.212, 0, 0], [0, 4.212, 0], [0, 0, 4.212]],
    "cell_unit": "angstrom",
    "positions": [
        {"element": "Mg", "coordinates": [0, 0, 0]},
        {"element": "O", "coordinates": [0.5, 0.5, 0.5]},
    ],
    "position_unit": "crystal",
    "pseudopotentials": {"Mg": "Mg.pbe-spn-kjpaw_psl.1.0.0.UPF", "O": "O.pbe-n-kjpaw_psl.0.1.UPF"},
}

PARAMETER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "calculation": {"type": "string", "enum": ["scf", "relax", "vc-relax"]},
        "ecutwfc_ry": {"type": "number", "exclusiveMinimum": 0},
        "ecutrho_ry": {"type": "number", "exclusiveMinimum": 0},
        "k_points": {"type": "array", "minItems": 6, "maxItems": 6, "prefixItems": [{"type": "integer", "minimum": 1}, {"type": "integer", "minimum": 1}, {"type": "integer", "minimum": 1}, {"type": "integer", "enum": [0, 1]}, {"type": "integer", "enum": [0, 1]}, {"type": "integer", "enum": [0, 1]}], "items": False},
        "conv_thr": {"type": "number", "exclusiveMinimum": 0},
        "prefix": {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_-]{0,63}$"},
        "pseudo_dir": {"type": "string", "minLength": 1},
        "outdir": {"type": "string", "minLength": 1},
        "occupations": {"type": "string", "enum": ["fixed", "smearing", "tetrahedra"]},
        "smearing": {"type": "string", "enum": ["gaussian", "methfessel-paxton", "marzari-vanderbilt", "cold", "mv", "mp", "fd"]},
        "degauss_ry": {"type": "number", "minimum": 0},
        "nspin": {"type": "integer", "enum": [1, 2]},
        "mixing_beta": {"type": "number", "exclusiveMinimum": 0, "maximum": 1},
    },
    "required": ["calculation", "ecutwfc_ry", "ecutrho_ry", "k_points", "conv_thr"],
    "additionalProperties": False,
    "allOf": [{"if": {"properties": {"occupations": {"const": "smearing"}}, "required": ["occupations"]}, "then": {"required": ["smearing", "degauss_ry"]}}],
}


def _validate(value: Any, schema: dict[str, Any], name: str) -> None:
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda error: tuple(str(part) for part in error.absolute_path))
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.absolute_path) or name
        raise ToolExecutionError("invalid_parameters", f"{location}: {error.message}")


def validate_node_params(params: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    """Return readable JSON Schema errors in stable order."""
    errors = sorted(Draft202012Validator(schema).iter_errors(params), key=lambda error: (tuple(str(part) for part in error.absolute_path), error.message))
    return [f"{'.'.join(str(part) for part in error.absolute_path) or 'params'}: {error.message}" for error in errors]


def qe_structure(ctx: NodeExecution) -> dict[str, Any]:
    structure = ctx.node.params
    _validate(structure, STRUCTURE_SCHEMA, "structure")
    elements = {atom["element"] for atom in structure["positions"]}
    missing = sorted(elements - set(structure["pseudopotentials"]))
    unused = sorted(set(structure["pseudopotentials"]) - elements)
    if missing or unused:
        details = []
        if missing: details.append(f"missing pseudopotentials for {', '.join(missing)}")
        if unused: details.append(f"unused pseudopotentials for {', '.join(unused)}")
        raise ToolExecutionError("invalid_parameters", "; ".join(details))
    if any(not math.isfinite(float(value)) for row in structure["cell"] for value in row) or any(not math.isfinite(float(value)) for atom in structure["positions"] for value in atom["coordinates"]):
        raise ToolExecutionError("invalid_parameters", "Cell and atomic coordinates must be finite numbers")
    a, b, c = structure["cell"]
    determinant = a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0])
    if abs(determinant) < 1e-10:
        raise ToolExecutionError("invalid_parameters", "Cell vectors must span a non-zero volume")
    return {"kind": "CrystalStructure", **structure, "composition": _composition(structure["positions"])}


def _composition(positions: list[dict[str, Any]]) -> dict[str, int]:
    result: dict[str, int] = {}
    for atom in positions:
        result[atom["element"]] = result.get(atom["element"], 0) + 1
    return dict(sorted(result.items()))


def _number(value: float) -> str:
    return f"{value:.10f}".rstrip("0").rstrip(".") if value else "0"


def qe_pw_input(ctx: NodeExecution) -> dict[str, Any]:
    structure_node = ctx.runtime.node_input(ctx.state, ctx.node.id, "structure")
    structure = structure_node.output or {}
    if structure.get("kind") != "CrystalStructure":
        raise ToolExecutionError("invalid_parameters", "Connected input is not a CrystalStructure")
    params = ctx.node.params
    _validate(params, PARAMETER_SCHEMA, "parameters")
    if params["ecutrho_ry"] < params["ecutwfc_ry"]:
        raise ToolExecutionError("invalid_parameters", "ecutrho_ry must be greater than or equal to ecutwfc_ry")
    cell = "\n".join("  " + " ".join(_number(float(x)) for x in row) for row in structure["cell"])
    species = "\n".join(
        f"  {element:<3} {_number(float(_atomic_mass(element, structure.get('atomic_masses', {}))))} {filename}"
        for element, filename in sorted(structure["pseudopotentials"].items())
    )
    positions = "\n".join(
        f"{atom['element']:<3} " + " ".join(_number(float(x)) for x in atom["coordinates"])
        for atom in structure["positions"]
    )
    prefix = params.get("prefix", "matflow_qe")
    smearing = ""
    if params.get("occupations") == "smearing":
        smearing = f"  smearing = '{params.get('smearing', 'mv')}'\n  degauss = {params.get('degauss_ry', 0.01):g}\n"
    text = f"""&CONTROL
  calculation = '{params['calculation']}'
  prefix = '{prefix}'
  pseudo_dir = '{params.get('pseudo_dir', './pseudo')}'
  outdir = '{params.get('outdir', './tmp')}'
  tprnfor = .true.
  tstress = .true.
/
&SYSTEM
  ibrav = 0
  nat = {len(structure['positions'])}
  ntyp = {len(structure['pseudopotentials'])}
  ecutwfc = {params['ecutwfc_ry']:g}
  ecutrho = {params['ecutrho_ry']:g}
  occupations = '{params.get('occupations', 'fixed')}'
  nspin = {params.get('nspin', 1)}
  input_dft = 'PBE'
{smearing}/
&ELECTRONS
  conv_thr = {params['conv_thr']:.8g}
  mixing_beta = {params.get('mixing_beta', 0.3):g}
/
CELL_PARAMETERS {structure['cell_unit']}
{cell}
ATOMIC_SPECIES
{species}
ATOMIC_POSITIONS {structure['position_unit']}
{positions}
K_POINTS automatic
  {' '.join(str(value) for value in params['k_points'])}
"""
    return {"kind": "QEInput", "input_text": text, "prefix": prefix, "atom_count": len(structure["positions"]), "composition": structure["composition"], "parameters": params}


_MASSES = {"H": 1.008, "O": 15.999, "Mg": 24.305, "Fe": 55.845, "Co": 58.933, "Ni": 58.693, "Mn": 54.938, "Cr": 51.996, "Ti": 47.867, "Cu": 63.546, "C": 12.011, "N": 14.007, "Al": 26.982, "Si": 28.085, "La": 138.905, "Ce": 140.116}


def _atomic_mass(element: str, supplied: dict[str, Any] | None = None) -> float:
    if element in (supplied or {}):
        return float(supplied[element])
    if element not in _MASSES:
        raise ToolExecutionError("invalid_parameters", f"No atomic mass is configured for {element}")
    return _MASSES[element]


def qe_parse_output(ctx: NodeExecution) -> dict[str, Any]:
    stdout_node = ctx.runtime.node_input(ctx.state, ctx.node.id, "stdout")
    payload = stdout_node.output or {}
    output = payload.get("text")
    if not isinstance(output, str) or not output.strip():
        raise ToolExecutionError("qe_output_missing", "QE output is missing or empty")
    if "JOB DONE" not in output:
        raise ToolExecutionError("qe_not_converged", "QE output does not contain the successful JOB DONE marker")
    energy_matches = re.findall(r"!\s*total energy\s*=\s*([-+0-9.EeDd]+)\s*Ry", output)
    if not energy_matches:
        raise ToolExecutionError("qe_output_missing", "QE output is missing the final total energy")
    energy_ry = float(energy_matches[-1].replace("D", "E").replace("d", "e"))
    fermi_matches = re.findall(r"(?:the )?Fermi energy is\s*([-+0-9.EeDd]+)\s*ev", output, flags=re.IGNORECASE)
    convergence = re.findall(r"convergence has been achieved in\s+(\d+)\s+iterations", output, flags=re.IGNORECASE)
    if not convergence:
        raise ToolExecutionError("qe_not_converged", "QE output has no electronic convergence marker")
    return {
        "kind": "QEResult",
        "convergence": "converged" if convergence else "job_done_without_scf_marker",
        "iterations": int(convergence[-1]) if convergence else None,
        "energy": {"value": energy_ry, "unit": "Ry"},
        "fermi_energy": {"value": float(fermi_matches[-1].replace("D", "E").replace("d", "e")), "unit": "eV"} if fermi_matches else None,
        "source": payload.get("source", "provided_output"),
        "source_path": payload.get("source_path"),
        "provenance": "historical_output_replay" if payload.get("source") == "archived_qe_output" else "provided_output",
    }


def _spec(tool_id: str, label: str, description: str, *, inputs: dict[str, str], outputs: dict[str, str], params: dict[str, Any], parameter_schema: dict[str, Any], executor: str, required_inputs: list[str] | None = None, input_schema: dict[str, Any] | None = None, output_schema: dict[str, Any] | None = None) -> ToolSpec:
    return ToolSpec(
        tool_id=tool_id, label=label, category="QE", description=description,
        inputs=inputs, outputs=outputs, params=params, parameter_schema=parameter_schema,
        input_schema=input_schema or {"type": "object"},
        output_schema=output_schema or {"type": "object", "required": ["kind"]},
        executor_ref=f"builtin:{executor}", required_inputs=required_inputs or [],
        preview_spec=PreviewSpec(outputs={next(iter(outputs)): {"renderer": "json_tree"}}),
    )


def _register(registry: ExecutorRegistry) -> None:
    registry.register("builtin:qe_structure", qe_structure)
    registry.register("builtin:qe_pw_input", qe_pw_input)
    registry.register("builtin:qe_parse_output", qe_parse_output)


def build_package() -> DomainPackage:
    return DomainPackage(
        manifest=DomainPackageManifest(
            package_id="qe", version="1.0.0", label="Quantum ESPRESSO",
            description="Generate pw.x inputs and parse auditable Quantum ESPRESSO results.",
            acceptance_tests=("tests/test_qe_package.py",),
        ),
        data_types={
            "CrystalStructure": DataTypeDefinition(name="CrystalStructure", parents=["Artifact"], description="Cell, species, pseudopotentials and atomic coordinates."),
            "QEInput": DataTypeDefinition(name="QEInput", parents=["Artifact"], description="A validated Quantum ESPRESSO pw.x input deck."),
            "QEStdout": DataTypeDefinition(name="QEStdout", parents=["Artifact"], description="Quantum ESPRESSO standard output with source provenance."),
            "QEResult": DataTypeDefinition(name="QEResult", parents=["Artifact"], description="Parsed energy, Fermi level and convergence state."),
        },
        tool_specs={
            "qe_structure": _spec("qe_structure", "Crystal Structure", "Validate a crystal cell, atomic coordinates and pseudopotential mapping.", inputs={}, outputs={"structure": "CrystalStructure"}, params=STRUCTURE_DEFAULT, parameter_schema=STRUCTURE_SCHEMA, executor="qe_structure", output_schema={"type": "object", "required": ["kind", "cell", "positions", "pseudopotentials"]}),
            "qe_pw_input": _spec("qe_pw_input", "QE pw.x Input", "Generate a complete Quantum ESPRESSO pw.x input deck from a typed crystal structure and validated SCF/relax parameters.", inputs={"structure": "CrystalStructure"}, outputs={"input": "QEInput"}, params={"calculation": "scf", "ecutwfc_ry": 50, "ecutrho_ry": 400, "k_points": [3, 3, 3, 0, 0, 0], "conv_thr": 1e-8, "prefix": "matflow_mgo", "pseudo_dir": "./pseudo", "outdir": "./tmp", "occupations": "fixed", "smearing": "mv", "degauss_ry": 0.01, "nspin": 1, "mixing_beta": 0.3}, parameter_schema=PARAMETER_SCHEMA, executor="qe_pw_input", required_inputs=["structure"], output_schema={"type": "object", "required": ["kind", "input_text", "atom_count", "composition"]}),
            "qe_parse_output": _spec("qe_parse_output", "QE Result Parser", "Parse final total energy, Fermi energy and convergence evidence from QE output.", inputs={"input": "QEInput", "stdout": "QEStdout"}, outputs={"result": "QEResult"}, params={}, parameter_schema={"type": "object", "properties": {}, "additionalProperties": False}, executor="qe_parse_output", required_inputs=["input", "stdout"], output_schema={"type": "object", "required": ["kind", "convergence", "energy", "provenance"]}),
        },
        register_executors=_register,
    )

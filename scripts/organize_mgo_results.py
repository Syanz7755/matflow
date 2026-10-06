"""Build one provenance-preserving MgO QE calculation table from a simulation tree."""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


def meta_values(text: str) -> dict[str, str]:
    values = {}
    for line in text.splitlines():
        line = re.sub(r"^\s*!\s*", "", line)
        match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*?)\s*$", line)
        if match and match.group(1) not in {"schema_version"}:
            values[match.group(1)] = match.group(2).strip().strip("\"'")
    return values


def section(lines: list[str], marker: str, end_markers: tuple[str, ...]) -> tuple[str | None, list[str]]:
    for i, line in enumerate(lines):
        if line.strip().upper().startswith(marker):
            unit = line.strip().split(maxsplit=1)[1] if len(line.strip().split(maxsplit=1)) > 1 else ""
            rows = []
            for item in lines[i + 1:]:
                current = item.strip().upper()
                is_header = any(current.startswith(header) for header in ("&CONTROL", "&SYSTEM", "&ELECTRONS", "CELL_PARAMETERS", "ATOMIC_SPECIES", "ATOMIC_POSITIONS", "K_POINTS", "CONSTRAINTS", "OCCUPATIONS", "HUBBARD"))
                if not current or is_header or any(current.startswith(end) for end in end_markers):
                    if rows: break
                    continue
                rows.append(item.split())
            return unit, rows
    return None, []


def parse_input(path: Path, root: Path) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    meta = meta_values(text)
    lines = text.splitlines()
    cell_unit, cell_rows = section(lines, "CELL_PARAMETERS", ("ATOMIC_SPECIES",))
    _, species_rows = section(lines, "ATOMIC_SPECIES", ("ATOMIC_POSITIONS", "K_POINTS"))
    position_unit, position_rows = section(lines, "ATOMIC_POSITIONS", ("K_POINTS", "CONSTRAINTS", "OCCUPATIONS"))
    species = {row[0]: row[2] for row in species_rows if len(row) >= 3}
    composition = Counter(row[0] for row in position_rows if len(row) >= 4)
    # Species declarations can include unused potentials (for example an
    # unrelated upstream QE example ships Mg/O pseudo files). Require the
    # actual atomic positions or an explicit formula in metadata.
    is_mgo = (composition.get("Mg", 0) > 0 and composition.get("O", 0) > 0) or bool(
        re.search(r"\bMg\d*\s*O\d*\b|\bMgO\b", meta.get("composition", ""), re.I)
    )
    if not is_mgo:
        return None
    def value(name: str) -> str | None:
        match = re.search(rf"^\s*{re.escape(name)}\s*=\s*([^,\r\n/]+)", text, flags=re.MULTILINE | re.IGNORECASE)
        return match.group(1).strip().strip("'\"") if match else None
    parameters = {
        "calculation": meta.get("calc_type") or value("calculation"),
        "functional": meta.get("functional") or value("input_dft"),
        "ecutwfc_ry": meta.get("ecutwfc_ry") or value("ecutwfc"),
        "ecutrho_ry": meta.get("ecutrho_ry") or value("ecutrho"),
        "k_points": meta.get("k_points"),
        "conv_thr": meta.get("conv_thr") or value("conv_thr"),
        "nspin": meta.get("nspin") or value("nspin"),
        "occupations": meta.get("occupations") or value("occupations"),
        "smearing": meta.get("smearing") or value("smearing"),
        "degauss_ry": meta.get("degauss_ry") or value("degauss"),
        "pseudopotentials": species,
    }
    parameters = {key: item for key, item in parameters.items() if item not in (None, "")}
    try:
        declared_atoms = int(meta.get("nat") or value("nat") or 0) or None
    except ValueError:
        declared_atoms = None
    configuration = {
        "cell_unit": cell_unit,
        "cell": [[float(item) for item in row[:3]] for row in cell_rows if len(row) >= 3 and all(re.fullmatch(r"[-+0-9.EeDd]+", item) for item in row[:3])],
        "position_unit": position_unit,
        "atom_count": declared_atoms or (sum(composition.values()) if composition else None),
        "atom_counts": dict(sorted(composition.items())) if composition else {},
        "positions_complete": declared_atoms is None or not composition or sum(composition.values()) == declared_atoms,
        "dopant": meta.get("dopant"),
        "defect": meta.get("defect"),
        "supercell": meta.get("supercell"),
        "case_id": meta.get("case_id"),
    }
    rid = meta.get("case_id") or path.relative_to(root).with_suffix("").as_posix()
    return {"record_id": rid, "composition": meta.get("composition") or dict(sorted(composition.items())), "configuration": configuration, "parameters": parameters, "energy": {}, "property": {}, "convergence": "unknown", "source_path": [path.relative_to(root).as_posix()], "aliases": {path.stem.casefold(), rid.casefold()}}


def parse_output(text: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    energy = re.findall(r"!\s*total energy\s*=\s*([-+0-9.EeDd]+)\s*Ry", text, flags=re.I)
    fermi = re.findall(r"(?:the )?Fermi energy is\s*([-+0-9.EeDd]+)\s*ev", text, flags=re.I)
    total_mag = re.findall(r"total magnetization\s*=\s*([-+0-9.EeDd]+)\s*Bohr", text, flags=re.I)
    abs_mag = re.findall(r"absolute magnetization\s*=\s*([-+0-9.EeDd]+)\s*Bohr", text, flags=re.I)
    gap = re.findall(r"(?:band gap|gap proxy)\s*[=:]\s*([-+0-9.EeDd]+)\s*eV", text, flags=re.I)
    def number(value: str) -> float:
        return float(value.replace("D", "E").replace("d", "e"))
    energy_data = {"total_energy_ry": number(energy[-1])} if energy else {}
    property_data = {}
    if fermi: property_data["fermi_energy_ev"] = number(fermi[-1])
    if total_mag: property_data["total_magnetization_bohr"] = number(total_mag[-1])
    if abs_mag: property_data["absolute_magnetization_bohr"] = number(abs_mag[-1])
    if gap: property_data["gap_proxy_ev"] = number(gap[-1])
    if "convergence has been achieved" in text.lower(): convergence = "converged"
    elif "job done" in text.lower(): convergence = "job_done_only"
    elif "convergence not achieved" in text.lower() or "maximum number of steps" in text.lower(): convergence = "not_converged"
    else: convergence = "unknown"
    return energy_data, property_data, convergence


def collect(root: Path) -> list[dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for path in root.rglob("*.in"):
        if "node_modules" in path.parts or ".git" in path.parts or "qe_mgo_tm_resources" in path.parts:
            continue
        item = parse_input(path, root)
        if item is None: continue
        key = str(item["record_id"]).casefold()
        target = records.setdefault(key, item)
        if item["record_id"] not in target["source_path"]:
            target["source_path"].extend(p for p in item["source_path"] if p not in target["source_path"])
        target["aliases"].update(item["aliases"])

    # Fold existing summary tables into the input-derived record rather than duplicating cases.
    for csv_path in root.rglob("*.csv"):
        if "node_modules" in csv_path.parts or ".git" in csv_path.parts or csv_path.name.casefold() == "mgo_structured_results.csv": continue
        try:
            with csv_path.open(encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    rid = row.get("case_id") or row.get("record_id")
                    if not rid: continue
                    key = rid.casefold()
                    if key not in records:
                        composition_text = row.get("composition", "")
                        # Summary files may contain unrelated upstream QE
                        # examples under a directory whose name happens to
                        # contain "mgo". Admit summary-only rows only when the
                        # row itself declares both Mg and O.
                        elements = set(re.findall(r"([A-Z][a-z]?)\s*\d*", composition_text))
                        if not {"Mg", "O"}.issubset(elements): continue
                    target = records.setdefault(key, {"record_id": rid, "composition": row.get("composition") or "", "configuration": {}, "parameters": {}, "energy": {}, "property": {}, "convergence": "unknown", "source_path": [], "aliases": {key}})
                    for field, source in (("total_energy_ry", "total_energy_ry"), ("total_energy_ev", "total_energy_ev")):
                        if row.get(source):
                            try: target["energy"][field] = float(row[source])
                            except ValueError: pass
                    for field in ("fermi_ev", "total_magnetization", "absolute_magnetization", "homo_ev", "lumo_ev", "gap_proxy_ev"):
                        if row.get(field):
                            try: target["property"][field] = float(row[field])
                            except ValueError: pass
                    if row.get("job_done", "").lower() in {"yes", "true", "1"} and target["convergence"] == "unknown": target["convergence"] = "job_done_only"
                    target["source_path"].append(csv_path.relative_to(root).as_posix())
        except (OSError, UnicodeError):
            continue

    file_index = list(root.rglob("*.out")) + list(root.rglob("*.log"))
    for path in file_index:
        if "node_modules" in path.parts or ".git" in path.parts or "qe_mgo_tm_resources" in path.parts: continue
        try: text = path.read_text(encoding="utf-8", errors="replace")
        except OSError: continue
        if not ("Program PWSCF" in text[:4000] or re.search(r"file\s+Mg[^\r\n]*\.UPF", text, re.I) and re.search(r"file\s+O[^\r\n]*\.UPF", text, re.I)):
            continue
        energy, properties, convergence = parse_output(text)
        if not energy and not properties and convergence == "unknown": continue
        stem = path.stem.casefold()
        candidates = [record for record in records.values() if any(alias and (alias in stem or stem in alias) for alias in record["aliases"])]
        if not candidates:
            # Keep otherwise-unmatched calculation output as its own auditable row when its path identifies MgO.
            if not re.search(r"mgo|mg_o|MgO", str(path), re.I): continue
            rid = path.relative_to(root).with_suffix("").as_posix()
            candidates = [records.setdefault(rid.casefold(), {"record_id": rid, "composition": "", "configuration": {}, "parameters": {}, "energy": {}, "property": {}, "convergence": "unknown", "source_path": [], "aliases": {stem, rid.casefold()}})]
        # Prefer the most specific case-id match when an output name contains several aliases.
        target = max(candidates, key=lambda record: max((len(alias) for alias in record["aliases"] if alias and alias in stem), default=0))
        target["energy"].update(energy)
        target["property"].update(properties)
        if convergence != "unknown": target["convergence"] = convergence
        rel = path.relative_to(root).as_posix()
        if rel not in target["source_path"]: target["source_path"].append(rel)

    result = []
    for record in records.values():
        record.pop("aliases", None)
        record["source_path"] = "; ".join(sorted(set(record["source_path"])))
        result.append(record)
    return sorted(result, key=lambda item: item["record_id"].casefold())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path(r"D:\Researches\EBrick\simuls"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.source.resolve()
    to_stdout = args.output is not None and str(args.output) == "-"
    output = None if to_stdout else (args.output or root / "results" / "mgo_structured_results.csv").resolve()
    if output is not None: output.parent.mkdir(parents=True, exist_ok=True)
    rows = collect(root)
    fields = ["composition", "configuration", "parameters", "energy", "property", "convergence", "source_path", "record_id"]
    if to_stdout:
        handle = sys.stdout
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: json.dumps(row[field], ensure_ascii=False, sort_keys=True) if isinstance(row[field], (dict, list)) else row[field] for field in fields})
    else:
        with output.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: json.dumps(row[field], ensure_ascii=False, sort_keys=True) if isinstance(row[field], (dict, list)) else row[field] for field in fields})
    print(f"Wrote {len(rows)} MgO calculation records to {output or 'stdout'}", file=sys.stderr if to_stdout else sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

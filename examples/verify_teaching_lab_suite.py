"""Offline acceptance check for the teaching-lab prompt suite.

This validates only deterministic fixtures and declared expected outcomes.  It
does not call a model, browse for a tool, or claim that preset candidates have
real executors.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).parent
PROJECT = ROOT.parent
SUITE_PATH = ROOT / "teaching_lab_prompt_suite.json"
EXPECTED_PATH = ROOT / "teaching_lab_expected_results.json"
REPORT_PATH = ROOT / "reports" / "teaching_lab_acceptance.json"
STYLES = {"canonical_zh", "colloquial_zh", "formal_zh", "english"}


def rows(relative_path: str) -> list[dict[str, str]]:
    with (PROJECT / relative_path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def linear_fit(xs: list[float], ys: list[float]) -> tuple[float, float]:
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)) / sum((x - mean_x) ** 2 for x in xs)
    return slope, mean_y - slope * mean_x


def numeric_checks() -> list[str]:
    failures: list[str] = []
    eis = rows("examples/data/01_eis_basic_qc/eis_spectrum.csv")
    if abs(float(eis[0]["z_real_ohm"]) - 5.0) > 0.1:
        failures.append("EIS high-frequency intercept is outside tolerance.")

    xrd = rows("examples/data/02_xrd_anatase_identification/xrd_anatase.csv")
    main_peak = max(xrd, key=lambda item: float(item["intensity_counts"]))
    if abs(float(main_peak["two_theta_deg"]) - 25.3) > 0.15:
        failures.append("XRD dominant peak is not anatase-like 25.3 degrees.")

    uvvis = rows("examples/data/03_uvvis_methylene_blue_decay/absorbance_time_series.csv")
    time_zero = [item for item in uvvis if item["time_min"] == "0"]
    if int(max(time_zero, key=lambda item: float(item["absorbance_au"]))["wavelength_nm"]) != 664:
        failures.append("UV-Vis lambda max is not 664 nm.")

    pycnometer = rows("examples/data/04_pycnometer_specific_gravity/pycnometer_measurements.csv")
    values = []
    for item in pycnometer:
        empty, water, sample, sample_water = (float(item[key]) for key in ("empty_pycnometer_g", "pycnometer_plus_water_g", "pycnometer_plus_sample_g", "pycnometer_plus_sample_plus_water_g"))
        values.append((sample - empty) / ((water - empty) - (sample_water - sample)))
    if abs(sum(values) / len(values) - 2.6) > 0.02:
        failures.append("Pycnometer specific gravity is outside tolerance.")

    tga = rows("examples/data/05_tga_caco3_content/tga_mass_loss.csv")
    caco3 = (100 - float(tga[-1]["mass_percent"])) * 100.09 / 44.01
    if abs(caco3 - 20.0) > 0.5:
        failures.append("TGA CaCO3 mass fraction is outside tolerance.")

    ftir = rows("examples/data/06_ftir_functional_group_assignment/ftir_spectrum.csv")
    if abs(float(max(ftir, key=lambda item: float(item["absorbance_au"]))["wavenumber_cm-1"]) - 1710) > 10:
        failures.append("FTIR dominant peak is outside tolerance.")

    dsc = rows("examples/data/07_dsc_transition_enthalpy/dsc_heating.csv")
    if abs(float(max(dsc, key=lambda item: float(item["heating_heat_flow_mw"]))["temperature_c"]) - 58) > 1:
        failures.append("DSC peak temperature is outside tolerance.")

    four_point = rows("examples/data/08_four_point_probe_resistivity/four_point_measurements.csv")
    slope, _ = linear_fit([float(item["current_ma"]) for item in four_point], [float(item["voltage_mv"]) for item in four_point])
    if abs(slope - 120.0) > 0.01:
        failures.append("Four-point voltage/current slope is outside tolerance.")

    tensile = rows("examples/data/09_tensile_curve_analysis/tensile_curve.csv")
    elastic = tensile[1:5]
    modulus, _ = linear_fit([float(item["engineering_strain"]) for item in elastic], [float(item["engineering_stress_mpa"]) for item in elastic])
    if abs(modulus / 1000 - 70.0) > 0.1:
        failures.append("Tensile Young's modulus is outside tolerance.")

    titration = rows("examples/data/10_acid_base_titration_analysis/titration_curve.csv")
    changes = [(float(next_item["titrant_volume_ml"]), float(next_item["ph"]) - float(item["ph"])) for item, next_item in zip(titration, titration[1:])]
    if abs(max(changes, key=lambda pair: pair[1])[0] - 25.0) > 1.0:
        failures.append("Titration equivalence region is outside tolerance.")

    rc = rows("examples/data/11_rc_transient_fit/rc_charge.csv")
    at_tau = next(item for item in rc if item["time_ms"] == "20")
    tau = -20.0 / math.log(1 - float(at_tau["capacitor_voltage_v"]) / 5.0)
    if abs(tau - 20.0) > 0.05:
        failures.append("RC time constant is outside tolerance.")

    photoelectric = rows("examples/data/12_photoelectric_planck_fit/photoelectric_measurements.csv")
    frequencies = [299_792_458 / (float(item["wavelength_nm"]) * 1e-9) for item in photoelectric]
    slope, intercept = linear_fit(frequencies, [float(item["stopping_voltage_v"]) for item in photoelectric])
    if abs(slope - 4.1357e-15) > 2e-18 or abs(-intercept - 2.1) > 0.01:
        failures.append("Photoelectric linear fit is outside tolerance.")

    michelson = rows("examples/data/13_michelson_wavelength_fit/michelson_fringes.csv")
    wavelengths = [2 * float(item["mirror_displacement_um"]) * 1000 / float(item["fringe_count"]) for item in michelson]
    if abs(sum(wavelengths) / len(wavelengths) - 632.8) > 1.0:
        failures.append("Michelson wavelength is outside tolerance.")
    return failures


def evaluate() -> dict:
    suite = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    expected = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
    scenarios = suite.get("scenarios", [])
    failures: list[str] = []
    if len(scenarios) != 15:
        failures.append("Suite must contain exactly 15 scenarios.")
    prompt_case_count = sum(len(item.get("prompt_variants", [])) for item in scenarios) + len(suite.get("cross_cutting_cases", []))
    if prompt_case_count != 64:
        failures.append("Suite must contain 64 prompt cases.")
    known = expected.get("known_results", {})
    if set(known) != {item.get("scenario_id") for item in scenarios}:
        failures.append("Expected-results IDs must exactly match scenario IDs.")
    for item in scenarios:
        if item.get("expected_result") != known.get(item.get("scenario_id")):
            failures.append(f"Expected result mismatch for {item.get('scenario_id')}.")
        if {variant.get("style") for variant in item.get("prompt_variants", [])} != STYLES:
            failures.append(f"Prompt style set is incomplete for {item.get('scenario_id')}.")
        for fixture in item.get("fixtures", []):
            if not (PROJECT / fixture).is_file():
                failures.append(f"Fixture is missing: {fixture}.")
    missing = [item for item in scenarios if item.get("registry_status") == "tool_manager_required"]
    if len(missing) != 2 or any(item.get("registry_target_id") is not None for item in missing):
        failures.append("Exactly two intentionally missing tools must require Tool Manager review.")
    failures.extend(numeric_checks())
    return {
        "suite": str(SUITE_PATH.relative_to(PROJECT)),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenario_count": len(scenarios), "prompt_case_count": prompt_case_count,
        "tool_manager_required_count": len(missing), "failure_count": len(failures), "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the deterministic teaching-lab prompt suite.")
    parser.add_argument("--check", action="store_true", help="write the report and return non-zero if acceptance fails")
    args = parser.parse_args()
    report = evaluate()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 1 if args.check and report["failure_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

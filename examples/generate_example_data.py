"""Generate deterministic, synthetic input data for the MatFlow example cases.

The inputs are teaching/test fixtures only.  They are deliberately simple so the
expected result can be asserted in automated end-to-end tests.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path


ROOT = Path(__file__).parent / "data"


def write_csv(relative_path: str, fieldnames: list[str], rows: list[dict[str, float | str]]) -> None:
    destination = ROOT / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def generate_eis() -> None:
    rows = []
    for frequency_hz in (100000, 50000, 20000, 10000, 5000, 2000, 1000, 500, 200, 100, 50, 20, 10):
        omega = 2 * math.pi * frequency_hz
        resistance_ohm = 5.0
        charge_transfer_ohm = 40.0
        capacitance_f = 1.0e-4
        parallel = 1 / (1 / charge_transfer_ohm + 1j * omega * capacitance_f)
        impedance = resistance_ohm + parallel
        rows.append({
            "frequency_hz": frequency_hz,
            "z_real_ohm": round(impedance.real, 5),
            "z_imag_ohm": round(impedance.imag, 5),
        })
    write_csv("01_eis_basic_qc/eis_spectrum.csv", ["frequency_hz", "z_real_ohm", "z_imag_ohm"], rows)


def generate_xrd() -> None:
    rows = []
    # Smooth baseline plus anatase-like reflections.  No physical instrument model is implied.
    peaks = [(25.3, 100.0, 0.24), (37.8, 22.0, 0.30), (48.0, 42.0, 0.28), (53.9, 18.0, 0.30), (55.1, 16.0, 0.30), (62.7, 20.0, 0.34)]
    for index in range(401):
        two_theta = 20.0 + index * 0.125
        intensity = 8.0 + 0.04 * (two_theta - 20.0)
        for center, height, sigma in peaks:
            intensity += height * math.exp(-0.5 * ((two_theta - center) / sigma) ** 2)
        rows.append({"two_theta_deg": round(two_theta, 3), "intensity_counts": round(intensity, 3)})
    write_csv("02_xrd_anatase_identification/xrd_anatase.csv", ["two_theta_deg", "intensity_counts"], rows)


def generate_uvvis() -> None:
    calibration = []
    for concentration, absorbance in ((0.0, 0.002), (1.0, 0.126), (2.0, 0.251), (3.0, 0.376), (4.0, 0.501), (5.0, 0.626)):
        calibration.append({"concentration_mg_l": concentration, "absorbance_at_664nm": absorbance})
    write_csv("03_uvvis_methylene_blue_decay/calibration_curve.csv", ["concentration_mg_l", "absorbance_at_664nm"], calibration)

    concentrations = (5.0, 4.05, 3.24, 2.59, 2.07, 1.66)
    timepoints = (0, 10, 20, 30, 40, 50)
    rows = []
    for time_min, concentration in zip(timepoints, concentrations, strict=True):
        for wavelength_nm in range(580, 741, 2):
            baseline = 0.004 + 0.00002 * (wavelength_nm - 580)
            peak = 0.124 * concentration * math.exp(-0.5 * ((wavelength_nm - 664) / 17) ** 2)
            rows.append({
                "time_min": time_min,
                "wavelength_nm": wavelength_nm,
                "absorbance_au": round(baseline + peak, 5),
            })
    write_csv("03_uvvis_methylene_blue_decay/absorbance_time_series.csv", ["time_min", "wavelength_nm", "absorbance_au"], rows)


def generate_pycnometer() -> None:
    rows = [
        {"replicate": "A", "empty_pycnometer_g": 25.000, "pycnometer_plus_water_g": 50.000, "pycnometer_plus_sample_g": 35.000, "pycnometer_plus_sample_plus_water_g": 56.154},
        {"replicate": "B", "empty_pycnometer_g": 25.000, "pycnometer_plus_water_g": 50.000, "pycnometer_plus_sample_g": 35.000, "pycnometer_plus_sample_plus_water_g": 56.146},
        {"replicate": "C", "empty_pycnometer_g": 25.000, "pycnometer_plus_water_g": 50.000, "pycnometer_plus_sample_g": 35.000, "pycnometer_plus_sample_plus_water_g": 56.162},
    ]
    write_csv("04_pycnometer_specific_gravity/pycnometer_measurements.csv", list(rows[0]), rows)


def generate_tga() -> None:
    rows = []
    for temperature_c in range(30, 901, 10):
        # 20 wt% CaCO3 gives 8.80 wt% CO2 loss, using 44.01 / 100.09.
        loss_fraction = 0.0880 / (1 + math.exp(-(temperature_c - 735) / 18))
        rows.append({"temperature_c": temperature_c, "mass_percent": round(100.0 * (1 - loss_fraction), 4)})
    write_csv("05_tga_caco3_content/tga_mass_loss.csv", ["temperature_c", "mass_percent"], rows)


if __name__ == "__main__":
    generate_eis()
    generate_xrd()
    generate_uvvis()
    generate_pycnometer()
    generate_tga()
    print(f"Wrote synthetic fixtures under {ROOT}")

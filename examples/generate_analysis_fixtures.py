"""Generate reproducible noisy XRD and FTIR fixtures plus independent truth metadata."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


SEEDS = (20260930, 20261001, 20261002)


def _xrd(seed: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    rng = np.random.default_rng(seed)
    two_theta = np.arange(20.0, 70.0001, 0.05)
    zero_shift = float(rng.uniform(-0.03, 0.03))
    intensity_scale = float(rng.uniform(0.92, 1.08))
    baseline = 65.0 + rng.uniform(0.35, 0.55) * (two_theta - 20.0)
    signal = baseline.copy()
    peaks = [(25.3, 1150, 0.16), (37.8, 310, 0.20), (48.0, 520, 0.19), (53.9, 260, 0.21), (55.1, 235, 0.21), (62.7, 280, 0.23)]
    for center, height, sigma in peaks:
        signal += intensity_scale * height * np.exp(-0.5 * ((two_theta - (center + zero_shift)) / sigma) ** 2)
    counts = rng.poisson(np.clip(signal, 0, None)).astype(float)
    spike_indices = rng.choice(len(counts), size=2, replace=False)
    counts[spike_indices] += rng.uniform(80, 140, size=2)
    frame = pd.DataFrame({"two_theta_deg": np.round(two_theta, 5), "intensity_counts": np.round(counts, 3)})
    truth = {
        "dominant_phase": "anatase_tio2", "main_peak_deg": 25.3,
        "reference_peaks_deg": [item[0] for item in peaks], "zero_shift_deg": zero_shift,
        "intensity_scale": intensity_scale, "poisson_counting_noise": True, "sparse_spikes": 2,
    }
    return frame, truth


def _ftir(seed: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    rng = np.random.default_rng(seed)
    wavenumber = np.arange(4000.0, 598.0, -2.0)
    axis_shift = float(rng.uniform(-2.0, 2.0))
    amplitude_scale = float(rng.uniform(0.95, 1.05))
    noise_sigma = float(rng.uniform(0.003, 0.008))
    baseline_offset = float(rng.uniform(-0.005, 0.005))
    baseline_slope = float(rng.uniform(-4e-6, 4e-6))
    absorbance = 0.015 + baseline_offset + baseline_slope * (wavenumber - 2000)
    peaks = [(1710, 0.90, 35), (2920, 0.35, 55), (1450, 0.18, 45)]
    for center, height, width in peaks:
        absorbance += amplitude_scale * height * np.exp(-0.5 * ((wavenumber - (center + axis_shift)) / width) ** 2)
    absorbance += rng.normal(0, noise_sigma, len(wavenumber))
    outliers = rng.choice(len(absorbance), size=2, replace=False)
    absorbance[outliers] += rng.uniform(0.015, 0.03, size=2)
    frame = pd.DataFrame({"wavenumber_cm-1": np.round(wavenumber, 3), "absorbance_au": np.round(absorbance, 6)})
    truth = {
        "main_peak_cm-1": 1710.0, "assignment": "carbonyl_candidate",
        "reference_peaks_cm-1": [item[0] for item in peaks], "axis_shift_cm-1": axis_shift,
        "amplitude_scale": amplitude_scale, "noise_sigma_au": noise_sigma,
        "baseline_offset_au": baseline_offset, "baseline_slope_au_per_cm-1": baseline_slope,
        "sparse_outliers": 2,
    }
    return frame, truth


def generate_fixture_set(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    fixtures = []
    for domain, builder in (("xrd", _xrd), ("ftir", _ftir)):
        for seed in SEEDS:
            frame, truth = builder(seed)
            relative = Path(domain) / f"{domain}_{seed}.csv"
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            frame.to_csv(destination, index=False)
            fixtures.append({
                "fixture_id": f"{domain}_{seed}", "domain": domain, "seed": seed,
                "role": "baseline" if seed == SEEDS[0] else "holdout",
                "path": relative.as_posix(), "ground_truth": truth,
            })
    manifest = {"schema_version": "1.0", "generator": "generate_analysis_fixtures", "fixtures": fixtures}
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    generate_fixture_set(Path(__file__).parent / "data" / "configured_analysis")

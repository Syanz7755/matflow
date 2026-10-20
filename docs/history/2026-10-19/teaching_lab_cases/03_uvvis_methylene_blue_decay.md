# 03 · UV-Vis: methylene-blue peak extraction and concentration decay

## Purpose

Verify the calibration curve, peak extraction at each time point, and the concentration change obtained from the Beer–Lambert relation.

## Input

- `examples/data/03_uvvis_methylene_blue_decay/calibration_curve.csv`
- `examples/data/03_uvvis_methylene_blue_decay/absorbance_time_series.csv`

## Suggested prompt

Submit: `Use the calibration curve to analyze the UV-Vis time series of methylene blue, find λmax and calculate the concentration decay over time.`

## Expected result

- λmax at every time point should lie in 662–666 nm.
- The calibration curve is approximately `A = 0.124 C + 0.002`, with C in mg/L.
- The initial concentration is about 5.0 mg/L and about 1.66 mg/L at 50 min; the concentration should decrease monotonically with time.
- The result must retain the calibration range (0–5 mg/L) and use it as an extrapolation check.

## Boundary

This is teaching data with no interfering peaks, no scattering and no baseline drift. A real photocatalysis experiment also needs blanks, dark adsorption, replicates and error analysis.

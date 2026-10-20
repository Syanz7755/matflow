# 01 · EIS basic quality control and Nyquist plot

## Purpose

Verify the minimal closed loop from impedance CSV import through column mapping, EIS quality control and Nyquist plotting.

## Input

`examples/data/01_eis_basic_qc/eis_spectrum.csv`. The required columns are `frequency_hz`, `z_real_ohm` and `z_imag_ohm`; frequency is in Hz and impedance in Ω.

## Suggested prompt

Submit: `Run basic quality checks on this EIS dataset and generate a Nyquist plot.` (the multilingual suite also submits the Chinese equivalent).

## Expected result

- The route should select `eis_basic_qc` and then connect `plot_nyquist` (or the user confirms that plotting step).
- All 13 data points are finite numbers and every frequency is positive.
- The real part of the impedance at the high-frequency end is about 5.0 Ω (tolerance ±0.2 Ω).
- The UI should show the structured quality-control result, the graph node states and the trace ID; the sign of the imaginary part must not be silently rewritten.

## Boundary

This is an idealized synthetic `R(RC)` spectrum and must not be used to validate equivalent-circuit fit authenticity.

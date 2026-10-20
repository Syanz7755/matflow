# 02 · XRD: anatase TiO₂ phase identification

## Purpose

Verify column recognition, peak extraction and a conservative phase suggestion based on a reference peak table for a 2θ–intensity spectrum.

## Input

`examples/data/02_xrd_anatase_identification/xrd_anatase.csv` with the columns `two_theta_deg` and `intensity_counts`. Scan range 20–70°, step 0.125°.

## Suggested prompt

Submit: `Extract the XRD peaks and identify the most likely TiO2 phase in this sample.`

## Expected result

- The parser identifies the horizontal axis as 2θ (degree) and the vertical axis as intensity (counts).
- The strongest peak is at about 25.25–25.38°; secondary peaks at about 37.8°, 48.0°, 53.9°, 55.1° and 62.7° should also be detected.
- The result should offer a **candidate identification** "consistent with the anatase TiO₂ reference peaks" and state that a reference database or standard card is required for confirmation.
- If `xrd_phase_identification` is not registered, routing must not fabricate an execution result; it should return a structured status of confirmation-required / tool-missing.

## Boundary

The spectrum is a synthetic anatase-like peak shape and must not be used for crystallite size, microstrain, Rietveld quantification or publication-grade phase identification.
